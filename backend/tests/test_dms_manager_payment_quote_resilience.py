import json
import subprocess

from backend.modules import dms_manager as dms_manager_module


def _cp(returncode: int, payload: dict | None = None, stderr: str = "") -> subprocess.CompletedProcess:
    stdout = json.dumps(payload or {})
    return subprocess.CompletedProcess(args=["nunet"], returncode=returncode, stdout=stdout, stderr=stderr)


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
    def fake_run_dms_command_with_passphrase(argv, **kwargs):
        return _cp(0, {"error": "quote already used"})

    monkeypatch.setattr(
        dms_manager_module,
        "run_dms_command_with_passphrase",
        fake_run_dms_command_with_passphrase,
    )

    mgr = dms_manager_module.DMSManager()
    result = mgr.cancel_payment_quote("quote-123")

    assert result["status"] == "success"


def test_cancel_payment_quote_treats_not_found_as_success_when_command_fails(monkeypatch):
    def fake_run_dms_command_with_passphrase(argv, **kwargs):
        return _cp(1, {"error": "quote not found"})

    monkeypatch.setattr(
        dms_manager_module,
        "run_dms_command_with_passphrase",
        fake_run_dms_command_with_passphrase,
    )

    mgr = dms_manager_module.DMSManager()
    result = mgr.cancel_payment_quote("quote-123")

    assert result["status"] == "success"
