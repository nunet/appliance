import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.nunet_api.routers import payments as payments_router

CARDANO_ADDRESS = (
    "addr_test1qqm9ehanrh5rkukd0jwrl4j4zhnlzhkutwcukxqjdr3yfwydfmfydwq78revg8sx3wf3aj9gwn5kqyg0l2485zrj3mvsktcw4k"
)


def _tx(unique_id: str, to_address: str, amount: str, metadata, *, metadata_key: str = "metadata"):
    payload = {
        "unique_id": unique_id,
        "payment_validator_did": "did:prism:validator",
        "contract_did": "did:prism:contract",
        "to_address": to_address,
        "amount": amount,
        "status": "unpaid",
        "tx_hash": "",
    }
    payload[metadata_key] = metadata
    return payload


def test_norm_tx_keys_supports_metadata_for_all_payment_models():
    samples = [
        (
            "pay-per-time",
            _tx(
                "550e8400-e29b-41d4-a716-446655440000",
                "0x" + "1" * 40,
                "10.500000",
                {
                    "deployment_id": "deployment-123",
                    "total_utilization_sec": 3600.0,
                    "allocation_count": 2,
                    "allocations": [
                        {"allocation_id": "alloc-1"},
                        {"allocation_id": "alloc-2"},
                    ],
                },
            ),
            ("deployment_id", "deployment-123"),
        ),
        (
            "pay-per-resource",
            _tx(
                "550e8400-e29b-41d4-a716-446655440001",
                "0x" + "2" * 40,
                "25.750000",
                json.dumps(
                    {
                        "deployment_id": "deployment-456",
                        "total_utilization_sec": 7200.0,
                        "allocation_count": 1,
                        "allocations": [{"allocation_id": "alloc-3", "resources": {"cpu_cores": 4}}],
                    }
                ),
                metadata_key="Metadata",
            ),
            ("deployment_id", "deployment-456"),
        ),
        (
            "periodic",
            _tx(
                "550e8400-e29b-41d4-a716-446655440002",
                "0x" + "3" * 40,
                "50.000000",
                {
                    "deployment_id": "deployment-789",
                    "total_utilization_sec": 86400.0,
                    "period_start": "2024-01-01T00:00:00Z",
                    "period_end": "2024-01-31T23:59:59Z",
                    "periods_invoiced": 1,
                    "allocation_count": 3,
                },
            ),
            ("periods_invoiced", 1),
        ),
        (
            "pay-per-deployment",
            _tx(
                "550e8400-e29b-41d4-a716-446655440003",
                "0x" + "4" * 40,
                "15.000000",
                {"deployment_count": 3},
            ),
            ("deployment_count", 3),
        ),
        (
            "pay-per-allocation",
            _tx(
                "550e8400-e29b-41d4-a716-446655440004",
                "0x" + "5" * 40,
                "30.000000",
                {"allocation_count": 5},
            ),
            ("allocation_count", 5),
        ),
        (
            "fixed-rental",
            _tx(
                "550e8400-e29b-41d4-a716-446655440005",
                "0x" + "6" * 40,
                "100.000000",
                {
                    "periods_invoiced": 1,
                    "period_start": "2024-01-01T00:00:00Z",
                    "period_end": "2024-01-31T23:59:59Z",
                    "last_invoice_at": "2023-12-31T23:59:59Z",
                },
            ),
            ("last_invoice_at", "2023-12-31T23:59:59Z"),
        ),
    ]

    for _, raw, (field, expected) in samples:
        normalized = payments_router._norm_tx_keys(raw)
        assert normalized["metadata"] is not None
        assert normalized["metadata"][field] == expected


