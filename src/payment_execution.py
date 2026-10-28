"""Durable fulfillment before settlement, shared by HTTP and MCP.

No private keys or raw signed payment headers are stored. A completed result is
returned on an identical retry. A different request cannot spend the same nonce.
An ambiguous settlement is quarantined: never authorize a second charge to recover.
"""
import hashlib
import json
import os
import secrets
import sqlite3
import time
import asyncio
from contextlib import contextmanager
from pathlib import Path

from .x402_middleware import _payment_envelope, verify_x402_payment, verify_x402_authorization


class ToolFailure(Exception):
    def __init__(self, message, status=503, code="upstream_unavailable"):
        super().__init__(message)
        self.status, self.code = status, code


@contextmanager
def _db():
    path = Path(os.getenv("X402_STATE_DB", str(Path(__file__).resolve().parent.parent / "state" / "x402.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("""CREATE TABLE IF NOT EXISTS operations (
        authorization TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL,
        owner TEXT, updated REAL NOT NULL, result TEXT, receipt TEXT, error TEXT
    )""")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _reply_error(code, message, status, authorization=None):
    body = {"status": "error", "error": code, "message": message, "charged": False}
    if authorization:
        body["operation_id"] = authorization
    return status, body, None


async def execute_paid_request(raw_header, tool_name, resource_url, arguments, fulfill):
    """Return (HTTP status, result, payment receipt) with at most one settlement attempt."""
    retired_merchant = False
    try:
        # Completed results remain recoverable after authorization expiry.
        _, _, identity, _ = _payment_envelope(raw_header, tool_name, resource_url, validate_time=False)
    except Exception as exc:
        try:
            # Rotation must preserve already paid deliveries. This parser mode
            # cannot authorize any fresh preparation or settlement below.
            _, _, identity, _ = _payment_envelope(raw_header, tool_name, resource_url, validate_time=False, retired_merchant=True)
            retired_merchant = True
        except Exception:
            return _reply_error("invalid_payment", str(exc), 402)
    authorization = hashlib.sha256(identity.encode()).hexdigest()
    fingerprint = hashlib.sha256(json.dumps({
        "tool": tool_name, "resource": resource_url, "arguments": arguments,
    }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    owner = secrets.token_hex(16)
    now = time.time()
    try:
        with _db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM operations WHERE authorization=?", (authorization,)).fetchone()
            if row and row["fingerprint"] != fingerprint:
                return _reply_error("payment_request_conflict", "Authorization is already bound to a different request", 409, authorization)
            if row and row["state"] == "completed":
                return 200, json.loads(row["result"]), json.loads(row["receipt"])
            if row and row["state"] in ("settling", "unknown"):
                result = _reply_error("settlement_unknown", "Settlement needs reconciliation. Retry with the SAME authorization; do not purchase again.", 503, authorization)
                result[1]["charged"] = "unknown"
                return result
            if row and row["state"] == "rejected":
                return _reply_error("payment_rejected", row["error"] or "Settlement rejected", 402, authorization)
            if retired_merchant:
                return _reply_error("retired_merchant", "This recipient is retired. Only completed legacy deliveries can be recovered with this authorization.", 402, authorization)
            if row and row["state"] == "preparing" and row["updated"] > now - 120:
                return _reply_error("operation_pending", "The same operation is already being prepared; retry the same authorization", 409, authorization)
            valid, _, error, status = verify_x402_payment(raw_header, tool_name, resource_url, settle=False)
            if not valid:
                return _reply_error("invalid_payment", error, status, authorization)
            if row and row["state"] == "prepared":
                result = json.loads(row["result"])
                db.execute("UPDATE operations SET owner=?,updated=? WHERE authorization=?", (owner, now, authorization))
            else:
                result = None
                db.execute("""INSERT INTO operations(authorization,fingerprint,state,owner,updated)
                    VALUES(?,?,'preparing',?,?) ON CONFLICT(authorization) DO UPDATE SET
                    state='preparing',owner=excluded.owner,updated=excluded.updated,error=NULL""",
                    (authorization, fingerprint, owner, now))
        # Network verification runs after the claim commits, outside a SQLite lock.
        authorized, facilitator, error, status = await asyncio.to_thread(verify_x402_authorization, raw_header, tool_name, resource_url)
        if not authorized:
            with _db() as db:
                db.execute("UPDATE operations SET state='failed',error=?,updated=? WHERE authorization=? AND owner=? AND state IN ('preparing','prepared')",
                           (error, time.time(), authorization, owner))
            return _reply_error("payment_verification_failed", error, status, authorization)
        if result is None:
            try:
                result = await fulfill(tool_name, arguments)
                if not isinstance(result, dict) or result.get("error") or result.get("status") in ("error", "unavailable"):
                    raise ToolFailure("The requested analysis could not be fulfilled")
                json_result = json.dumps(result, separators=(",", ":"), allow_nan=False)
            except Exception as exc:
                with _db() as db:
                    db.execute("UPDATE operations SET state='failed',error=?,updated=? WHERE authorization=? AND owner=? AND state='preparing'",
                               (str(exc), time.time(), authorization, owner))
                if isinstance(exc, ToolFailure):
                    return _reply_error(exc.code, str(exc), exc.status, authorization)
                return _reply_error("fulfillment_failed", "Provider execution failed before settlement; no payment was submitted", 503, authorization)
            with _db() as db:
                changed = db.execute("UPDATE operations SET state='prepared',result=?,updated=? WHERE authorization=? AND owner=? AND state='preparing'",
                                     (json_result, time.time(), authorization, owner)).rowcount
                if changed != 1:
                    return _reply_error("operation_pending", "Preparation was superseded; retry the same authorization", 409, authorization)
        with _db() as db:
            changed = db.execute("UPDATE operations SET state='settling',updated=? WHERE authorization=? AND owner=? AND state='prepared'",
                                 (time.time(), authorization, owner)).rowcount
            if changed != 1:
                return _reply_error("operation_pending", "Settlement is already being handled; retry the same authorization", 409, authorization)
        valid, receipt, error, status = await asyncio.to_thread(verify_x402_payment, raw_header, tool_name, resource_url, facilitator=facilitator)
        with _db() as db:
            if valid:
                db.execute("UPDATE operations SET state='completed',receipt=?,updated=? WHERE authorization=? AND owner=? AND state='settling'",
                           (json.dumps(receipt, separators=(",", ":")), time.time(), authorization, owner))
            else:
                db.execute("UPDATE operations SET state=?,error=?,receipt=?,updated=? WHERE authorization=? AND owner=? AND state='settling'",
                           ("unknown" if status == 503 else "rejected", error, json.dumps(receipt) if receipt else None, time.time(), authorization, owner))
        if not valid:
            reply = _reply_error("settlement_unknown" if status == 503 else "payment_rejected", error, status, authorization)
            if status == 503:
                reply[1]["charged"] = "unknown"
            return reply
        return 200, result, receipt
    except sqlite3.Error:
        # If a write failed after broadcast, fail safely rather than submitting again.
        reply = _reply_error("payment_state_unavailable", "Payment state is unavailable. Retain and retry the SAME authorization; do not purchase again.", 503, authorization)
        reply[1]["charged"] = "unknown"
        return reply
