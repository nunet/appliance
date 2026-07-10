import json
import subprocess

from backend.modules import dms_manager as dms_manager_module


def _cp(returncode: int, payload: dict | None = None, stderr: str = "") -> subprocess.CompletedProcess:
    stdout = json.dumps(payload or {})
    return subprocess.CompletedProcess(args=["nunet"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_get_payment_quote_appends_dest_flag(monkeypatch):
    calls: list[list[str]] = []

    def fake_run_dms_command_with_passphrase(argv, **kwargs):
        calls.append(list(argv))
        return _cp(0, {"quote_id": "quote-1", "expires_at": "2030-01-01T00:00:00Z"})

    monkeypatch.setattr(
        dms_manager_module,
        "run_dms_command_with_passphrase",
        fake_run_dms_command_with_passphrase,
    )

    mgr = dms_manager_module.DMSManager()
    result = mgr.get_payment_quote("unique-1", "did:key:z6MkDestExample")

    assert result["status"] == "success"
    assert len(calls) == 1
    assert "--dest" in calls[0]
    assert "did:key:z6MkDestExample" in calls[0]


def test_validate_payment_quote_appends_dest_flag(monkeypatch):
    calls: list[list[str]] = []

    def fake_run_dms_command_with_passphrase(argv, **kwargs):
        calls.append(list(argv))
        return _cp(0, {"valid": True})

    monkeypatch.setattr(
        dms_manager_module,
        "run_dms_command_with_passphrase",
        fake_run_dms_command_with_passphrase,
    )

    mgr = dms_manager_module.DMSManager()
    result = mgr.validate_payment_quote("quote-1", "did:key:z6MkDestExample")

    assert result["status"] == "success"
    assert len(calls) == 1
    assert "--dest" in calls[0]
    assert "did:key:z6MkDestExample" in calls[0]


def test_confirm_transaction_retries_without_quote_id_on_terminal_quote_error(monkeypatch):
    calls: list[list[str]] = []
    responses = [
        _cp(
            0,
            {
                "error": "quote validation failed: quote already used: quote-123",
            },
        ),
        _cp(0, {"error": ""}),
    ]

    def fake_run_dms_command_with_passphrase(argv, **kwargs):
        calls.append(list(argv))
        return responses.pop(0)

    monkeypatch.setattr(
        dms_manager_module,
        "run_dms_command_with_passphrase",
        fake_run_dms_command_with_passphrase,
    )
    monkeypatch.setattr(dms_manager_module.time, "sleep", lambda *_: None)

    mgr = dms_manager_module.DMSManager()
    result = mgr.confirm_transaction(
        unique_id="unique-1",
        tx_hash="0x" + "1" * 64,
        blockchain="ETHEREUM",
        quote_id="quote-123",
    )

    assert result["status"] == "success"
    assert len(calls) == 2
    assert "--quote-id" in calls[0]
    assert "--quote-id" not in calls[1]


def test_confirm_transaction_stops_retrying_on_terminal_quote_error_without_quote_id(monkeypatch):
    calls: list[list[str]] = []

    def fake_run_dms_command_with_passphrase(argv, **kwargs):
        calls.append(list(argv))
        return _cp(0, {"error": "quote validation failed: quote expired"})

    monkeypatch.setattr(
        dms_manager_module,
        "run_dms_command_with_passphrase",
        fake_run_dms_command_with_passphrase,
    )
    monkeypatch.setattr(dms_manager_module.time, "sleep", lambda *_: None)

    mgr = dms_manager_module.DMSManager()
    result = mgr.confirm_transaction(
        unique_id="unique-2",
        tx_hash="0x" + "2" * 64,
        blockchain="ETHEREUM",
    )

    assert result["status"] == "error"
    assert "quote expired" in result["message"].lower()
    assert len(calls) == 1


def test_cancel_payment_quote_treats_already_used_as_success(monkeypatch):
    calls: list[list[str]] = []

    def fake_run_dms_command_with_passphrase(argv, **kwargs):
        calls.append(list(argv))
        return _cp(0, {"error": "quote already used"})

    monkeypatch.setattr(
        dms_manager_module,
        "run_dms_command_with_passphrase",
        fake_run_dms_command_with_passphrase,
    )

    mgr = dms_manager_module.DMSManager()
    result = mgr.cancel_payment_quote("quote-123", "did:key:z6MkDestExample")

    assert result["status"] == "success"
    assert len(calls) == 1
    assert "--dest" in calls[0]
    assert "did:key:z6MkDestExample" in calls[0]


def test_cancel_payment_quote_treats_not_found_as_success_when_command_fails(monkeypatch):
    calls: list[list[str]] = []

    def fake_run_dms_command_with_passphrase(argv, **kwargs):
        calls.append(list(argv))
        return _cp(1, {"error": "quote not found"})

    monkeypatch.setattr(
        dms_manager_module,
        "run_dms_command_with_passphrase",
        fake_run_dms_command_with_passphrase,
    )

    mgr = dms_manager_module.DMSManager()
    result = mgr.cancel_payment_quote("quote-123", "did:key:z6MkDestExample")

    assert result["status"] == "success"
    assert len(calls) == 1
    assert "--dest" in calls[0]
    assert "did:key:z6MkDestExample" in calls[0]


def test_list_transactions_uses_hyphenated_filter_cli_flags(monkeypatch):
    calls: list[list[str]] = []

    def fake_run_dms_command_with_passphrase(argv, **kwargs):
        calls.append(list(argv))
        return _cp(0, {"transactions": [], "pagination": {"total_count": 0}})

    monkeypatch.setattr(
        dms_manager_module,
        "run_dms_command_with_passphrase",
        fake_run_dms_command_with_passphrase,
    )

    mgr = dms_manager_module.DMSManager()
    result = mgr.list_transactions(
        blockchain="CARDANO",
        limit=10,
        offset=0,
        sort="-created_at",
        unique_id="uid-99",
        deployment_id="fa0dea",
        contract_did="did:key:zContract",
        status=["paid"],
        to_address="addr_to",
        from_address="addr_from",
        tx_hash="0xabc",
    )

    assert result["status"] == "success"
    assert len(calls) == 1
    argv = calls[0]
    assert "--unique-id" in argv
    assert argv[argv.index("--unique-id") + 1] == "uid-99"
    assert "--filter" in argv
    assert argv[argv.index("--filter") + 1] == "deployment_id=fa0dea"
    assert "--tx-hash" in argv
    assert argv[argv.index("--tx-hash") + 1] == "0xabc"
    assert "--unique_id" not in argv
    assert "--deployment_id" not in argv
    assert "--tx_hash" not in argv
