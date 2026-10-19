import asyncio
import json
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from src.mcp_server import MCP_TOOLS, handle_mcp_request
from src.config import SERVICE_VERSION

async def list_tools_handler(ctx, params=None) -> types.ListToolsResult:
    tools_list = []
    for t in MCP_TOOLS:
        tools_list.append(
            types.Tool(
                name=t["name"],
                description=t.get("description", ""),
                inputSchema=t.get("inputSchema", {"type": "object", "properties": {}}),
            )
        )
    return types.ListToolsResult(tools=tools_list)

async def call_tool_handler(ctx, params) -> types.CallToolResult:
    name = params.name
    arguments = params.arguments or {}
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    res, _ = await handle_mcp_request(req)
    content_list = res.get("result", {}).get("content", [])
    if content_list:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=c.get("text", "")) for c in content_list]
        )
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(res))]
    )

server = Server(
    "stealthguard-402",
    version=SERVICE_VERSION,
    on_list_tools=list_tools_handler,
    on_call_tool=call_tool_handler,
)

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )

if __name__ == "__main__":
    asyncio.run(main())
