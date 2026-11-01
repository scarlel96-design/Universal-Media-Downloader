"""Connect to an address that was already checked.

httpcore passes the origin hostname into ``connect_tcp`` and later uses that
same hostname for TLS SNI. Replacing only the TCP target keeps the Host header
and the certificate name on the site, while the socket goes to the pinned
address. A missing pin fails closed instead of resolving again.
"""

from __future__ import annotations

import httpcore

from umd.netpolicy import pin_keys


class _PinTable:
    def __init__(self) -> None:
        self._pins: dict[tuple[str, int], str] = {}

    def remember(self, host: str, port: int, ip: str) -> None:
        for key in pin_keys(host, port):
            self._pins[key] = ip

    def lookup(self, host: str, port: int) -> str:
        for key in pin_keys(host, port):
            found = self._pins.get(key)
            if found:
                return found
        raise httpcore.ConnectError("연결 주소가 확인되지 않았습니다")


class PinnedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, inner: httpcore.AsyncNetworkBackend, table: _PinTable) -> None:
        self._inner = inner
        self._table = table

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ):
        target = self._table.lookup(host, port)
        return await self._inner.connect_tcp(
            target, port, timeout=timeout, local_address=local_address, socket_options=socket_options
        )

    async def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options=None):
        raise httpcore.ConnectError("unix 소켓은 허용되지 않습니다")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class PinnedSyncBackend(httpcore.NetworkBackend):
    def __init__(self, inner: httpcore.NetworkBackend, table: _PinTable) -> None:
        self._inner = inner
        self._table = table

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ):
        target = self._table.lookup(host, port)
        return self._inner.connect_tcp(
            target, port, timeout=timeout, local_address=local_address, socket_options=socket_options
        )

    def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options=None):
        raise httpcore.ConnectError("unix 소켓은 허용되지 않습니다")

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)


def empty_pins() -> _PinTable:
    return _PinTable()
