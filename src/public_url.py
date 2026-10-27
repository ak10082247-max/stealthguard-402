"""Reject private destinations before fetches and redirects."""
import ipaddress
import socket
from urllib.parse import urlparse
from .tool_validation import validate_url


def resolve_public_url(url):
    validate_url(url)
    host = urlparse(url).hostname
    if host.lower() in ("localhost", "metadata.google.internal") or host.lower().endswith((".localhost", ".local", ".internal")):
        raise ValueError("Private destinations are not supported")
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        addresses = list({r[4][0] for r in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError("Private destinations are not supported")
    return url, addresses


def require_public_url(url):
    return resolve_public_url(url)[0]


def fetch_pinned(url, *, method="GET", headers=None, body=None, limit=2_000_000):
    """Resolve, validate and pin the actual TLS/HTTP socket, with no automatic redirect."""
    from curl_cffi import CurlOpt
    from curl_cffi.requests import Session
    _, addresses = resolve_public_url(url)
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    ip = next((ip for ip in addresses if ":" not in ip), addresses[0])
    address = f"[{ip}]" if ":" in ip else ip
    clean_headers = {k: v for k, v in (headers or {}).items() if k.lower() not in ("host", "content-length", "connection", "proxy-authorization")}
    if method not in ("GET", "HEAD", "POST") or (body and len(body) > 200000):
        raise ValueError("Unsupported browser subrequest")
    with Session(curl_options={CurlOpt.RESOLVE: [f"{parsed.hostname}:{port}:{address}"]}, trust_env=False, impersonate="chrome") as session:
        response = session.request(method, url, headers=clean_headers, data=body, timeout=15, allow_redirects=False, stream=True)
        chunks, length = [], 0
        try:
            for chunk in response.iter_content():
                length += len(chunk)
                if length > limit:
                    raise ValueError("Target response exceeds extraction size limit")
                chunks.append(chunk)
            result_headers = {k: v for k, v in response.headers.items() if k.lower() not in ("content-encoding", "content-length", "transfer-encoding", "connection")}
            return {"status": response.status_code, "headers": result_headers, "body": b"".join(chunks), "resolved_ip": ip}
        finally:
            response.close()
