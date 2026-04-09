from backend.modules.dms_utils import _fmt_resources


def test_fmt_resources_cpu_ram_disk_ignores_gpu_list():
    """_fmt_resources only formats CPU/RAM/Disk; GPU details live elsewhere."""
    payload = {
        "Resources": {
            "cpu": {"cores": 10.5},
            "gpus": [
                {
                    "index": 0,
                    "vendor": "NVIDIA",
                    "model": "NVIDIA GeForce RTX 3060",
                    "vram": 9663676416,
                }
            ],
            "ram": {"size": 13958643712},
            "disk": {"size": 43787191582},
        }
    }

    formatted = _fmt_resources(payload)

    assert "Cores: 10.5" in formatted
    assert "RAM: 13.0 GB" in formatted
    assert "Disk: 40.78 GB" in formatted
    assert "GPU" not in formatted


def test_fmt_resources_without_gpu_keeps_existing_shape():
    payload = {
        "cpu": {"cores": 2},
        "ram": {"size": 4 * 1024**3},
        "disk": {"size": 50 * 1024**3},
    }

    formatted = _fmt_resources(payload)

    assert formatted == "Cores: 2, RAM: 4.0 GB, Disk: 50.0 GB"
