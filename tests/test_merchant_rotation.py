"""Public-recipient rotation must also change the fleet verifier allowlist."""
import base64
import hashlib
import json
import time

import httpx
import pytest
from src import public_url, config
from src import api, payment_execution, x402_middleware as payment
from src.tool_executor import fulfill_tool
from tests import test_payment_contract_regressions as fixtures


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_STATE_DB", str(tmp_path / "rotation.sqlite3"))
    for name in ("WALLET_ADDRESS", "X402_RECIPIENT_ADDRESS", "SOLANA_MERCHANT_ADDRESS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: pytest.fail("No live payment calls are permitted"))


@pytest.mark.asyncio
@pytest.mark.parametrize("recipient,expected", [
    ("0x80E0Ae84679b7f11bE171DaADd492FBECf628cd6", True),
    ("0x73279fa4BadA7CAC888c62CDa4f5c8104765f6f1", False),
])
async def test_verifier_trusts_new_public_recipient_and_rejects_compromised_old_one(monkeypatch, recipient, expected):
    url = "https://stealthguard-402.onrender.com/v1/stealth_scrape_and_sanitize"
    challenge = {"x402Version": 2, "resource": {"url": url}, "accepts": [{"scheme": "exact", "network": config.NETWORK, "amount": "15000", "asset": config.ASSET, "payTo": recipient, "maxTimeoutSeconds": 300, "extra": {"name": "USD Coin", "version": "2"}}]}
    monkeypatch.setattr(public_url, "require_public_url", lambda value: value)
    monkeypatch.setattr(public_url, "fetch_pinned", lambda value: {"status": 402, "headers": {"payment-required": base64.b64encode(json.dumps(challenge).encode()).decode()}, "body": json.dumps(challenge).encode()})
    result = await fulfill_tool("security_x402_endpoint_verifier", {"endpoint_url": url})
    assert result["settlement_safe"] is expected
    assert result["structural_schema_valid"] is True


def test_current_public_merchant_defaults():
    assert config.DEFAULT_RECIPIENT == "0x80E0Ae84679b7f11bE171DaADd492FBECf628cd6"
    assert config.DEFAULT_SOLANA_RECIPIENT == "9wuMysgXwNhtQeqJgGByAiMYc4EjzZ5wUSmnjrrt3ffh"


@pytest.mark.parametrize("name,old", [
    ("WALLET_ADDRESS", config.RETIRED_RECIPIENT),
    ("WALLET_ADDRESS", config.RETIRED_RECIPIENT.lower()),
    ("X402_RECIPIENT_ADDRESS", config.RETIRED_RECIPIENT),
])
@pytest.mark.asyncio
async def test_stale_environment_quotes_and_validates_only_rotated_public_recipients(monkeypatch, name, old):
    monkeypatch.setenv(name, " " + old + " ")
    monkeypatch.setenv("SOLANA_MERCHANT_ADDRESS", " " + config.RETIRED_SOLANA_RECIPIENT + " ")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url=config.get_public_url()) as client:
        result = await client.get(config.TOOL_PRICING[fixtures.TOOL]["path"])
    assert result.status_code == 402
    quotes = json.loads(base64.b64decode(result.headers["payment-required"]))["accepts"]
    assert [q["payTo"] for q in quotes] == [config.DEFAULT_RECIPIENT, config.DEFAULT_SOLANA_RECIPIENT]
    for payload in (fixtures.evm_payment(), fixtures.sol_payment()):
        _, quote, _, _ = payment._payment_envelope(json.dumps(payload), fixtures.TOOL, fixtures.URL)
        assert quote["payTo"] in (config.DEFAULT_RECIPIENT, config.DEFAULT_SOLANA_RECIPIENT)


@pytest.mark.parametrize("name,value,getter", [
    ("WALLET_ADDRESS", "0x1111111111111111111111111111111111111111", config.get_recipient_address),
    ("X402_RECIPIENT_ADDRESS", "0x2222222222222222222222222222222222222222", config.get_recipient_address),
    ("SOLANA_MERCHANT_ADDRESS", fixtures.SOL_PAYER, config.get_solana_recipient_address),
])
def test_rotation_preserves_unrelated_custom_merchants(monkeypatch, name, value, getter):
    monkeypatch.setenv(name, value)
    assert getter() == value


