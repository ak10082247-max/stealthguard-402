"""No live keys, wallets, settlement services, or paid requests are used here."""
import base64
import copy
import json
import time
import pytest
import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from src import x402_middleware as payment
from src.config import ASSET, CHAIN_ID, NETWORK, SOLANA_NETWORK, SOLANA_FEE_PAYER, get_recipient_address
from src.payment_execution import execute_paid_request, ToolFailure

TOOL = "stealth_scrape_and_sanitize"
URL = "https://stealthguard-402.onrender.com/v1/stealth_scrape_and_sanitize"
SOL_TEST_KEY = Ed25519PrivateKey.from_private_bytes(bytes([7])*32)
SOL_TEST_PUBLIC = SOL_TEST_KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
SOL_PAYER = payment._base58(SOL_TEST_PUBLIC)
SOL_TX = "2" * 88


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_STATE_DB", str(tmp_path / "payments.sqlite3"))
    payment.REPLAY_CACHE.clear()
    # Any unmocked HTTP is a test failure, never a live purchase.
    def no_network(*a, **kw):
        raise AssertionError("Unexpected live HTTP in payment regression")
    monkeypatch.setattr(httpx.Client, "post", no_network)


def sol_payment():
    quote = payment.build_402_challenge(TOOL, URL)[1]
    number = 0
    for char in SOLANA_FEE_PAYER:
        number = number*58 + payment._BASE58.index(char)
    sponsor = number.to_bytes(32, "big")
    # Inert, genuinely signed v0 message with no transfer instructions. Mock
    # facilitator validates this fixture; it is never submitted to any network.
    message = bytes([128, 2, 1, 0, 2]) + sponsor + SOL_TEST_PUBLIC + bytes(32) + bytes([0, 0])
    transaction = bytes([2]) + bytes(64) + SOL_TEST_KEY.sign(message) + message
    return {"x402Version": 2, "resource": quote["resource"], "accepted": quote["accepts"][1],
            "payload": {"transaction": base64.b64encode(transaction).decode()}}


def mock_settler(monkeypatch, data, status=200):
    class Calls(list):
        verifications = None
    calls = Calls()
    calls.verifications = []
    def post(client, url, **kwargs):
        if url.endswith("/verify"):
            calls.verifications.append((url, kwargs))
            canonical = kwargs["json"]["paymentPayload"]
            payer = canonical["payload"].get("authorization", {}).get("from") or SOL_PAYER
            return httpx.Response(200, json={"isValid": True, "payer": payer}, request=httpx.Request("POST", url))
        calls.append((url, kwargs))
        return httpx.Response(status, json=data, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.Client, "post", post)
    return calls


def valid_receipt():
    return {"success": True, "transaction": SOL_TX, "payer": SOL_PAYER, "network": SOLANA_NETWORK, "amount": "15000"}


