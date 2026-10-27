import json
import os
import time
import hashlib
from datetime import datetime
from typing import Dict, Any, List

MAX_MEMORY_RECORDS = 200
_MEMORY_STORE: List[Dict[str, Any]] = []
_PAID_MEMORY_STORE: List[Dict[str, Any]] = []
_LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "deliveries.jsonl")

def decode_payer_from_header(raw_header: str) -> Dict[str, Any]:
    if not raw_header:
        return {"payer": "unpaid_probe", "amount": 0.0}
    try:
        import base64
        cleaned = raw_header.strip()
        if not cleaned.startswith("{"):
            cleaned = base64.b64decode(cleaned).decode("utf-8")
        data = json.loads(cleaned)
        
        auth = data.get("payload", {}).get("authorization") or data.get("authorization") or data
        if isinstance(auth, dict) and "from" in auth:
            val_raw = int(auth.get("value", 5000))
            return {"payer": str(auth["from"]).lower(), "amount": val_raw / 1e6}
        if "payer" in data:
            return {"payer": str(data["payer"]).lower(), "amount": float(data.get("amount", 0.005))}
    except Exception:
        pass
    return {"payer": "unknown_signer", "amount": 0.005}

def record_delivery(
    endpoint: str,
    method: str,
    status_code: int,
    latency_ms: float,
    user_agent: str,
    client_ip: str,
    referer: str,
    request_input: Any,
    raw_payment_header: str = None,
    payment_response_header: str = None,
    response_preview: str = ""
):
    if endpoint in ["/health", "/ping", "/favicon.ico"]:
        return

    payer_info = decode_payer_from_header(raw_payment_header)
    resolved_payer = payer_info["payer"]
    resolved_amount = 0.0
    settled = False

    if payment_response_header:
        try:
            import base64
            cleaned_resp = payment_response_header.strip()
            if not cleaned_resp.startswith("{"):
                cleaned_resp = base64.b64decode(cleaned_resp).decode("utf-8")
            data_resp = json.loads(cleaned_resp)
            if "payer" in data_resp:
                resolved_payer = str(data_resp["payer"]).lower()
            if data_resp.get("success") is True and data_resp.get("network") in ("eip155:8453", "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp") and data_resp.get("transaction"):
                resolved_amount = float(data_resp["amount"]) / 1e6
                settled = True
        except Exception:
            pass

    req_input_str = "{}"
    try:
        req_input_str = json.dumps(request_input, sort_keys=True, separators=(",", ":"))
    except Exception:
        req_input_str = str(request_input)[:500]

    # Telemetry must not publish or log customer prompts, extracted pages or signed authorizations.
    request_digest = hashlib.sha256(req_input_str.encode()).hexdigest()
    resp_preview_str = hashlib.sha256((response_preview or "").encode()).hexdigest()

    record = {
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "settled": settled,
        "payer_wallet": resolved_payer,
        "amount_usdc": resolved_amount,
        "endpoint": endpoint,
        "method": method,
        "user_agent": user_agent or "none",
        "client_ip": client_ip or "unknown",
        "referer": referer or "direct",
        "request_input_sha256": request_digest,
        "http_status": status_code,
        "latency_ms": round(latency_ms, 2),
        "response_preview_sha256": resp_preview_str
    }

    # Emit structured JSON log to stdout for Render log tailing
    print(json.dumps({
        "ts": record["timestamp_utc"],
        "service": "stealthguard-402",
        "endpoint": f"{method} {endpoint}",
        "status": status_code,
        "durationMs": record["latency_ms"],
        "settled": settled,
        "payer": resolved_payer,
        "amountUsdc": resolved_amount,
        "requestInputSha256": request_digest,
        "responsePreviewSha256": resp_preview_str
    }), flush=True)

    _MEMORY_STORE.insert(0, record)
    if len(_MEMORY_STORE) > MAX_MEMORY_RECORDS:
        _MEMORY_STORE.pop()

    if settled and not any(r.get("transaction") == data_resp.get("transaction") for r in _PAID_MEMORY_STORE):
        record["transaction"] = data_resp["transaction"]
        _PAID_MEMORY_STORE.insert(0, record)
        if len(_PAID_MEMORY_STORE) > MAX_MEMORY_RECORDS:
            _PAID_MEMORY_STORE.pop()

    try:
        with open(_LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass

def get_recent_deliveries() -> List[Dict[str, Any]]:
    return list(_MEMORY_STORE)

def get_paid_deliveries() -> List[Dict[str, Any]]:
    return list(_PAID_MEMORY_STORE)
