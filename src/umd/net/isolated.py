"""Run a third-party extractor in a child process.

The child owns the process-wide DNS guard. The parent keeps the normal
resolver, so a local download can resolve 127.0.0.1 while the child runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from umd.netpolicy import DnsError, ExtractError, PolicyError


class IsolatedStop(ExtractError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


_KINDS = {
    "PolicyError": PolicyError,
    "DnsError": DnsError,
    "ExtractError": ExtractError,
}


def call(op: str, payload: dict, *, timeout: float = 180) -> dict:
    env = os.environ.copy()
    env["UMD_IN_WORKER"] = "1"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2]) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-m", "umd.net.child"],
        input=json.dumps({"op": op, "payload": payload}, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        timeout=timeout,
        env=env,
        check=False,
    )
    text = proc.stdout.decode("utf-8", errors="replace").strip()
    line = text.splitlines()[-1] if text else ""
    try:
        body = json.loads(line) if line else {}
    except json.JSONDecodeError as exc:
        detail = (proc.stderr.decode("utf-8", errors="replace") or text)[-400:]
        raise ExtractError(detail or "격리 프로세스가 결과를 반환하지 않았습니다") from exc
    if proc.returncode != 0 or not body.get("ok"):
        kind = str(body.get("kind") or "ExtractError")
        message = str(body.get("error") or "격리 프로세스가 실패했습니다")
        if kind == "TransferStop":
            raise IsolatedStop(message)
        raise _KINDS.get(kind, ExtractError)(message)
    result = body.get("result")
    return result if isinstance(result, dict) else {}
