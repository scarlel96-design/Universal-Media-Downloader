"""Background fetch and one download thread. SQLite writes are serialized."""

from __future__ import annotations

import asyncio
import json
import threading

from PySide6.QtCore import QObject, Signal, Slot

from umd.download.engine import DownloadEngine, DownloadItem, ItemEvent
from umd.download.schedule import EngineConfig
from umd.extract.fetch import fetch_text
from umd.extract.html_images import extract_images
from umd.storage.database import Library


class ExtractWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url

    @Slot()
    def run(self) -> None:
        try:
            final, html = fetch_text(self._url)
            candidates = extract_images(html, final)
            payload = json.dumps(
                {"pageUrl": final, "items": [item.as_dict() for item in candidates]},
                ensure_ascii=False,
            )
            self.finished.emit(payload)
        except Exception as exc:  # noqa: BLE001 — shown in the shell toast
            self.failed.emit(str(exc))


def _item_from_row(row: dict) -> DownloadItem:
    capable = row.get("resumeCapable", -1)
    return DownloadItem(
        item_id=str(row.get("itemId") or ""),
        url=str(row.get("fetchUrl") or row.get("mediaUrl") or ""),
        priority=int(row.get("priority") or 0),
        status=str(row.get("status") or "대기"),
        part_path=str(row.get("partPath") or ""),
        reserved_path=str(row.get("savedPath") or ""),
        downloaded=int(row.get("downloaded") or 0),
        total=int(row["totalSize"]) if int(row.get("totalSize") or 0) > 0 else None,
        etag=str(row.get("etag") or ""),
        last_modified=str(row.get("lastModified") or ""),
        resume_capable=None if capable is None or int(capable) < 0 else int(capable),
        retry_count=int(row.get("retryCount") or 0),
        note=str(row.get("note") or ""),
    )


def _db_values(event: ItemEvent) -> dict:
    values: dict = {
        "status": event.status,
        "downloaded_bytes": event.downloaded,
        "retry_count": event.retry_count,
        "etag": event.etag,
        "last_modified": event.last_modified,
        "note": event.note,
        "part_path": event.part_path,
        "priority": event.priority,
    }
    if event.total >= 0:
        values["total_size"] = event.total
    if event.resume_capable >= 0:
        values["resume_capable"] = event.resume_capable
    if event.http_status is not None:
        values["http_status"] = event.http_status
    if event.terminal or event.path:
        values["path"] = event.path
        values["size"] = event.size if event.size else event.downloaded
        values["error"] = event.error
    return values


class DownloadWorker(QObject):
    item_finished = Signal(str)
    progress = Signal(str)
    finished = Signal()

    def __init__(
        self,
        items: list[dict],
        directory: str,
        *,
        library: Library | None = None,
        config: EngineConfig | None = None,
    ) -> None:
        super().__init__()
        self._items = items
        self._directory = directory
        self._library = library
        self._config = config or EngineConfig()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._engine: DownloadEngine | None = None
        self._thread_id = 0
        self._cancel_early = False
        self._pause_early = False

    @Slot()
    def cancel(self) -> None:
        self._cancel_early = True
        self._pause_early = False
        self._call(lambda engine: engine.request_cancel_all())

    @Slot()
    def pause(self) -> None:
        self._pause_early = True
        self._call(lambda engine: engine.request_pause())

    @Slot()
    def resume(self) -> None:
        self._call(lambda engine: engine.request_resume())

    @Slot(str)
    def cancelOne(self, item_id: str) -> None:
        self._call(lambda engine: engine.request_cancel_one(item_id))

    @Slot(int, int)
    def setLimits(self, global_limit: int, per_host: int) -> None:
        self._call(lambda engine: engine.request_limits(global_limit, per_host))

    def _call(self, action) -> None:
        loop = self._loop
        engine = self._engine
        if loop is None or engine is None or not loop.is_running():
            return
        loop.call_soon_threadsafe(action, engine)

    @Slot()
    def run(self) -> None:
        self._thread_id = threading.get_ident()
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        engine = DownloadEngine(
            self._directory,
            [_item_from_row(row) for row in self._items],
            self._config,
            on_event=self._on_event,
        )
        self._engine = engine
        if self._pause_early:
            engine.request_pause()
        if self._cancel_early:
            engine.request_cancel_all()
        try:
            loop.run_until_complete(engine.run())
        finally:
            self.finished.emit()
            self._engine = None
            loop.close()
            self._loop = None

    def _on_event(self, event: ItemEvent) -> None:
        event.py_thread = self._thread_id or threading.get_ident()
        if self._library is not None and (event.checkpoint or event.terminal):
            self._library.apply_transfer(event.item_id, _db_values(event))
            if event.host:
                self._library.note_host(
                    event.host,
                    http_status=event.http_status,
                    error_streak=event.host_streak,
                    concurrency_limit=event.host_limit,
                    in_flight=event.host_in_flight,
                )
        payload = event.to_json()
        if event.terminal:
            self.item_finished.emit(payload)
        else:
            self.progress.emit(payload)
