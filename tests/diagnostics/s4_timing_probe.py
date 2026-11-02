"""External stage probe for WO-REUSE-01-S4.

Patches sit only inside ``installed_probe`` and are removed before the
function returns. The download engine's decisions are unchanged. Nothing in
the returned record stores a URL, a path, or a credential.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import linecache
import socket
import sys
import threading
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _entry in (_ROOT / "src", _ROOT / "tests"):
    _text = str(_entry)
    if _text not in sys.path:
        sys.path.insert(0, _text)

import httpx
from httpcore._async.http11 import AsyncHTTP11Connection
from httpcore._backends.anyio import AnyIOBackend

from umd.download import engine as engine_mod
from umd.download.engine import DownloadEngine, DownloadItem
from umd.download.schedule import EngineConfig, HostBook, SlotGate
from wo02_support import PNG, LabServer, Reply, overlaps

_MILESTONES = (
    "engine_init_start",
    "engine_init_end",
    "loop_entered",
    "client_ready",
    "first_task_scheduled",
    "request_send_start",
    "first_response",
    "last_response",
    "last_file_finalized",
    "tasks_complete",
    "client_closed",
    "asyncio_run_return",
)

_CHAIN = (
    "run_job_enter",
    "engine_init_start",
    "engine_init_end",
    "asyncio_run_enter",
    "loop_entered",
    "client_aenter_start",
    "client_aenter_end",
    "schedule_return",
    "client_aexit_start",
    "client_aexit_end",
    "engine_run_return",
    "asyncio_run_return",
    "run_job_return",
)

_CHAIN_NAMES = (
    "enter_to_init",
    "engine_init",
    "init_to_asyncio_run",
    "loop_prep",
    "loop_to_client_start",
    "httpx_client_enter",
    "schedule_until_tasks_done",
    "tasks_done_to_client_close",
    "httpx_client_close",
    "after_close_until_engine_returns",
    "loop_teardown",
    "after_asyncio_run",
)


class _FILETIME(ctypes.Structure):
    _fields_ = (("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32))


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = (
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    )


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = (
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    )


def _filetime_value(value: _FILETIME) -> int:
    return (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)


def _system_times() -> tuple[int, int, int] | None:
    idle, kernel, user = _FILETIME(), _FILETIME(), _FILETIME()
    ok = ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    )
    if not ok:
        return None
    return _filetime_value(idle), _filetime_value(kernel), _filetime_value(user)


def _process_times() -> tuple[int, int] | None:
    kernel, user = _FILETIME(), _FILETIME()
    created, exited = _FILETIME(), _FILETIME()
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ok = ctypes.windll.kernel32.GetProcessTimes(
        handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)
    )
    if not ok:
        return None
    return _filetime_value(kernel), _filetime_value(user)


def _memory_status() -> dict[str, int] | None:
    status = _MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(status)
    ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    if not ok:
        return None
    return {
        "memory_load_percent": int(status.dwMemoryLoad),
        "avail_phys_bytes": int(status.ullAvailPhys),
        "total_phys_bytes": int(status.ullTotalPhys),
    }


def _working_set() -> int | None:
    counters = _PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(
        handle, ctypes.byref(counters), counters.cb
    )
    if not ok:
        return None
    return int(counters.WorkingSetSize)


def _cpu_percent(before: tuple[int, int, int] | None, after: tuple[int, int, int] | None) -> float | None:
    if before is None or after is None:
        return None
    idle = after[0] - before[0]
    total = (after[1] - before[1]) + (after[2] - before[2])
    if total <= 0:
        return None
    return 100.0 * (total - idle) / total


def _redact(value):
    if isinstance(value, str):
        if "://" in value or "@" in value or "secret" in value.lower():
            return "[redacted]"
        return value
    if isinstance(value, dict):
        return {str(key): _redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, (int, float)) or value is None:
        return value
    if isinstance(value, bool):
        return value
    return "[redacted]"


class ProbeState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.point_ns: dict[str, int] = {}
        self.point_sec: dict[str, float] = {}
        self.first_ns: dict[str, int] = {}
        self.first_sec: dict[str, float] = {}
        self.last_ns: dict[str, int] = {}
        self.last_sec: dict[str, float] = {}
        self.sums: dict[str, int] = {}
        self.counts: dict[str, int] = {}
        self.scheduler_wait_ns: list[int] = []
        self.scheduler_empty_wait_ns: list[int] = []

    def point(self, name: str) -> None:
        now_ns = time.perf_counter_ns()
        now_sec = time.perf_counter()
        with self._lock:
            self.point_ns[name] = now_ns
            self.point_sec[name] = now_sec

    def span_start(self, name: str) -> tuple[int, float]:
        now_ns = time.perf_counter_ns()
        now_sec = time.perf_counter()
        with self._lock:
            if name not in self.first_ns:
                self.first_ns[name] = now_ns
                self.first_sec[name] = now_sec
        return now_ns, now_sec

    def span_end(self, name: str, started_ns: int) -> None:
        now_ns = time.perf_counter_ns()
        now_sec = time.perf_counter()
        with self._lock:
            self.last_ns[name] = now_ns
            self.last_sec[name] = now_sec
            self.sums[name] = self.sums.get(name, 0) + (now_ns - started_ns)
            self.counts[name] = self.counts.get(name, 0) + 1

    def add_ns(self, name: str, delta_ns: int) -> None:
        with self._lock:
            self.sums[name] = self.sums.get(name, 0) + delta_ns
            self.counts[name] = self.counts.get(name, 0) + 1

    def note_scheduler_wait(self, delta_ns: int, empty: bool) -> None:
        with self._lock:
            self.sums["scheduler_wait"] = self.sums.get("scheduler_wait", 0) + delta_ns
            self.counts["scheduler_wait"] = self.counts.get("scheduler_wait", 0) + 1
            if len(self.scheduler_wait_ns) < 64:
                self.scheduler_wait_ns.append(delta_ns)
            if empty:
                self.sums["scheduler_empty_wait"] = self.sums.get("scheduler_empty_wait", 0) + delta_ns
                self.counts["scheduler_empty_wait"] = self.counts.get("scheduler_empty_wait", 0) + 1
                if len(self.scheduler_empty_wait_ns) < 64:
                    self.scheduler_empty_wait_ns.append(delta_ns)


def _install(state: ProbeState, saved: list) -> None:
    def save_attr(obj, name: str, wrapper) -> None:
        # Module attributes must be put back. Deleting them removes the name.
        saved.append((obj, name, getattr(obj, name), True))
        setattr(obj, name, wrapper)

    def save_method(cls, name: str, wrapper) -> None:
        had = name in cls.__dict__
        saved.append((cls, name, getattr(cls, name), had))
        setattr(cls, name, wrapper)

    def wrapped_init(self, *args, **kwargs):
        state.point("engine_init_start")
        try:
            return original_init(self, *args, **kwargs)
        finally:
            state.point("engine_init_end")

    def wrapped_run_job(*args, **kwargs):
        state.point("run_job_enter")
        try:
            return original_run_job(*args, **kwargs)
        finally:
            state.point("run_job_return")

    async def wrapped_engine_run(self):
        state.point("loop_entered")
        try:
            return await original_engine_run(self)
        finally:
            state.point("engine_run_return")

    def wrapped_asyncio_run(main, *args, **kwargs):
        state.point("asyncio_run_enter")
        try:
            return original_asyncio_run(main, *args, **kwargs)
        finally:
            state.point("asyncio_run_return")

    async def wrapped_aenter(self):
        state.point("client_aenter_start")
        try:
            return await original_aenter(self)
        finally:
            state.point("client_aenter_end")

    async def wrapped_aexit(self, *args, **kwargs):
        state.point("client_aexit_start")
        try:
            return await original_aexit(self, *args, **kwargs)
        finally:
            state.point("client_aexit_end")

    async def wrapped_schedule(self):
        original_create = asyncio.create_task
        original_wait = asyncio.wait

        def wrapped_create(coro, **kwargs):
            started = time.perf_counter_ns()
            try:
                return original_create(coro, **kwargs)
            finally:
                state.span_start("first_task")
                state.add_ns("create_task", time.perf_counter_ns() - started)

        async def wrapped_wait(fs, *, timeout=None, return_when=asyncio.ALL_COMPLETED):
            started = time.perf_counter_ns()
            done, pending = await original_wait(fs, timeout=timeout, return_when=return_when)
            if timeout == 0.05:
                state.note_scheduler_wait(time.perf_counter_ns() - started, not done)
            return done, pending

        asyncio.create_task = wrapped_create
        asyncio.wait = wrapped_wait
        try:
            return await original_schedule(self)
        finally:
            asyncio.create_task = original_create
            asyncio.wait = original_wait
            state.point("schedule_return")

    async def wrapped_send(self, request, *args, **kwargs):
        started, _sec = state.span_start("httpx_send")
        try:
            response = await original_send(self, request, *args, **kwargs)
            state.span_end("httpx_send_return", started)
            return response
        finally:
            state.span_end("httpx_send", started)

    async def wrapped_connect(self, *args, **kwargs):
        started, _sec = state.span_start("connect_tcp")
        try:
            return await original_connect(self, *args, **kwargs)
        finally:
            state.span_end("connect_tcp", started)

    async def wrapped_headers(self, request):
        started, _sec = state.span_start("request_headers")
        try:
            return await original_headers(self, request)
        finally:
            state.span_end("request_headers", started)

    async def wrapped_recv(self, request):
        started, _sec = state.span_start("response_headers")
        try:
            return await original_recv(self, request)
        finally:
            state.span_end("response_headers", started)

    def wrapped_getaddrinfo(*args, **kwargs):
        started = time.perf_counter_ns()
        try:
            return original_getaddrinfo(*args, **kwargs)
        finally:
            state.add_ns("getaddrinfo", time.perf_counter_ns() - started)

    def wrapped_replace(src, dst):
        started, _sec = state.span_start("replace")
        try:
            return original_replace(src, dst)
        finally:
            state.span_end("replace", started)

    def wrapped_open(self, mode="r", *args, **kwargs):
        handle = original_open(self, mode, *args, **kwargs)
        text = str(mode)
        try:
            if "w" in text or "a" in text or "+" in text:
                _wrap_io(handle, "write", "body_write", state)
            elif "r" in text:
                _wrap_io(handle, "read", "sniff_read", state)
        except (AttributeError, TypeError):
            state.add_ns("io_wrap_skipped", 0)
        return handle

    def wrapped_admit(self, url, *args, **kwargs):
        started = time.perf_counter_ns()
        try:
            return original_admit(self, url, *args, **kwargs)
        finally:
            state.add_ns("admit", time.perf_counter_ns() - started)

    def wrapped_emit(self, *args, **kwargs):
        started = time.perf_counter_ns()
        try:
            return original_emit(self, *args, **kwargs)
        finally:
            state.add_ns("emit", time.perf_counter_ns() - started)

    def wrapped_part(self, *args, **kwargs):
        started, _sec = state.span_start("part_create")
        try:
            return original_part(self, *args, **kwargs)
        finally:
            state.span_end("part_create", started)

    def wrapped_commit(self, *args, **kwargs):
        started, _sec = state.span_start("commit")
        try:
            return original_commit(self, *args, **kwargs)
        finally:
            state.span_end("commit", started)

    async def wrapped_global_acquire(self):
        started = time.perf_counter_ns()
        try:
            return await original_global_acquire(self)
        finally:
            state.add_ns("slot_gate_acquire", time.perf_counter_ns() - started)

    async def wrapped_host_acquire(self, host):
        started = time.perf_counter_ns()
        try:
            return await original_host_acquire(self, host)
        finally:
            state.add_ns("host_gate_acquire", time.perf_counter_ns() - started)

    def wrapped_getline(*args, **kwargs):
        started = time.perf_counter_ns()
        try:
            return original_getline(*args, **kwargs)
        finally:
            state.add_ns("linecache_getline", time.perf_counter_ns() - started)

    def wrapped_guard():
        state.point("socket_guard_start")
        started = time.perf_counter_ns()
        try:
            return original_guard()
        finally:
            state.point("socket_guard_end")
            state.add_ns("socket_guard", time.perf_counter_ns() - started)

    def wrapped_client_init(self, *args, **kwargs):
        state.point("client_init_start")
        started = time.perf_counter_ns()
        try:
            return original_client_init(self, *args, **kwargs)
        finally:
            state.point("client_init_end")
            state.add_ns("client_init", time.perf_counter_ns() - started)

    def wrapped_ssl(*args, **kwargs):
        state.point("ssl_context_start")
        started = time.perf_counter_ns()
        try:
            return original_ssl(*args, **kwargs)
        finally:
            state.point("ssl_context_end")
            state.add_ns("ssl_context", time.perf_counter_ns() - started)

    original_init = DownloadEngine.__init__
    original_run_job = engine_mod.run_job
    original_engine_run = DownloadEngine.run
    original_asyncio_run = asyncio.run
    original_aenter = httpx.AsyncClient.__aenter__
    original_aexit = httpx.AsyncClient.__aexit__
    original_schedule = DownloadEngine._schedule
    original_send = httpx.AsyncClient.send
    original_connect = AnyIOBackend.connect_tcp
    original_headers = AsyncHTTP11Connection._send_request_headers
    original_recv = AsyncHTTP11Connection._receive_response_headers
    original_getaddrinfo = socket.getaddrinfo
    original_replace = engine_mod.os.replace
    original_open = Path.open
    original_admit = DownloadEngine._admit
    original_emit = DownloadEngine._emit
    original_part = DownloadEngine._part_for
    original_commit = DownloadEngine._commit
    original_global_acquire = SlotGate.acquire
    original_host_acquire = HostBook.acquire
    original_getline = linecache.getline
    original_guard = engine_mod.install_windows_socket_close
    original_client_init = httpx.AsyncClient.__init__
    import httpx._transports.default as _httpx_transport

    original_ssl = _httpx_transport.create_ssl_context

    save_method(DownloadEngine, "__init__", wrapped_init)
    save_attr(engine_mod, "run_job", wrapped_run_job)
    save_method(DownloadEngine, "run", wrapped_engine_run)
    save_attr(asyncio, "run", wrapped_asyncio_run)
    save_method(httpx.AsyncClient, "__aenter__", wrapped_aenter)
    save_method(httpx.AsyncClient, "__aexit__", wrapped_aexit)
    save_method(DownloadEngine, "_schedule", wrapped_schedule)
    save_method(httpx.AsyncClient, "send", wrapped_send)
    save_method(AnyIOBackend, "connect_tcp", wrapped_connect)
    save_method(AsyncHTTP11Connection, "_send_request_headers", wrapped_headers)
    save_method(AsyncHTTP11Connection, "_receive_response_headers", wrapped_recv)
    save_attr(socket, "getaddrinfo", wrapped_getaddrinfo)
    save_attr(engine_mod.os, "replace", wrapped_replace)
    save_method(Path, "open", wrapped_open)
    save_method(DownloadEngine, "_admit", wrapped_admit)
    save_method(DownloadEngine, "_emit", wrapped_emit)
    save_method(DownloadEngine, "_part_for", wrapped_part)
    save_method(DownloadEngine, "_commit", wrapped_commit)
    save_method(SlotGate, "acquire", wrapped_global_acquire)
    save_method(HostBook, "acquire", wrapped_host_acquire)
    save_attr(linecache, "getline", wrapped_getline)
    save_attr(engine_mod, "install_windows_socket_close", wrapped_guard)
    save_method(httpx.AsyncClient, "__init__", wrapped_client_init)
    save_attr(_httpx_transport, "create_ssl_context", wrapped_ssl)


def _wrap_io(handle, method_name: str, bucket: str, state: ProbeState) -> None:
    original = getattr(handle, method_name)

    def timed(*args, **kwargs):
        started, _sec = state.span_start(bucket)
        try:
            return original(*args, **kwargs)
        finally:
            state.span_end(bucket, started)

    setattr(handle, method_name, timed)


def _restore(saved: list) -> None:
    for obj, name, original, had in reversed(saved):
        if had:
            setattr(obj, name, original)
        else:
            delattr(obj, name)


class installed_probe:
    def __init__(self, state: ProbeState) -> None:
        self.state = state
        self.saved: list = []

    def __enter__(self) -> ProbeState:
        _install(self.state, self.saved)
        return self.state

    def __exit__(self, exc_type, exc, tb) -> None:
        _restore(self.saved)
        self.saved.clear()


def _chain(state: ProbeState) -> tuple[list[dict], int | str]:
    if any(name not in state.point_ns for name in _CHAIN):
        return [], "NOT MEASURED"
    origin = state.point_ns["run_job_enter"]
    rows = []
    total = 0
    for name, start_name, end_name in zip(_CHAIN_NAMES, _CHAIN, _CHAIN[1:]):
        duration = state.point_ns[end_name] - state.point_ns[start_name]
        total += duration
        rows.append(
            {
                "name": name,
                "start_ns": state.point_ns[start_name] - origin,
                "end_ns": state.point_ns[end_name] - origin,
                "duration_ns": duration,
                "overlap": name == "schedule_until_tasks_done",
            }
        )
    residual = (state.point_ns["run_job_return"] - origin) - total
    rows.append({"name": "main_chain_residual", "duration_ns": residual, "overlap": False})
    return rows, residual


def _milestone_map(state: ProbeState) -> dict[str, int | str]:
    origin = state.point_ns.get("run_job_enter")
    found: dict[str, int | str] = {}

    def rel(ns: int | None) -> int | str:
        if ns is None or origin is None:
            return "NOT MEASURED"
        return ns - origin

    mapping = {
        "engine_init_start": state.point_ns.get("engine_init_start"),
        "engine_init_end": state.point_ns.get("engine_init_end"),
        "loop_entered": state.point_ns.get("loop_entered"),
        "client_ready": state.point_ns.get("client_aenter_end"),
        "first_task_scheduled": state.first_ns.get("first_task"),
        "request_send_start": state.first_ns.get("request_headers"),
        "first_response": state.first_ns.get("response_headers"),
        "last_response": state.last_ns.get("response_headers"),
        "last_file_finalized": state.last_ns.get("replace"),
        "tasks_complete": state.point_ns.get("schedule_return"),
        "client_closed": state.point_ns.get("client_aexit_end"),
        "asyncio_run_return": state.point_ns.get("asyncio_run_return"),
    }
    for name in _MILESTONES:
        found[name] = rel(mapping[name])
    return found


def _p6_split(state: ProbeState, server_first: float | None, server_last: float | None) -> dict:
    start = state.point_sec.get("client_aenter_end")
    end = state.point_sec.get("schedule_return")
    if start is None or end is None or server_first is None or server_last is None:
        return {"status": "NOT MEASURED"}
    if not (start <= server_first <= server_last <= end):
        return {"status": "NOT MEASURED"}
    return {
        "status": "measured",
        "before_server_span_s": server_first - start,
        "server_span_wall_s": server_last - server_first,
        "after_server_span_s": end - server_last,
        "overlap": True,
        "note": "wall split of client ready to tasks done; the middle overlaps client work",
    }


def export_probe(state: ProbeState, server_first: float | None, server_last: float | None) -> dict:
    chain, residual = _chain(state)
    milestones = _milestone_map(state)
    not_measured = [name for name, value in milestones.items() if value == "NOT MEASURED"]
    if state.counts.get("getaddrinfo", 0) <= 0:
        not_measured.append("dns")
    complete = not any(name in not_measured for name in _MILESTONES) and residual == 0
    origin = state.point_ns.get("run_job_enter")

    def rel_first(name: str) -> int | str:
        if origin is None or name not in state.first_ns:
            return "NOT MEASURED"
        return state.first_ns[name] - origin

    def rel_last(name: str) -> int | str:
        if origin is None or name not in state.last_ns:
            return "NOT MEASURED"
        return state.last_ns[name] - origin

    return {
        "milestones_ns": milestones,
        "main_chain": chain,
        "main_chain_residual_ns": residual,
        "measurement_complete": complete,
        "not_measured": not_measured,
        "cumulative_ns": dict(state.sums),
        "counts": dict(state.counts),
        "scheduler_wait_ns": list(state.scheduler_wait_ns),
        "scheduler_empty_wait_ns": list(state.scheduler_empty_wait_ns),
        "first_ns": {name: rel_first(name) for name in sorted(state.first_ns)},
        "last_ns": {name: rel_last(name) for name in sorted(state.last_ns)},
        "p6_split": _p6_split(state, server_first, server_last),
        "intervals_overlap": [
            "schedule_until_tasks_done",
            "connect_tcp",
            "request_headers",
            "response_headers",
            "httpx_send",
            "body_write",
            "commit",
            "replace",
            "slot_gate_acquire",
            "host_gate_acquire",
        ],
    }


def _directory_result(directory: Path) -> tuple[int, int]:
    count = 0
    size = 0
    for path in directory.iterdir():
        if path.is_file() and not path.name.startswith("."):
            count += 1
            size += path.stat().st_size
    return count, size


def run_measured(
    directory: Path,
    *,
    limit: int,
    hold: float,
    probe: bool,
    url_userinfo: str | None = None,
) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    lab = LabServer()
    state = ProbeState()
    saved_run = DownloadEngine.run
    saved_lookup = socket.getaddrinfo
    try:
        def handler(_path, _query, _headers):
            return Reply(
                200,
                PNG,
                {"Content-Type": "image/png", "ETag": '"same"'},
                hold=hold,
            )

        for index in range(limit):
            lab.mount(f"/p{limit}-{index}.png", handler)
        if url_userinfo:
            urls = [f"http://{url_userinfo}@127.0.0.1:{lab.port}/p{limit}-{index}.png" for index in range(limit)]
        else:
            urls = [lab.url(f"/p{limit}-{index}.png") for index in range(limit)]
        items = [DownloadItem(item_id=f"item-{index}", url=url) for index, url in enumerate(urls)]
        config = EngineConfig(
            global_limit=limit,
            per_host=limit,
            timeout=8,
            max_retries=2,
            backoff_base=0.05,
        )
        guard_before = len(engine_mod.shutdown_10022_events)
        guard_installed = bool(engine_mod._close_guard_installed)
        cpu_before = _system_times()
        proc_before = _process_times()
        mem_before = _memory_status()
        ws_before = _working_set()
        if probe:
            with installed_probe(state):
                outcome = _execute(lab, directory, items, config, hold)
        else:
            outcome = _execute(lab, directory, items, config, hold)
        if probe and DownloadEngine.run is not saved_run:
            raise RuntimeError("probe left DownloadEngine.run patched")
        if probe and socket.getaddrinfo is not saved_lookup:
            raise RuntimeError("probe left socket.getaddrinfo patched")
        cpu_after = _system_times()
        proc_after = _process_times()
        mem_after = _memory_status()
        ws_after = _working_set()
        file_count, file_bytes = _directory_result(directory)
        record = {
            "probe": probe,
            "limit": limit,
            "hold_s": hold,
            "threshold_s": hold * 4,
            "elapsed_s": outcome["elapsed_s"],
            "within_threshold": outcome["within_threshold"],
            "functional_pass": outcome["functional_pass"],
            "download_pass": outcome["download_pass"],
            "failure": outcome["failure"],
            "file_count": file_count,
            "file_bytes": file_bytes,
            "peak_connections": outcome["peak_connections"],
            "server_peak": outcome["server_peak"],
            "server_connections": outcome["server_connections"],
            "overlap": outcome["overlap"],
            "server_span_count": outcome["server_span_count"],
            "server_hold_max_s": outcome["server_hold_max_s"],
            "server_span_wall_s": outcome["server_span_wall_s"],
            "server_first_start_s": outcome["server_first_start_s"],
            "server_last_end_s": outcome["server_last_end_s"],
            "cpu_percent_during": _cpu_percent(cpu_before, cpu_after),
            "process_cpu_s": None
            if proc_before is None or proc_after is None
            else ((proc_after[0] - proc_before[0]) + (proc_after[1] - proc_before[1])) / 10_000_000,
            "memory_load_before": None if mem_before is None else mem_before["memory_load_percent"],
            "memory_load_after": None if mem_after is None else mem_after["memory_load_percent"],
            "avail_phys_before": None if mem_before is None else mem_before["avail_phys_bytes"],
            "avail_phys_after": None if mem_after is None else mem_after["avail_phys_bytes"],
            "process_ws_before": ws_before,
            "process_ws_after": ws_after,
            "proactor_10022_events": len(engine_mod.shutdown_10022_events) - guard_before,
            "close_guard_was_installed": guard_installed,
        }
        if probe:
            record.update(export_probe(state, outcome["server_first_abs"], outcome["server_last_abs"]))
        else:
            record["measurement_complete"] = False
            record["not_measured"] = ["stages"]
            record["milestones_ns"] = {name: "NOT MEASURED" for name in _MILESTONES}
        if record.get("cpu_percent_during") is None or record.get("memory_load_after") is None:
            record["measurement_complete"] = False
            record.setdefault("not_measured", [])
            if record["cpu_percent_during"] is None:
                record["not_measured"].append("cpu_percent_during")
            if record["memory_load_after"] is None:
                record["not_measured"].append("memory_load")
        return _redact(record)
    finally:
        lab.shutdown()


def _execute(lab: LabServer, directory: Path, items: list[DownloadItem], config: EngineConfig, hold: float) -> dict:
    started = time.perf_counter()
    engine = engine_mod.run_job(directory, items, config)
    elapsed = time.perf_counter() - started
    stats = lab.snapshot()
    spans = stats["spans"]
    bad = 0
    for event in engine.events:
        if event.terminal and event.status != "완료":
            bad += 1
    server_peak = int(stats["peak_active"])
    overlap = overlaps(spans) if len(spans) >= 2 else False
    functional = bad == 0 and engine.peak_connections <= config.global_limit and server_peak <= config.global_limit
    if config.global_limit > 1:
        functional = functional and server_peak >= config.global_limit - 1 and overlap
    within = elapsed < hold * 4
    reasons = []
    if bad:
        reasons.append("items")
    if engine.peak_connections > config.global_limit:
        reasons.append("peak")
    if server_peak > config.global_limit or (config.global_limit > 1 and server_peak < config.global_limit - 1):
        reasons.append("server_peak")
    if config.global_limit > 1 and not overlap:
        reasons.append("overlap")
    if not within:
        reasons.append("elapsed")
    if spans:
        hold_max = max(end - start for start, end in spans)
        wall = max(end for _start, end in spans) - min(start for start, _end in spans)
        first = min(start for start, _end in spans)
        last = max(end for _start, end in spans)
        first_rel = first - started
        last_rel = last - started
    else:
        hold_max = wall = first_rel = last_rel = "NOT MEASURED"
        first = last = None
    return {
        "elapsed_s": elapsed,
        "within_threshold": within,
        "functional_pass": functional,
        "download_pass": functional and within,
        "failure": ",".join(reasons),
        "peak_connections": engine.peak_connections,
        "server_peak": server_peak,
        "server_connections": int(stats["connections"]),
        "overlap": overlap,
        "server_span_count": len(spans),
        "server_hold_max_s": hold_max,
        "server_span_wall_s": wall,
        "server_first_start_s": first_rel,
        "server_last_end_s": last_rel,
        "server_first_abs": first,
        "server_last_abs": last,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--hold", type=float, required=True)
    parser.add_argument("--probe", type=int, choices=(0, 1), required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args(argv)
    exit_code = 0
    for index in range(args.repeat):
        directory = args.directory if args.repeat == 1 else args.directory / str(index)
        try:
            record = run_measured(
                directory,
                limit=args.limit,
                hold=args.hold,
                probe=bool(args.probe),
            )
        except Exception:
            print(json.dumps({"probe": bool(args.probe), "repeat": index, "measurement_complete": False, "crash": "Exception"}))
            return 1
        record["repeat"] = index
        print(json.dumps(record, separators=(",", ":")))
        if args.probe and not record.get("measurement_complete"):
            exit_code = 2
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
