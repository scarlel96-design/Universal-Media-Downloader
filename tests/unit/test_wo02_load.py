"""Local bulk timing. These numbers are not an internet speed claim."""

from __future__ import annotations

import ctypes
import json
import logging
import time
import tracemalloc

logging.getLogger("asyncio").setLevel(logging.CRITICAL)
from ctypes import wintypes
from pathlib import Path

from umd.download.engine import DownloadItem, run_job
from umd.download.schedule import EngineConfig
from umd.storage.database import Library
from wo02_support import PNG, LabServer, Reply, unique_png


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _working_set() -> int:
    counters = _Counters()
    counters.cb = ctypes.sizeof(counters)
    ok = _psapi.GetProcessMemoryInfo(_kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    if not ok:
        return 0
    return int(counters.WorkingSetSize)


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_psapi = ctypes.WinDLL("psapi", use_last_error=True)
_kernel32.GetCurrentProcess.restype = wintypes.HANDLE
_psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
_psapi.GetProcessMemoryInfo.restype = wintypes.BOOL


def _run(folder: Path, urls: list[str], config: EngineConfig) -> dict:
    items = [DownloadItem(f"n{index}", url) for index, url in enumerate(urls)]
    before = _working_set()
    peak = before
    started = time.perf_counter()
    engine = run_job(folder, items, config)
    # Working set after the run is a floor; sample the process once more.
    peak = max(peak, _working_set(), before)
    elapsed = time.perf_counter() - started
    done = [event for event in engine.events if event.terminal and event.status == "완료"]
    return {
        "elapsed_s": round(elapsed, 3),
        "completed": len(done),
        "peak_connections": engine.peak_connections,
        "working_set_after": _working_set(),
        "working_set_before": before,
    }


def test_five_thousand_local_images_and_large_file(tmp_path: Path):
    lab = LabServer()
    try:
        count = 5000

        def bulk(path, _query, _headers):
            index = int(path.rsplit("/", 1)[-1].split(".")[0])
            return Reply(200, unique_png(index), {"Content-Type": "image/png"})

        lab.mount_prefix("/b/", bulk)
        urls = [lab.url(f"/b/{index}.png") for index in range(count)]
        folder = tmp_path / "bulk"
        folder.mkdir()
        database = tmp_path / "bulk.sqlite"
        library = Library(str(database))
        rows = [
            {
                "title": f"img-{index}",
                "mediaUrl": urls[index],
                "classification": "content",
                "reasons": "본문",
                "selected": True,
                "status": "대기",
            }
            for index in range(count)
        ]
        # The queue is the download engine. Record completion in SQLite as each file finishes.
        started = time.perf_counter()
        before = _working_set()
        peak_ws = before

        def on_event(event) -> None:
            nonlocal peak_ws
            if event.terminal:
                library.apply_transfer(
                    event.item_id,
                    {
                        "status": event.status,
                        "path": event.path,
                        "size": event.size,
                        "error": event.error,
                        "downloaded_bytes": event.downloaded,
                    },
                )
            current = _working_set()
            if current > peak_ws:
                peak_ws = current

        items = []
        # create_job once would rewrite ids. Store under the ids the engine uses.
        job_rows = []
        for index, url in enumerate(urls):
            job_rows.append(
                {
                    "title": f"img-{index}",
                    "mediaUrl": url,
                    "classification": "content",
                    "reasons": "본문",
                    "selected": True,
                    "status": "대기",
                }
            )
        library.create_job("http://127.0.0.1/bulk", job_rows)
        id_by_url = {row["mediaUrl"]: row["itemId"] for row in job_rows}
        from umd.download.engine import DownloadEngine
        import asyncio

        engine = DownloadEngine(
            folder,
            [DownloadItem(id_by_url[url], url) for url in urls],
            EngineConfig(preset="균형", timeout=20, max_retries=2, backoff_base=0.05),
            on_event=on_event,
        )
        asyncio.run(engine.run())
        elapsed = time.perf_counter() - started
        files = [path for path in folder.iterdir() if not path.name.startswith(".")]
        assert len(files) == count
        mismatched = 0
        for index in range(count):
            file = folder / f"{index}.png"
            if not file.is_file() or file.read_bytes() != unique_png(index):
                mismatched += 1
        assert mismatched == 0
        assert not list(folder.glob(".*.part"))
        stored = library.items(library.latest_job()["id"])
        assert sum(1 for row in stored if row["download_status"] == "완료") == count
        assert library.integrity_issues() == []
        bulk_metrics = {
            "files": count,
            "elapsed_s": round(elapsed, 3),
            "peak_connections": engine.peak_connections,
            "server_peak": lab.snapshot()["peak_active"],
            "working_set_before": before,
            "working_set_peak": peak_ws,
            "integrity_mismatches": mismatched,
        }
        assert engine.peak_connections <= 12
        assert lab.snapshot()["peak_active"] <= 12

        large = PNG + bytes(6 * 1024 * 1024)
        lab.mount("/large.png", lambda *_args: Reply(200, large, {"Content-Type": "image/png"}))
        tracemalloc.start()
        baseline = tracemalloc.get_traced_memory()[1]
        large_folder = tmp_path / "large"
        large_folder.mkdir()
        large_engine = run_job(
            large_folder,
            [DownloadItem("large", lab.url("/large.png"))],
            EngineConfig(global_limit=1, per_host=1, timeout=20, max_retries=0),
        )
        traced = tracemalloc.get_traced_memory()[1] - baseline
        tracemalloc.stop()
        saved = next(path for path in large_folder.iterdir() if not path.name.startswith("."))
        assert saved.read_bytes() == large
        assert traced < len(large) // 2

        compare_lab = lab
        sample = [lab.url(f"/b/{index}.png") for index in range(80)]
        seq_dir = tmp_path / "seq"
        par_dir = tmp_path / "par"
        seq_dir.mkdir()
        par_dir.mkdir()
        # The bulk mount is still in place. Add a short hold by remounting a prefix? Keep the fast bodies.
        # A separate held route makes the parallel difference visible.
        def held(path, _query, _headers):
            index = int(path.rsplit("/", 1)[-1].split(".")[0])
            return Reply(200, unique_png(index), {"Content-Type": "image/png"}, hold=0.02)

        lab.mount_prefix("/h/", held)
        held_urls = [lab.url(f"/h/{index}.png") for index in range(80)]
        lab.reset_stats()
        sequential = _run(seq_dir, held_urls, EngineConfig(global_limit=1, per_host=1, timeout=30, max_retries=1, backoff_base=0.05))
        seq_peak = lab.snapshot()["peak_active"]
        lab.reset_stats()
        parallel = _run(par_dir, held_urls, EngineConfig(preset="균형", timeout=30, max_retries=1, backoff_base=0.05))
        par_peak = lab.snapshot()["peak_active"]
        assert sequential["completed"] == 80
        assert parallel["completed"] == 80
        assert par_peak <= 3
        assert sequential["elapsed_s"] > parallel["elapsed_s"]
        metrics = {
            "bulk": bulk_metrics,
            "large_file_bytes": len(large),
            "large_file_traced_bytes": traced,
            "sequential": {**sequential, "server_peak": seq_peak},
            "parallel": {**parallel, "server_peak": par_peak},
            "note": "local fixture only; not an internet throughput claim",
        }
        print("WO02_METRICS " + json.dumps(metrics, ensure_ascii=False))
        (tmp_path / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        library.close()
    finally:
        lab.shutdown()