def evm_payment():
    # A public deterministic test key; never funded, never submitted to a network.
    account = Account.from_key(bytes.fromhex("01" * 32))
    auth = {"from": account.address, "to": get_recipient_address(), "value": "15000",
            "validAfter": "0", "validBefore": str(int(time.time()) + 60), "nonce": "0x" + "ab"*32}
    types = {"EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                             {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}],
             "TransferWithAuthorization": [{"name": "from", "type": "address"}, {"name": "to", "type": "address"},
                                            {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
                                            {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"}]}
    message = {**auth, "value": 15000, "validAfter": 0, "validBefore": int(auth["validBefore"]), "nonce": bytes.fromhex(auth["nonce"][2:])}
    signable = encode_typed_data(full_message={"types": types, "primaryType": "TransferWithAuthorization",
        "domain": {"name": "USD Coin", "version": "2", "chainId": CHAIN_ID, "verifyingContract": ASSET}, "message": message})
    return {"x402Version": 2, "payload": {"authorization": auth, "signature": "0x" + account.sign_message(signable).signature.hex()}}


def test_success_receipt_preserves_genuine_acknowledgement(monkeypatch):
    calls = mock_settler(monkeypatch, valid_receipt())
    valid, info, error, status = payment.verify_x402_payment(json.dumps(sol_payment()), TOOL, URL)
    assert valid and status == 200 and error is None
    assert info == {**valid_receipt(), "resource": URL}
    decoded = json.loads(base64.b64decode(payment.create_payment_response_header(info)))
    assert decoded["success"] is True and decoded["transaction"] == SOL_TX
    assert len(calls) == 1 and calls[0][1]["json"]["paymentRequirements"]["amount"] == "15000"


@pytest.mark.parametrize("data,status,expected", [
    ({"success": False, "errorReason": "insufficient_funds"}, 200, 402),
    ({"success": False, "errorReason": "rejected"}, 400, 402),
    ({"transaction": SOL_TX, "payer": SOL_PAYER}, 200, 503),
    ({"success": "true", "transaction": SOL_TX, "payer": SOL_PAYER}, 200, 503),
    ({"success": True, "payer": SOL_PAYER}, 200, 503),
    ({**valid_receipt(), "network": NETWORK}, 200, 503),
    ({**valid_receipt(), "amount": "1"}, 200, 503),
    ({"error": "upstream timeout"}, 502, 503),
])
def test_failed_or_ambiguous_settlement_never_becomes_success(monkeypatch, data, status, expected):
    calls = mock_settler(monkeypatch, data, status)
    valid, info, _, result_status = payment.verify_x402_payment(json.dumps(sol_payment()), TOOL, URL)
    assert not valid and (info is None or "settlement_candidate" in info) and result_status == expected and len(calls) == 1


@pytest.mark.parametrize("field,value", [("amount", "1"), ("network", "solana:wrong"), ("asset", "wrong"), ("payTo", SOL_PAYER), ("scheme", "upto"), ("maxTimeoutSeconds", 300.0)])
def test_client_cannot_replace_server_quote(monkeypatch, field, value):
    payload = sol_payment()
    payload["accepted"][field] = value
    calls = mock_settler(monkeypatch, valid_receipt())
    assert payment.verify_x402_payment(json.dumps(payload), TOOL, URL)[0] is False
    assert calls == []


@pytest.mark.parametrize("raw", ["[]", "null", '"value"', "e30=", "not-base64"])
def test_invalid_envelopes_rejected_without_settlement(raw):
    assert payment.verify_x402_payment(raw, TOOL, URL)[0] is False


def test_resource_bound_and_magic_test_signatures_removed(monkeypatch):
    payload = sol_payment()
    payload["resource"]["url"] = URL + "/other"
    assert payment.verify_x402_payment(json.dumps(payload), TOOL, URL)[0] is False
    monkeypatch.setenv("TESTING", "1")
    payload = evm_payment()
    payload["payload"]["signature"] = "0x11" + "11" * 64
    assert payment.verify_x402_payment(json.dumps(payload), TOOL, URL)[0] is False


def test_base_valid_signature_requires_actual_settler_proof(monkeypatch):
    payload = evm_payment()
    payer = payload["payload"]["authorization"]["from"]
    monkeypatch.setattr(payment, "settle_via_cdp_facilitator", lambda *a: (True, {"success": True, "payer": payer}, None))
    assert payment.verify_x402_payment(json.dumps(payload), TOOL, URL)[3] == 503
    monkeypatch.setattr(payment, "settle_via_cdp_facilitator", lambda *a: (True, {"success": True, "payer": payer, "transaction": "0x"+"12"*32}, None))
    valid, info, _, status = payment.verify_x402_payment(json.dumps(payload), TOOL, URL)
    assert valid and status == 200 and info["success"] is True and info["amount"] == "15000"


def test_cdp_timeout_never_resubmits_to_second_relay(monkeypatch):
    monkeypatch.setattr(payment, "load_cdp_credentials", lambda: ("dummy", "dummy"))
    monkeypatch.setattr(payment, "generate_cdp_jwt", lambda *a: "dummy")
    def timeout(*a, **kw):
        raise httpx.ReadTimeout("simulated acknowledgement loss")
    monkeypatch.setattr(httpx.Client, "post", timeout)
    def must_not_relay(*a, **kw):
        raise AssertionError("Ambiguous payment must never be resubmitted")
    monkeypatch.setattr(payment, "_settle_via_payai_facilitator", must_not_relay)
    ok, data, error = payment.settle_via_cdp_facilitator({}, {})
    assert not ok and data is None and "SETTLEMENT_UNKNOWN" in error


def test_no_cdp_credentials_uses_direct_payai_before_any_attempt(monkeypatch):
    payload = evm_payment()
    payer = payload["payload"]["authorization"]["from"]
    monkeypatch.setattr(payment, "load_cdp_credentials", lambda: (None, None))
    calls = mock_settler(monkeypatch, {"success": True, "payer": payer, "transaction": "0x"+"12"*32, "network": NETWORK})
    valid, info, _, status = payment.verify_x402_payment(json.dumps(payload), TOOL, URL)
    assert valid and status == 200 and info["success"] is True
    assert len(calls) == 1 and calls[0][0] == "https://facilitator.payai.network/settle"
    assert calls[0][1]["json"]["x402Version"] == 2


@pytest.mark.asyncio
async def test_sponsor_signature_change_cannot_create_second_operation(monkeypatch):
    calls = mock_settler(monkeypatch, valid_receipt())
    async def fulfill(*args):
        return {"unique": "owner-result"}
    payload = sol_payment()
    first = await execute_paid_request(json.dumps(payload), TOOL, URL, {}, fulfill)
    serialized = bytearray(base64.b64decode(payload["payload"]["transaction"]))
    serialized[1:65] = bytes([99])*64  # Sponsor slot is not the buyer authorization.
    payload["payload"]["transaction"] = base64.b64encode(serialized).decode()
    second = await execute_paid_request(json.dumps(payload), TOOL, URL, {}, fulfill)
    assert first == second and first[0] == 200 and len(calls) == 1


@pytest.mark.asyncio
async def test_fulfillment_failure_is_not_charged(monkeypatch):
    calls = mock_settler(monkeypatch, valid_receipt())
    async def broken(*a):
        raise ToolFailure("Browser unavailable")
    status, body, receipt = await execute_paid_request(json.dumps(sol_payment()), TOOL, URL, {"url": "https://example.com"}, broken)
    assert status == 503 and body["charged"] is False and receipt is None and calls == []


@pytest.mark.asyncio
async def test_durable_result_replay_and_request_binding(monkeypatch):
    calls = mock_settler(monkeypatch, valid_receipt())
    fulfill_calls = []
    async def fulfill(tool, args):
        fulfill_calls.append(args)
        return {"url": args["url"], "unique": "prepared-before-payment"}
    header = json.dumps(sol_payment())
    args = {"url": "https://example.com"}
    first = await execute_paid_request(header, TOOL, URL, args, fulfill)
    payment.REPLAY_CACHE.clear()  # Simulate restart; recovery must use SQLite, not RAM.
    second = await execute_paid_request(header, TOOL, URL, args, fulfill)
    conflict = await execute_paid_request(header, TOOL, URL, {"url": "https://example.org"}, fulfill)
    assert first == second and first[0] == 200
    assert conflict[0] == 409 and len(calls) == len(fulfill_calls) == 1


@pytest.mark.asyncio
async def test_ambiguous_charge_quarantined_and_prepared_result_retained(monkeypatch):
    calls = mock_settler(monkeypatch, {"payer": SOL_PAYER, "transaction": SOL_TX})
    async def fulfill(*a):
        return {"unique": "result-retained-for-reconciliation"}
    header = json.dumps(sol_payment())
    first = await execute_paid_request(header, TOOL, URL, {}, fulfill)
    payment.REPLAY_CACHE.clear()
    second = await execute_paid_request(header, TOOL, URL, {}, fulfill)
    assert first[0] == second[0] == 503 and second[1]["charged"] == "unknown"
    assert len(calls) == 1
    import os, sqlite3
    with sqlite3.connect(os.environ["X402_STATE_DB"]) as db:
        row = db.execute("SELECT state,result FROM operations").fetchone()
    assert row[0] == "unknown" and "retained-for-reconciliation" in row[1]


@pytest.mark.asyncio
async def test_concurrent_duplicate_preparation_settles_once(monkeypatch):
    import asyncio
    calls = mock_settler(monkeypatch, valid_receipt())
    started, proceed = asyncio.Event(), asyncio.Event()
    async def fulfill(*a):
        started.set()
        await proceed.wait()
        return {"unique": "one-operation"}
    header = json.dumps(sol_payment())
    task = asyncio.create_task(execute_paid_request(header, TOOL, URL, {}, fulfill))
    await started.wait()
    duplicate = await execute_paid_request(header, TOOL, URL, {}, fulfill)
    proceed.set()
    original = await task
    assert duplicate[0] == 409 and original[0] == 200 and len(calls) == 1