def test_list_payments_returns_metadata_for_all_payment_models():
    txs = [
        _tx(
            "550e8400-e29b-41d4-a716-446655440000",
            "0x" + "1" * 40,
            "10.500000",
            {"deployment_id": "deployment-123", "allocation_count": 2, "total_utilization_sec": 3600.0},
        ),
        _tx(
            "550e8400-e29b-41d4-a716-446655440001",
            "0x" + "2" * 40,
            "25.750000",
            {"deployment_id": "deployment-456", "allocation_count": 1, "total_utilization_sec": 7200.0},
        ),
        _tx(
            "550e8400-e29b-41d4-a716-446655440002",
            "0x" + "3" * 40,
            "50.000000",
            {
                "deployment_id": "deployment-789",
                "period_start": "2024-01-01T00:00:00Z",
                "period_end": "2024-01-31T23:59:59Z",
                "periods_invoiced": 1,
            },
        ),
        _tx(
            "550e8400-e29b-41d4-a716-446655440003",
            "0x" + "4" * 40,
            "15.000000",
            {"deployment_count": 3},
        ),
        _tx(
            "550e8400-e29b-41d4-a716-446655440004",
            "0x" + "5" * 40,
            "30.000000",
            {"allocation_count": 5},
        ),
        _tx(
            "550e8400-e29b-41d4-a716-446655440005",
            "0x" + "6" * 40,
            "100.000000",
            {
                "periods_invoiced": 1,
                "period_start": "2024-01-01T00:00:00Z",
                "period_end": "2024-01-31T23:59:59Z",
                "last_invoice_at": "2023-12-31T23:59:59Z",
            },
        ),
    ]

    class StubPaymentsManager:
        def list_transactions(self, blockchain=None):
            return {"status": "success", "transactions": txs}

    app = FastAPI()
    app.include_router(payments_router.router, prefix="/payments")
    app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()

    with TestClient(app) as client:
        response = client.get("/payments/list_payments")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 6
    assert body["ignored_count"] == 0

    by_id = {item["unique_id"]: item for item in body["items"]}
    assert by_id["550e8400-e29b-41d4-a716-446655440000"]["metadata"]["deployment_id"] == "deployment-123"
    assert by_id["550e8400-e29b-41d4-a716-446655440001"]["metadata"]["allocation_count"] == 1
    assert by_id["550e8400-e29b-41d4-a716-446655440002"]["metadata"]["periods_invoiced"] == 1
    assert by_id["550e8400-e29b-41d4-a716-446655440003"]["metadata"]["deployment_count"] == 3
    assert by_id["550e8400-e29b-41d4-a716-446655440004"]["metadata"]["allocation_count"] == 5
    assert by_id["550e8400-e29b-41d4-a716-446655440005"]["metadata"]["last_invoice_at"] == "2023-12-31T23:59:59Z"


def test_list_payments_keeps_transaction_when_metadata_is_missing():
    txs = [
        {
            "unique_id": "550e8400-e29b-41d4-a716-446655440006",
            "payment_validator_did": "did:prism:validator",
            "contract_did": "did:prism:contract",
            "to_address": "0x" + "7" * 40,
            "amount": "11.000000",
            "status": "unpaid",
            "tx_hash": "",
        }
    ]

    class StubPaymentsManager:
        def list_transactions(self, blockchain=None):
            return {"status": "success", "transactions": txs}

    app = FastAPI()
    app.include_router(payments_router.router, prefix="/payments")
    app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()

    with TestClient(app) as client:
        response = client.get("/payments/list_payments")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["ignored_count"] == 0
    assert body["items"][0]["metadata"] is None


def test_list_payments_coerces_invalid_metadata_to_none():
    txs = [
        _tx(
            "550e8400-e29b-41d4-a716-446655440007",
            "0x" + "8" * 40,
            "12.000000",
            "not-json",
            metadata_key="Metadata",
        )
    ]

    class StubPaymentsManager:
        def list_transactions(self, blockchain=None):
            return {"status": "success", "transactions": txs}

    app = FastAPI()
    app.include_router(payments_router.router, prefix="/payments")
    app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()

    with TestClient(app) as client:
        response = client.get("/payments/list_payments")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["ignored_count"] == 0
    assert body["items"][0]["metadata"] is None