def retired_payment(monkeypatch, network):
    if network == config.NETWORK:
        with monkeypatch.context() as scoped:
            scoped.setattr(fixtures, "get_recipient_address", lambda: config.RETIRED_RECIPIENT)
            return fixtures.evm_payment()
    payload = fixtures.sol_payment()
    payload["accepted"]["payTo"] = config.RETIRED_SOLANA_RECIPIENT
    return payload


@pytest.mark.parametrize("network", [config.NETWORK, config.SOLANA_NETWORK])
@pytest.mark.parametrize("state", [None, "preparing", "prepared", "unknown"])
@pytest.mark.asyncio
async def test_retired_authorization_can_never_start_or_resume_a_charge(monkeypatch, network, state):
    payload = retired_payment(monkeypatch, network)
    _, _, identity, _ = payment._payment_envelope(json.dumps(payload), fixtures.TOOL, fixtures.URL, retired_merchant=True)
    authorization = hashlib.sha256(identity.encode()).hexdigest()
    args = {"url": "https://example.org"}
    fingerprint = hashlib.sha256(json.dumps({"tool": fixtures.TOOL, "resource": fixtures.URL, "arguments": args}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if state:
        with payment_execution._db() as db:
            db.execute("INSERT INTO operations(authorization,fingerprint,state,owner,updated) VALUES(?,?,?,?,?)", (authorization, fingerprint, state, "old-worker", time.time() - 180))
    async def forbidden(*a, **kw):
        pytest.fail("Retired authorization cannot acquire a provider result or settle")
    status, body, receipt = await payment_execution.execute_paid_request(json.dumps(payload), fixtures.TOOL, fixtures.URL, args, forbidden)
    assert status == (503 if state == "unknown" else 402)
    assert receipt is None
    assert body["charged"] == ("unknown" if state == "unknown" else False)


@pytest.mark.parametrize("network", [config.NETWORK, config.SOLANA_NETWORK])
@pytest.mark.asyncio
async def test_completed_legacy_delivery_recovers_exact_receipt_without_new_charge(monkeypatch, network):
    payload = retired_payment(monkeypatch, network)
    _, _, identity, _ = payment._payment_envelope(json.dumps(payload), fixtures.TOOL, fixtures.URL, retired_merchant=True)
    authorization = hashlib.sha256(identity.encode()).hexdigest()
    args = {"url": "https://example.org"}
    fingerprint = hashlib.sha256(json.dumps({"tool": fixtures.TOOL, "resource": fixtures.URL, "arguments": args}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    retained = {"delivered": "original paid result"}
    receipt = {"success": True, "transaction": "legacy-confirmed-reference", "network": network, "resource": fixtures.URL}
    with payment_execution._db() as db:
        db.execute("INSERT INTO operations(authorization,fingerprint,state,owner,updated,result,receipt) VALUES(?,?,'completed',?,?,?,?)", (authorization, fingerprint, "old-worker", time.time() - 180, json.dumps(retained), json.dumps(receipt)))
    async def forbidden(*a, **kw):
        pytest.fail("Historical recovery never re-runs fulfillment or settlement")
    status, result, recovered_receipt = await payment_execution.execute_paid_request(json.dumps(payload), fixtures.TOOL, fixtures.URL, args, forbidden)
    assert status == 200 and result == retained and recovered_receipt == receipt
    status, _, _ = await payment_execution.execute_paid_request(json.dumps(payload), fixtures.TOOL, fixtures.URL, {"url": "https://other.org"}, forbidden)
    assert status == 409
    if network == config.NETWORK:
        payload["payload"]["signature"] = "0x" + "00" * 65
    else:
        wire = bytearray(base64.b64decode(payload["payload"]["transaction"]))
        wire[65] ^= 1
        payload["payload"]["transaction"] = base64.b64encode(wire).decode()
    status, _, _ = await payment_execution.execute_paid_request(json.dumps(payload), fixtures.TOOL, fixtures.URL, args, forbidden)
    assert status == 402
