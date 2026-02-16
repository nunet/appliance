import json
import sys
import types
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.nunet_api import security as security_module


@pytest.fixture(scope="session", autouse=True)
def stub_external_modules(tmp_path_factory):
    """Provide lightweight stand-ins for modules with heavy side effects."""
    stubs_root = tmp_path_factory.mktemp("nunet_stub_modules")
    ensembles_dir = stubs_root / "ensembles"
    ensembles_dir.mkdir(parents=True, exist_ok=True)
    onboarding_dir = stubs_root / "onboarding"
    onboarding_dir.mkdir(parents=True, exist_ok=True)

    modules_pkg = types.ModuleType("modules")
    modules_pkg.__path__ = []  # mark as package
    sys.modules["modules"] = modules_pkg

    def add_submodule(name: str) -> types.ModuleType:
        module = types.ModuleType(f"modules.{name}")
        sys.modules[f"modules.{name}"] = module
        setattr(modules_pkg, name, module)
        return module

    def _command_result(message: str = "ok") -> dict[str, Any]:
        return {
            "status": "success",
            "message": message,
            "stdout": "",
            "stderr": "",
            "returncode": 0,
        }

    mod_dms_manager = add_submodule("dms_manager")

    class DummyDMSManager:
        def __init__(self, *args, **kwargs):
            self.base_dir = ensembles_dir
            self.scripts_dir = stubs_root / "scripts"
            self.scripts_dir.mkdir(parents=True, exist_ok=True)

        def get_dms_version(self) -> str:
            return "0.0.0"

        def check_dms_installation(self) -> dict[str, str]:
            return {"status": "not_installed", "version": "0.0.0"}

        def get_self_peer_info(self) -> dict[str, Any]:
            return {
                "peer_id": "stub-peer",
                "context": "local",
                "did": "did:stub:peer",
                "local_addrs": ["/ip4/10.0.0.1"],
                "public_addrs": ["/ip4/1.2.3.4"],
                "relay_addrs": [],
                "is_relayed": False,
            }

        def get_peer_id(self) -> str:
            return "stub-peer-id"

        def restart_dms(self) -> dict[str, Any]:
            return _command_result("restart")

        def onboard_compute(self) -> dict[str, Any]:
            return _command_result("onboard")

        def offboard_compute(self) -> dict[str, Any]:
            return _command_result("offboard")

        def get_resource_allocation(self) -> dict[str, Any]:
            result = _command_result(json.dumps({"cpu": "0%", "memory": "0 MB"}))
            result["message"] = json.dumps({"cpu": "0%", "memory": "0 MB"})
            return result

        def view_peer_details(self) -> dict[str, Any]:
            result = _command_result(json.dumps({"peers": []}))
            result["message"] = json.dumps({"peers": []})
            return result

        def list_transactions(self, blockchain: str | None = None) -> dict[str, Any]:
            return {"status": "success", "transactions": []}

        def get_structured_logs(
            self,
            alloc_dir=None,
            lines: int = 200,
            refresh_alloc_logs: bool = True,
            include_dms_logs: bool = True,
        ) -> dict[str, Any]:
            return {
                "status": "success",
                "message": "ok",
                "allocation": {
                    "dir": str(alloc_dir) if alloc_dir else None,
                    "stdout": {
                        "path": "stdout.log",
                        "exists": False,
                        "readable": False,
                        "size_bytes": 0,
                    },
                    "stderr": {
                        "path": "stderr.log",
                        "exists": False,
                        "readable": False,
                        "size_bytes": 0,
                    },
                },
                "dms_logs": {
                    "source": "journalctl",
                    "lines": lines,
                    "stdout": "",
                    "stderr": "",
                    "returncode": 0,
                },
            }

        def get_filtered_dms_logs(
            self,
            deployment_id: str,
            *,
            query: str | None = None,
            max_lines: int = 400,
            last_run: bool = True,
            view: str = "compact",
        ) -> dict[str, Any]:
            return {
                "source": "nunet-logs",
                "lines": max_lines,
                "stdout": "",
                "stderr": "",
                "returncode": 0,
            }

        def __getattr__(self, attr: str):
            def _(*_args, **_kwargs):
                return _command_result(f"{attr} executed")

            return _

    mod_dms_manager.DMSManager = DummyDMSManager

    mod_dms_utils = add_submodule("dms_utils")
    mod_dms_utils.get_cached_dms_peer_raw = lambda *args, **kwargs: ""
    mod_dms_utils.get_cached_dms_resource_info = lambda *args, **kwargs: {}
    mod_dms_utils.get_cached_dms_status_info = lambda *args, **kwargs: {}
    mod_dms_utils.get_dms_status_info = lambda *args, **kwargs: {}
    mod_dms_utils.run_dms_command_with_passphrase = lambda *args, **kwargs: _command_result("run")

    mod_ensemble_mgr = add_submodule("ensemble_manager_v2")

    class DummyEnsembleManagerV2:
        def __init__(self, *args, **kwargs):
            self.base_dir = ensembles_dir
            self.source_dir = ensembles_dir
            self.repo = ensembles_dir

        def get_ensemble_files(self):
            return []

        def get_deployments_for_web(self, *args, **kwargs):
            return {"status": "success", "deployments": [], "count": 0}

        def view_running_ensembles(self):
            return {"status": "success", "message": "", "items": []}

        def __getattr__(self, attr: str):
            def _(*_args, **_kwargs):
                return {"status": "success", "message": f"{attr} executed"}

            return _

    mod_ensemble_mgr.EnsembleManagerV2 = DummyEnsembleManagerV2

    mod_ensemble_utils = add_submodule("ensemble_utils")
    mod_ensemble_utils.scan_ensembles_directory = lambda *args, **kwargs: []
    mod_ensemble_utils.load_ensemble_metadata = lambda *args, **kwargs: {}
    mod_ensemble_utils.process_yaml_template = lambda *args, **kwargs: {"content": ""}
    mod_ensemble_utils.validate_form_data = lambda *args, **kwargs: {"valid": True, "errors": []}
    mod_ensemble_utils.save_deployment_instance = lambda *args, **kwargs: {"saved": True}
    mod_ensemble_utils.get_deployment_options = lambda *args, **kwargs: {}

    mod_onboarding = add_submodule("onboarding_manager")

    class DummyOnboardingManager:
        STATE_PATH = onboarding_dir / "onboarding_state.json"
        LOG_PATH = onboarding_dir / "onboarding.log"

        def __init__(self, *args, **kwargs):
            self.state = {"step": "init", "logs": []}
            self.use_mock_api = kwargs.get("use_mock_api", False)

        def load_state(self):
            return self.state

        def save_state(self):
            self.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.STATE_PATH.write_text("{}", encoding="utf-8")

        def append_log(self, step, message, **_kwargs):
            self.state.setdefault("logs", []).append({"step": step, "message": message})

        def update_state(self, **kwargs):
            self.state.update(kwargs)

        def clear_state(self):
            if self.STATE_PATH.exists():
                self.STATE_PATH.unlink()
            self.state = {"step": "init", "logs": []}

        def mark_onboarding_complete(self, *_args, **_kwargs):
            self.state["completed"] = True

        def log(self, _message):
            pass

        def get_onboarding_status(self):
            return self.state

        def __getattr__(self, _attr):
            def _(*_args, **_kwargs):
                return {}

            return _

    mod_onboarding.OnboardingManager = DummyOnboardingManager

    mod_org_manager = add_submodule("organization_manager")

    class DummyOrganizationManager:
        def __getattr__(self, _attr):
            def _(*_args, **_kwargs):
                return []

            return _

    mod_org_manager.OrganizationManager = DummyOrganizationManager

    mod_org_utils = add_submodule("org_utils")
    mod_org_utils.load_known_organizations = lambda *args, **kwargs: []
    mod_org_utils.get_joined_organizations_with_details = lambda *args, **kwargs: []
    mod_org_utils.get_joined_organizations_with_names = lambda *args, **kwargs: []

    mod_utils = add_submodule("utils")
    mod_utils.get_local_ip = lambda: "127.0.0.1"
    mod_utils.get_public_ip = lambda: "127.0.0.1"
    mod_utils.get_appliance_version = lambda: "0.0.0"
    mod_utils.get_ssh_status = lambda: "SSH: Stopped | Authorized Keys: 0"

    termios_stub = types.ModuleType("termios")
    # Populate the common POSIX termios flags so code importing termios finds the constants on Windows tests
    for name in [
        "TCSAFLUSH",
        "TCSANOW",
        "TCSADRAIN",
        "ICANON",
        "ECHO",
        "ECHONL",
        "OPOST",
        "ISIG",
        "ICRNL",
        "IXON",
        "IXOFF",
        "BRKINT",
        "INPCK",
        "ISTRIP",
        "CSIZE",
        "PARENB",
        "CS8",
        "CS7",
        "ECHOE",
        "ECHOK",
        "VMIN",
        "VTIME",
        "IEXTEN",
    ]:
        setattr(termios_stub, name, 0)
    termios_stub.tcsetattr = lambda *args, **kwargs: None
    termios_stub.tcgetattr = lambda *_args, **_kwargs: [0, 0, 0, 0, 0, 0]
    sys.modules["termios"] = termios_stub

    yield


