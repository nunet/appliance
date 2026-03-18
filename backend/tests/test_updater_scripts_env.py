from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _make_fake_wget(bin_dir: Path, *, stable_available: bool) -> None:
    script = bin_dir / "wget"
    script.write_text(
        """#!/usr/bin/env bash
set -e
if [[ "$1" == "--spider" ]]; then
  url="${@: -1}"
  if [[ "$url" == *"stable.deb" ]]; then
    if [[ "${FAKE_STABLE_AVAILABLE:-0}" == "1" ]]; then
      exit 0
    fi
    exit 1
  fi
  exit 0
fi

out=""
for ((i=1; i<=$#; i++)); do
  arg="${!i}"
  if [[ "$arg" == "-O" ]]; then
    j=$((i+1))
    out="${!j}"
  fi
done

if [[ -n "$out" ]]; then
  printf 'dummy' > "$out"
fi
exit 0
""",
        encoding="utf-8",
    )
    script.chmod(0o755)


def _run_script(script_path: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script_path)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _parse_key_values(stdout: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


@pytest.mark.parametrize(
    "script_rel",
    [
        "deploy/scripts/updater.sh",
        "deploy/scripts/dms-updater.sh",
    ],
)
def test_updater_scripts_dry_run_show_fallback_when_stable_unavailable(tmp_path, script_rel):
    script_path = ROOT / script_rel
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    _make_fake_wget(fake_bin, stable_available=False)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    env["APPLIANCE_ENV"] = "production"
    env["NUNET_UPDATER_DRY_RUN"] = "1"
    env["FAKE_STABLE_AVAILABLE"] = "0"

    result = _run_script(script_path, env)
    assert result.returncode == 0, result.stderr

    payload = _parse_key_values(result.stdout)
    assert payload["environment"] == "production"
    assert payload["channel"] == "stable"
    assert payload["resolved_channel"] == "latest"
    assert payload["fell_back"] == "true"


@pytest.mark.parametrize(
    "script_rel",
    [
        "deploy/scripts/updater.sh",
        "deploy/scripts/dms-updater.sh",
    ],
)
def test_updater_scripts_dry_run_staging_uses_latest(tmp_path, script_rel):
    script_path = ROOT / script_rel
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    _make_fake_wget(fake_bin, stable_available=True)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    env["APPLIANCE_ENV"] = "staging"
    env["NUNET_UPDATER_DRY_RUN"] = "1"
    env["FAKE_STABLE_AVAILABLE"] = "1"

    result = _run_script(script_path, env)
    assert result.returncode == 0, result.stderr

    payload = _parse_key_values(result.stdout)
    assert payload["environment"] == "staging"
    assert payload["channel"] == "latest"
    assert payload["resolved_channel"] == "latest"
    assert payload["fell_back"] == "false"


@pytest.mark.parametrize(
    "script_rel",
    [
        "deploy/scripts/updater.sh",
        "deploy/scripts/dms-updater.sh",
    ],
)
def test_updater_scripts_fail_for_invalid_appliance_env(tmp_path, script_rel):
    script_path = ROOT / script_rel
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    _make_fake_wget(fake_bin, stable_available=True)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    env["APPLIANCE_ENV"] = "prod"
    env["NUNET_UPDATER_DRY_RUN"] = "1"

    result = _run_script(script_path, env)
    assert result.returncode != 0
    assert "Invalid APPLIANCE_ENV" in result.stderr
