import base64
import json
import socket
import pytest
import httpx

from src import public_url, payment_execution
from src import x402_middleware as payment
from src.config import SOLANA_NETWORK
from tests.test_payment_contract_regressions import sol_payment, TOOL, URL


@pytest.mark.parametrize("url", ["http://127.0.0.1", "http://169.254.169.254", "https://[::1]", "http://10.0.0.1", "https://localhost", "https://foo.internal"])
def test_private_targets_are_rejected_before_transport(url):
    with pytest.raises(ValueError):
        public_url.require_public_url(url)


def test_dns_mixed_public_private_answers_rejected(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)), (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0))])
    with pytest.raises(ValueError):
        public_url.require_public_url("https://public.invalid")


def test_validated_dns_address_is_pinned_to_actual_curl_connection(monkeypatch):
    import curl_cffi.requests
    from curl_cffi import CurlOpt
    lookups, transport = [], []
    def resolve(*args, **kwargs):
        lookups.append(args[0])
        ip = "93.184.216.34" if len(lookups) == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))]
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    class Response:
        status_code = 200
        headers = {"content-type": "text/plain", "content-encoding": "gzip"}
        def iter_content(self):
            yield b"owner fixture response"
        def close(self):
            pass
    class Session:
        def __init__(self, **kwargs):
            transport.append(kwargs)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def request(self, method, url, **kwargs):
            assert url == "https://public.invalid/path" and kwargs["allow_redirects"] is False
            assert transport[0]["trust_env"] is False
            assert transport[0]["curl_options"][CurlOpt.RESOLVE] == ["public.invalid:443:93.184.216.34"]
            return Response()
    monkeypatch.setattr(curl_cffi.requests, "Session", Session)
    result = public_url.fetch_pinned("https://public.invalid/path")
    assert lookups == ["public.invalid"] and result["resolved_ip"] == "93.184.216.34"
    assert "content-encoding" not in result["headers"]


def test_invalid_ed25519_buyer_proof_rejected_without_facilitator(monkeypatch):
    payload = sol_payment()
    serialized = bytearray(base64.b64decode(payload["payload"]["transaction"]))
    serialized[65] ^= 1
    payload["payload"]["transaction"] = base64.b64encode(serialized).decode()
    def no_call(*a, **kw):
        pytest.fail("Invalid local signature must not reach a facilitator")
    monkeypatch.setattr(httpx.Client, "post", no_call)
    valid, _, error, status = payment.verify_x402_payment(json.dumps(payload), TOOL, URL)
    assert not valid and status == 402 and "buyer signature" in error


@pytest.mark.asyncio
async def test_facilitator_rejection_happens_before_provider_work_and_settlement(monkeypatch, tmp_path):
    monkeypatch.setenv("X402_STATE_DB", str(tmp_path / "payments.sqlite"))
    calls = []
    def post(client, url, **kwargs):
        calls.append(url)
        assert url.endswith("/verify")
        return httpx.Response(200, json={"isValid": False, "invalidReason": "insufficient_funds"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.Client, "post", post)
    async def must_not_fulfill(*args):
        pytest.fail("Rejected wallet must not consume provider resources")
    status, result, receipt = await payment_execution.execute_paid_request(json.dumps(sol_payment()), TOOL, URL, {}, must_not_fulfill)
    assert status == 402 and result["charged"] is False and receipt is None and len(calls) == 1
