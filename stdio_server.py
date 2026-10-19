import sys
import json
import asyncio
from src.mcp_server import handle_mcp_request

async def run_stdio():
    """
    Standard input/output JSON-RPC 2.0 loop for Model Context Protocol (MCP) clients.
    Fully compatible with mcp-proxy, Claude Desktop, Cursor, Glama, and Smithery.
    """
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            # JSON-RPC 2.0 Notifications have no 'id' and MUST NOT receive a response
            if "id" not in req or str(req.get("method", "")).startswith("notifications/"):
                continue

            res, _ = await handle_mcp_request(req)
            if res:
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()
        except Exception as e:
            err_res = {
                "jsonrpc": "2.0",
                "id": req.get("id") if "req" in locals() and isinstance(req, dict) else None,
                "error": {"code": -32603, "message": str(e)},
            }
            sys.stdout.write(json.dumps(err_res) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    asyncio.run(run_stdio())