def _reset_backend_modules() -> None:
    preserved = {"backend.nunet_api.security"}
    for name in list(sys.modules):
        if name.startswith("backend.nunet_api") and name not in preserved:
            sys.modules.pop(name)


@pytest.fixture
def app(monkeypatch, tmp_path, stub_external_modules):
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    (static_dir / "index.html").write_text("ok", encoding="utf-8")
    monkeypatch.setenv("NUNET_STATIC_DIR", str(static_dir))

    creds_path = tmp_path / "creds.json"
    monkeypatch.setenv(security_module.CREDENTIALS_ENV_KEY, str(creds_path))

    _reset_backend_modules()
    import backend.nunet_api.main as main_module

    yield main_module.app

    if creds_path.exists():
        creds_path.unlink()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def _collect_api_routes(fastapi_app) -> list[APIRoute]:
    return [
        route
        for route in fastapi_app.routes
        if isinstance(route, APIRoute) and route.endpoint.__module__.startswith("backend.nunet_api")
    ]


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_auth_setup_and_token_flow(client):
    try:
        status_response = client.get("/auth/status")
        assert status_response.status_code == 200
        assert status_response.json()["password_set"] is False

        expected_conflict = client.post("/auth/token", json={"password": "wrong"})
        assert expected_conflict.status_code == 409

        setup_payload = {"password": "StrongPass9"}
        setup_response = client.post("/auth/setup", json=setup_payload)
        assert setup_response.status_code == 200
        setup_data = setup_response.json()
        assert setup_data.get("access_token")
        assert setup_data.get("token_type") == "bearer"

        bad_login = client.post("/auth/token", json={"password": "not_the_password"})
        assert bad_login.status_code == 401

        good_login = client.post("/auth/token", json=setup_payload)
        assert good_login.status_code == 200
        token_data = good_login.json()
        assert token_data.get("access_token")
        assert token_data.get("token_type") == "bearer"
    finally:
        security_module.clear_credentials()


