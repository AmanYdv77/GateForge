import ipaddress
from typing import Final

import structlog
from fastapi import HTTPException, Request, status

logger = structlog.get_logger(__name__)

DEFAULT_FALLBACK_IP: Final[str] = "127.0.0.1"


def parse_network(
    cidr_or_ip: str,
) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
    """Safely parse a single IP address or CIDR subnet block into an IP network object."""
    cleaned = cidr_or_ip.strip()
    if not cleaned:
        return None

    try:
        if "/" in cleaned:
            return ipaddress.ip_network(cleaned, strict=False)
        # Parse single IP and wrap as /32 or /128 single-host subnet
        addr = ipaddress.ip_address(cleaned)
        prefix_len = 32 if addr.version == 4 else 128
        return ipaddress.ip_network(f"{addr}/{prefix_len}", strict=False)
    except ValueError as exc:
        logger.warning("invalid_ip_cidr_definition", entry=cleaned, error=str(exc))
        return None


def extract_client_ip(request: Request | None) -> str:
    """Extract client remote IP from request headers or ASGI connection info.

    Checks:
    1. X-Forwarded-For (first IP in comma-separated proxy chain)
    2. X-Real-IP
    3. request.client.host
    4. Fallback to 127.0.0.1
    """
    if request is None:
        return DEFAULT_FALLBACK_IP

    # 1. Forwarded chain check
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_part = forwarded_for.split(",")[0].strip()
        if client_part:
            return client_part

    # 2. X-Real-IP check
    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    # 3. Direct socket connection client host
    if request.client and request.client.host:
        return request.client.host.strip()

    return DEFAULT_FALLBACK_IP


def is_ip_allowed(client_ip: str | None, allowed_cidrs: list[str]) -> bool:
    """Evaluate whether an incoming client IP matches any allowed CIDR block or IP address.

    Returns True if allowed_cidrs is empty (no restriction configured).
    """
    if not allowed_cidrs:
        return True

    if not client_ip:
        return False

    try:
        ip = ipaddress.ip_address(client_ip.strip())
    except ValueError:
        logger.warning("invalid_client_ip_format", client_ip=client_ip)
        return False

    for entry in allowed_cidrs:
        net = parse_network(entry)
        if net is not None and ip in net:
            return True

    return False


def evaluate_ip_access(
    request: Request | None,
    allowed_cidrs: list[str],
) -> None:
    """Validate client IP against enterprise allowlist; raises 403 Forbidden if not authorized."""
    if not allowed_cidrs:
        return

    client_ip = extract_client_ip(request)
    if not is_ip_allowed(client_ip, allowed_cidrs):
        logger.warning(
            "ip_allowlist_violation",
            client_ip=client_ip,
            allowed_cidrs=allowed_cidrs,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Client IP {client_ip} is not authorized for this API key",
        )
