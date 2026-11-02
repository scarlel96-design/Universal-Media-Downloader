"""Fresh-process preset timings for WO-REUSE-01-S4.

This file is not named test_*.py, so pytest does not collect it.
Each sample is a new Python process. A probed sample that does not return a
complete measurement is stored as invalid and is not counted as a pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_PYTHON = Path(r"C:\Users\scarl\.pwragent\profiles\default\projects\2026-11-01-a128f5\.venv\Scripts\python.exe")
_PROBE = Path(__file__).with_name("s4_timing_probe.py")
_COUNTERS = [
    r"\Processor Information(_Total)\% Processor Performance",
    r"\Processor Information(_Total)\Processor Frequency",
    r"\Processor Information(_Total)\% of Maximum Frequency",
    r"\Processor Information(_Total)\% Performance Limit",
    r"\PhysicalDisk(_Total)\Avg. Disk sec/Read",
    r"\PhysicalDisk(_Total)\Avg. Disk sec/Write",
    r"\PhysicalDisk(_Total)\Current Disk Queue Length",
    r"\PhysicalDisk(_Total)\Avg. Disk Queue Length",
    r"\Memory\Available MBytes",
    r"\Memory\Committed Bytes",
    r"\Memory\Cache Bytes",
]
_SEQUENCE = (
    ("bare", 0),
    ("probed", 1),
    ("probed", 1),
    ("probed", 1),
    ("bare", 0),
    ("probed", 1),
    ("probed", 1),
    ("probed", 1),
    ("bare", 0),
    ("probed", 1),
    ("probed", 1),
    ("probed", 1),
    ("probed", 1),
)


def _environment(label: str) -> dict:
    names = ",".join("'" + item.replace("'", "''") + "'" for item in _COUNTERS)
    script = f"""
