"""Fetch a local HTML fixture. Public hosts are refused before any connection.

Redirects are not followed automatically. Each hop is checked before it is opened.
"""

from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, url2pathname

from umd.netpolicy import is_allowed_url, strip_userinfo

_LIMIT = 2_000_000


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def fetch_text(url: str) -> tuple[str, str]:
    """Return ``(final_url, html)``. Raises if the URL is not a local fixture."""
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


def _fetch_http(url: str) -> tuple[str, bytes]:
    opener = build_opener(_NoRedirect)
    current = url
    last_reset: ConnectionResetError | None = None
    for _hop in range(4):
        if not is_allowed_url(current):
            raise PermissionError("리다이렉트 주소가 허용되지 않습니다")
        request = Request(current, headers={"User-Agent": "UniversalMediaDownloader/0.1"})
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
