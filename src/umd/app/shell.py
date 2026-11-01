"""QML-facing state for the sample library and for extracted image jobs."""

from __future__ import annotations

import json
import threading
import time
from collections import deque

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QModelIndex,
    QObject,
    QSortFilterProxyModel,
    Qt,
    QThread,
    Signal,
    Slot,
)

from umd.app.catalog import CATALOG, accepts_kind
from umd.app.host import windows_reduce_motion
from umd.app.jobs import DownloadWorker, ExtractWorker
from umd.app.motion import TOKENS
from umd.app.tokens import DARK, LIGHT
from umd.download.schedule import PRESETS, EngineConfig
from umd.extract.html_images import CLASS_LABELS
from umd.netpolicy import is_allowed_url
from umd.storage.database import Library, media_hue

_SAMPLE_STATUS = "원본은 저장하지 않음 · 분석 엔진 미연결"


def _sample_row(title: str, kind: str, selected: bool, hue: int) -> dict:
    return {
        "title": title,
        "kind": kind,
        "selected": selected,
        "hue": hue,
        "previewUrl": "",
        "classification": "content",
        "reasons": "",
        "status": "대기",
        "fetchUrl": "",
        "mediaUrl": "",
        "pageUrl": "",
        "override": "",
        "itemId": "",
        "error": "",
        "savedPath": "",
        "byteSize": 0,
        "downloaded": 0,
        "totalSize": 0,
        "progress": -1.0,
        "partPath": "",
        "etag": "",
        "lastModified": "",
        "resumeCapable": -1,
        "retryCount": 0,
        "priority": 0,
        "note": "",
    }


def row_from_candidate(item: dict, page_url: str) -> dict:
    classification = str(item["classification"])
    reasons = item.get("reasons") or []
    if isinstance(reasons, list):
        reasons = " · ".join(str(part) for part in reasons)
    url = str(item["url"])
    return {
        "title": str(item.get("title") or "image"),
        "kind": "image",
        "selected": classification == "content",
        "hue": media_hue(url),
        "previewUrl": url,
        "classification": classification,
        "reasons": reasons,
        "status": "대기",
        "fetchUrl": url,
        "mediaUrl": url,
        "pageUrl": page_url,
        "override": "",
        "itemId": "",
        "error": "",
        "savedPath": "",
        "byteSize": 0,
        "downloaded": 0,
        "totalSize": 0,
        "progress": -1.0,
        "partPath": "",
        "etag": "",
        "lastModified": "",
        "resumeCapable": -1,
        "retryCount": 0,
        "priority": 0,
        "note": "",
    }


