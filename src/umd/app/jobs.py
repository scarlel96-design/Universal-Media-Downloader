"""Background fetch and one download thread. SQLite writes are serialized."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from umd.download.engine import DownloadEngine, DownloadItem, ItemEvent
from umd.download.schedule import EngineConfig
from umd.storage.database import Library


class ExtractWorker(QObject):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, network_mode: str = "local") -> None:
        super().__init__()
        self._url = url
        self._mode = network_mode if network_mode in {"local", "public"} else "local"

    @Slot()
    def run(self) -> None:
        try:
            from umd.extract.router import extract_page

            result = extract_page(self._url, network_mode=self._mode)
            self.finished.emit(json.dumps(result.payload(), ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001 — shown in the shell toast
            self.failed.emit(str(exc))


def _split_rows(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    images: list[dict] = []
    videos: list[dict] = []
    galleries: list[dict] = []
    for row in rows:
        delivery = str(row.get("delivery") or "")
        if delivery == "yt-dlp" or (row.get("kind") == "video" and delivery != "http"):
            videos.append(row)
        elif delivery == "gallery-dl":
            galleries.append(row)
        else:
            images.append(row)
    return images, videos, galleries


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
        self._video_marks: dict[str, int] = {}

    @Slot()
    def cancel(self) -> None:
        self._cancel_early = True
        self._pause_early = False
        try:
            (Path(self._directory) / ".umd-cancel").write_text("1", encoding="ascii")
        except OSError:
            pass
        self._call(lambda engine: engine.request_cancel_all())

    @Slot()
    def pause(self) -> None:
        self._pause_early = True
        self._call(lambda engine: engine.request_pause())

    @Slot()
    def resume(self) -> None:
        self._pause_early = False
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
        images, videos, galleries = _split_rows(self._items)
        try:
            if images:
                self._run_images(images)
            if self._cancel_early:
                self._cancel_rest(videos + galleries)
            else:
                self._run_galleries(galleries)
                self._run_videos(videos)
        finally:
            self.finished.emit()
            self._engine = None
            loop = self._loop
            self._loop = None
            if loop is not None and not loop.is_closed():
                loop.close()

    def _run_images(self, rows: list[dict]) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        engine = DownloadEngine(
            self._directory,
            [_item_from_row(row) for row in rows],
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
            self._engine = None

    def _run_galleries(self, rows: list[dict]) -> None:
        if not rows:
            return
        from umd.download.gallery_job import download_selected

        groups: dict[str, list[dict]] = {}
        for row in rows:
            if row.get("selected", True) is False:
                continue
            page = str(row.get("mediaReference") or row.get("pageUrl") or "")
            groups.setdefault(page, []).append(row)
        for page, group in groups.items():
            if self._cancel_early:
                for row in group:
                    self._emit_row(row, status="취소", terminal=True)
                continue
            only = {
                str(row.get("originalUrl") or row.get("fetchUrl") or "")
                for row in group
            }
            only.discard("")
            try:
                batch = download_selected(
                    page,
                    Path(self._directory),
                    only,
                    should_stop=lambda: self._cancel_early,
                )
            except Exception as exc:  # noqa: BLE001 — one page failure is not an extractor failure
                for row in group:
                    self._emit_row(row, status="실패", error=str(exc)[:300], terminal=True)
                continue
            saved = {item.url: item for item in batch.files}
            for row in group:
                url = str(row.get("originalUrl") or row.get("fetchUrl") or "")
                item = saved.get(url)
                if item is None or item.state == "cancelled":
                    status = "취소" if batch.cancelled or self._cancel_early else "실패"
                    error = "" if status == "취소" else "저장한 파일이 없습니다"
                    self._emit_row(row, status=status, error=error, terminal=True)
                    continue
                if item.state == "failed":
                    self._emit_row(row, status="실패", error=item.error or "저장에 실패했습니다", terminal=True)
                    continue
                note = "이미 저장된 파일" if item.state == "existing" else ""
                self._emit_row(
                    row,
                    status="완료",
                    path=item.path,
                    size=item.size,
                    downloaded=item.size,
                    total=item.size,
                    note=note,
                    terminal=True,
                )

    def _run_videos(self, rows: list[dict]) -> None:
        pending = list(rows)
        while pending:
            if self._cancel_early:
                self._cancel_rest(pending)
                return
            if self._pause_early:
                time.sleep(0.05)
                continue
            row = pending.pop(0)
            if self._one_video(row) == "pause":
                pending.insert(0, row)

    def _one_video(self, row: dict) -> str:
        from umd.download.video_job import TransferStop, download_video

        page = str(row.get("mediaReference") or row.get("pageUrl") or row.get("fetchUrl") or "")
        page = page.split("#", 1)[0]
        self._emit_row(row, status="다운로드 중")

        def should_stop() -> str:
            if self._cancel_early:
                return "cancel"
            if self._pause_early:
                return "pause"
            return ""

        def on_progress(downloaded: int, total: int) -> None:
            self._emit_row(row, status="다운로드 중", downloaded=downloaded, total=total)

        try:
            path, size = download_video(
                page,
                Path(self._directory),
                format_id=str(row.get("formatId") or ""),
                should_stop=should_stop,
                on_progress=on_progress,
            )
        except TransferStop as exc:
            if exc.reason == "pause":
                self._emit_row(row, status="일시정지", checkpoint=True)
                return "pause"
            self._emit_row(row, status="취소", terminal=True)
            return "cancel"
        except Exception as exc:  # noqa: BLE001 — download failure, not an extractor failure
            self._emit_row(row, status="실패", error=str(exc)[:300], terminal=True)
            return "fail"
        self._emit_row(
            row,
            status="완료",
            path=str(path),
            size=size,
            downloaded=size,
            total=size if size > 0 else -1,
            terminal=True,
        )
        return "done"

    def _cancel_rest(self, rows: list[dict]) -> None:
        for row in rows:
            self._emit_row(row, status="취소", terminal=True)

    def _emit_row(
        self,
        row: dict,
        *,
        status: str,
        downloaded: int = 0,
        total: int = -1,
        path: str = "",
        size: int = 0,
        error: str = "",
        note: str = "",
        terminal: bool = False,
        checkpoint: bool = False,
    ) -> None:
        item_id = str(row.get("itemId") or "")
        mark = total >= 0 and downloaded > 0 and downloaded - self._video_marks.get(item_id, 0) >= 256 * 1024
        if mark:
            self._video_marks[item_id] = downloaded
        event = ItemEvent(
            item_id=item_id,
            status=status,
            path=path,
            size=size,
            downloaded=downloaded,
            total=total,
            error="" if status == "완료" else error,
            note=note,
            terminal=terminal,
            checkpoint=checkpoint or terminal or mark,
            priority=int(row.get("priority") or 0),
        )
        self._on_event(event)

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
