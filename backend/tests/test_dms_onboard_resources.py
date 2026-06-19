"""Unit tests for DMS onboard resource calculation and response handling."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from modules.dms_manager import (
    DMSManager,
    _clamp_onboard_cpu_cores,
    _clamp_onboard_disk_gib,
    _clamp_onboard_gpu_vram_gib,
    _clamp_onboard_ram_gib,
    _onboard_actor_error_from_output,
)


class TestClampHelpers:
    def test_clamp_disk_large_host_caps_at_90_percent(self):
        # 300 GiB total, 283 GiB free -> 278 candidate, capped at 270 GiB
        assert _clamp_onboard_disk_gib(300.0, 283.0) == 270.0

    def test_clamp_disk_uncapped_before_90_percent_limit(self):
        assert _clamp_onboard_disk_gib(100.0, 80.0) == 75.0

    def test_clamp_disk_below_minimum_returns_zero(self):
        assert _clamp_onboard_disk_gib(10.0, 5.0) == 0.0

    def test_clamp_ram_respects_min_and_max_percent(self):
        total = 100.0
        free = 95.0
        assert _clamp_onboard_ram_gib(total, free) == 90.0

    def test_clamp_ram_enforces_minimum_when_free_is_low(self):
        total = 100.0
        free = 8.0
        assert _clamp_onboard_ram_gib(total, free) == 10.0

    def test_clamp_gpu_vram_uses_10_to_90_percent(self):
        assert _clamp_onboard_gpu_vram_gib(24.0) == 21.6
        assert _clamp_onboard_gpu_vram_gib(10.0) == 9

    def test_clamp_cpu_never_exceeds_total(self):
        assert _clamp_onboard_cpu_cores(16) == 15
        assert _clamp_onboard_cpu_cores(1) == 1


class TestOnboardActorErrorParsing:
    def test_onboard_actor_error_from_output_success_false_stdout(self):
        payload = json.dumps(
            {
                "success": False,
                "onboarded": False,
                "error": "capacity not met: expected Disk to be between 1 GiB and 270 GiB, got 278 GiB",
            }
        )
        err = _onboard_actor_error_from_output(payload, "")
        assert err is not None
        assert "270 GiB" in err

    def test_onboard_actor_error_from_output_success_false_stderr(self):
        payload = json.dumps({"success": False, "error": "rejected on stderr"})
        err = _onboard_actor_error_from_output("", payload)
        assert err == "rejected on stderr"

    def test_onboard_actor_error_from_output_onboarded_false(self):
        payload = json.dumps({"success": True, "onboarded": False})
        err = _onboard_actor_error_from_output(payload, "")
        assert err is not None
        assert "onboarded: false" in err

    def test_onboard_actor_error_from_output_success_true(self):
        payload = json.dumps({"success": True, "onboarded": True})
        assert _onboard_actor_error_from_output(payload, "") is None


class TestOnboardCompute:
    def test_onboard_compute_happy_path(self, monkeypatch):
        mgr = DMSManager()
        monkeypatch.setattr(
            DMSManager,
            "_calculate_onboard_resources",
            staticmethod(
                lambda: {
                    "cpu_cores": 4,
                    "ram_gb": 16.0,
                    "disk_gb": 100.0,
                    "gpus": [],
                }
            ),
        )
        monkeypatch.setattr(
            "modules.dms_manager.run_dms_command_with_passphrase",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout='{"success": true, "onboarded": true}',
                stderr="",
            ),
        )
        monkeypatch.setattr("modules.dms_manager._verify_dms_onboarded", lambda: (True, None))

        result = mgr.onboard_compute()
        assert result["status"] == "success"

    def test_onboard_compute_returns_error_on_dms_rejection(self, monkeypatch):
        mgr = DMSManager()
        monkeypatch.setattr(
            DMSManager,
            "_calculate_onboard_resources",
            staticmethod(lambda: {"cpu_cores": 4, "ram_gb": 16.0, "disk_gb": 278.0, "gpus": []}),
        )
        error_text = (
            "could not validate onboarding prerequisites: capacity not met: "
            "expected Disk to be between 1 GiB and 270 GiB, got 278 GiB"
        )
        monkeypatch.setattr(
            "modules.dms_manager.run_dms_command_with_passphrase",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout="",
                stderr=json.dumps({"success": False, "onboarded": False, "error": error_text}),
            ),
        )

        result = mgr.onboard_compute()
        assert result["status"] == "error"
        assert "270 GiB" in result["message"]

    def test_onboard_compute_returns_error_when_status_not_onboarded(self, monkeypatch):
        mgr = DMSManager()
        monkeypatch.setattr(
            DMSManager,
            "_calculate_onboard_resources",
            staticmethod(lambda: {"cpu_cores": 4, "ram_gb": 16.0, "disk_gb": 100.0, "gpus": []}),
        )
        monkeypatch.setattr(
            "modules.dms_manager.run_dms_command_with_passphrase",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout='{"success": true}',
                stderr="",
            ),
        )
        monkeypatch.setattr(
            "modules.dms_manager._verify_dms_onboarded",
            lambda: (False, "DMS did not report onboarded after compute onboard command (last status: NOT ONBOARDED)"),
        )

        result = mgr.onboard_compute()
        assert result["status"] == "error"
        assert "did not report onboarded" in result["message"]


class TestCalculateOnboardResourcesIntegration:
    def test_calculate_onboard_resources_large_disk_host(self, monkeypatch):
        hardware_spec = {
            "OK": True,
            "Resources": {
                "cpu": {"cores": 8},
                "ram": {"size": int(32 * 1024**3)},
                "disk": {"size": int(300 * 1024**3)},
                "gpus": [],
            },
        }

        def fake_run(cmd, *args, **kwargs):
            if cmd[:2] == ["free", "-k"]:
                return SimpleNamespace(
                    returncode=0,
                    stdout="Mem:       33554432       1048576       32505856\n",
                    stderr="",
                )
            if cmd[:2] == ["df", "-k"]:
                # total ~300 GiB, free ~283 GiB
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        "Filesystem     1K-blocks      Used Available Use% Mounted on\n"
                        "/dev/root      314572800  10485760 296687616  4% /\n"
                    ),
                    stderr="",
                )
            return SimpleNamespace(returncode=1, stdout="", stderr="unexpected")

        monkeypatch.setattr(
            "modules.dms_manager.run_dms_command_with_passphrase",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout=json.dumps(hardware_spec),
                stderr="",
            ),
        )
        monkeypatch.setattr("modules.dms_manager.subprocess.run", fake_run)

        resources = DMSManager._calculate_onboard_resources()
        assert resources["disk_gb"] == 270.0
        assert resources["cpu_cores"] == 7
        assert resources["ram_gb"] > 0
