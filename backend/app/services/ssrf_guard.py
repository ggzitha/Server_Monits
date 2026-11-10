"""
ssrf_guard.py - Server-Side Request Forgery (SSRF) Protection

Validates outbound URLs before HTTP polling:
1. Resolves hostname to IP addresses via DNS.
2. Rejects loopback (127.0.0.0/8, ::1), private subnets (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16),
   carrier-grade NAT (100.64.0.0/10), link-local (169.254.0.0/16, fe80::/10), multicast,
   and AWS/GCP/Azure instance metadata endpoints (169.254.169.254) unless explicitly permitted
   by an admin-configured allow-list.
3. Strictly forbids non-HTTP(S) schemes (file://, gopher://, ftp://).
"""
import ipaddress
import socket
from urllib.parse import urlparse
from typing import List, Optional, Tuple


BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    # IPv6
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]


class SSRFValidationError(ValueError):
    """Raised when an outbound URL fails SSRF security checks."""
    pass


def validate_url_for_ssrf(
    url: str,
    allow_private_ranges: bool = False,
    domain_allow_list: Optional[List[str]] = None,
) -> Tuple[str, str, int]:
    """
    Validate target URL against SSRF attack vectors.
    Returns (normalized_url, resolved_ip, port).
    """
    if not url:
        raise SSRFValidationError("URL cannot be empty")

    parsed = urlparse(url)

    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFValidationError(f"Invalid URL scheme '{parsed.scheme}'. Only http and https are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("Missing hostname in URL")

    # Check domain allow-list if defined
    if domain_allow_list:
        is_allowed = False
        for allowed in domain_allow_list:
            allowed = allowed.strip().lower()
            if hostname.lower() == allowed or hostname.lower().endswith("." + allowed):
                is_allowed = True
                break
        if not is_allowed:
            raise SSRFValidationError(f"Domain '{hostname}' is not in the configured allow-list.")

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

    # Resolve hostname to IP addresses
    try:
        addr_info = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise SSRFValidationError(f"Could not resolve hostname '{hostname}': {e}")

    if not addr_info:
        raise SSRFValidationError(f"No IP addresses resolved for '{hostname}'")

    first_ip = None
    for item in addr_info:
        sockaddr = item[4]
        ip_str = sockaddr[0]
        if not first_ip:
            first_ip = ip_str

        ip_obj = ipaddress.ip_address(ip_str)

        # Cloud metadata endpoint protection (e.g., AWS/GCP/Azure: 169.254.169.254)
        if str(ip_obj) == "169.254.169.254":
            raise SSRFValidationError("Requests to cloud instance metadata service (169.254.169.254) are forbidden.")

        if not allow_private_ranges:
            for blocked_net in BLOCKED_NETWORKS:
                if ip_obj in blocked_net:
                    raise SSRFValidationError(
                        f"Resolved address '{ip_str}' belongs to restricted network '{blocked_net}'. "
                        "Access to internal/private networks is blocked by default."
                    )

    return url, str(first_ip), port