def test_registered_routes_cover_expected_prefixes(app):
    routes = _collect_api_routes(app)
    assert routes
    prefixes = {
        route.path.split("/", 2)[1]
        for route in routes
        if route.path.startswith("/") and route.path not in {"/", "/health"}
    }
    expected = {"auth", "dms", "sys", "ensemble", "organizations", "payments"}
    assert expected.issubset(prefixes)


def test_dms_status_returns_normalized_snapshot(client, monkeypatch):
    from backend.nunet_api.routers import dms as dms_router

    status_payload = {
        "dms_status": "Ready",
        "dms_version": "1.2.3",
        "dms_running": "\u001b[32mRunning\u001b[0m",
        "dms_context": "local",
        "dms_did": "did:nunet:123",
        "dms_peer_id": "peer-123",
        "dms_is_relayed": True,
    }
    monkeypatch.setattr(dms_router, "get_cached_dms_status_info", lambda: status_payload)

    response = client.get("/dms/status")
    assert response.status_code == 200
    body = response.json()
    assert body["dms_running"] is True
    assert body["dms_status"] == "Ready"
    assert body["dms_peer_id"] == "peer-123"


def test_dms_resources_allocated_parses_json_payload(client):
    from backend.nunet_api.routers import dms as dms_router

    class StubManager:
        def get_resource_allocation(self):
            return {
                "status": "success",
                "message": json.dumps({"cpu": "2 cores", "memory": "4 GB"}),
                "stdout": "",
                "stderr": "",
                "returncode": 0,
            }

    client.app.dependency_overrides[dms_router.get_mgr] = lambda: StubManager()
    try:
        response = client.get("/dms/resources/allocated")
    finally:
        client.app.dependency_overrides.pop(dms_router.get_mgr, None)

    assert response.status_code == 200
    body = response.json()
    assert body == {"cpu": "2 cores", "memory": "4 GB"}


