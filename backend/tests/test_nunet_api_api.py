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
    mod_dms_utils.invalidate_all_dms_caches = lambda *args, **kwargs: None
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

        @staticmethod
        def _is_onboarded_status(value) -> bool:
            if isinstance(value, bool):
                return value
            if not isinstance(value, str):
                return False

            # Strip common ANSI escape fragments and normalize whitespace/case.
            cleaned = value.replace("\x1b[0m", "").strip().upper()
            if "NOT" in cleaned and "ONBOARD" in cleaned:
                return False
            return "ONBOARD" in cleaned

        def __getattr__(self, _attr):
            def _(*_args, **_kwargs):
                return {}

            return _

    mod_onboarding.OnboardingManager = DummyOnboardingManager

    mod_appliance_manager = add_submodule("appliance_manager")

    class DummyApplianceManager:
        def get_uptime(self) -> str:
            return "0 days, 0:00:00"

        def get_systemd_logs(self, lines: int = 50):
            return {}

    mod_appliance_manager.ApplianceManager = DummyApplianceManager

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
    mod_org_utils.refresh_known_organizations = lambda *args, **kwargs: []
    mod_org_utils.normalize_org_roles = lambda *args, **kwargs: []
    mod_org_utils.extract_role_profiles = lambda *args, **kwargs: []
    mod_org_utils.get_tokenomics_config = lambda *args, **kwargs: {"enabled": False, "chain": None}
    mod_org_utils.TOKENOMICS_CHAIN_ALLOWLIST = []

    mod_contract_templates = add_submodule("contract_templates")
    mod_contract_templates.list_contract_templates = lambda *args, **kwargs: []
    mod_contract_templates.get_contract_template = lambda *args, **kwargs: None

    mod_upnp_manager = add_submodule("upnp_manager")

    class DummyUPnPManager:
        def discover_gateway(self, *args, **kwargs):
            return {"status": "success", "gateway_found": False, "router_info": {}}

        def list_port_mappings(self, *args, **kwargs):
            return {"status": "success", "mappings": []}

        def check_port_mapping(self, *args, **kwargs):
            return {"status": "success", "mapping": None}

        def add_port_mapping(self, *args, **kwargs):
            return {"status": "success", "message": "ok"}

        def delete_port_mapping(self, *args, **kwargs):
            return {"status": "success", "message": "ok"}

        def configure_appliance_port_forwarding(self, *args, **kwargs):
            return {"status": "success", "message": "ok"}

        def disable_appliance_port_forwarding(self, *args, **kwargs):
            return {"status": "success", "message": "ok"}

    mod_upnp_manager.UPnPManager = DummyUPnPManager

    mod_utils = add_submodule("utils")
    mod_utils.get_local_ip = lambda: "127.0.0.1"
    mod_utils.get_public_ip = lambda: "127.0.0.1"
    mod_utils.get_appliance_version = lambda: "0.0.0"
    mod_utils.get_ssh_status = lambda: "SSH: Stopped | Authorized Keys: 0"
    mod_utils.get_dms_updates = lambda *args, **kwargs: {"status": "success", "updates": []}
    mod_utils.trigger_dms_update = lambda *args, **kwargs: {"status": "success", "message": "ok"}
    mod_utils.get_updates = lambda *args, **kwargs: {"status": "success", "updates": []}
    mod_utils.trigger_appliance_update = lambda *args, **kwargs: {"status": "success", "message": "ok"}

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
    monkeypatch.setenv("HOME", str(tmp_path))
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
        setup_token = security_module.ensure_setup_token()
        setup_response = client.post("/auth/setup", json=setup_payload, params={"setup_token": setup_token})
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
    expected = {"auth", "dms", "sys", "ensemble", "filesystem", "organizations", "payments"}
    assert expected.issubset(prefixes)


def test_dms_status_returns_normalized_snapshot(authed_client, monkeypatch):
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
    monkeypatch.setattr(dms_router, "get_cached_dms_status_info", lambda *args, **kwargs: status_payload)

    response = authed_client.get("/dms/status")
    assert response.status_code == 200
    body = response.json()
    assert body["dms_running"] is True
    assert body["dms_status"] == "Ready"
    assert body["dms_peer_id"] == "peer-123"


