import base64
import json
import time
import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data

from src.config import NETWORK, CHAIN_ID, ASSET, get_recipient_address
from src.x402_middleware import (
    build_402_challenge,
    verify_x402_payment,
    create_payment_response_header,
    REPLAY_CACHE,
)

def test_build_402_challenge_headers_and_body():
    headers, body = build_402_challenge(
        tool_name="stealth_scrape_and_sanitize",
        resource_url="https://stealthguard-402.onrender.com/v1/stealth_scrape_and_sanitize",
    )
    assert headers["X-402-Version"] == "2"
    assert headers["X-402-Network"] == "base"
    assert headers["X-402-Chain-Id"] == "8453"
    assert headers["X-402-Amount"] == "0.005"
    assert headers["X-402-Amount-Units"] == "5000"
    assert headers["X-402-Asset"].lower() == ASSET.lower()
    assert headers["X-402-Payment-To"].lower() == get_recipient_address().lower()
    assert "PAYMENT-REQUIRED" in headers

    # Verify IETF MPP WWW-Authenticate header
    assert "WWW-Authenticate" in headers
    assert 'Payment id="' in headers["WWW-Authenticate"]
    assert 'realm="stealthguard-402.onrender.com"' in headers["WWW-Authenticate"]
    assert 'method="evm"' in headers["WWW-Authenticate"]
    assert 'intent="charge"' in headers["WWW-Authenticate"]
    assert 'request="' in headers["WWW-Authenticate"]
    assert 'expires="' in headers["WWW-Authenticate"]

    # Verify Access-Control-Expose-Headers includes required settlement headers
    expose = headers["Access-Control-Expose-Headers"]
    assert "PAYMENT-REQUIRED" in expose
    assert "PAYMENT-RESPONSE" in expose
    assert "WWW-Authenticate" in expose
    assert "Payment-Receipt" in expose

    # Decode and verify base64 challenge payload
    raw_b64 = headers["PAYMENT-REQUIRED"]
    decoded = json.loads(base64.b64decode(raw_b64).decode("utf-8"))
    assert decoded["x402Version"] == 2

    # Resource must be an object with https URL and description <= 450 chars
    assert isinstance(decoded["resource"], dict)
    assert decoded["resource"]["url"].startswith("https://")
    assert decoded["resource"]["mimeType"] == "application/json"
    assert len(decoded["resource"]["description"]) <= 450

    # accepts[0] must not have a raw string "resource"
    assert len(decoded["accepts"]) == 1
    accept = decoded["accepts"][0]
    assert accept["scheme"] == "exact"
    assert accept["network"] == NETWORK
    assert accept["asset"].lower() == ASSET.lower()
    assert accept["amount"] == "5000"
    assert accept["payTo"].lower() == get_recipient_address().lower()
    assert "bazaar" in decoded["extensions"]

    # Body must also have resource object with https URL
    assert isinstance(body["resource"], dict)
    assert body["resource"]["url"].startswith("https://")
    assert body["x402Version"] == 2

def test_unpaid_verification_returns_402():
    is_valid, pay_info, err, status = verify_x402_payment(None, "stealth_scrape_and_sanitize")
    assert is_valid is False
    assert status == 402
    assert "Missing" in err

def test_valid_eip712_payment_verification_and_replay_protection():
    REPLAY_CACHE.clear()
    payer = Account.create()
    recipient = get_recipient_address()
    amount = 5000
    now = int(time.time())

    types = {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "TransferWithAuthorization": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ],
    }

    domain = {
        "name": "USD Coin",
        "version": "2",
        "chainId": CHAIN_ID,
        "verifyingContract": ASSET,
    }

    nonce_bytes = b"\x01" * 32
    nonce_hex = "0x" + nonce_bytes.hex()

    message = {
        "from": payer.address,
        "to": recipient,
        "value": amount,
        "validAfter": 0,
        "validBefore": now + 600,
        "nonce": nonce_bytes,
    }

    signable = encode_typed_data(full_message={
        "types": types,
        "primaryType": "TransferWithAuthorization",
        "domain": domain,
        "message": message,
    })

    signed = payer.sign_message(signable)
    signature_hex = signed.signature.hex()
    if not signature_hex.startswith("0x"):
        signature_hex = "0x" + signature_hex

    payment_payload = {
        "x402Version": 2,
        "payload": {
            "signature": signature_hex,
            "authorization": {
                "from": payer.address,
                "to": recipient,
                "value": amount,
                "validAfter": 0,
                "validBefore": now + 600,
                "nonce": nonce_hex,
            },
        },
    }

    raw_header = json.dumps(payment_payload)

    # 1. First execution: should succeed and verify
    is_valid, pay_info, err, status = verify_x402_payment(raw_header, "stealth_scrape_and_sanitize")
    assert is_valid is True
    assert status == 200
    assert pay_info is not None
    assert pay_info["success"] is True
    assert pay_info["payer"].lower() == payer.address.lower()
    assert pay_info["amount"] == "5000"

    # Verify PAYMENT-RESPONSE header generation
    resp_hdr = create_payment_response_header(pay_info)
    assert resp_hdr is not None
    decoded_resp = json.loads(base64.b64decode(resp_hdr).decode("utf-8"))
    assert decoded_resp["success"] is True

    # 2. Second execution with identical signature: REPLAY ATTACK should be prevented with 409
    is_valid_replay, pay_info_replay, err_replay, status_replay = verify_x402_payment(
        raw_header, "stealth_scrape_and_sanitize"
    )
    assert is_valid_replay is False
    assert status_replay == 409
    assert "Replay prevented" in err_replay
