"""Unit tests for the independent DMS Prometheus metrics exporter."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SERVER_PATH = (
    Path(__file__).resolve().parents[2]
    / "deploy"
    / "plugins"
    / "telemetry-exporter"
    / "dms-metrics"
    / "server.py"
)


@pytest.fixture(scope="module")
def exporter():
    spec = importlib.util.spec_from_file_location("nunet_dms_metrics_server", SERVER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.context = "dms"
        self.calls = []

    def actor_json(self, endpoint, *extra):
        key = endpoint
        if extra:
            key = endpoint + " " + " ".join(extra)
        self.calls.append(key)
        return self.responses.get(key, (False, None, "missing"))


def _capacity(cores, ram, disk):
    return {
        "Resources": {
            "cpu": {"cores": cores},
            "ram": {"size": ram},
            "disk": {"size": disk},
            "gpus": [{"index": 0, "vendor": "NVIDIA", "model": "T4", "vram": 16 * 1024**3}],
        }
    }


def test_resource_totals_cpu_ram_disk_only(exporter):
    payload = {
        "Resources": {
            "cpu": {"cores": 8},
            "ram": {"size": 16 * 1024**3},
            "disk": {"size": 100 * 1024**3},
            "gpus": [
                {"index": 0, "vendor": "NVIDIA", "model": "L40S", "vram": 48 * 1024**3, "cores": 18176},
            ],
        }
    }
    totals = exporter._resource_totals(payload)
    assert totals == {
        "cores": 8,
        "ram_bytes": 16 * 1024**3,
        "disk_bytes": 100 * 1024**3,
    }
    assert "gpu_count" not in totals


def test_collector_queries_onboarded_free_allocated_only(exporter):
    onboarded = _capacity(8, 16 * 1024**3, 100 * 1024**3)
    free = _capacity(4, 8 * 1024**3, 50 * 1024**3)
    allocated = _capacity(1, 1 * 1024**3, 5 * 1024**3)
    client = FakeClient(
        {
            "/dms/node/resources/onboarded": (True, onboarded, ""),
            "/dms/node/resources/free": (True, free, ""),
            "/dms/node/resources/allocated": (True, allocated, ""),
            "/dms/node/hardware/spec": (True, onboarded, ""),
            "/dms/node/onboarding/status": (True, {"onboarded": True}, ""),
            "/dms/node/peers/list": (True, {"peers": ["a", "b"]}, ""),
            "/dms/node/deployment/list": (True, {"Deployments": {"d1": {"Status": "Running"}}}, ""),
        }
    )
    text = exporter.MetricsCollector(client, ttl=0).render()
    normalized = text.replace(".0", "")

    assert sorted(client.calls) == [
        "/dms/node/resources/allocated",
        "/dms/node/resources/free",
        "/dms/node/resources/onboarded",
    ]

    assert 'nunet_dms_resource_cores{state="onboarded"} 8' in normalized
    assert 'nunet_dms_resource_cores{state="free"} 4' in normalized
    assert 'nunet_dms_resource_cores{state="allocated"} 1' in normalized
    assert 'nunet_dms_resource_ram_bytes{state="onboarded"}' in text
    assert 'nunet_dms_resource_ram_bytes{state="free"}' in text
    assert 'nunet_dms_resource_ram_bytes{state="allocated"}' in text
    assert 'nunet_dms_resource_disk_bytes{state="onboarded"}' in text

    assert "nunet_dms_resource_gpu_count" not in text
    assert "nunet_dms_gpu_vram_bytes" not in text
    assert "nunet_dms_gpu_cores" not in text
    assert "nunet_dms_peers" not in text
    assert "nunet_dms_deployments" not in text
    assert "nunet_dms_onboarded " not in text
    assert "nunet_dms_info" not in text
    assert "hardware/spec" not in text
    assert "onboarding/status" not in text

    assert 'endpoint="/dms/node/resources/onboarded"} 1' in normalized
    assert 'endpoint="/dms/node/resources/free"} 1' in normalized
    assert 'endpoint="/dms/node/resources/allocated"} 1' in normalized
    assert "nunet_dms_up 1" in normalized
    assert "nunet_dms_scrape_success 1" in normalized
    assert "nunet_dms_scrape_duration_seconds" in text


def test_collector_emits_zeros_when_unonboarded_style(exporter):
    """Capacity snapshots must still be emitted; do not gate on onboarded status."""
    zero = _capacity(0, 0, 0)
    client = FakeClient(
        {
            "/dms/node/resources/onboarded": (True, zero, ""),
            "/dms/node/resources/free": (True, zero, ""),
            "/dms/node/resources/allocated": (True, zero, ""),
        }
    )
    text = exporter.MetricsCollector(client, ttl=0).render()
    normalized = text.replace(".0", "")
    assert 'nunet_dms_resource_cores{state="onboarded"} 0' in normalized
    assert 'nunet_dms_resource_cores{state="free"} 0' in normalized
    assert 'nunet_dms_resource_cores{state="allocated"} 0' in normalized


def test_collector_marks_failure_when_one_resource_query_fails(exporter):
    client = FakeClient(
        {
            "/dms/node/resources/onboarded": (True, _capacity(8, 1, 1), ""),
            "/dms/node/resources/free": (True, _capacity(2, 1, 1), ""),
            "/dms/node/resources/allocated": (False, None, "timeout"),
        }
    )
    text = exporter.MetricsCollector(client, ttl=0).render()
    normalized = text.replace(".0", "")
    assert 'nunet_dms_resource_cores{state="onboarded"} 8' in normalized
    assert 'nunet_dms_resource_cores{state="free"} 2' in normalized
    assert 'state="allocated"' not in text
    assert 'endpoint="/dms/node/resources/allocated"} 0' in normalized
    assert "nunet_dms_up 0" in normalized
    assert "nunet_dms_scrape_success 0" in normalized
    assert "allocated error: timeout" in text


def test_prom_escape(exporter):
    assert exporter._prom_escape('a"b\\c') == 'a\\"b\\\\c'
