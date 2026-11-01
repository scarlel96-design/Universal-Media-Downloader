"""Open a separate browser window so the user can log in.

The program does not type a password, solve a CAPTCHA, or walk around a
login form. The user closes the window when they are done. The cookie jar
stays in the temp session store for that host only.
"""

from __future__ import annotations

import time
from urllib.parse import urlsplit

from umd.auth.session import SessionStore
from umd.extract.browser import browser_enabled
from umd.net.policy_proxy import PolicyProxy
from umd.netpolicy import ExtractError


def open_login_window(url: str, store: SessionStore, *, headless: bool = False, interact=None) -> None:
    if not browser_enabled():
        raise ExtractError("브라우저 분석은 이 환경에서 비활성화되어 있습니다")
    from playwright.sync_api import sync_playwright

    from umd.extract.browser import _gate, _goto

    host = (urlsplit(url).hostname or "").lower()
    local = host in {"127.0.0.1", "localhost"}
    proxy = None if local else PolicyProxy("public")
    browser = None
    try:
        with sync_playwright() as playwright:
            launch = {
                "headless": headless,
                "args": ["--disable-dev-shm-usage", "--js-flags=--max-old-space-size=256"],
            }
            if proxy is not None:
                launch["proxy"] = {"server": proxy.url, "bypass": "<-loopback>"}
            browser = playwright.chromium.launch(**launch)
            context = browser.new_context(viewport={"width": 1100, "height": 720})
            page = context.new_page()
            page.route("**/*", lambda route: _gate(route, "local" if local else "public"))
            _goto(page, url)
            if interact is not None:
                interact(page)
            elif not headless:
                page.wait_for_event("close", timeout=0)
            state = context.storage_state()
            store.save(host, state, expires_at=time.time() + 3600)
            context.close()
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if proxy is not None:
            proxy.close()
