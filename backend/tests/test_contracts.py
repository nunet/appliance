import json
import os
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.nunet_api.routers import contracts
from backend.nunet_api.schemas import (
    ContractActionResponse,
    ContractListResponse,
    ContractTemplateDetail,
    ContractTemplateListResponse,
)
from modules import dms_utils
from modules import dms_manager as dms_manager_module
from modules.dms_manager import DMSManager


def test_contract_utils_list_incoming_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: Dict[str, List[str]] = {}

    def fake_run(cmd: List[str], **kwargs: Any) -> SimpleNamespace:
        captured["cmd"] = cmd
        payload = {
            "contracts": [
                {"contract_did": "did:example:123", "current_state": "ACCEPTED"},
            ]
        }
        return SimpleNamespace(stdout=json.dumps(payload), stderr="", returncode=0)

    monkeypatch.setattr(dms_utils, "run_dms_command_with_passphrase", fake_run)

    result = dms_utils.contract_list_incoming()

    assert result["success"] is True
    assert result["data"]["contracts"][0]["contract_did"] == "did:example:123"
    assert captured["cmd"] == [
        "nunet",
        "contracts",
        "--context",
        "dms",
        "list",
        "incoming",
    ]


def test_contract_utils_list_outgoing_uses_contracts_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: Dict[str, List[str]] = {}

    def fake_run(cmd: List[str], **kwargs: Any) -> SimpleNamespace:
        captured["cmd"] = cmd
        payload = {"contracts": []}
        return SimpleNamespace(stdout=json.dumps(payload), stderr="", returncode=0)

    monkeypatch.setattr(dms_utils, "run_dms_command_with_passphrase", fake_run)

    result = dms_utils.contract_list_outgoing()

    assert result["success"] is True
    assert captured["cmd"] == [
        "nunet",
        "contracts",
        "--context",
        "dms",
        "list",
        "outgoing",
    ]


def test_contract_utils_list_incoming_falls_back_when_contracts_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[List[str]] = []

    def fake_run(cmd: List[str], **kwargs: Any) -> SimpleNamespace:
        calls.append(cmd)
        if len(calls) == 1:
            return SimpleNamespace(stdout="", stderr='Error: unknown command "contracts" for "nunet"', returncode=1)
        payload = {"contracts": [{"contract_did": "did:example:fallback", "current_state": "PENDING"}]}
        return SimpleNamespace(stdout=json.dumps(payload), stderr="", returncode=0)

    monkeypatch.setattr(dms_utils, "run_dms_command_with_passphrase", fake_run)

    result = dms_utils.contract_list_incoming()

    assert result["success"] is True
    assert result["endpoint"] == "/dms/tokenomics/contract/list_incoming"
    assert calls[1][2] == "cmd"  # actor fallback