def _format_bytes(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{int(size)} B"


def _format_eta(seconds: float | None) -> str:
    if seconds is None:
        return "계산 중"
    whole = max(0, int(seconds))
    if whole < 60:
        return f"{whole}초"
    return f"{whole // 60}분 {whole % 60}초"


class MediaListModel(QAbstractListModel):
    TitleRole = Qt.ItemDataRole.UserRole + 1
    KindRole = Qt.ItemDataRole.UserRole + 2
    SelectedRole = Qt.ItemDataRole.UserRole + 3
    HueRole = Qt.ItemDataRole.UserRole + 4
    PreviewRole = Qt.ItemDataRole.UserRole + 5
    ClassificationRole = Qt.ItemDataRole.UserRole + 6
    ReasonsRole = Qt.ItemDataRole.UserRole + 7
    StatusRole = Qt.ItemDataRole.UserRole + 8
    OverrideRole = Qt.ItemDataRole.UserRole + 9
    ProgressRole = Qt.ItemDataRole.UserRole + 10
    ResumeRole = Qt.ItemDataRole.UserRole + 11
    NoteRole = Qt.ItemDataRole.UserRole + 12

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows = [
            _sample_row(item.title, item.kind, item.selected, item.hue) for item in CATALOG
        ]

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.TitleRole: b"title",
            self.KindRole: b"kind",
            self.SelectedRole: b"selected",
            self.HueRole: b"hue",
            self.PreviewRole: b"previewUrl",
            self.ClassificationRole: b"classification",
            self.ReasonsRole: b"reasons",
            self.StatusRole: b"status",
            self.OverrideRole: b"override",
            self.ProgressRole: b"progress",
            self.ResumeRole: b"resumeCapable",
            self.NoteRole: b"note",
        }

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, self.TitleRole):
            return row["title"]
        if role == self.KindRole:
            return row["kind"]
        if role == self.SelectedRole:
            return row["selected"]
        if role == self.HueRole:
            return row["hue"]
        if role == self.PreviewRole:
            return row.get("previewUrl") or ""
        if role == self.ClassificationRole:
            return row.get("classification") or "content"
        if role == self.ReasonsRole:
            return row.get("reasons") or ""
        if role == self.StatusRole:
            return row.get("status") or "대기"
        if role == self.OverrideRole:
            return row.get("override") or ""
        if role == self.ProgressRole:
            return float(row.get("progress", -1.0))
        if role == self.ResumeRole:
            return int(row.get("resumeCapable", -1))
        if role == self.NoteRole:
            return row.get("note") or ""
        return None

    def item(self, row: int) -> dict:
        return self._rows[row]

    def replace(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def find_id(self, item_id: str) -> dict | None:
        for row in self._rows:
            if row.get("itemId") == item_id:
                return row
        return None

    def _changed(self, row: int, roles: list[int]) -> None:
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, roles)

    def toggle(self, row: int) -> bool:
        item = self._rows[row]
        item["selected"] = not item["selected"]
        visibility = False
        if item.get("classification") in {"excluded", "uncertain"}:
            item["override"] = "included" if item["selected"] else ""
            visibility = item.get("classification") == "excluded"
        self._changed(row, [self.SelectedRole, self.OverrideRole])
        return visibility

    def set_selected_visible(self, proxy: QSortFilterProxyModel, selected: bool) -> bool:
        visibility = False
        for source_row in range(len(self._rows)):
            source_index = self.index(source_row, 0)
            if not proxy.mapFromSource(source_index).isValid():
                continue
            item = self._rows[source_row]
            item["selected"] = selected
            if item.get("classification") == "excluded":
                override = "included" if selected else ""
                if item.get("override") != override:
                    visibility = True
                item["override"] = override
            elif item.get("classification") == "uncertain":
                item["override"] = "included" if selected else ""
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._rows) - 1, 0),
                [self.SelectedRole, self.OverrideRole],
            )
        return visibility

    def set_status(self, item_id: str, status: str) -> None:
        for row_index, row in enumerate(self._rows):
            if row.get("itemId") == item_id:
                row["status"] = status
                self._changed(row_index, [self.StatusRole])
                return

    def apply_result(self, item_id: str, status: str, path: str, size: int, error: str) -> dict | None:
        for row_index, row in enumerate(self._rows):
            if row.get("itemId") == item_id:
                row["status"] = status
                row["savedPath"] = path
                row["byteSize"] = size
                row["error"] = error
                if status == "완료" and size > 0:
                    row["progress"] = 1.0
                    row["downloaded"] = size
                    row["totalSize"] = size
                self._changed(row_index, [self.StatusRole, self.ProgressRole, self.NoteRole, self.ResumeRole])
                return row
        return None

    def apply_progress(
        self,
        item_id: str,
        downloaded: int,
        total: int,
        status: str,
        note: str,
        resume_capable: int,
    ) -> dict | None:
        for row_index, row in enumerate(self._rows):
            if row.get("itemId") != item_id:
                continue
            if row.get("status") in {"완료", "실패", "취소"} and status not in {"완료", "실패", "취소"}:
                return row
            if status:
                row["status"] = status
            row["downloaded"] = downloaded
            if total > 0:
                row["totalSize"] = total
                row["progress"] = downloaded / total
            else:
                row["progress"] = -1.0
            if note:
                row["note"] = note
            if resume_capable >= 0:
                row["resumeCapable"] = resume_capable
            self._changed(
                row_index,
                [self.StatusRole, self.ProgressRole, self.NoteRole, self.ResumeRole],
            )
            return row
        return None