def test_dms_resources_allocated_parses_json_payload(authed_client):
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

    authed_client.app.dependency_overrides[dms_router.get_mgr] = lambda: StubManager()
    try:
        response = authed_client.get("/dms/resources/allocated")
    finally:
        authed_client.app.dependency_overrides.pop(dms_router.get_mgr, None)

    assert response.status_code == 200
    body = response.json()
    assert body == {"cpu": "2 cores", "memory": "4 GB"}


def test_dms_peers_connected_uses_cached_payload(authed_client, monkeypatch):
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
    monkeypatch.setattr(dms_router, "get_cached_dms_peer_raw", lambda *args, **kwargs: json.dumps(peers_payload))

    response = authed_client.get("/dms/peers/connected")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["raw"] is None
    assert data["peers"][0]["peer_id"] == "peer-1"


def test_sysinfo_ssh_status_parses_authorized_keys(authed_client, monkeypatch):
    from backend.nunet_api.routers import sysinfo as sysinfo_router

    ssh_line = "\u001b[32mSSH: Running | Authorized Keys: 5\u001b[0m"
    monkeypatch.setattr(sysinfo_router, "get_ssh_status", lambda: ssh_line)

    response = authed_client.get("/sys/ssh-status")
    assert response.status_code == 200
    assert response.json() == {"running": True, "authorized_keys": 5}


def test_payments_list_payments_normalizes_transactions(authed_client):
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

    authed_client.app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()
    try:
        response = authed_client.get("/payments/list_payments")
    finally:
        authed_client.app.dependency_overrides.pop(payments_router.get_mgr, None)

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


def test_payments_list_payments_handles_list_addresses(authed_client):
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

    authed_client.app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()
    try:
        response = authed_client.get("/payments/list_payments")
    finally:
        authed_client.app.dependency_overrides.pop(payments_router.get_mgr, None)

    assert response.status_code == 200
    body = response.json()
    assert body["ignored_count"] == 0
    assert body["items"][0]["to_address"] == addr
    assert body["items"][0]["blockchain"] == "ETHEREUM"


