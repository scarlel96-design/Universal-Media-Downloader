"""Bulk image downloads on one asyncio loop and one HTTPX client.

The client does not follow redirects. Each hop is checked again. Slots are
held only while a response is open, and the whole body is never buffered.
Proxy and Tor settings are not read from the environment.
"""

from __future__ import annotations

import asyncio
import heapq
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx

from umd.download.images import _allocate, _filename, sniff_image
from umd.download.pin import PinnedBackend, empty_pins
from umd.download.schedule import RETRYABLE_STATUS, EngineConfig, HostBook, SlotGate, retry_delay
from umd.netpolicy import USER_AGENT, assess_public_url, is_allowed_url, strip_userinfo

_PERMANENT = "permanent"
_RETRY = "retry"
_RESTART = "restart"
_PAUSED = "paused"
_CANCEL = "cancel"
_DONE = "done"


@dataclass
class DownloadItem:
    item_id: str
    url: str
    priority: int = 0
    status: str = "대기"
    part_path: str = ""
    reserved_path: str = ""
    downloaded: int = 0
    total: int | None = None
    etag: str = ""
    last_modified: str = ""
    resume_capable: int | None = None
    retry_count: int = 0
    note: str = ""


@dataclass
class ItemEvent:
    item_id: str
    status: str
    path: str = ""
    size: int = 0
    downloaded: int = 0
    total: int = -1
    error: str = ""
    http_status: int | None = None
    etag: str = ""
    last_modified: str = ""
    resume_capable: int = -1
    retry_count: int = 0
    part_path: str = ""
    note: str = ""
    host: str = ""
    terminal: bool = False
    checkpoint: bool = False
    py_thread: int = 0
    priority: int = 0
    host_limit: int = 0
    host_streak: int = 0
    host_in_flight: int = 0

    def to_json(self) -> str:
        payload = {
            "itemId": self.item_id,
            "status": self.status,
            "path": self.path,
            "size": self.size,
            "downloaded": self.downloaded,
            "total": self.total,
            "error": self.error,
            "httpStatus": self.http_status,
            "etag": self.etag,
            "lastModified": self.last_modified,
            "resumeCapable": self.resume_capable,
            "retryCount": self.retry_count,
            "partPath": self.part_path,
            "note": self.note,
            "host": self.host,
            "terminal": self.terminal,
            "checkpoint": self.checkpoint,
            "pyThread": self.py_thread,
            "priority": self.priority,
            "hostLimit": self.host_limit,
            "hostStreak": self.host_streak,
            "hostInFlight": self.host_in_flight,
        }
        return json.dumps(payload, ensure_ascii=False)


@dataclass
class _Outcome:
    kind: str
    delay: float = 0.0
    error: str = ""
    http_status: int | None = None


def _host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _parse_content_range(value: str | None) -> tuple[int, int, int | None] | None:
    if not value:
        return None
    text = value.strip().lower()
    if not text.startswith("bytes"):
        return None
    try:
        span, _, total_text = text.split(" ", 1)[1].partition("/")
        start_text, _, end_text = span.partition("-")
        start = int(start_text)
        end = int(end_text)
        total = None if total_text.strip() == "*" else int(total_text)
    except (ValueError, IndexError):
        return None
    if end < start:
        return None
    return start, end, total


class _Names:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reserved: set[str] = set()

    def take(self, directory: Path, url: str, kind: str, preferred: str) -> Path:
        with self._lock:
            if preferred:
                path = Path(preferred)
                if path.parent == directory and path.name and not path.exists():
                    if path.name not in self._reserved:
                        self._reserved.add(path.name)
                    return path
            allocated = _allocate(directory, _filename(url, kind), self._reserved)
            return allocated