def test_dms_peers_connected_uses_cached_payload(client, monkeypatch):
    from backend.nunet_api.routers import dms as dms_router

    peers_payload = {
        "peers": [
            {
                "peer_id": "peer-1",
                "did": "did:peer:1",
                "context": "prod",
                "local_addrs": ["/ip4/10.0.0.2"],
                "public_addrs": ["/ip4/8.8.8.8"],
                "relay_addrs": [],
            }
        ]
    }
    monkeypatch.setattr(dms_router, "get_cached_dms_peer_raw", lambda: json.dumps(peers_payload))

    response = client.get("/dms/peers/connected")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["raw"] is None
    assert data["peers"][0]["peer_id"] == "peer-1"


def test_sysinfo_ssh_status_parses_authorized_keys(client, monkeypatch):
    from backend.nunet_api.routers import sysinfo as sysinfo_router

    ssh_line = "\u001b[32mSSH: Running | Authorized Keys: 5\u001b[0m"
    monkeypatch.setattr(sysinfo_router, "get_ssh_status", lambda: ssh_line)

    response = client.get("/sys/ssh-status")
    assert response.status_code == 200
    assert response.json() == {"running": True, "authorized_keys": 5}


def test_payments_list_payments_normalizes_transactions(client):
    from backend.nunet_api.routers import payments as payments_router

    class StubPaymentsManager:
        def list_transactions(self, blockchain=None):
            return {
                "status": "success",
                "transactions": [
                    {
                        "unique_id": "2",
                        "status": "paid",
                        "to_address": "0x" + "a" * 40,
                        "amount": "1.000000",
                        "payment_validator_did": "did:validator:2",
                        "contract_did": "did:contract:2",
                        "tx_hash": "0x" + "b" * 64,
                    },
                    {
                        "unique_id": "1",
                        "status": "unpaid",
                        "to_address": "0x" + "c" * 40,
                        "amount": "0.500000",
                        "payment_validator_did": "did:validator:1",
                        "contract_did": "did:contract:1",
                        "tx_hash": "0x" + "d" * 64,
                        "metadata": {
                            "deployment_id": "deployment-123",
                            "allocation_count": 2,
                            "total_utilization_sec": 3600,
                        },
                    },
                ]
            }

    client.app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()
    try:
        response = client.get("/payments/list_payments")
    finally:
        client.app.dependency_overrides.pop(payments_router.get_mgr, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    assert body["paid_count"] == 1
    assert body["unpaid_count"] == 1
    assert body["ignored_count"] == 0
    assert body["items"][0]["unique_id"] == "1"
    assert body["items"][0]["blockchain"] == "ETHEREUM"
    assert body["items"][0]["metadata"]["deployment_id"] == "deployment-123"


def test_payments_list_payments_normalizes_metadata_variants(client):
    from backend.nunet_api.routers import payments as payments_router

    class StubPaymentsManager:
        def list_transactions(self, blockchain=None):
            return {
                "status": "success",
                "transactions": [
                    {
                        "unique_id": "1",
                        "status": "unpaid",
                        "to_address": "0x" + "c" * 40,
                        "amount": "1.250000",
                        "payment_validator_did": "did:validator:1",
                        "contract_did": "did:contract:1",
                        "tx_hash": "",
                        "Metadata": "{\"deployment_id\":\"dep-a\",\"allocation_count\":3}",
                    },
                    {
                        "unique_id": "2",
                        "status": "paid",
                        "to_address": "0x" + "d" * 40,
                        "amount": "2.000000",
                        "payment_validator_did": "did:validator:2",
                        "contract_did": "did:contract:2",
                        "tx_hash": "0x" + "a" * 64,
                        "metadata": "not-json",
                    },
                ],
            }

    client.app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()
    try:
        response = client.get("/payments/list_payments")
    finally:
        client.app.dependency_overrides.pop(payments_router.get_mgr, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    assert body["items"][0]["unique_id"] == "1"
    assert body["items"][0]["metadata"]["deployment_id"] == "dep-a"
    assert body["items"][0]["metadata"]["allocation_count"] == 3
    assert body["items"][1]["metadata"] is None


def test_payments_list_payments_handles_list_addresses(client):
    from backend.nunet_api.routers import payments as payments_router

    addr = "0x" + "e" * 40

    class StubPaymentsManager:
        def list_transactions(self, blockchain=None):
            return {
                "status": "success",
                "transactions": [
                    {
                        "unique_id": "1",
                        "status": "paid",
                        "to_address": [addr, "0x" + "f" * 40],
                        "amount": "2.0",
                        "payment_validator_did": "did:validator:1",
                        "contract_did": "did:contract:1",
                        "tx_hash": "0x" + "a" * 64,
                    }
                ],
            }

    client.app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()
    try:
        response = client.get("/payments/list_payments")
    finally:
        client.app.dependency_overrides.pop(payments_router.get_mgr, None)

    assert response.status_code == 200
    body = response.json()
    assert body["ignored_count"] == 0
    assert body["items"][0]["to_address"] == addr
    assert body["items"][0]["blockchain"] == "ETHEREUM"


def test_payments_list_payments_ignores_invalid_payloads(client):
    from backend.nunet_api.routers import payments as payments_router

    class StubPaymentsManager:
        def list_transactions(self, blockchain=None):
            return {
                "status": "success",
                "transactions": [
                    {
                        "unique_id": "1",
                        "status": "unpaid",
                        "to_address": "",
                        "amount": "not-a-number",
                    },
                    {
                        "unique_id": "2",
                        "status": "paid",
                        "to_address": "0x" + "a" * 40,
                        "amount": "1.0",
                    },
                    "bad",
                ],
            }

    client.app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()
    try:
        response = client.get("/payments/list_payments")
    finally:
        client.app.dependency_overrides.pop(payments_router.get_mgr, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["ignored_count"] == 2
    assert body["items"][0]["unique_id"] == "2"


def test_payments_list_payments_supports_cardano(client):
    from backend.nunet_api.routers import payments as payments_router

    cardano_addr = "addr_test1qqm9ehanrh5rkukd0jwrl4j4zhnlzhkutwcukxqjdr3yfwydfmfydwq78revg8sx3wf3aj9gwn5kqyg0l2485zrj3mvsktcw4k"

    class StubPaymentsManager:
        def list_transactions(self, blockchain=None):
            return {
                "status": "success",
                "transactions": [
                    {
                        "unique_id": "cardano-1",
                        "status": "unpaid",
                        "to_address": [{"blockchain": "CARDANO", "provider_addr": cardano_addr}],
                        "amount": "5",
                        "payment_validator_did": "did:validator:3",
                        "contract_did": "did:contract:3",
                        "tx_hash": "",
                    }
                ],
            }

    client.app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()
    try:
        response = client.get("/payments/list_payments")
    finally:
        client.app.dependency_overrides.pop(payments_router.get_mgr, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["items"][0]["blockchain"] == "CARDANO"
    assert body["items"][0]["to_address"] == cardano_addr


def test_organizations_status_includes_timeline(client, monkeypatch):
    from backend.nunet_api.routers import organizations as org_router

    sample_state = {
        "step": "pending_authorization",
        "progress": 42,
        "api_status": "processing",
        "logs": [{"step": "select_org"}, {"step": "pending_authorization"}],
        "org_data": {"name": "Test Org"},
    }
    monkeypatch.setattr(org_router._onboarding, "get_onboarding_status", lambda: sample_state)

    response = client.get("/organizations/status")
    assert response.status_code == 200
    data = response.json()
    assert data["current_step"] == "pending_authorization"
    assert data["progress"] == 42
    assert any(step["id"] == "pending_authorization" and step["state"] == "active" for step in data["step_states"])


def test_join_submit_with_org_did_does_not_revert_to_select_org(client, monkeypatch):
    from backend.nunet_api.routers import organizations as org_router

    org_did = "did:key:test"
    org_entry = {
        "name": "Test Org",
        "roles": ["compute_provider"],
        "join_fields": [],
    }

    class RecordingOnboardingManager:
        def __init__(self):
            self.state = {"step": "init", "logs": []}
            self.step_history: list[str] = []
            self._resource_snapshot = {
                "onboarding_status": "ONBOARDED",
                "onboarded_resources": "Cores: 2, RAM: 4 GB, Disk: 50 GB",
                "free_resources": "demo",
                "allocated_resources": "demo",
                "dms_resources": {"cpu": {"cores": 2}, "ram": {"size": 4096}},
            }
            self.dms_manager = types.SimpleNamespace(
                get_self_peer_info=lambda: {
                    "did": "did:peer:test",
                    "peer_id": "peer-test",
                    "context": "local",
                    "public_addrs": [],
                    "local_addrs": [],
                }
            )

        def update_state(self, **kwargs):
            old_step = self.state.get("step")
            self.state.update(kwargs)
            new_step = self.state.get("step")
            if new_step and new_step != old_step:
                self.step_history.append(new_step)
                logs = self.state.setdefault("logs", [])
                logs.append({"step": new_step, "message": f"step->{new_step}"})

        def append_log(self, step, message, **_):
            self.state.setdefault("logs", []).append({"step": step, "message": message})

        def get_onboarding_status(self):
            return dict(self.state)

        def ensure_pre_onboarding(self):
            return dict(self._resource_snapshot)

        def api_submit_join(self, payload, resource_info=None):
            self.last_payload = payload
            return {"status": "pending", "id": "req-123", "status_token": "token-abc"}

    recording_mgr = RecordingOnboardingManager()
    monkeypatch.setattr(org_router, "_onboarding", recording_mgr)
    monkeypatch.setattr(org_router, "_ensure_state_file", lambda mgr: None)
    monkeypatch.setattr(org_router, "load_known_organizations", lambda: {org_did: org_entry})
    monkeypatch.setattr(org_router, "normalize_org_roles", lambda _entry: (["compute_provider"], []))
    monkeypatch.setattr(org_router, "extract_role_profiles", lambda _entry: {"compute_provider": {}})
    monkeypatch.setattr(org_router, "get_tokenomics_config", lambda _entry: {"enabled": False, "chain": None})
    monkeypatch.setattr(
        org_router,
        "get_cached_dms_status_info",
        lambda: {"dms_did": "did:dms:test", "dms_peer_id": "peer-test"},
    )
    monkeypatch.setattr(
        org_router,
        "get_cached_dms_resource_info",
        lambda: {"onboarding_status": "ONBOARDED", "onboarded_resources": "{}", "dms_resources": {}},
    )
    monkeypatch.setattr(org_router.role_metadata, "record_role_selection", lambda *args, **kwargs: None)
    monkeypatch.setattr(org_router.role_metadata, "record_join_payload", lambda *args, **kwargs: None)
    monkeypatch.setattr(org_router.role_metadata, "record_org_tokenomics", lambda *args, **kwargs: None)
    monkeypatch.setattr(org_router.role_metadata, "record_last_request_id", lambda *args, **kwargs: None)

    payload = {
        "org_did": org_did,
        "name": "Alice Example",
        "email": "alice@example.com",
        "roles": ["compute_provider"],
        "why_join": "compute_provider",
    }

    response = client.post("/organizations/join/submit", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["step"] == "join_data_sent"
    assert body["api_status"] == "pending"

    # Ensure the server-side step history never reverts to select_org
    assert "select_org" not in recording_mgr.step_history
    assert recording_mgr.step_history[0] == "collect_join_data"
    assert recording_mgr.step_history[-1] == "join_data_sent"

    payload_resources = recording_mgr.last_payload["dms_resources"]
    assert payload_resources["onboarded_resources"] == "Cores: 2, RAM: 4 GB, Disk: 50 GB"

    snapshot = recording_mgr.state.get("last_resource_snapshot", {})
    assert snapshot.get("onboarded_resources") == "Cores: 2, RAM: 4 GB, Disk: 50 GB"

    snapshots = [client.get("/organizations/status").json(), client.get("/organizations/status").json()]
    for snapshot in snapshots:
        assert snapshot["current_step"] == "join_data_sent"
        assert snapshot["current_step"] != "select_org"


def test_onboarding_manager_onboarded_status_detection():
    from modules.onboarding_manager import OnboardingManager

    assert OnboardingManager._is_onboarded_status("ONBOARDED") is True
    assert OnboardingManager._is_onboarded_status("  \x1b[0mOnboarded  ") is True
    assert OnboardingManager._is_onboarded_status("NOT ONBOARDED") is False
    assert OnboardingManager._is_onboarded_status("pending") is False
    assert OnboardingManager._is_onboarded_status(True) is True
    assert OnboardingManager._is_onboarded_status(False) is False
def test_ensemble_templates_list_uses_relative_paths(client, tmp_path):
    from backend.nunet_api.routers import ensemble as ensemble_router

    base_dir = tmp_path / "ensembles"
    base_dir.mkdir()
    template_path = base_dir / "demo" / "app.yaml"
    template_path.parent.mkdir(parents=True, exist_ok=True)
    template_path.write_text("kind: Demo", encoding="utf-8")

    class StubEnsembleManager:
        def __init__(self):
            self.base_dir = base_dir
            self.source_dir = base_dir
            self.repo = base_dir

        def get_ensemble_files(self):
            return [(0, template_path)]

    client.app.dependency_overrides[ensemble_router.get_mgr] = lambda: StubEnsembleManager()
    try:
        response = client.get("/ensemble/templates")
    finally:
        client.app.dependency_overrides.pop(ensemble_router.get_mgr, None)

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["relative_path"] == "demo/app.yaml"


def test_no_websocket_routes_registered(app):
    ws_routes = [
        route
        for route in app.routes
        if route.__class__.__name__ == "WebSocketRoute" and route.endpoint.__module__.startswith("backend.nunet_api")
    ]
    assert not ws_routes, "WebSocket routes should be removed from backend.nunet_api"
