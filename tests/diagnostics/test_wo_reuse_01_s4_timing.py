"""WO-REUSE-01-S4 diagnostic checks.

These tests record stage timings. They do not replace the 1.8 second preset
gate and they do not treat a slow preset run as a pass.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

from umd.download.engine import DownloadEngine
from wo02_support import PNG

from s4_timing_probe import _MILESTONES, run_measured

_SECRET = "s4-secret-token-9f3a"


def _write(path: Path, record: dict) -> dict:
    path.write_text(json.dumps(record), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not path.is_file() or not loaded:
        raise AssertionError("timing record was not stored")
    return loaded


def test_run_job_stage_timings_are_recorded(tmp_path: Path):
    record = run_measured(tmp_path / "stages", limit=2, hold=0.0, probe=True)
    loaded = _write(tmp_path / "stages.json", record)
    assert loaded["measurement_complete"] is True
    assert loaded["main_chain_residual_ns"] == 0
    for name in _MILESTONES:
        assert isinstance(loaded["milestones_ns"][name], int), name
    assert loaded["file_count"] == 2
    assert "dns" in loaded["not_measured"] or loaded["counts"].get("getaddrinfo", 0) > 0


def test_parallel_requests_preserve_actual_overlap(tmp_path: Path):
    record = run_measured(tmp_path / "overlap", limit=4, hold=0.2, probe=True)
    loaded = _write(tmp_path / "overlap.json", record)
    assert loaded["measurement_complete"] is True
    assert loaded["overlap"] is True
    assert loaded["server_peak"] >= 3
    assert loaded["peak_connections"] <= 4
    assert loaded["server_peak"] <= 4
    assert loaded["functional_pass"] is True
    assert loaded["server_hold_max_s"] >= 0.2


def test_client_shutdown_time_is_measured(tmp_path: Path):
    record = run_measured(tmp_path / "close", limit=1, hold=0.0, probe=True)
    loaded = _write(tmp_path / "close.json", record)
    close = next(row for row in loaded["main_chain"] if row["name"] == "httpx_client_close")
    assert isinstance(close["duration_ns"], int)
    assert close["duration_ns"] >= 0
    assert isinstance(loaded["milestones_ns"]["client_closed"], int)


def test_engine_startup_time_is_measured(tmp_path: Path):
    record = run_measured(tmp_path / "start", limit=1, hold=0.0, probe=True)
    loaded = _write(tmp_path / "start.json", record)
    init = next(row for row in loaded["main_chain"] if row["name"] == "engine_init")
    loop = next(row for row in loaded["main_chain"] if row["name"] == "loop_prep")
    assert isinstance(init["duration_ns"], int) and init["duration_ns"] >= 0
    assert isinstance(loop["duration_ns"], int) and loop["duration_ns"] >= 0
    assert isinstance(loaded["milestones_ns"]["engine_init_end"], int)
    assert isinstance(loaded["milestones_ns"]["loop_entered"], int)


def test_timing_probe_does_not_change_download_result(tmp_path: Path):
    probed = run_measured(tmp_path / "probed", limit=2, hold=0.0, probe=True)
    bare = run_measured(tmp_path / "bare", limit=2, hold=0.0, probe=False)

    def bodies(directory: Path) -> list[bytes]:
        files = [path for path in directory.iterdir() if path.is_file() and not path.name.startswith(".")]
        return sorted(path.read_bytes() for path in files)

    assert bodies(tmp_path / "probed") == bodies(tmp_path / "bare")
    assert bodies(tmp_path / "probed") == [PNG, PNG]
    assert probed["file_count"] == bare["file_count"] == 2
    for record in (probed, bare):
        reasons = [part for part in record["failure"].split(",") if part]
        assert "items" not in reasons
        assert "peak" not in reasons
        assert "server_peak" not in reasons


def test_preset_results_preserve_original_threshold():
    source = (Path(__file__).resolve().parents[1] / "unit" / "test_wo02_engine.py").read_text(encoding="utf-8")
    assert '@pytest.mark.parametrize("limit", [4, 12, 24])' in source
    assert "hold = 0.45" in source
    assert "assert elapsed < hold * 4" in source


def test_same_code_under_different_load_is_reported(tmp_path: Path):
    first = run_measured(tmp_path / "load-a", limit=1, hold=0.0, probe=True)
    second = run_measured(tmp_path / "load-b", limit=1, hold=0.0, probe=True)
    first["load_label"] = "sample-a"
    second["load_label"] = "sample-b"
    loaded = _write(tmp_path / "loads.json", {"runs": [first, second]})
    assert len(loaded["runs"]) == 2
    for row in loaded["runs"]:
        assert row["measurement_complete"] is True
        assert isinstance(row["elapsed_s"], float)
        assert isinstance(row["cpu_percent_during"], float)
        assert isinstance(row["memory_load_before"], int)
        assert isinstance(row["memory_load_after"], int)
        assert row["limit"] == 1
    assert loaded["runs"][0]["load_label"] != loaded["runs"][1]["load_label"]


def test_no_secret_url_appears_in_diagnostics(tmp_path: Path):
    record = run_measured(
        tmp_path / "secret",
        limit=1,
        hold=0.0,
        probe=True,
        url_userinfo=f"user:{_SECRET}",
    )
    loaded = _write(tmp_path / "secret.json", record)
    text = json.dumps(loaded)
    assert _SECRET not in text
    assert "://" not in text
    assert loaded["file_count"] == 1
    assert loaded["functional_pass"] is True


def test_probe_restores_download_engine(tmp_path: Path):
    original_run = DownloadEngine.run
    original_lookup = socket.getaddrinfo
    run_measured(tmp_path / "restore", limit=1, hold=0.0, probe=True)
    assert DownloadEngine.run is original_run
    assert socket.getaddrinfo is original_lookup