class DownloadEngine:
    def __init__(
        self,
        directory: str | Path,
        items: list[DownloadItem],
        config: EngineConfig | None = None,
        *,
        on_event=None,
    ) -> None:
        self.directory = Path(directory)
        self.items = items
        self.config = config or EngineConfig()
        self._on_event = on_event or (lambda _event: None)
        global_limit, per_host = self.config.limits()
        self._global = SlotGate(global_limit)
        self._hosts = HostBook(per_host)
        self._names = _Names()
        self._pause = False
        self._cancel_all = False
        self._cancel_ids: set[str] = set()
        self._resume = asyncio.Event()
        self._resume.set()
        self._client: httpx.AsyncClient | None = None
        self._pins = empty_pins()
        self._tasks: dict[str, asyncio.Task[str]] = {}
        self._last_emit: dict[str, float] = {}
        self._persisted_at: dict[str, int] = {}
        self._accounted: dict[str, int] = {}
        self._done_bytes = 0
        self._seq = 0
        self._pending_limits: tuple[int, int] | None = None
        self.peak_connections = 0
        self.events: list[ItemEvent] = []

    @property
    def global_limit(self) -> int:
        return self._global.limit

    def request_pause(self) -> None:
        self._pause = True
        self._resume.clear()

    def request_resume(self) -> None:
        self._pause = False
        self._resume.set()

    def request_cancel_all(self) -> None:
        self._cancel_all = True
        self._pause = False
        self._resume.set()
        for task in list(self._tasks.values()):
            task.cancel()

    def request_cancel_one(self, item_id: str) -> None:
        self._cancel_ids.add(item_id)
        task = self._tasks.get(item_id)
        if task is not None:
            task.cancel()

    def request_limits(self, global_limit: int, per_host: int) -> None:
        self._pending_limits = (max(1, int(global_limit)), max(1, int(per_host)))

    async def _apply_pending_limits(self) -> None:
        pending = getattr(self, "_pending_limits", None)
        if not pending:
            return
        self._pending_limits = None
        global_limit, per_host = pending
        await self._global.set_limit(global_limit)
        await self._hosts.retarget(per_host)

    async def run(self) -> None:
        if not self.directory.is_dir():
            for item in self.items:
                self._emit(item, status="실패", error="저장 경로가 올바르지 않습니다", terminal=True)
            return
        global_limit, _per_host = self.config.limits()
        pool = max(24, global_limit)
        public = self.config.network_mode == "public"
        timeout = (
            httpx.Timeout(self.config.timeout, connect=min(10.0, self.config.timeout))
            if public
            else httpx.Timeout(self.config.timeout)
        )
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "identity",
        }
        limits = httpx.Limits(
            max_connections=pool,
            max_keepalive_connections=0 if public else pool,
        )
        client_kwargs: dict = {
            "follow_redirects": False,
            "timeout": timeout,
            "headers": headers,
            "trust_env": False,
        }
        if self.config.transport is not None:
            client_kwargs["transport"] = self.config.transport
        elif public:
            transport = httpx.AsyncHTTPTransport(trust_env=False, retries=0, limits=limits)
            transport._pool._network_backend = PinnedBackend(transport._pool._network_backend, self._pins)
            client_kwargs["transport"] = transport
        else:
            client_kwargs["limits"] = limits
        async with httpx.AsyncClient(**client_kwargs) as client:
            self._client = client
            try:
                await self._schedule()
            finally:
                self._client = None
        self.peak_connections = self._global.peak

    async def _schedule(self) -> None:
        queue: list[tuple[int, int, DownloadItem]] = []
        seen: set[str] = set()
        for item in self.items:
            if item.item_id in seen:
                self._emit(item, status="실패", error="같은 항목이 이미 큐에 있습니다", terminal=True)
                continue
            seen.add(item.item_id)
            if item.status == "완료":
                continue
            self._push(queue, item)
        running: set[asyncio.Task[str]] = set()
        owners: dict[asyncio.Task[str], DownloadItem] = {}
        while queue or running:
            await self._apply_pending_limits()
            if self._cancel_all:
                for task in list(running):
                    task.cancel()
                while queue:
                    _priority, _seq, queued = heapq.heappop(queue)
                    self._finish_cancel(queued)
            if self._pause and not self._cancel_all:
                if running:
                    done, running = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
                    self._collect(done, owners, queue)
                    continue
                await self._resume.wait()
                continue
            window = max(1, self._global.limit * 2)
            while queue and len(running) < window and not self._pause and not self._cancel_all:
                _priority, _seq, item = heapq.heappop(queue)
                if item.item_id in self._cancel_ids:
                    self._finish_cancel(item)
                    continue
                task = asyncio.create_task(self._guard(item))
                self._tasks[item.item_id] = task
                running.add(task)
                owners[task] = item
            if not running:
                if queue and self._pause:
                    continue
                break
            done, running = await asyncio.wait(
                running, timeout=0.05, return_when=asyncio.FIRST_COMPLETED
            )
            self._collect(done, owners, queue)
        for task in running:
            owners.pop(task, None)

    def _collect(
        self,
        done: set[asyncio.Task[str]],
        owners: dict[asyncio.Task[str], DownloadItem],
        queue: list[tuple[int, int, DownloadItem]],
    ) -> None:
        for task in done:
            item = owners.pop(task)
            self._tasks.pop(item.item_id, None)
            try:
                action = task.result()
            except asyncio.CancelledError:
                continue
            if action == _PAUSED:
                self._push(queue, item)

    def _push(self, queue: list[tuple[int, int, DownloadItem]], item: DownloadItem) -> None:
        self._seq += 1
        heapq.heappush(queue, (-int(item.priority), self._seq, item))

    async def _guard(self, item: DownloadItem) -> str:
        host = _host_of(strip_userinfo(item.url))
        try:
            return await self._run_item(item, host)
        except asyncio.CancelledError:
            self._discard(item)
            self._accounted.pop(item.item_id, None)
            self._finish_cancel(item)
            raise

    async def _run_item(self, item: DownloadItem, host: str) -> str:
        while True:
            if self._cancel_all or item.item_id in self._cancel_ids:
                self._discard(item)
                self._finish_cancel(item)
                return _CANCEL
            if self._pause:
                self._emit(item, status="일시정지", checkpoint=True)
                return _PAUSED
            gate = await self._hosts.acquire(host)
            try:
                await self._global.acquire()
                try:
                    outcome = await self._once(item, host)
                finally:
                    await self._global.release()
            finally:
                await gate.release()
            if outcome.kind == _DONE:
                await self._hosts.reward(host)
                return _DONE
            if outcome.kind == _PAUSED:
                return _PAUSED
            if outcome.kind == _CANCEL:
                return _CANCEL
            if outcome.kind == _RESTART:
                continue
            if outcome.kind == _PERMANENT:
                self._discard(item)
                self._accounted.pop(item.item_id, None)
                self._emit(
                    item,
                    status="실패",
                    error=outcome.error,
                    http_status=outcome.http_status,
                    terminal=True,
                )
                return "fail"
            item.retry_count += 1
            await self._hosts.penalize(host)
            if item.retry_count > self.config.max_retries:
                self._discard(item)
                self._accounted.pop(item.item_id, None)
                self._emit(
                    item,
                    status="실패",
                    error=outcome.error or "다운로드에 실패했습니다",
                    http_status=outcome.http_status,
                    terminal=True,
                )
                return "fail"
            reason = await self._sleep(outcome.delay, item.item_id)
            if reason == _CANCEL:
                self._discard(item)
                self._finish_cancel(item)
                return _CANCEL
            if reason == _PAUSED:
                self._emit(item, status="일시정지", checkpoint=True)
                return _PAUSED

    async def _sleep(self, delay: float, item_id: str) -> str | None:
        left = max(0.0, delay)
        while left > 0:
            if self._cancel_all or item_id in self._cancel_ids:
                return _CANCEL
            if self._pause:
                return _PAUSED
            step = min(0.05, left)
            await asyncio.sleep(step)
            left -= step
        if self._cancel_all or item_id in self._cancel_ids:
            return _CANCEL
        if self._pause:
            return _PAUSED
        return None

    def _admit(self, url: str, *, redirect: bool) -> tuple[str | None, str]:
        if self.config.network_mode == "public":
            decision = assess_public_url(url, resolver=self.config.resolver)
            if not decision.allowed:
                message = decision.message or "허용되지 않은 주소입니다"
                if redirect:
                    message = f"리다이렉트 주소가 허용되지 않습니다: {message}"
                return None, message
            self._pins.remember(decision.host, decision.port, decision.pin)
            return decision.safe_url, ""
        if not is_allowed_url(url):
            message = "리다이렉트 주소가 허용되지 않습니다" if redirect else "허용되지 않은 주소입니다"
            return None, message
        return strip_userinfo(url), ""

    async def _once(self, item: DownloadItem, host: str) -> _Outcome:
        url, error = self._admit(item.url, redirect=False)
        if url is None:
            return _Outcome(_PERMANENT, error=error)
        if urlsplit(url).scheme == "file":
            return self._save_file_url(item, url)
        try:
            return await self._http(item, url, host, depth=0)
        except httpx.TimeoutException:
            return _Outcome(_RETRY, delay=self._backoff(item), error="시간이 초과되었습니다")
        except httpx.TransportError as exc:
            return _Outcome(_RETRY, delay=self._backoff(item), error=_safe_transport(exc))

    def _backoff(self, item: DownloadItem) -> float:
        return retry_delay(
            max(1, item.retry_count + 1),
            None,
            cap=self.config.backoff_cap,
            base=self.config.backoff_base,
        )

    async def _http(self, item: DownloadItem, url: str, host: str, depth: int) -> _Outcome:
        assert self._client is not None
        have = self._local_bytes(item)
        headers: dict[str, str] = {}
        if have > 0:
            headers["Range"] = f"bytes={have}-"
            if item.etag:
                headers["If-Range"] = item.etag
            elif item.last_modified:
                headers["If-Range"] = item.last_modified
        response = await self._client.send(self._client.build_request("GET", url, headers=headers), stream=True)
        try:
            status = response.status_code
            if status in {301, 302, 303, 307, 308}:
                return await self._redirect(item, response, host, depth)
            if self.config.network_mode == "public" and status in {401, 403}:
                if status == 401:
                    return _Outcome(_PERMANENT, error="인증이 필요합니다 (HTTP 401)", http_status=401)
                return _Outcome(_PERMANENT, error="접근이 거부되었습니다 (HTTP 403)", http_status=403)
            if status in RETRYABLE_STATUS:
                delay = retry_delay(
                    max(1, item.retry_count + 1),
                    response.headers.get("retry-after"),
                    cap=self.config.retry_after_cap,
                    base=self.config.backoff_base,
                )
                return _Outcome(_RETRY, delay=delay, error=f"HTTP {status}", http_status=status)
            if 400 <= status < 500:
                return _Outcome(_PERMANENT, error=f"HTTP {status}", http_status=status)
            if status not in {200, 206}:
                return _Outcome(_PERMANENT, error=f"HTTP {status}", http_status=status)
            etag = response.headers.get("etag") or ""
            modified = response.headers.get("last-modified") or ""
            if status == 206:
                parsed = _parse_content_range(response.headers.get("content-range"))
                if parsed is None or parsed[0] != have:
                    return _Outcome(_PERMANENT, error="HTTP 206 범위가 요청과 다릅니다", http_status=206)
                if item.etag and etag and item.etag != etag:
                    self._discard(item)
                    item.downloaded = 0
                    item.etag = ""
                    item.last_modified = ""
                    item.note = "원본 변경"
                    return _Outcome(_RESTART, http_status=206)
                item.resume_capable = 1
                item.total = parsed[2] if parsed[2] is not None else item.total
                expected = parsed[1] - parsed[0] + 1
                return await self._consume(
                    item, response, append_at=have, expected=expected, etag=etag, modified=modified, host=host
                )
            if have > 0:
                changed = bool(item.etag and etag and item.etag != etag)
                self._discard(item)
                item.downloaded = 0
                item.note = "원본 변경" if changed else "재개 불가"
                item.resume_capable = 1 if changed else 0
                if changed:
                    item.etag = ""
                    item.last_modified = ""
            declared = _content_length(response)
            if declared is not None:
                item.total = declared
            return await self._consume(
                item, response, append_at=0, expected=declared, etag=etag, modified=modified, host=host
            )
        finally:
            await _close_quietly(response)

    async def _redirect(self, item: DownloadItem, response: httpx.Response, host: str, depth: int) -> _Outcome:
        location = response.headers.get("location") or ""
        status = response.status_code
        current = str(response.url)
        await _close_quietly(response)
        if depth >= 3 or not location:
            return _Outcome(_PERMANENT, error="리다이렉트 주소가 허용되지 않습니다", http_status=status)
        target = urljoin(current, location)
        safe, error = self._admit(target, redirect=True)
        if safe is None or urlsplit(safe).scheme == "file":
            return _Outcome(
                _PERMANENT,
                error=error or "리다이렉트 주소가 허용되지 않습니다",
                http_status=status,
            )
        return await self._http(item, safe, _host_of(safe), depth + 1)

    async def _consume(
        self,
        item: DownloadItem,
        response: httpx.Response,
        *,
        append_at: int,
        expected: int | None,
        etag: str,
        modified: str,
        host: str,
    ) -> _Outcome:
        if expected is not None and self.config.per_file_cap is not None:
            full = append_at + expected
            if full > self.config.per_file_cap:
                self._discard(item)
                return _Outcome(_PERMANENT, error="파일 크기 상한을 넘습니다", http_status=response.status_code)
        projected = append_at + expected if expected is not None else append_at
        if expected is not None and not self._fits_total(item, projected):
            self._discard(item)
            return _Outcome(_PERMANENT, error="전체 용량 상한을 넘습니다", http_status=response.status_code)
        if expected is not None:
            self._accounted[item.item_id] = projected
        part = self._part_for(item, append_at)
        written = 0
        try:
            with part.open("r+b") as handle:
                handle.seek(append_at)
                handle.truncate(append_at)
                async for chunk in response.aiter_bytes(self.config.chunk_size):
                    if self._cancel_all or item.item_id in self._cancel_ids:
                        handle.truncate(0)
                        handle.close()
                        self._discard(item)
                        self._finish_cancel(item)
                        return _Outcome(_CANCEL)
                    if self._pause:
                        handle.flush()
                        item.downloaded = append_at + written
                        self._accounted[item.item_id] = item.downloaded
                        self._emit(item, status="일시정지", checkpoint=True, http_status=response.status_code)
                        return _Outcome(_PAUSED)
                    if not chunk:
                        continue
                    next_size = append_at + written + len(chunk)
                    if self.config.per_file_cap is not None and next_size > self.config.per_file_cap:
                        handle.truncate(0)
                        self._discard(item)
                        return _Outcome(_PERMANENT, error="파일 크기 상한을 넘습니다", http_status=response.status_code)
                    if not self._fits_total(item, next_size):
                        handle.truncate(0)
                        self._discard(item)
                        return _Outcome(_PERMANENT, error="전체 용량 상한을 넘습니다", http_status=response.status_code)
                    handle.write(chunk)
                    written += len(chunk)
                    item.downloaded = append_at + written
                    self._accounted[item.item_id] = item.downloaded
                    if etag:
                        item.etag = etag
                    if modified:
                        item.last_modified = modified
                    self._maybe_progress(item, response.status_code)
        except httpx.TransportError:
            self._truncate_part(part, append_at)
            item.downloaded = append_at
            return _Outcome(_RETRY, delay=self._backoff(item), error="응답이 잘렸습니다", http_status=response.status_code)
        if written <= 0 and append_at <= 0:
            self._discard(item)
            return _Outcome(_PERMANENT, error="빈 응답", http_status=response.status_code)
        if expected is not None and written != expected:
            self._truncate_part(part, append_at)
            item.downloaded = append_at
            return _Outcome(_RETRY, delay=self._backoff(item), error="응답이 잘렸습니다", http_status=response.status_code)
        item.downloaded = append_at + written
        if item.total is None:
            item.total = item.downloaded
        if etag:
            item.etag = etag
        if modified:
            item.last_modified = modified
        return self._commit(item, part, response.status_code, host)

    def _fits_total(self, item: DownloadItem, next_size: int) -> bool:
        cap = self.config.total_cap
        if cap is None:
            return True
        others = self._done_bytes
        for key, value in self._accounted.items():
            if key != item.item_id:
                others += value
        return others + next_size <= cap

    def _save_file_url(self, item: DownloadItem, url: str) -> _Outcome:
        from urllib.request import url2pathname

        source = Path(url2pathname(urlsplit(url).path))
        if not source.is_file():
            return _Outcome(_PERMANENT, error="원본 파일을 찾지 못했습니다")
        data_size = source.stat().st_size
        if self.config.per_file_cap is not None and data_size > self.config.per_file_cap:
            return _Outcome(_PERMANENT, error="파일 크기 상한을 넘습니다")
        if not self._fits_total(item, data_size):
            return _Outcome(_PERMANENT, error="전체 용량 상한을 넘습니다")
        part = self.directory / f".umd-{uuid4().hex}.part"
        item.part_path = str(part)
        written = 0
        with source.open("rb") as incoming, part.open("wb") as handle:
            while True:
                chunk = incoming.read(self.config.chunk_size)
                if not chunk:
                    break
                handle.write(chunk)
                written += len(chunk)
                item.downloaded = written
        item.total = written
        return self._commit(item, part, 200, "")

    def _commit(self, item: DownloadItem, part: Path, http_status: int, host: str) -> _Outcome:
        if item.downloaded <= 0 or not part.is_file():
            self._discard(item)
            return _Outcome(_PERMANENT, error="빈 응답", http_status=http_status)
        with part.open("rb") as handle:
            kind = sniff_image(handle.read(16))
        if kind is None:
            self._discard(item)
            return _Outcome(_PERMANENT, error="허용되지 않은 이미지 형식", http_status=http_status)
        target = self._names.take(self.directory, item.url, kind, item.reserved_path)
        item.reserved_path = str(target)
        self._emit(
            item,
            status="다운로드 중",
            path=str(target),
            http_status=http_status,
            checkpoint=True,
        )
        os.replace(part, target)
        item.part_path = ""
        if not target.is_file() or target.stat().st_size != item.downloaded:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
            return _Outcome(_PERMANENT, error="저장한 파일 크기가 응답과 다릅니다", http_status=http_status)
        self._done_bytes += item.downloaded
        self._accounted.pop(item.item_id, None)
        self._emit(
            item,
            status="완료",
            path=str(target),
            http_status=http_status,
            terminal=True,
        )
        return _Outcome(_DONE, http_status=http_status)

    def _local_bytes(self, item: DownloadItem) -> int:
        if not item.part_path:
            return 0
        part = Path(item.part_path)
        if not part.is_file():
            item.part_path = ""
            item.downloaded = 0
            return 0
        size = part.stat().st_size
        item.downloaded = size
        return size

    def _part_for(self, item: DownloadItem, append_at: int) -> Path:
        if append_at > 0 and item.part_path and Path(item.part_path).is_file():
            return Path(item.part_path)
        part = self.directory / f".umd-{uuid4().hex}.part"
        part.touch()
        item.part_path = str(part)
        item.downloaded = 0
        return part

    def _maybe_progress(self, item: DownloadItem, http_status: int) -> None:
        now = time.monotonic()
        last = self._last_emit.get(item.item_id, 0.0)
        persisted = self._persisted_at.get(item.item_id, -1)
        checkpoint = persisted < 0 or item.downloaded - persisted >= 256 * 1024
        if not checkpoint and now - last < 0.1:
            return
        self._last_emit[item.item_id] = now
        if checkpoint:
            self._persisted_at[item.item_id] = item.downloaded
        self._emit(item, status="다운로드 중", http_status=http_status, checkpoint=checkpoint)

    def _emit(
        self,
        item: DownloadItem,
        *,
        status: str,
        error: str = "",
        path: str = "",
        http_status: int | None = None,
        terminal: bool = False,
        checkpoint: bool = False,
    ) -> None:
        host = _host_of(strip_userinfo(item.url))
        active, limit, streak = self._hosts.stats(host)
        if error and _secret_in(error, item.url):
            error = "다운로드에 실패했습니다"
        event = ItemEvent(
            item_id=item.item_id,
            status=status,
            path=path or (item.reserved_path if terminal and status == "완료" else ""),
            size=item.downloaded if (terminal and status == "완료") or (checkpoint and path) else 0,
            downloaded=item.downloaded,
            total=-1 if item.total is None else int(item.total),
            error="" if status == "완료" else error,
            http_status=http_status,
            etag=item.etag,
            last_modified=item.last_modified,
            resume_capable=-1 if item.resume_capable is None else int(item.resume_capable),
            retry_count=item.retry_count,
            part_path="" if terminal and status == "완료" else item.part_path,
            note="" if status != "완료" else item.note,
            host=host,
            terminal=terminal,
            checkpoint=checkpoint or terminal,
            priority=item.priority,
            host_limit=limit,
            host_streak=streak,
            host_in_flight=active,
        )
        if terminal and status == "완료":
            event.path = path or item.reserved_path
            event.size = item.downloaded
            event.part_path = ""
        elif checkpoint and path:
            event.path = path
        item.status = status
        self._on_event(event)

    def _finish_cancel(self, item: DownloadItem) -> None:
        if item.status == "취소":
            return
        self._accounted.pop(item.item_id, None)
        self._emit(item, status="취소", error="사용자가 취소했습니다", terminal=True)

    def _discard(self, item: DownloadItem) -> None:
        if item.part_path:
            try:
                Path(item.part_path).unlink(missing_ok=True)
            except OSError:
                pass
        item.part_path = ""
        item.downloaded = 0

    def _truncate_part(self, part: Path, size: int) -> None:
        try:
            with part.open("r+b") as handle:
                handle.truncate(size)
        except OSError:
            pass