def test_list_payments_ignores_invalid_transaction_even_when_metadata_present():
    txs = [
        {
            "unique_id": "550e8400-e29b-41d4-a716-446655440008",
            "payment_validator_did": "did:prism:validator",
            "contract_did": "did:prism:contract",
            "to_address": "",
            "amount": "13.000000",
            "status": "unpaid",
            "tx_hash": "",
            "metadata": {"deployment_id": "deployment-invalid"},
        }
    ]

    class StubPaymentsManager:
        def list_transactions(self, blockchain=None):
            return {"status": "success", "transactions": txs}

    app = FastAPI()
    app.include_router(payments_router.router, prefix="/payments")
    app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()

    with TestClient(app) as client:
        response = client.get("/payments/list_payments")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 0
    assert body["ignored_count"] == 1


def test_list_payments_extracts_to_and_from_addresses():
    provider = "0x" + "b" * 40
    requester = "0x" + "c" * 40
    txs = [
        {
            "unique_id": "550e8400-e29b-41d4-a716-446655440010",
            "payment_validator_did": "did:prism:validator",
            "contract_did": "did:prism:contract",
            "to_address": [
                {
                    "blockchain": "ETHEREUM",
                    "provider_addr": provider,
                    "requester_addr": requester,
                }
            ],
            "amount": "1.0",
            "status": "unpaid",
            "tx_hash": "",
            "metadata": {"deployment_id": "dep-addr"},
        }
    ]

    class StubPaymentsManager:
        def list_transactions(self, blockchain=None):
            return {"status": "success", "transactions": txs}

    app = FastAPI()
    app.include_router(payments_router.router, prefix="/payments")
    app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()

    with TestClient(app) as client:
        response = client.get("/payments/list_payments")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["ignored_count"] == 0
    assert body["items"][0]["to_address"] == provider
    assert body["items"][0]["from_address"] == requester


def test_valid_amount_str_accepts_up_to_16_decimals_for_eth_and_cardano():
    assert payments_router._valid_amount_str("1.1234567890123456", 16) is True
    assert payments_router._valid_amount_str("0.0000000000000001", 16) is True
    assert payments_router._valid_amount_str("1.12345678901234567", 16) is False


def test_list_payments_accepts_16_decimal_amounts_and_rejects_17():
    cardano_tx = _tx(
        "550e8400-e29b-41d4-a716-446655441001",
        CARDANO_ADDRESS,
        "2.1234567890123456",
        {"deployment_id": "cardano-16-decimals"},
    )
    cardano_tx["to_address"] = [{"blockchain": "CARDANO", "provider_addr": CARDANO_ADDRESS}]

    txs = [
        _tx(
            "550e8400-e29b-41d4-a716-446655441000",
            "0x" + "9" * 40,
            "1.1234567890123456",
            {"deployment_id": "eth-16-decimals"},
        ),
        cardano_tx,
        _tx(
            "550e8400-e29b-41d4-a716-446655441002",
            "0x" + "a" * 40,
            "3.12345678901234567",
            {"deployment_id": "eth-17-decimals"},
        ),
    ]

    class StubPaymentsManager:
        def list_transactions(self, blockchain=None):
            return {"status": "success", "transactions": txs}

    app = FastAPI()
    app.include_router(payments_router.router, prefix="/payments")
    app.dependency_overrides[payments_router.get_mgr] = lambda: StubPaymentsManager()

    with TestClient(app) as client:
        response = client.get("/payments/list_payments")

    assert response.status_code == 200
    body = response.json()

    # 16-decimal ETH + 16-decimal Cardano pass validation
    assert body["total_count"] == 2
    ids = {item["unique_id"] for item in body["items"]}
    assert "550e8400-e29b-41d4-a716-446655441000" in ids
    assert "550e8400-e29b-41d4-a716-446655441001" in ids

    # 17-decimal ETH fails validation and is ignored
    assert body["ignored_count"] == 1
    ignored_ids = {item["unique_id"] for item in (body.get("ignored") or [])}
    assert "550e8400-e29b-41d4-a716-446655441002" in ignored_ids
