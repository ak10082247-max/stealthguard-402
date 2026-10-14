# stealthguard-mcp (Python)

Zero-config stdio Model Context Protocol (MCP) proxy for [StealthGuard-402](https://github.com/ak10082247-max/stealthguard-402).

## Installation

```bash
pip install stealthguard-mcp
```
or run directly via `uvx`:
```bash
uvx stealthguard-mcp
```

## Client Configuration

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "stealthguard": {
      "command": "uvx",
      "args": ["stealthguard-mcp"]
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "stealthguard": {
      "command": "stealthguard-mcp"
    }
  }
}
```