async def _close_quietly(response: httpx.Response) -> None:
    """Close a streamed response without turning a finished transfer into a retry.

    On Windows the lab server shuts the socket down after the body. httpx then
    raises while releasing the connection, which used to replace a 429 or a
    completed 200 with a transport retry.
    """
    try:
        await response.aclose()
    except (httpx.HTTPError, OSError, RuntimeError):
        return


def _content_length(response: httpx.Response) -> int | None:
    raw = response.headers.get("content-length")
    if raw and raw.isdigit():
        return int(raw)
    return None


def _safe_transport(exc: BaseException) -> str:
    text = str(exc)
    if "timed out" in text.lower() or "timeout" in text.lower():
        return "시간이 초과되었습니다"
    return "연결이 끊어졌습니다"


def _secret_in(error: str, url: str) -> bool:
    parts = urlsplit(url)
    secret = parts.password or parts.username or ""
    return bool(secret) and secret in error


def run_job(
    directory: str | Path,
    items: list[DownloadItem],
    config: EngineConfig | None = None,
    *,
    on_event=None,
) -> DownloadEngine:
    events: list[ItemEvent] = []

    def _collect(event: ItemEvent) -> None:
        events.append(event)
        if on_event is not None:
            on_event(event)

    engine = DownloadEngine(directory, items, config, on_event=_collect)
    asyncio.run(engine.run())
    engine.events = events
    return engine