$names = @({names})
$result = [ordered]@{{
  label = '{label}'
  captured_at = (Get-Date).ToUniversalTime().ToString('o')
}}
$counters = [ordered]@{{}}
try {{
  $sample = Get-Counter -Counter $names -SampleInterval 1 -MaxSamples 1 -ErrorAction Stop
  foreach ($item in $sample.CounterSamples) {{
    $counters[$item.Path.Split('\\')[-1]] = $item.CookedValue
  }}
}} catch {{
  foreach ($name in $names) {{
    try {{
      $one = Get-Counter -Counter $name -SampleInterval 1 -MaxSamples 1 -ErrorAction Stop
      $counters[$one.CounterSamples[0].Path.Split('\\')[-1]] = $one.CounterSamples[0].CookedValue
    }} catch {{
      $counters[$name] = 'NOT MEASURED'
    }}
  }}
}}
$result.counters = $counters
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$result.wmi_current_mhz = [int]$cpu.CurrentClockSpeed
$result.wmi_max_mhz = [int]$cpu.MaxClockSpeed
$result.cpu_name = [string]$cpu.Name
$os = Get-CimInstance Win32_OperatingSystem
$result.free_kb = [int64]$os.FreePhysicalMemory
$result.total_kb = [int64]$os.TotalVisibleMemorySize
$mc = Get-Process -Name 'Memory Compression' -ErrorAction SilentlyContinue
if ($mc) {{ $result.compression_ws = [int64]$mc.WorkingSet64 }} else {{ $result.compression_ws = 'NOT MEASURED' }}
$result.disk_free = [int64](Get-PSDrive C).Free
$result.scheme = ((powercfg /getactivescheme) -join ' ')
try {{
  $def = Get-MpComputerStatus
  $result.defender_realtime = [bool]$def.RealTimeProtectionEnabled
  $result.defender_antivirus = [bool]$def.AntivirusEnabled
  $result.defender_ioav = [bool]$def.IoavProtectionEnabled
}} catch {{
  $result.defender_realtime = 'NOT MEASURED'
}}
$top = Get-Process | Sort-Object CPU -Descending | Select-Object -First 8
$result.top = @($top | ForEach-Object {{
  [ordered]@{{ name = [string]$_.Name; id = [int]$_.Id; cpu_s = $_.CPU; ws = [int64]$_.WorkingSet64 }}
}})
$result | ConvertTo-Json -Depth 5 -Compress
"""
    completed = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return {"label": label, "status": "NOT MEASURED", "error": completed.stderr[-300:]}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"label": label, "status": "NOT MEASURED"}
    payload["status"] = "measured"
    return payload


def _run_one(limit: int, probe: int, directory: Path, repeat: int = 1) -> list[dict]:
    completed = subprocess.run(
        [
            str(_PYTHON),
            "-u",
            str(_PROBE),
            "--limit",
            str(limit),
            "--hold",
            "0.45",
            "--probe",
            str(probe),
            "--repeat",
            str(repeat),
            "--directory",
            str(directory),
        ],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )
    rows = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            row = {"measurement_complete": False, "crash": "json"}
        row["process_exit"] = completed.returncode
        row["sample_kind"] = "probed" if probe else "bare"
        row["fresh_process"] = repeat == 1
        if probe and not row.get("measurement_complete"):
            row["recorded_pass"] = False
        rows.append(row)
    if not rows:
        rows.append(
            {
                "limit": limit,
                "probe": bool(probe),
                "sample_kind": "probed" if probe else "bare",
                "measurement_complete": False,
                "recorded_pass": False,
                "process_exit": completed.returncode,
                "crash": "no-json",
                "fresh_process": repeat == 1,
            }
        )
    return rows


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd() / "s4-preset-matrix.jsonl"
    work = Path(sys.argv[2]) if len(sys.argv) > 2 else out.with_suffix("")
    work.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=_ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "src/umd/download/engine.py", "src/umd/download/schedule.py"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    header = {
        "kind": "header",
        "git_head": head,
        "engine_schedule_diff": diff or "clean",
        "hold_s": 0.45,
        "threshold_s": 1.8,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with out.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(header) + "\n")
        handle.write(json.dumps({"kind": "environment", **_environment("pre-matrix")}) + "\n")
        handle.flush()
        for limit in (4, 12, 24):
            before = _process_snapshot()
            for index, (kind, probe) in enumerate(_SEQUENCE):
                directory = work / f"limit-{limit}" / f"{index:02d}-{kind}"
                started = time.perf_counter()
                rows = _run_one(limit, probe, directory)
                for row in rows:
                    row["kind"] = "sample"
                    row["sequence"] = index
                    row["runner_s"] = time.perf_counter() - started
                    handle.write(json.dumps(row) + "\n")
                    handle.flush()
                    ssl_ns = (row.get("cumulative_ns") or {}).get("ssl_context")
                    ssl_ms = "na" if not isinstance(ssl_ns, int) else f"{ssl_ns / 1e6:.1f}"
                    print(
                        f"limit={limit} {kind} seq={index} exit={row.get('process_exit')} "
                        f"elapsed={row.get('elapsed_s')} pass={row.get('download_pass')} "
                        f"complete={row.get('measurement_complete')} ssl_ms={ssl_ms} fail={row.get('failure')}",
                        flush=True,
                    )
            after = _process_snapshot()
            handle.write(
                json.dumps(
                    {
                        "kind": "process_delta",
                        "limit": limit,
                        "before": before,
                        "after": after,
                    }
                )
                + "\n"
            )
            handle.write(json.dumps({"kind": "environment", **_environment(f"after-limit-{limit}")}) + "\n")
            handle.flush()
        pair_dir = work / "same-process-limit-12"
        for row in _run_one(12, 1, pair_dir, repeat=2):
            row["kind"] = "same-process"
            row["sample_kind"] = "probed"
            handle.write(json.dumps(row) + "\n")
            ssl_ns = (row.get("cumulative_ns") or {}).get("ssl_context")
            ssl_text = "na" if not isinstance(ssl_ns, int) else f"{ssl_ns / 1e6:.1f}"
            print(
                f"same-process repeat={row.get('repeat')} elapsed={row.get('elapsed_s')} "
                f"ssl_ms={ssl_text} pass={row.get('download_pass')}",
                flush=True,
            )
        handle.write(json.dumps({"kind": "environment", **_environment("post-matrix")}) + "\n")
    print(f"wrote {out}", flush=True)
    return 0


def _process_snapshot() -> list[dict]:
    completed = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-Command",
            "Get-Process | Sort-Object CPU -Descending | Select-Object -First 8 Name, Id, CPU, WorkingSet64 | "
            "ConvertTo-Json -Compress",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    rows = []
    for item in payload:
        rows.append(
            {
                "name": item.get("Name"),
                "id": item.get("Id"),
                "cpu_s": item.get("CPU"),
                "ws": item.get("WorkingSet64"),
            }
        )
    return rows


if __name__ == "__main__":
    sys.exit(main())
