from modules import dms_utils


def test_get_dms_resource_info_enriches_gpu_make_and_model(monkeypatch):
    responses = {
        "/dms/node/onboarding/status": {"onboarded": True},
        "/dms/node/resources/free": {
            "Resources": {
                "cpu": {"cores": 8},
                "ram": {"size": 34359738368},
                "disk": {"size": 549755813888},
            }
        },
        "/dms/node/resources/allocated": {
            "Resources": {
                "cpu": {"cores": 8},
                "ram": {"size": 34359738368},
                "disk": {"size": 549755813888},
            }
        },
        "/dms/node/resources/onboarded": {
            "Resources": {
                "cpu": {"cores": 8},
                "ram": {"size": 34359738368},
                "disk": {"size": 549755813888},
                "gpus": [
                    {
                        "index": 0,
                        "uuid": "GPU-0",
                        "vram": 25769803776,
                    }
                ],
            }
        },
        "/dms/node/hardware/spec": {
            "OK": True,
            "Resources": {
                "gpus": [
                    {
                        "index": 0,
                        "uuid": "GPU-0",
                        "vendor": "NVIDIA",
                        "model": "GeForce RTX 4090",
                        "vram": 25769803776,
                    }
                ]
            },
        },
    }

    monkeypatch.setattr(dms_utils, "_call_actor_json", lambda endpoint, **kwargs: responses.get(endpoint))

    info = dms_utils.get_dms_resource_info()
    gpus = info["dms_resources"]["gpus"]
    assert len(gpus) == 1
    assert gpus[0]["make"] == "NVIDIA"
    assert gpus[0]["vendor"] == "NVIDIA"
    assert gpus[0]["model"] == "GeForce RTX 4090"


def test_get_dms_resource_info_uses_hardware_spec_gpu_when_resource_gpu_missing(monkeypatch):
    responses = {
        "/dms/node/onboarding/status": {"onboarded": True},
        "/dms/node/resources/free": {
            "Resources": {
                "cpu": {"cores": 8},
                "ram": {"size": 34359738368},
                "disk": {"size": 549755813888},
            }
        },
        "/dms/node/resources/allocated": {
            "Resources": {
                "cpu": {"cores": 8},
                "ram": {"size": 34359738368},
                "disk": {"size": 549755813888},
            }
        },
        "/dms/node/resources/onboarded": {
            "Resources": {
                "cpu": {"cores": 8},
                "ram": {"size": 34359738368},
                "disk": {"size": 549755813888},
                "gpus": [],
            }
        },
        "/dms/node/hardware/spec": {
            "Resources": {
                "gpus": [
                    {
                        "index": 1,
                        "make": "AMD",
                        "model": "Radeon RX 7900",
                        "vram": 25769803776,
                    }
                ]
            },
        },
    }

    monkeypatch.setattr(dms_utils, "_call_actor_json", lambda endpoint, **kwargs: responses.get(endpoint))

    info = dms_utils.get_dms_resource_info()
    gpus = info["dms_resources"]["gpus"]
    assert len(gpus) == 1
    assert gpus[0]["index"] == 1
    assert gpus[0]["make"] == "AMD"
    assert gpus[0]["vendor"] == "AMD"
    assert gpus[0]["model"] == "Radeon RX 7900"
