"""Fetch HTML. Local mode refuses public hosts. Public mode checks every hop.

Redirects are not followed automatically. Each hop is checked before it is opened.
"""

from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, url2pathname

import httpx

from umd.download.pin import PinnedSyncBackend, empty_pins
from umd.netpolicy import (
    AuthError,
    HttpAccessError,
    PolicyError,
    USER_AGENT,
    assess_public_url,
    is_allowed_url,
    strip_userinfo,
)

_LIMIT = 2_000_000


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def fetch_text(url: str, *, network_mode: str = "local") -> tuple[str, str]:
    """Return ``(final_url, html)``. Local mode raises if the URL is not a fixture."""
    if network_mode == "public":
        final, data = _fetch_public(url)
    else:
        if not is_allowed_url(url):
            raise PermissionError("허용되지 않은 주소입니다")
        parts = urlsplit(url)
        if parts.scheme == "file":
            data = Path(url2pathname(parts.path)).read_bytes()
            final = strip_userinfo(url)
        else:
            final, data = _fetch_http(strip_userinfo(url))
    if len(data) > _LIMIT:
        raise ValueError("HTML이 너무 큽니다")
    return final, data.decode("utf-8", errors="replace")


def _fetch_public(url: str) -> tuple[str, bytes]:
    current = strip_userinfo(url)
    pins = empty_pins()
    transport = httpx.HTTPTransport(trust_env=False, retries=0)
    transport._pool._network_backend = PinnedSyncBackend(transport._pool._network_backend, pins)
    timeout = httpx.Timeout(20.0, connect=10.0)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Encoding": "identity",
    }
    with httpx.Client(
        transport=transport,
        follow_redirects=False,
        trust_env=False,
        timeout=timeout,
        headers=headers,
    ) as client:
        for hop in range(4):
            decision = assess_public_url(current)
            if not decision.allowed:
                message = decision.message or "허용되지 않은 주소입니다"
                if hop:
                    message = f"리다이렉트 주소가 허용되지 않습니다: {message}"
                raise PolicyError(message)
            pins.remember(decision.host, decision.port, decision.pin)
            with client.stream("GET", decision.safe_url) as response:
                status = response.status_code
                if status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location") or ""
                    if not location:
                        raise PolicyError("리다이렉트 주소가 허용되지 않습니다")
                    current = strip_userinfo(urljoin(str(response.url), location))
                    continue
                if status in {401, 403}:
                    if status == 401:
                        raise AuthError("인증이 필요합니다 (HTTP 401)")
                    raise AuthError("접근이 거부되었습니다 (HTTP 403)")
                if status != 200:
                    raise HttpAccessError(f"HTTP {status}")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > _LIMIT:
                        raise ValueError("HTML이 너무 큽니다")
                    chunks.append(chunk)
                return strip_userinfo(str(response.url)), b"".join(chunks)
    raise PolicyError("리다이렉트 주소가 허용되지 않습니다")


def _fetch_http(url: str) -> tuple[str, bytes]:
    opener = build_opener(_NoRedirect)
    current = url
    last_reset: ConnectionResetError | None = None
    for _hop in range(4):
        if not is_allowed_url(current):
            raise PermissionError("리다이렉트 주소가 허용되지 않습니다")
        request = Request(current, headers={"User-Agent": USER_AGENT})
        for _attempt in range(4):
            try:
                with opener.open(request, timeout=20) as response:
                    final = strip_userinfo(response.geturl())
                    if not is_allowed_url(final):
                        raise PermissionError("리다이렉트 주소가 허용되지 않습니다")
                    return final, response.read(_LIMIT + 1)
            except HTTPError as exc:
                if exc.code in {301, 302, 303, 307, 308}:
                    location = exc.headers.get("Location")
                    exc.close()
                    if not location:
                        raise PermissionError("리다이렉트 주소가 허용되지 않습니다") from exc
                    current = strip_userinfo(urljoin(current, location))
                    break
                exc.close()
                raise
            except ConnectionResetError as exc:
                last_reset = exc
        else:
            assert last_reset is not None
            raise last_reset
    raise PermissionError("리다이렉트 주소가 허용되지 않습니다")