def test_payments_list_payments_ignores_invalid_payloads(authed_client):
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

    authed_client.app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()
    try:
        response = authed_client.get("/payments/list_payments")
    finally:
        authed_client.app.dependency_overrides.pop(payments_router.get_mgr, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["ignored_count"] == 2
    assert body["items"][0]["unique_id"] == "2"


def test_payments_list_payments_supports_cardano(authed_client):
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

    authed_client.app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()
    try:
        response = authed_client.get("/payments/list_payments")
    finally:
        authed_client.app.dependency_overrides.pop(payments_router.get_mgr, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["items"][0]["blockchain"] == "CARDANO"
    assert body["items"][0]["to_address"] == cardano_addr


def test_organizations_status_includes_timeline(authed_client, monkeypatch):
    from backend.nunet_api.routers import organizations as org_router

    sample_state = {
        "step": "pending_authorization",
        "progress": 42,
        "api_status": "processing",
        "logs": [{"step": "select_org"}, {"step": "pending_authorization"}],
        "org_data": {"name": "Test Org"},
    }
    monkeypatch.setattr(org_router._onboarding, "get_onboarding_status", lambda: sample_state)

    response = authed_client.get("/organizations/status")
    assert response.status_code == 200
    data = response.json()
    assert data["current_step"] == "pending_authorization"
    assert data["progress"] == 42
    assert any(step["id"] == "pending_authorization" and step["state"] == "active" for step in data["step_states"])


def test_join_submit_with_org_did_does_not_revert_to_select_org(authed_client, monkeypatch):
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

        def _is_onboarded_status(self, value) -> bool:
            from modules.onboarding_manager import OnboardingManager

            return OnboardingManager._is_onboarded_status(value)

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
        lambda *args, **kwargs: {"dms_did": "did:dms:test", "dms_peer_id": "peer-test"},
    )
    monkeypatch.setattr(
        org_router,
        "get_cached_dms_resource_info",
        lambda *args, **kwargs: {"onboarding_status": "ONBOARDED", "onboarded_resources": "{}", "dms_resources": {}},
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

    response = authed_client.post("/organizations/join/submit", json=payload)
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

    snapshots = [authed_client.get("/organizations/status").json(), authed_client.get("/organizations/status").json()]
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
def test_ensemble_templates_list_uses_relative_paths(authed_client, tmp_path):
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

    authed_client.app.dependency_overrides[ensemble_router.get_mgr] = lambda: StubEnsembleManager()
    try:
        response = authed_client.get("/ensemble/templates")
    finally:
        authed_client.app.dependency_overrides.pop(ensemble_router.get_mgr, None)

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


@pytest.fixture
def authed_client(client):
    client.app.dependency_overrides[security_module.require_auth] = lambda: "admin"
    try:
        yield client
    finally:
        client.app.dependency_overrides.pop(security_module.require_auth, None)


@pytest.fixture
def filesystem_root(monkeypatch, tmp_path):
    import backend.nunet_api.routers.filesystem as fs_router

    root = tmp_path / "fsroot"
    root.mkdir()
    resolved = root.resolve()
    monkeypatch.setattr(fs_router, "ROOT_DIR", resolved)
    monkeypatch.setattr(fs_router, "ALLOWED_ROOTS", [resolved])
    monkeypatch.setattr(fs_router, "LISTABLE_DIRS", {resolved})
    return root


def test_filesystem_list_happy(authed_client, filesystem_root):
    docs = filesystem_root / "docs"
    docs.mkdir()
    (docs / "note.txt").write_text("hi", encoding="utf-8")
    (filesystem_root / "readme.md").write_text("ok", encoding="utf-8")

    response = authed_client.get("/filesystem/list", params={"path": str(filesystem_root)})
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    body = response.json()
    assert body["root"] == str(filesystem_root)
    assert body["path"] == str(filesystem_root)
    assert body["relative_path"] == "."

    items = body["items"]
    names = {item["name"] for item in items}
    assert {"docs", "readme.md"} <= names

    dir_indexes = [idx for idx, item in enumerate(items) if item["is_dir"]]
    file_indexes = [idx for idx, item in enumerate(items) if item["is_file"]]
    if dir_indexes and file_indexes:
        assert max(dir_indexes) < min(file_indexes)


def test_filesystem_list_rejects_file_path(authed_client, filesystem_root):
    target = filesystem_root / "file.txt"
    target.write_text("content", encoding="utf-8")
    response = authed_client.get("/filesystem/list", params={"path": str(target)})
    assert response.status_code == 400


def test_filesystem_list_rejects_outside_root(authed_client, filesystem_root):
    outside = filesystem_root.parent
    response = authed_client.get("/filesystem/list", params={"path": str(outside)})
    assert response.status_code == 400


def test_filesystem_upload_happy(authed_client, filesystem_root):
    dest = filesystem_root / "uploads"
    files = [
        ("files", ("a.txt", b"alpha", "text/plain")),
        ("files", ("b.txt", b"beta", "text/plain")),
    ]
    response = authed_client.post(
        "/filesystem/upload",
        data={"path": str(dest), "overwrite": "false"},
        files=files,
    )
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    body = response.json()
    assert body["status"] == "success"
    assert (dest / "a.txt").read_text(encoding="utf-8") == "alpha"
    assert (dest / "b.txt").read_text(encoding="utf-8") == "beta"


def test_filesystem_upload_rejects_existing_file(authed_client, filesystem_root):
    dest = filesystem_root / "uploads"
    dest.mkdir()
    (dest / "a.txt").write_text("old", encoding="utf-8")

    response = authed_client.post(
        "/filesystem/upload",
        data={"path": str(dest), "overwrite": "false"},
        files=[("files", ("a.txt", b"new", "text/plain"))],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"


def test_filesystem_copy_happy(authed_client, filesystem_root):
    src = filesystem_root / "source.txt"
    src.write_text("copy me", encoding="utf-8")
    dest_dir = filesystem_root / "copied"
    dest_dir.mkdir()

    response = authed_client.post(
        "/filesystem/copy",
        json={"sources": [str(src)], "destination": str(dest_dir), "overwrite": False},
    )
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    body = response.json()
    assert body["status"] == "success"
    assert (dest_dir / "source.txt").read_text(encoding="utf-8") == "copy me"


def test_filesystem_copy_rejects_outside_root(authed_client, filesystem_root):
    src = filesystem_root / "source.txt"
    src.write_text("copy me", encoding="utf-8")
    outside = filesystem_root.parent / "outside"

    response = authed_client.post(
        "/filesystem/copy",
        json={"sources": [str(src)], "destination": str(outside), "overwrite": False},
    )
    assert response.status_code == 400


def test_filesystem_copy_rejects_symlink_destination(authed_client, filesystem_root):
    src = filesystem_root / "source.txt"
    src.write_text("copy me", encoding="utf-8")
    dest_real = filesystem_root / "dest"
    dest_real.mkdir()
    dest_link = filesystem_root / "dest_link"
    try:
        dest_link.symlink_to(dest_real, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported on this platform")

    response = authed_client.post(
        "/filesystem/copy",
        json={"sources": [str(src)], "destination": str(dest_link), "overwrite": False},
    )
    assert response.status_code == 400


def test_filesystem_copy_requires_directory_for_multiple_sources(authed_client, filesystem_root):
    first = filesystem_root / "one.txt"
    second = filesystem_root / "two.txt"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    dest = filesystem_root / "target.txt"

    response = authed_client.post(
        "/filesystem/copy",
        json={"sources": [str(first), str(second)], "destination": str(dest), "overwrite": False},
    )
    assert response.status_code == 400


def test_filesystem_move_happy(authed_client, filesystem_root):
    src = filesystem_root / "move.txt"
    src.write_text("move me", encoding="utf-8")
    dest_dir = filesystem_root / "moved"
    dest_dir.mkdir()

    response = authed_client.post(
        "/filesystem/move",
        json={"sources": [str(src)], "destination": str(dest_dir), "overwrite": False},
    )
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    body = response.json()
    assert body["status"] == "success"
    assert not src.exists()
    assert (dest_dir / "move.txt").read_text(encoding="utf-8") == "move me"


def test_filesystem_move_requires_directory_for_multiple_sources(authed_client, filesystem_root):
    first = filesystem_root / "one.txt"
    second = filesystem_root / "two.txt"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    dest = filesystem_root / "target.txt"

    response = authed_client.post(
        "/filesystem/move",
        json={"sources": [str(first), str(second)], "destination": str(dest), "overwrite": False},
    )
    assert response.status_code == 400


def test_filesystem_move_rejects_symlink_destination(authed_client, filesystem_root):
    src = filesystem_root / "source.txt"
    src.write_text("move me", encoding="utf-8")
    dest_real = filesystem_root / "dest"
    dest_real.mkdir()
    dest_link = filesystem_root / "dest_link"
    try:
        dest_link.symlink_to(dest_real, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported on this platform")

    response = authed_client.post(
        "/filesystem/move",
        json={"sources": [str(src)], "destination": str(dest_link), "overwrite": False},
    )
    assert response.status_code == 400


def test_filesystem_delete_happy(authed_client, filesystem_root):
    target = filesystem_root / "trash.txt"
    target.write_text("delete me", encoding="utf-8")

    response = authed_client.request(
        "DELETE",
        "/filesystem",
        json={"paths": [str(target)], "recursive": False},
    )
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    body = response.json()
    assert body["status"] == "success"
    assert not target.exists()


def test_filesystem_delete_rejects_directory_without_recursive(authed_client, filesystem_root):
    folder = filesystem_root / "folder"
    folder.mkdir()
    (folder / "nested.txt").write_text("nested", encoding="utf-8")

    response = authed_client.request(
        "DELETE",
        "/filesystem",
        json={"paths": [str(folder)], "recursive": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert folder.exists()


def test_filesystem_download_happy(authed_client, filesystem_root):
    target = filesystem_root / "download.txt"
    target.write_text("download me", encoding="utf-8")

    response = authed_client.get("/filesystem/download", params={"path": str(target)})
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    assert response.content == b"download me"


def test_filesystem_download_rejects_directory(authed_client, filesystem_root):
    folder = filesystem_root / "dir"
    folder.mkdir()

    response = authed_client.get("/filesystem/download", params={"path": str(folder)})
    assert response.status_code == 400


def test_filesystem_list_rejects_symlink(authed_client, filesystem_root):
    target = filesystem_root / "real"
    target.mkdir()
    link = filesystem_root / "link"
    link.symlink_to(target, target_is_directory=True)

    response = authed_client.get("/filesystem/list", params={"path": str(link)})
    assert response.status_code == 400


def test_filesystem_copy_rejects_symlink_source(authed_client, filesystem_root):
    target = filesystem_root / "real.txt"
    target.write_text("real", encoding="utf-8")
    link = filesystem_root / "link.txt"
    link.symlink_to(target)
    dest = filesystem_root / "dest"
    dest.mkdir()

    response = authed_client.post(
        "/filesystem/copy",
        json={"sources": [str(link)], "destination": str(dest), "overwrite": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"


def test_filesystem_move_rejects_symlink_source(authed_client, filesystem_root):
    target = filesystem_root / "real.txt"
    target.write_text("real", encoding="utf-8")
    link = filesystem_root / "link.txt"
    link.symlink_to(target)
    dest = filesystem_root / "dest"
    dest.mkdir()

    response = authed_client.post(
        "/filesystem/move",
        json={"sources": [str(link)], "destination": str(dest), "overwrite": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert link.exists()


def test_filesystem_download_rejects_symlink(authed_client, filesystem_root):
    target = filesystem_root / "real.txt"
    target.write_text("real", encoding="utf-8")
    link = filesystem_root / "link.txt"
    link.symlink_to(target)

    response = authed_client.get("/filesystem/download", params={"path": str(link)})
    assert response.status_code == 400


def test_filesystem_delete_symlink_happy(authed_client, filesystem_root):
    target = filesystem_root / "real.txt"
    target.write_text("real", encoding="utf-8")
    link = filesystem_root / "link.txt"
    link.symlink_to(target)

    response = authed_client.request(
        "DELETE",
        "/filesystem",
        json={"paths": [str(link)], "recursive": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert not link.exists()
    assert target.exists()


def test_filesystem_delete_broken_symlink_happy(authed_client, filesystem_root):
    target = filesystem_root / "missing.txt"
    link = filesystem_root / "broken.txt"
    link.symlink_to(target)

    response = authed_client.request(
        "DELETE",
        "/filesystem",
        json={"paths": [str(link)], "recursive": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert not link.exists()


def test_filesystem_upload_rejects_invalid_filename(authed_client, filesystem_root):
    dest = filesystem_root / "uploads"
    dest.mkdir()

    response = authed_client.post(
        "/filesystem/upload",
        data={"path": str(dest), "overwrite": "false"},
        files=[("files", ("../bad.txt", b"bad", "text/plain"))],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"


def test_filesystem_upload_rejects_path_when_destination_is_file(authed_client, filesystem_root):
    dest = filesystem_root / "dest.txt"
    dest.write_text("not a dir", encoding="utf-8")

    response = authed_client.post(
        "/filesystem/upload",
        data={"path": str(dest), "overwrite": "false"},
        files=[("files", ("a.txt", b"alpha", "text/plain"))],
    )
    assert response.status_code == 400


def test_filesystem_upload_rejects_path_traversal(authed_client, filesystem_root):
    outside = filesystem_root / ".."
    response = authed_client.post(
        "/filesystem/upload",
        data={"path": str(outside), "overwrite": "false"},
        files=[("files", ("a.txt", b"alpha", "text/plain"))],
    )
    assert response.status_code == 400


def test_filesystem_upload_rejects_symlink_destination(authed_client, filesystem_root):
    target = filesystem_root / "real_uploads"
    target.mkdir()
    link = filesystem_root / "link_uploads"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported on this platform")

    response = authed_client.post(
        "/filesystem/upload",
        data={"path": str(link), "overwrite": "false"},
        files=[("files", ("a.txt", b"alpha", "text/plain"))],
    )
    assert response.status_code == 400


def test_filesystem_copy_overwrite_file(authed_client, filesystem_root):
    src = filesystem_root / "source.txt"
    src.write_text("new", encoding="utf-8")
    dest = filesystem_root / "target.txt"
    dest.write_text("old", encoding="utf-8")

    response = authed_client.post(
        "/filesystem/copy",
        json={"sources": [str(src)], "destination": str(dest), "overwrite": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert dest.read_text(encoding="utf-8") == "new"


def test_filesystem_move_overwrite_file(authed_client, filesystem_root):
    src = filesystem_root / "source.txt"
    src.write_text("new", encoding="utf-8")
    dest = filesystem_root / "target.txt"
    dest.write_text("old", encoding="utf-8")

    response = authed_client.post(
        "/filesystem/move",
        json={"sources": [str(src)], "destination": str(dest), "overwrite": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert dest.read_text(encoding="utf-8") == "new"
    assert not src.exists()


def test_filesystem_delete_nonexistent_reports_error(authed_client, filesystem_root):
    missing = filesystem_root / "missing.txt"
    response = authed_client.request(
        "DELETE",
        "/filesystem",
        json={"paths": [str(missing)], "recursive": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"


def test_filesystem_download_rejects_outside_root(authed_client, filesystem_root):
    outside = filesystem_root.parent / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    response = authed_client.get("/filesystem/download", params={"path": str(outside)})
    assert response.status_code == 400


def test_filesystem_folder_happy(authed_client, filesystem_root):
    folder = filesystem_root / "new_dir"
    response = authed_client.post(
        "/filesystem/folder",
        json={"path": str(folder), "parents": False, "exist_ok": False},
    )
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    body = response.json()
    assert body["status"] == "success"
    assert folder.is_dir()


def test_filesystem_folder_exist_ok(authed_client, filesystem_root):
    folder = filesystem_root / "existing"
    folder.mkdir()
    response = authed_client.post(
        "/filesystem/folder",
        json={"path": str(folder), "parents": False, "exist_ok": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"


def test_filesystem_folder_rejects_when_file_exists(authed_client, filesystem_root):
    target = filesystem_root / "occupied"
    target.write_text("nope", encoding="utf-8")
    response = authed_client.post(
        "/filesystem/folder",
        json={"path": str(target), "parents": False, "exist_ok": False},
    )
    assert response.status_code == 409


@pytest.fixture
def filesystem_allowlist(monkeypatch, tmp_path):
    import backend.nunet_api.routers.filesystem as fs_router

    root = tmp_path / "home"
    allowed_appliance = root / "nunet" / "appliance"
    allowed_ensembles = root / "ensembles"
    allowed_contracts = root / "contracts"
    disallowed = root / "other"
    disallowed_hidden = root / ".secrets"

    allowed_appliance.mkdir(parents=True)
    allowed_ensembles.mkdir(parents=True)
    allowed_contracts.mkdir(parents=True)
    disallowed.mkdir(parents=True)
    disallowed_hidden.mkdir(parents=True)
    (root / "nunet" / "other").mkdir(parents=True)

    root_resolved = root.resolve()
    nunet_resolved = (root / "nunet").resolve()
    allowed_roots = [allowed_appliance.resolve(), allowed_ensembles.resolve(), allowed_contracts.resolve()]

    monkeypatch.setattr(fs_router, "ROOT_DIR", root_resolved)
    monkeypatch.setattr(fs_router, "ALLOWED_ROOTS", allowed_roots)
    monkeypatch.setattr(
        fs_router,
        "LISTABLE_DIRS",
        {root_resolved, nunet_resolved, *allowed_roots},
    )

    return {
        "root": root,
        "allowed_appliance": allowed_appliance,
        "allowed_ensembles": allowed_ensembles,
        "allowed_contracts": allowed_contracts,
        "disallowed": disallowed,
    }


def test_filesystem_list_filters_root_to_allowlist(authed_client, filesystem_allowlist):
    root = filesystem_allowlist["root"]
    response = authed_client.get("/filesystem/list", params={"path": str(root)})
    assert response.status_code == 200
    items = response.json()["items"]
    names = {item["name"] for item in items}
    assert {"contracts", "ensembles", "nunet"} <= names
    assert "other" not in names
    assert ".secrets" not in names


def test_filesystem_list_filters_bridge_dir(authed_client, filesystem_allowlist):
    bridge = filesystem_allowlist["root"] / "nunet"
    response = authed_client.get("/filesystem/list", params={"path": str(bridge)})
    assert response.status_code == 200
    items = response.json()["items"]
    names = {item["name"] for item in items}
    assert names == {"appliance"}


def test_filesystem_list_rejects_disallowed_dir(authed_client, filesystem_allowlist):
    disallowed = filesystem_allowlist["disallowed"]
    response = authed_client.get("/filesystem/list", params={"path": str(disallowed)})
    assert response.status_code == 403


def test_filesystem_download_rejects_disallowed_path(authed_client, filesystem_allowlist):
    disallowed = filesystem_allowlist["disallowed"]
    target = disallowed / "secret.txt"
    target.write_text("nope", encoding="utf-8")
    response = authed_client.get("/filesystem/download", params={"path": str(target)})
    assert response.status_code == 403


def test_filesystem_upload_rejects_disallowed_destination(authed_client, filesystem_allowlist):
    disallowed = filesystem_allowlist["disallowed"]
    response = authed_client.post(
        "/filesystem/upload",
        data={"path": str(disallowed), "overwrite": "false"},
        files=[("files", ("a.txt", b"alpha", "text/plain"))],
    )
    assert response.status_code == 403


def test_filesystem_folder_rejects_disallowed_path(authed_client, filesystem_allowlist):
    disallowed = filesystem_allowlist["disallowed"] / "new_dir"
    response = authed_client.post(
        "/filesystem/folder",
        json={"path": str(disallowed), "parents": True, "exist_ok": False},
    )
    assert response.status_code == 403


def test_filesystem_copy_rejects_disallowed_destination(authed_client, filesystem_allowlist):
    allowed_contracts = filesystem_allowlist["allowed_contracts"]
    source = allowed_contracts / "source.txt"
    source.write_text("ok", encoding="utf-8")
    disallowed = filesystem_allowlist["disallowed"] / "copy_here"

    response = authed_client.post(
        "/filesystem/copy",
        json={"sources": [str(source)], "destination": str(disallowed), "overwrite": False},
    )
    assert response.status_code == 403


def test_filesystem_move_rejects_disallowed_destination(authed_client, filesystem_allowlist):
    allowed_contracts = filesystem_allowlist["allowed_contracts"]
    source = allowed_contracts / "source.txt"
    source.write_text("ok", encoding="utf-8")
    disallowed = filesystem_allowlist["disallowed"] / "move_here"

    response = authed_client.post(
        "/filesystem/move",
        json={"sources": [str(source)], "destination": str(disallowed), "overwrite": False},
    )
    assert response.status_code == 403


def test_filesystem_delete_disallowed_path_reports_error(authed_client, filesystem_allowlist):
    disallowed = filesystem_allowlist["disallowed"] / "secret.txt"
    disallowed.write_text("nope", encoding="utf-8")

    response = authed_client.request(
        "DELETE",
        "/filesystem",
        json={"paths": [str(disallowed)], "recursive": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["items"][0]["status"] == "error"
    assert body["items"][0]["message"] == "Path is not allowed"