class KindFilterProxy(QSortFilterProxyModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._mode = "all"
        self._show_excluded = False
        self.setDynamicSortFilter(True)

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        if mode not in {"all", "image", "video"}:
            mode = "all"
        self._mode = mode
        self.invalidate()

    def set_show_excluded(self, enabled: bool) -> None:
        self._show_excluded = bool(enabled)
        self.invalidate()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        kind = model.data(index, MediaListModel.KindRole)
        if not accepts_kind(str(kind), self._mode):
            return False
        classification = model.data(index, MediaListModel.ClassificationRole) or "content"
        override = model.data(index, MediaListModel.OverrideRole) or ""
        if classification == "excluded" and override != "included" and not self._show_excluded:
            return False
        return True


class Palette(QObject):
    changed = Signal()

    def __init__(self, shell: ShellState, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._shell = shell
        shell.themeChanged.connect(self.changed.emit)

    def _value(self, key: str) -> str:
        table = DARK if self._shell.theme == "dark" else LIGHT
        return table[key]

    @Property(str, notify=changed)
    def windowBg(self) -> str:
        return self._value("window_bg")

    @Property(str, notify=changed)
    def canvas(self) -> str:
        return self._value("canvas")

    @Property(str, notify=changed)
    def toolbar(self) -> str:
        return self._value("toolbar")

    @Property(str, notify=changed)
    def sidebar(self) -> str:
        return self._value("sidebar")

    @Property(str, notify=changed)
    def border(self) -> str:
        return self._value("border")

    @Property(str, notify=changed)
    def text(self) -> str:
        return self._value("text")

    @Property(str, notify=changed)
    def title(self) -> str:
        return self._value("title")

    @Property(str, notify=changed)
    def muted(self) -> str:
        return self._value("muted")

    @Property(str, notify=changed)
    def pill(self) -> str:
        return self._value("pill")

    @Property(str, notify=changed)
    def accent(self) -> str:
        return self._value("accent")

    @Property(str, notify=changed)
    def accentText(self) -> str:
        return self._value("accent_text")

    @Property(str, notify=changed)
    def hover(self) -> str:
        return self._value("hover")

    @Property(str, notify=changed)
    def statusBg(self) -> str:
        return self._value("status_bg")

    @Property(str, notify=changed)
    def inspectorBg(self) -> str:
        return self._value("inspector_bg")

    @Property(str, notify=changed)
    def field(self) -> str:
        return self._value("field")

    @Property(str, notify=changed)
    def danger(self) -> str:
        return self._value("danger")


class MotionBridge(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    @Property(int, constant=True)
    def buttonHoverMs(self) -> int:
        return TOKENS["button_hover"].duration_ms

    @Property(int, constant=True)
    def sidebarSelectMs(self) -> int:
        return TOKENS["sidebar_select"].duration_ms

    @Property(int, constant=True)
    def inspectorMs(self) -> int:
        return TOKENS["inspector"].duration_ms

    @Property(float, constant=True)
    def inspectorSpring(self) -> float:
        return float(TOKENS["inspector"].spring or 0)

    @Property(float, constant=True)
    def inspectorDamping(self) -> float:
        return float(TOKENS["inspector"].damping or 0)

    @Property(float, constant=True)
    def inspectorMass(self) -> float:
        return float(TOKENS["inspector"].mass or 1)

    @Property(str, constant=True)
    def inspectorCancel(self) -> str:
        return TOKENS["inspector"].cancel_policy

    @Property(str, constant=True)
    def reducedAlternative(self) -> str:
        return TOKENS["inspector"].reduced_motion

    @Property(int, constant=True)
    def gridSelectMs(self) -> int:
        return TOKENS["grid_select"].duration_ms

    @Property(int, constant=True)
    def thumbnailMs(self) -> int:
        return TOKENS["thumbnail_in"].duration_ms

    @Property(float, constant=True)
    def successSpring(self) -> float:
        return float(TOKENS["success"].spring or 0)

    @Property(float, constant=True)
    def successDamping(self) -> float:
        return float(TOKENS["success"].damping or 0)

    @Property(float, constant=True)
    def successMass(self) -> float:
        return float(TOKENS["success"].mass or 1)


class ShellState(QObject):
    themeChanged = Signal()
    pageChanged = Signal()
    filterChanged = Signal()
    inspectorOpenChanged = Signal()
    sidebarOpenChanged = Signal()
    reduceMotionChanged = Signal()
    countsChanged = Signal()
    detailChanged = Signal()
    toastChanged = Signal()
    urlChanged = Signal()
    jobPhaseChanged = Signal()
    notesChanged = Signal()
    showExcludedChanged = Signal()
    progressChanged = Signal()

    def __init__(
        self,
        model: MediaListModel,
        proxy: KindFilterProxy,
        parent: QObject | None = None,
        *,
        library: Library | None = None,
    ) -> None:
        super().__init__(parent)
        self._model = model
        self._proxy = proxy
        self._library = library
        self._theme = "light"
        self._page = "미디어 보관함"
        self._filter = "all"
        self._inspector = False
        self._sidebar = True
        self._reduce = windows_reduce_motion()
        self._url = ""
        self._toast = ""
        self._detail_title = CATALOG[0].title
        self._detail_kind = CATALOG[0].kind
        self._detail_hue = CATALOG[0].hue
        self._detail_preview = ""
        self._detail_source = "시안 데이터"
        self._detail_relevance = "본문 미디어(예시)"
        self._detail_status = "다운로드 미연결"
        self._detail_reasons = ""
        self._detail_id = ""
        self._phase = "대기"
        self._using_samples = True
        self._show_excluded = False
        self._banner = "콘텐츠가 준비되었습니다 · 디자인 셸"
        self._grid_note = "샘플 콘텐츠 · 본문 우선 필터"
        self._status_line = _SAMPLE_STATUS
        self._download_dir = ""
        self._job_id = ""
        self._off_ui = False
        self._active_ids: list[str] = []
        self._mode = "균형"
        self._per_file_cap: int | None = None
        self._total_cap: int | None = None
        self._metrics_visible = False
        self._metrics_line = ""
        self._overall_percent = -1
        self._detail_progress = ""
        self._done_count = 0
        self._fail_count = 0
        self._bytes: dict[str, tuple[int, int]] = {}
        self._samples: deque[tuple[float, int]] = deque()
        self._extract_thread: QThread | None = None
        self._extract_worker: ExtractWorker | None = None
        self._download_thread: QThread | None = None
        self._download_worker: DownloadWorker | None = None
        model.dataChanged.connect(lambda *_: self.countsChanged.emit())
        proxy.modelReset.connect(self.countsChanged.emit)
        proxy.layoutChanged.connect(self.countsChanged.emit)
        proxy.rowsInserted.connect(lambda *_: self.countsChanged.emit())
        proxy.rowsRemoved.connect(lambda *_: self.countsChanged.emit())

    @Property(str, notify=themeChanged)
    def theme(self) -> str:
        return self._theme

    @Property(str, notify=pageChanged)
    def page(self) -> str:
        return self._page

    @Property(str, notify=filterChanged)
    def filterMode(self) -> str:
        return self._filter

    @Property(bool, notify=inspectorOpenChanged)
    def inspectorOpen(self) -> bool:
        return self._inspector

    @Property(bool, notify=sidebarOpenChanged)
    def sidebarOpen(self) -> bool:
        return self._sidebar

    @Property(bool, notify=reduceMotionChanged)
    def reduceMotion(self) -> bool:
        return self._reduce

    @Property(int, notify=countsChanged)
    def selectedCount(self) -> int:
        return self._count(selected_only=True)

    @Property(int, notify=countsChanged)
    def visibleCount(self) -> int:
        return self._proxy.rowCount()

    @Property(str, notify=detailChanged)
    def detailTitle(self) -> str:
        return self._detail_title

    @Property(str, notify=detailChanged)
    def detailKind(self) -> str:
        if self._detail_kind == "video":
            return "영상 샘플"
        if self._detail_id or not self._using_samples:
            return "이미지"
        return "이미지 샘플"

    @Property(int, notify=detailChanged)
    def detailHue(self) -> int:
        return self._detail_hue

    @Property(str, notify=detailChanged)
    def detailPreview(self) -> str:
        return self._detail_preview

    @Property(str, notify=detailChanged)
    def detailSource(self) -> str:
        return self._detail_source

    @Property(str, notify=detailChanged)
    def detailRelevance(self) -> str:
        return self._detail_relevance

    @Property(str, notify=detailChanged)
    def detailStatus(self) -> str:
        return self._detail_status

    @Property(str, notify=detailChanged)
    def detailReasons(self) -> str:
        return self._detail_reasons

    @Property(str, notify=toastChanged)
    def toast(self) -> str:
        return self._toast

    @Property(str, notify=urlChanged)
    def url(self) -> str:
        return self._url

    @Property(str, notify=jobPhaseChanged)
    def jobPhase(self) -> str:
        return self._phase

    @Property(bool, notify=jobPhaseChanged)
    def downloadOffUiThread(self) -> bool:
        return self._off_ui

    @Property(str, notify=notesChanged)
    def banner(self) -> str:
        return self._banner

    @Property(str, notify=notesChanged)
    def gridNote(self) -> str:
        return self._grid_note

    @Property(str, notify=notesChanged)
    def statusLine(self) -> str:
        return self._status_line

    @Property(str, notify=progressChanged)
    def downloadMode(self) -> str:
        return self._mode

    @Property(bool, notify=progressChanged)
    def metricsVisible(self) -> bool:
        return self._metrics_visible

    @Property(str, notify=progressChanged)
    def metricsLine(self) -> str:
        return self._metrics_line

    @Property(int, notify=progressChanged)
    def overallPercent(self) -> int:
        return self._overall_percent

    @Property(str, notify=detailChanged)
    def detailProgress(self) -> str:
        return self._detail_progress

    @Property(int, notify=progressChanged)
    def doneCount(self) -> int:
        return self._done_count

    @Property(int, notify=progressChanged)
    def failedCount(self) -> int:
        return self._fail_count

    @Property(bool, notify=showExcludedChanged)
    def showExcluded(self) -> bool:
        return self._show_excluded

    @Property(bool, notify=notesChanged)
    def usingSamples(self) -> bool:
        return self._using_samples

    def _count(self, selected_only: bool) -> int:
        total = 0
        for row in range(self._model.rowCount()):
            source = self._model.index(row, 0)
            if not self._proxy.mapFromSource(source).isValid():
                continue
            if selected_only and not self._model.item(row)["selected"]:
                continue
            total += 1
        return total

    def _notify(self, message: str) -> None:
        self._toast = message
        self.toastChanged.emit()

    def _refresh_notes(self) -> None:
        if self._using_samples and self._phase == "추출 중":
            self._banner = "추출 중"
            self._status_line = "추출 중"
            return
        if self._using_samples and self._phase == "실패":
            self._banner = "실패"
            self._status_line = "실패"
            return
        if self._using_samples:
            self._banner = "콘텐츠가 준비되었습니다 · 디자인 셸"
            self._grid_note = "샘플 콘텐츠 · 본문 우선 필터"
            self._status_line = _SAMPLE_STATUS
            return
        counts = {"content": 0, "uncertain": 0, "excluded": 0}
        for index in range(self._model.rowCount()):
            label = self._model.item(index).get("classification") or "content"
            if label in counts:
                counts[label] += 1
        self._grid_note = (
            f"본문 {counts['content']} · 불확실 {counts['uncertain']} · 제외 {counts['excluded']}"
        )
        self._banner = self._phase
        if self._metrics_visible and self._phase in {"다운로드 중", "일시정지"}:
            self._status_line = self._metrics_line or self._phase
        else:
            self._status_line = self._phase

    def _set_phase(self, phase: str, *, persist: bool = True) -> None:
        self._phase = phase
        if persist and self._library is not None and self._job_id:
            self._library.set_job_status(self._job_id, phase)
        self._refresh_notes()
        self.jobPhaseChanged.emit()
        self.notesChanged.emit()

    def _persist_row(self, row: dict) -> None:
        if self._library is None or not row.get("itemId"):
            return
        self._library.update_selection(
            row["itemId"], bool(row["selected"]), row.get("override") or ""
        )

    def _persist_visible(self) -> None:
        for index in range(self._model.rowCount()):
            self._persist_row(self._model.item(index))

    def item_at(self, proxy_row: int) -> dict | None:
        source = self._proxy.mapToSource(self._proxy.index(proxy_row, 0))
        if not source.isValid():
            return None
        return self._model.item(source.row())

    def adopt_job(self, job: dict) -> None:
        self._job_id = str(job["id"])
        self._using_samples = False
        self._phase = str(job["status"])
        self._url = str(job["page_url"])
        self._refresh_notes()
        self.jobPhaseChanged.emit()
        self.notesChanged.emit()
        self.urlChanged.emit()
        self.countsChanged.emit()

    def joinWorkers(self) -> None:
        for thread in (self._extract_thread, self._download_thread):
            if thread is not None and thread.isRunning():
                thread.wait(5000)

    @Slot()
    def toggleTheme(self) -> None:
        self._theme = "dark" if self._theme == "light" else "light"
        self.themeChanged.emit()

    @Slot(str)
    def setPage(self, page: str) -> None:
        self._page = page
        self.pageChanged.emit()
        self._notify("화면 이동은 셸 미리보기입니다. 다운로드 엔진은 연결되지 않았습니다.")

    @Slot(str)
    def setFilter(self, mode: str) -> None:
        self._filter = mode if mode in {"all", "image", "video"} else "all"
        self._proxy.set_mode(self._filter)
        self.filterChanged.emit()
        self.countsChanged.emit()

    @Slot()
    def toggleInspector(self) -> None:
        self._inspector = not self._inspector
        self.inspectorOpenChanged.emit()

    @Slot()
    def toggleSidebar(self) -> None:
        self._sidebar = not self._sidebar
        self.sidebarOpenChanged.emit()

    @Slot(bool)
    def setReduceMotion(self, enabled: bool) -> None:
        self._reduce = bool(enabled)
        self.reduceMotionChanged.emit()

    @Slot()
    def toggleReduceMotion(self) -> None:
        self.setReduceMotion(not self._reduce)

    @Slot(str)
    def setUrl(self, value: str) -> None:
        self._url = value
        self.urlChanged.emit()

    @Slot(str)
    def setDownloadDirectory(self, path: str) -> None:
        self._download_dir = path

    @Slot()
    def toggleShowExcluded(self) -> None:
        self._show_excluded = not self._show_excluded
        self._proxy.set_show_excluded(self._show_excluded)
        self.showExcludedChanged.emit()
        self.countsChanged.emit()

    @Slot(int)
    def activate(self, proxy_row: int) -> None:
        proxy_index = self._proxy.index(proxy_row, 0)
        source = self._proxy.mapToSource(proxy_index)
        if not source.isValid():
            return
        visibility = self._model.toggle(source.row())
        item = self._model.item(source.row())
        self._persist_row(item)
        self._show_detail(item)
        self.countsChanged.emit()
        if visibility:
            self._proxy.invalidate()
        if not self._inspector:
            self._inspector = True
            self.inspectorOpenChanged.emit()

    def _show_detail(self, item: dict) -> None:
        self._detail_title = item["title"]
        self._detail_kind = item["kind"]
        self._detail_hue = int(item["hue"])
        self._detail_id = item.get("itemId") or ""
        fetch = item.get("fetchUrl") or ""
        if not fetch:
            self._detail_preview = ""
            self._detail_source = "시안 데이터"
            self._detail_relevance = "본문 미디어(예시)"
            self._detail_status = "다운로드 미연결"
            self._detail_reasons = ""
        else:
            classification = item.get("classification") or "uncertain"
            self._detail_preview = item.get("previewUrl") or ""
            self._detail_source = item.get("mediaUrl") or fetch
            self._detail_relevance = CLASS_LABELS.get(classification, classification)
            self._detail_status = item.get("status") or "대기"
            self._detail_reasons = item.get("reasons") or ""
        self.detailChanged.emit()

    @Slot()
    def selectAllVisible(self) -> None:
        if self._model.set_selected_visible(self._proxy, True):
            self._proxy.invalidate()
        self._persist_visible()
        self.countsChanged.emit()

    @Slot()
    def clearSelection(self) -> None:
        if self._model.set_selected_visible(self._proxy, False):
            self._proxy.invalidate()
        self._persist_visible()
        self.countsChanged.emit()

    @Slot(str, result=int)
    def findVisible(self, title: str) -> int:
        for proxy_row in range(self._proxy.rowCount()):
            item = self.item_at(proxy_row)
            if item and item["title"] == title:
                return proxy_row
        return -1

    @Slot()
    def analyze(self) -> None:
        if not self._url.strip():
            self._notify("분석할 URL이 없습니다. 주소 입력은 미리보기만 동작합니다.")
            return
        if self._extract_thread is not None and self._extract_thread.isRunning():
            self._notify("이미 추출 중입니다.")
            return
        if not is_allowed_url(self._url.strip()):
            self._notify("이 단계에서는 로컬 파일과 127.0.0.1 테스트 서버만 분석합니다.")
            return
        self._set_phase("추출 중", persist=False)
        worker = ExtractWorker(self._url.strip())
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_extracted)
        worker.failed.connect(self._on_extract_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        self._extract_worker = worker
        self._extract_thread = thread
        thread.start()

    @Slot(str)
    def _on_extracted(self, payload: str) -> None:
        data = json.loads(payload)
        page_url = str(data.get("pageUrl") or self._url.strip())
        rows = [row_from_candidate(item, page_url) for item in data.get("items") or []]
        if self._library is not None:
            self._job_id = self._library.create_job(page_url, rows)
        self._using_samples = False
        self._show_excluded = False
        self._proxy.set_show_excluded(False)
        self.showExcludedChanged.emit()
        self._filter = "all"
        self._proxy.set_mode("all")
        self.filterChanged.emit()
        self._model.replace(rows)
        shown = next((row for row in rows if row["classification"] == "content"), None)
        if shown is None and rows:
            shown = rows[0]
        if shown is not None:
            self._show_detail(shown)
        self._set_phase("추출 완료")
        content = sum(1 for row in rows if row["classification"] == "content")
        excluded = sum(1 for row in rows if row["classification"] == "excluded")
        self._notify(f"본문 이미지 {content}개, 제외 {excluded}개입니다.")
        self.countsChanged.emit()

    @Slot(str)
    def _on_extract_failed(self, message: str) -> None:
        self._set_phase("실패", persist=False)
        self._notify(message or "추출에 실패했습니다.")

    def _selected_targets(self) -> list[dict]:
        targets: list[dict] = []
        for row in range(self._model.rowCount()):
            source = self._model.index(row, 0)
            if not self._proxy.mapFromSource(source).isValid():
                continue
            item = self._model.item(row)
            if item.get("selected") and item.get("fetchUrl"):
                targets.append(dict(item))
        return targets

    def _pick_directory(self) -> str:
        from PySide6.QtWidgets import QApplication, QFileDialog

        app = QApplication.instance()
        if not isinstance(app, QApplication):
            return ""
        return QFileDialog.getExistingDirectory(None, "이미지를 저장할 폴더")

    @Slot()
    def download(self) -> None:
        rows = [self._model.item(index) for index in range(self._model.rowCount())]
        if not any(row.get("fetchUrl") for row in rows):
            self._notify("다운로드 엔진은 연결되지 않았습니다. 파일은 저장하지 않습니다.")
            return
        if self._download_thread is not None and self._download_thread.isRunning():
            self._notify("이미 다운로드 중입니다.")
            return
        targets = [item for item in self._selected_targets() if item.get("status") != "완료"]
        if not targets:
            selected = self._selected_targets()
            if selected and all(item.get("status") == "완료" for item in selected):
                self._notify("이미 완료된 항목입니다.")
            else:
                self._notify("선택된 이미지가 없습니다.")
            return
        directory = self._download_dir.strip()
        if not directory:
            directory = self._pick_directory()
        if not directory:
            self._notify("저장 폴더가 선택되지 않았습니다.")
            return
        from pathlib import Path

        if not Path(directory).is_dir():
            self._notify("저장 경로가 올바르지 않습니다.")
            self._set_phase("실패")
            return
        self._off_ui = False
        self._active_ids = [item["itemId"] for item in targets]
        self._bytes = {}
        self._samples.clear()
        self._metrics_visible = True
        self._done_count = 0
        self._fail_count = 0
        self._overall_percent = -1
        self._recompute_metrics()
        for item in targets:
            if item.get("status") not in {"일시정지", "다운로드 중"}:
                self._model.set_status(item["itemId"], "다운로드 중")
            if self._library is not None and item.get("itemId") and not item.get("partPath"):
                self._library.update_download(
                    item["itemId"], status="다운로드 중", path="", size=0, error=""
                )
        self._set_phase("다운로드 중")
        worker = DownloadWorker(
            targets,
            directory,
            library=self._library,
            config=self._engine_config(),
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.item_finished.connect(self._on_item_finished)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_download_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        self._download_worker = worker
        self._download_thread = thread
        thread.start()

    def _engine_config(self) -> EngineConfig:
        global_limit, per_host = PRESETS[self._mode]
        return EngineConfig(
            preset=self._mode,
            global_limit=global_limit,
            per_host=per_host,
            per_file_cap=self._per_file_cap,
            total_cap=self._total_cap,
        )

    @Slot(str)
    def setDownloadMode(self, mode: str) -> None:
        if mode not in PRESETS:
            return
        self._mode = mode
        if self._download_worker is not None:
            global_limit, per_host = PRESETS[mode]
            self._download_worker.setLimits(global_limit, per_host)
        self._recompute_metrics()

    @Slot(int, int)
    def setSizeCaps(self, per_file: int, total: int) -> None:
        self._per_file_cap = per_file if per_file > 0 else None
        self._total_cap = total if total > 0 else None

    @Slot(str, int)
    def setItemPriority(self, item_id: str, priority: int) -> None:
        row = self._model.find_id(item_id)
        if row is not None:
            row["priority"] = int(priority)
        if self._library is not None and item_id:
            self._library.set_priority(item_id, int(priority))

    @Slot()
    def pauseDownload(self) -> None:
        if self._download_worker is None:
            return
        self._download_worker.pause()
        self._set_phase("일시정지")

    @Slot()
    def resumeDownload(self) -> None:
        if self._download_worker is None:
            return
        self._download_worker.resume()
        self._set_phase("다운로드 중")

    @Slot(str)
    def cancelOne(self, item_id: str) -> None:
        if self._download_worker is not None:
            self._download_worker.cancelOne(item_id)

    @Slot()
    def retryFailed(self) -> None:
        if self._download_thread is not None and self._download_thread.isRunning():
            self._notify("이미 다운로드 중입니다.")
            return
        failed: list[dict] = []
        for index in range(self._model.rowCount()):
            item = self._model.item(index)
            if item.get("status") == "실패" and item.get("fetchUrl"):
                item["retryCount"] = 0
                item["status"] = "대기"
                failed.append(dict(item))
        if not failed:
            self._notify("다시 받을 실패 항목이 없습니다.")
            return
        self._active_ids = [item["itemId"] for item in failed]
        directory = self._download_dir.strip()
        if not directory:
            self._notify("저장 폴더가 선택되지 않았습니다.")
            return
        self._metrics_visible = True
        self._samples.clear()
        worker = DownloadWorker(
            failed,
            directory,
            library=self._library,
            config=self._engine_config(),
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.item_finished.connect(self._on_item_finished)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_download_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        self._download_worker = worker
        self._download_thread = thread
        self._set_phase("다운로드 중")
        thread.start()

    @Slot()
    def cancelDownload(self) -> None:
        if self._download_worker is not None:
            self._download_worker.cancel()

    def _remember(self, item_id: str, downloaded: int, total: int, status: str, size: int) -> None:
        if status == "완료" and size > 0:
            self._bytes[item_id] = (size, size)
        else:
            self._bytes[item_id] = (downloaded, total)

    def _recompute_metrics(self) -> None:
        received = 0
        total = 0
        unknown = False
        done = 0
        fail = 0
        for item_id in self._active_ids:
            row = self._model.find_id(item_id)
            got, full = self._bytes.get(item_id, (0, -1))
            if row is not None:
                if row.get("status") == "완료":
                    done += 1
                    if got <= 0:
                        got = int(row.get("byteSize") or 0)
                        full = got if got else full
                elif row.get("status") == "실패":
                    fail += 1
            received += max(0, got)
            if full is None or full < 0:
                unknown = True
            else:
                total += full
        now = time.monotonic()
        self._samples.append((now, received))
        while self._samples and now - self._samples[0][0] > 2.0:
            self._samples.popleft()
        speed = 0.0
        if len(self._samples) >= 2 and now - self._samples[0][0] >= 0.4:
            delta_t = now - self._samples[0][0]
            delta_b = received - self._samples[0][1]
            if delta_t > 0 and delta_b >= 0:
                speed = delta_b / delta_t
        if unknown or total <= 0:
            percent = -1
            eta = None
            remain = "전체 크기 알 수 없음"
        else:
            percent = min(100, int(received * 100 / total)) if total else -1
            remain = _format_bytes(max(0, total - received))
            eta = None if speed <= 0 else max(0.0, (total - received) / speed)
        speed_text = "계산 중" if speed <= 0 else f"{_format_bytes(int(speed))}/s"
        state = "일시정지" if self._phase == "일시정지" else "받는 중"
        self._done_count = done
        self._fail_count = fail
        self._overall_percent = percent
        self._metrics_line = (
            f"{self._mode} · {state} · 완료 {done} · 실패 {fail} · {remain} · {_format_eta(eta)} · {speed_text}"
        )
        if self._phase in {"다운로드 중", "일시정지"} and self._metrics_visible:
            self._status_line = self._metrics_line
            self.notesChanged.emit()
        self.progressChanged.emit()

    @Slot(str)
    def _on_progress(self, payload: str) -> None:
        data = json.loads(payload)
        worker_thread = int(data.get("pyThread") or 0)
        if worker_thread and worker_thread != threading.get_ident():
            self._off_ui = True
        item_id = str(data.get("itemId") or "")
        status = str(data.get("status") or "")
        downloaded = int(data.get("downloaded") or 0)
        total = int(data.get("total") if data.get("total") is not None else -1)
        note = str(data.get("note") or "")
        capable = int(data.get("resumeCapable") if data.get("resumeCapable") is not None else -1)
        self._model.apply_progress(item_id, downloaded, total, status, note, capable)
        self._remember(item_id, downloaded, total, status, 0)
        if item_id == self._detail_id:
            if total > 0:
                self._detail_progress = f"{_format_bytes(downloaded)} / {_format_bytes(total)}"
            elif downloaded > 0:
                self._detail_progress = f"{_format_bytes(downloaded)} · 전체 크기 알 수 없음"
            else:
                self._detail_progress = ""
            self._detail_status = status or self._detail_status
            self.detailChanged.emit()
        self._recompute_metrics()

    @Slot(str)
    def _on_item_finished(self, payload: str) -> None:
        data = json.loads(payload)
        worker_thread = int(data.get("pyThread") or 0)
        if worker_thread and worker_thread != threading.get_ident():
            self._off_ui = True
        item_id = str(data.get("itemId") or "")
        status = str(data.get("status") or "실패")
        path = str(data.get("path") or "")
        size = int(data.get("size") or 0)
        error = str(data.get("error") or "")
        note = str(data.get("note") or "")
        capable = int(data.get("resumeCapable") if data.get("resumeCapable") is not None else -1)
        row = self._model.apply_result(item_id, status, path, size, error)
        if row is not None:
            row["note"] = note
            row["resumeCapable"] = capable
            row["etag"] = str(data.get("etag") or "")
            row["partPath"] = "" if status == "완료" else str(data.get("partPath") or "")
        self._remember(item_id, int(data.get("downloaded") or 0), int(data.get("total") or -1), status, size)
        if row is not None and item_id == self._detail_id:
            self._detail_status = status if not note else f"{status} · {note}"
            if size > 0:
                self._detail_progress = _format_bytes(size)
            self.detailChanged.emit()
        self._recompute_metrics()
        self.countsChanged.emit()

    @Slot()
    def _on_download_finished(self) -> None:
        statuses = []
        for item_id in self._active_ids:
            row = self._model.find_id(item_id)
            statuses.append(row["status"] if row else "실패")
        if any(status == "실패" for status in statuses):
            phase = "실패"
        elif any(status == "취소" for status in statuses):
            phase = "취소"
        elif statuses and all(status == "완료" for status in statuses):
            phase = "완료"
        else:
            phase = "실패"
        saved = sum(1 for status in statuses if status == "완료")
        self._recompute_metrics()
        self._set_phase(phase)
        if phase == "완료":
            self._notify(f"{saved}개 파일을 저장했습니다.")
        elif phase == "취소":
            self._notify("다운로드를 취소했습니다.")
        else:
            self._notify("일부 이미지를 저장하지 못했습니다.")


class ShellBundle(QObject):
    """Owns every object the QML shell reads. QML must not delete them."""

    def __init__(self, parent: QObject | None = None, db_path: str | None = None) -> None:
        super().__init__(parent)
        self.library = Library(db_path or ":memory:")
        self.model = MediaListModel(self)
        self.proxy = KindFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.shell = ShellState(self.model, self.proxy, self, library=self.library)
        self.ink = Palette(self.shell, self)
        self.motion = MotionBridge(self)
        job = self.library.latest_job()
        if job is not None:
            self.model.replace(self.library.rows_for(job["id"]))
            self.shell.adopt_job(job)
            pending = [
                note
                for note in self.library.recovery
                if note.startswith("incomplete:") or note.startswith("restart:")
            ]
            if pending:
                self.shell._notify("중단된 다운로드가 있습니다. 재개할 수 있습니다.")

    def expose(self, engine) -> None:
        from PySide6.QtQml import QQmlEngine

        for obj in (self, self.model, self.proxy, self.shell, self.ink, self.motion):
            QQmlEngine.setObjectOwnership(obj, QQmlEngine.ObjectOwnership.CppOwnership)
        context = engine.rootContext()
        context.setContextProperty("shell", self.shell)
        context.setContextProperty("mediaModel", self.proxy)
        context.setContextProperty("ink", self.ink)
        context.setContextProperty("motion", self.motion)