def test_contract_utils_list_outgoing_reports_missing_contracts_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: List[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(stdout="", stderr='Error: unknown command "contracts" for "nunet"', returncode=1)

    monkeypatch.setattr(dms_utils, "run_dms_command_with_passphrase", fake_run)

    result = dms_utils.contract_list_outgoing()

    assert result["success"] is False
    assert result["error_code"] == "contracts_cli_missing"
    assert "upgrade" in result["error"]


def test_contract_utils_create_reports_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: List[str], **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(stdout="", stderr="boom", returncode=1)

    monkeypatch.setattr(dms_utils, "run_dms_command_with_passphrase", fake_run)

    result = dms_utils.contract_create("/tmp/contract.json")

    assert result["success"] is False
    assert "error" in result
    assert result["returncode"] == 1


def _make_test_app(manager: Any) -> TestClient:
    app = FastAPI()
    app.include_router(contracts.router, prefix="/contracts")
    app.dependency_overrides[contracts.get_mgr] = lambda: manager
    return TestClient(app)


class _ListStubManager:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload

    def list_incoming_contracts(self) -> Dict[str, Any]:
        return self.payload

    def list_outgoing_contracts(self) -> Dict[str, Any]:
        return self.payload


class _ListContractsStubManager:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload
        self.last_view: Optional[str] = None

    def list_contracts(self, view: str = "all", *, timeout: int = 30) -> Dict[str, Any]:
        self.last_view = view
        return self.payload


def test_contracts_router_incoming_success() -> None:
    raw_contract = {
        "ContractDID": "did:key:abc123",
        "current_state": "accepted",
        "contract_participants": {
            "provider": {"uri": "did:key:provider"},
            "requestor": {"uri": "did:key:requestor"},
        },
    }
    payload = {
        "status": "success",
        "contracts": [raw_contract],
        "raw": {"contracts": [raw_contract]},
        "stdout": "ok",
        "stderr": "",
        "returncode": 0,
        "command": "nunet actor cmd ...",
    }
    client = _make_test_app(_ListStubManager(payload))

    response = client.get("/contracts/incoming")
    assert response.status_code == 200

    data = ContractListResponse.model_validate(response.json())
    assert data.contracts[0].contract_did == "did:key:abc123"
    assert data.contracts[0].current_state.name == "ACCEPTED"


def test_contracts_router_outgoing_success() -> None:
    payload = {
        "status": "success",
        "contracts": [
            {"contract_did": "did:key:outgoing1", "current_state": "DRAFT"},
        ],
        "raw": {"contracts": [{"contract_did": "did:key:outgoing1", "current_state": "DRAFT"}]},
        "stdout": "",
        "stderr": "",
        "returncode": 0,
        "command": "nunet contracts ...",
    }
    client = _make_test_app(_ListStubManager(payload))

    response = client.get("/contracts/outgoing")
    assert response.status_code == 200

    data = ContractListResponse.model_validate(response.json())
    assert data.contracts[0].contract_did == "did:key:outgoing1"
    assert data.contracts[0].current_state.name == "DRAFT"


def test_contracts_router_list_endpoint_filters() -> None:
    raw_contract = {
        "contract_did": "did:key:filter1",
        "current_state": "signed",
    }
    payload = {
        "status": "success",
        "contracts": [raw_contract],
        "raw": {"contracts": [raw_contract, {"contract_did": "did:key:other"}]},
        "filter": "active",
        "total_count": 2,
        "filtered_count": 1,
        "stdout": "",
        "stderr": "",
        "returncode": 0,
        "command": "nunet actor cmd ...",
    }
    manager = _ListContractsStubManager(payload)
    client = _make_test_app(manager)

    response = client.get("/contracts/?view=active")
    assert response.status_code == 200
    assert manager.last_view == "active"

    data = ContractListResponse.model_validate(response.json())
    assert data.filter == "active"
    assert data.filtered_count == 1
    assert data.total_count == 2


def test_contracts_router_list_endpoint_supports_outgoing() -> None:
    payload = {
        "status": "success",
        "contracts": [{"contract_did": "did:key:out1", "current_state": "draft"}],
        "raw": {"contracts": [{"contract_did": "did:key:out1"}]},
        "filter": "outgoing",
        "total_count": 1,
        "filtered_count": 1,
        "stdout": "",
        "stderr": "",
        "returncode": 0,
        "command": "nunet contracts ...",
    }
    manager = _ListContractsStubManager(payload)
    client = _make_test_app(manager)

    response = client.get("/contracts/?view=outgoing")
    assert response.status_code == 200
    assert manager.last_view == "outgoing"

    data = ContractListResponse.model_validate(response.json())
    assert data.filter == "outgoing"
    assert len(data.contracts) == 1
def test_dms_manager_list_signed_filters_states(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "success": True,
        "endpoint": "contracts list incoming",
        "argv": ["nunet", "contracts", "--context", "dms", "list", "incoming"],
        "returncode": 0,
        "stdout": "",
        "stderr": "",
        "data": {
            "contracts": [
                {"contract_did": "did:key:a1", "current_state": "accepted"},
                {"contract_did": "did:key:signed", "current_state": "signed"},
                {"contract_did": "did:key:terminated", "current_state": "TERMINATED"},
            ]
        },
    }

    monkeypatch.setattr(dms_manager_module, "contract_list_incoming", lambda timeout=30: payload)

    mgr = DMSManager()
    result = mgr.list_signed_contracts()

    assert result["status"] == "success"
    contracts = result["contracts"]
    assert len(contracts) == 2
    assert {c["contract_did"] for c in contracts} == {"did:key:a1", "did:key:signed"}


def test_dms_manager_list_all_handles_missing_outgoing(monkeypatch: pytest.MonkeyPatch) -> None:
    incoming_payload = {
        "success": True,
        "endpoint": "contracts list incoming",
        "argv": [],
        "returncode": 0,
        "stdout": "",
        "stderr": "",
        "data": {"contracts": [{"contract_did": "did:key:only", "current_state": "draft"}]},
    }
    outgoing_payload = {
        "success": False,
        "endpoint": "contracts list outgoing",
        "argv": [],
        "returncode": 1,
        "stdout": "",
        "stderr": "",
        "error": "Outgoing contracts require a newer nunet CLI.",
        "error_code": "contracts_cli_missing",
    }

    monkeypatch.setattr(dms_manager_module, "contract_list_incoming", lambda timeout=30: incoming_payload)
    monkeypatch.setattr(dms_manager_module, "contract_list_outgoing", lambda timeout=30: outgoing_payload)

    mgr = DMSManager()
    result = mgr.list_contracts("all")

    assert result["status"] == "success"
    assert len(result["contracts"]) == 1
    assert "Outgoing contracts require" in result["message"]


class _SignedStubManager:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload

    def list_signed_contracts(self) -> Dict[str, Any]:
        return self.payload


def test_contracts_router_signed_success() -> None:
    payload = {
        "status": "success",
        "contracts": [
            {"contract_did": "did:key:signed", "current_state": "SIGNED"},
        ],
        "raw": {"contracts": [{"contract_did": "did:key:signed", "current_state": "SIGNED"}]},
        "stdout": "",
        "stderr": "",
        "returncode": 0,
        "command": "nunet actor cmd ...",
    }
    client = _make_test_app(_SignedStubManager(payload))

    response = client.get("/contracts/signed")
    assert response.status_code == 200
    data = ContractListResponse.model_validate(response.json())
    assert len(data.contracts) == 1
    assert data.contracts[0].current_state.name == "SIGNED"


class _CreateStubManager:
    def __init__(self) -> None:
        self.last_path: Optional[str] = None
        self.last_extra: Optional[List[str]] = None
        self.last_template_id: Optional[str] = None

    def create_contract(
        self,
        contract_file: str,
        *,
        extra_args: Optional[List[str]],
        template_id: Optional[str] = None,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        self.last_path = contract_file
        self.last_extra = extra_args
        self.last_template_id = template_id
        with open(contract_file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
            assert payload["contract_terms"] == "Standard"
        return {
            "status": "success",
            "message": "submitted",
            "contract_file": contract_file,
            "template_id": template_id,
            "stdout": "",
            "stderr": "",
            "returncode": 0,
            "command": "nunet actor cmd",
        }


def test_contracts_router_create_writes_contract_file_and_cleans_up(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _CreateStubManager()
    client = _make_test_app(manager)

    payload = {
        "contract": {
            "contract_terms": "Standard",
            "solution_enabler_did": {"uri": "did:key:se"},
            "payment_validator_did": {"uri": "did:key:pv"},
            "contract_participants": {
                "provider": {"uri": "did:key:provider"},
                "requestor": {"uri": "did:key:requestor"},
            },
        },
        "extra_args": ["--verbose"],
        "template_id": "local:default",
    }

    def fake_template_lookup(template_id: str):
        assert template_id == "local:default"
        return {
            "template_id": template_id,
            "display_name": "Default Contract",
            "source": "local",
            "origin": "backend/contracts/default.json",
            "contract": {"contract_terms": "Standard"},
        }

    monkeypatch.setattr(contracts, "fetch_contract_template", fake_template_lookup)

    response = client.post("/contracts/create", json=payload)
    assert response.status_code == 200

    data = ContractActionResponse.model_validate(response.json())
    assert manager.last_extra == ["--verbose"]
    assert manager.last_template_id == "local:default"
    assert data.template_id == "local:default"
    assert data.source == "local"
    assert manager.last_path is not None
    assert not os.path.exists(manager.last_path)


class _ApproveStubManager:
    def approve_contract(
        self,
        contract_did: str,
        *,
        extra_args: Optional[List[str]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        return {
            "status": "error",
            "message": "approval failed",
            "stdout": "",
            "stderr": "boom",
            "returncode": 1,
            "command": "nunet actor cmd",
        }


class _TerminateStubManager:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload
        self.last_did: Optional[str] = None
        self.last_host: Optional[str] = None
        self.last_extra: Optional[List[str]] = None

    def terminate_contract(
        self,
        contract_did: str,
        *,
        contract_host_did: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        self.last_did = contract_did
        self.last_host = contract_host_did
        self.last_extra = list(extra_args) if extra_args is not None else None
        return self.payload


def test_contracts_router_approve_error_response() -> None:
    client = _make_test_app(_ApproveStubManager())

    response = client.post("/contracts/approve", json={"contract_did": "did:key:oops"})
    assert response.status_code == 502

    data = response.json()
    assert data["detail"]["message"] == "approval failed"
    assert data["detail"]["returncode"] == 1


def test_contracts_router_terminate_success() -> None:
    payload = {
        "status": "success",
        "message": "termination started",
        "contract_did": "did:key:terminate",
        "contract_host_did": "did:key:host",
        "stdout": "",
        "stderr": "",
        "returncode": 0,
        "command": "nunet actor cmd",
    }
    manager = _TerminateStubManager(payload)
    client = _make_test_app(manager)

    body = {
        "contract_did": "did:key:terminate",
        "contract_host_did": "did:key:host",
        "extra_args": ["--force"],
    }
    response = client.post("/contracts/terminate", json=body)
    assert response.status_code == 200

    data = ContractActionResponse.model_validate(response.json())
    assert data.contract_did == "did:key:terminate"
    assert data.contract_host_did == "did:key:host"
    assert manager.last_did == "did:key:terminate"
    assert manager.last_host == "did:key:host"
    assert manager.last_extra == ["--force"]


def test_contracts_router_terminate_error_response() -> None:
    payload = {
        "status": "error",
        "message": "termination failed",
        "stdout": "",
        "stderr": "boom",
        "returncode": 2,
        "command": "nunet actor cmd",
    }
    manager = _TerminateStubManager(payload)
    client = _make_test_app(manager)

    response = client.post("/contracts/terminate", json={"contract_did": "did:key:nope"})
    assert response.status_code == 502

    detail = response.json()["detail"]
    assert detail["message"] == "termination failed"
    assert detail["returncode"] == 2


def test_contract_template_list_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_test_app(_ListStubManager({"status": "success", "contracts": [], "raw": {"contracts": []}}))

    monkeypatch.setattr(
        contracts,
        "list_contract_templates",
        lambda org_did=None: [
            {
                "template_id": "local:default",
                "display_name": "Default Contract",
                "source": "local",
                "origin": "backend/contracts/default.json",
                "tags": ["default"],
                "categories": [],
            }
        ],
    )

    response = client.get("/contracts/templates")
    assert response.status_code == 200
    data = ContractTemplateListResponse.model_validate(response.json())
    assert len(data.templates) == 1
    assert data.templates[0].template_id == "local:default"
    assert data.templates[0].source == "local"


def test_contract_template_detail_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_test_app(_ListStubManager({"status": "success", "contracts": [], "raw": {"contracts": []}}))

    monkeypatch.setattr(
        contracts,
        "fetch_contract_template",
        lambda template_id, org_did=None: {
            "template_id": template_id,
            "display_name": "Default Contract",
            "source": "local",
            "origin": "backend/contracts/default.json",
            "contract": {"contract_terms": "Standard"},
        },
    )

    response = client.get("/contracts/templates/local:default")
    assert response.status_code == 200
    detail = ContractTemplateDetail.model_validate(response.json())
    assert detail.template_id == "local:default"
    assert detail.contract["contract_terms"] == "Standard"
