"""Shared strict HTTP/MCP argument validation, before any settlement."""
import math
import json
import re
from urllib.parse import urlparse
from .config import TOOL_PRICING


def validate_url(url):
    if not isinstance(url, str) or not url.strip() or len(url) > 4096:
        raise ValueError("Expected an HTTP or HTTPS URL")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Expected an HTTP or HTTPS URL without embedded credentials")
    if parsed.port is not None and parsed.port not in (80, 443):
        raise ValueError("Only public HTTP/HTTPS ports are supported")
    return url


def validate_arguments(tool, args):
    if not isinstance(args, dict):
        raise ValueError("Tool arguments must be an object")
    schema = TOOL_PRICING[tool].get("input_schema", {})
    properties = schema.get("properties", {})
    args = dict(args)
    for name, spec in properties.items():
        if name not in args and "default" in spec:
            args[name] = spec["default"]
    for name in schema.get("required", []):
        if name not in args:
            raise ValueError(f"Missing required parameter: {name}")
    # Common options used by the original tools and their public routes.
    specs = {**properties, "strict_mode": {"type": "boolean"}, "render_js": {"type": "boolean"},
             "extract_schema": {"type": "object"}, "target_url": {"type": "string"}}
    for name, value in args.items():
        spec = specs.get(name)
        if spec is None:
            raise ValueError(f"Unknown parameter: {name}")
        expected = spec.get("type")
        valid = {
            "boolean": type(value) is bool,
            "integer": type(value) is int,
            "number": type(value) in (int, float) and math.isfinite(value),
            "string": isinstance(value, str), "array": isinstance(value, list), "object": isinstance(value, dict),
        }.get(expected, True)
        if not valid:
            raise ValueError(f"Parameter {name} must be a {expected}")
        if expected == "string" and (not value.strip() or len(value) > (200000 if name in ("text", "prompt_text") else 4096)):
            raise ValueError(f"Parameter {name} is empty or too long")
        if "enum" in spec and value not in spec["enum"]:
            raise ValueError(f"Unsupported {name}")
    if "limit" in args and not 1 <= args["limit"] <= 50:
        raise ValueError("limit must be between 1 and 50")
    if "min_order_usd" in args and not 0 <= args["min_order_usd"] <= 1000000000:
        raise ValueError("min_order_usd is out of range")
    if "assets" in args and (not 1 <= len(args["assets"]) <= 10 or any(not isinstance(a, str) or not re.fullmatch(r"[A-Z0-9]{1,15}", a) for a in args["assets"])):
        raise ValueError("assets must contain 1 to 10 uppercase asset symbols")
    if "chain" in args and args["chain"] not in ("base", "solana"):
        raise ValueError("Unsupported chain")
    for name in ("token_or_service_address", "token_address"):
        if name in args:
            value = args[name]
            is_base = args.get("chain", "base") == "base" if name == "token_or_service_address" else value.startswith("0x")
            pattern = r"0x[0-9a-fA-F]{40}" if is_base else r"[1-9A-HJ-NP-Za-km-z]{32,44}"
            if not re.fullmatch(pattern, value):
                raise ValueError(f"Invalid {name}")
    for name in ("url", "target_url", "endpoint_url"):
        if name in args:
            validate_url(args[name])
    if "depth" in args and args["depth"] not in ("summary", "comprehensive", "technical"):
        raise ValueError("Unsupported research depth")
    json.dumps(args, allow_nan=False)
    return args
