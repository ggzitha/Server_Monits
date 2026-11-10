"""
http_poller.py - Safe HTTP Polling Client with SSRF Protection
"""
import logging
from typing import Any, Dict, Optional
import httpx

from backend.app.services.ssrf_guard import validate_url_for_ssrf, SSRFValidationError

logger = logging.getLogger("server_monits.http_poller")


def extract_json_path(data: Any, path: Optional[str]) -> Any:
    """Extract nested value using dot-notation path, e.g. 'telemetry.temp_c'."""
    if not path or not path.strip() or path == "$":
        return data

    parts = path.strip().lstrip("$.").split(".")
    curr = data
    for p in parts:
        if isinstance(curr, dict) and p in curr:
            curr = curr[p]
        elif isinstance(curr, list) and p.isdigit():
            idx = int(p)
            if 0 <= idx < len(curr):
                curr = curr[idx]
            else:
                return None
        else:
            return None
    return curr


async def execute_safe_http_poll(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_path: Optional[str] = None,
    timeout_seconds: float = 5.0,
    allow_private_ranges: bool = False,
) -> Dict[str, Any]:
    """
    Perform an SSRF-safe HTTP GET request, validate redirect targets,
    and parse the response JSON.
    """
    validate_url_for_ssrf(url, allow_private_ranges=allow_private_ranges)

    req_headers = {"User-Agent": "ServerMonits-Poller/1.0", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    # Disable automatic redirects to prevent open-redirect SSRF bypasses
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
        current_url = url
        max_redirects = 3
        redirect_count = 0

        while True:
            try:
                resp = await client.get(current_url, headers=req_headers)
            except httpx.TimeoutException:
                raise ValueError(f"HTTP request timed out after {timeout_seconds}s")
            except Exception as e:
                raise ValueError(f"HTTP request failed: {e}")

            # Check redirect
            if resp.status_code in (301, 302, 303, 307, 308):
                redirect_count += 1
                if redirect_count > max_redirects:
                    raise ValueError("Too many HTTP redirects (max 3)")
                location = resp.headers.get("location")
                if not location:
                    raise ValueError(f"Redirect status {resp.status_code} with missing Location header")

                # Re-validate redirect target for SSRF
                resolved_location = str(httpx.URL(current_url).join(location))
                validate_url_for_ssrf(resolved_location, allow_private_ranges=allow_private_ranges)
                current_url = resolved_location
                continue
            break

        if resp.status_code >= 400:
            raise ValueError(f"HTTP error {resp.status_code}: {resp.text[:200]}")

        try:
            body = resp.json()
        except Exception:
            raise ValueError(f"Failed to parse response as JSON: {resp.text[:100]}")

        extracted = extract_json_path(body, json_path)
        return {
            "status_code": resp.status_code,
            "raw_body": body,
            "extracted_data": extracted,
            "url": current_url,
        }

