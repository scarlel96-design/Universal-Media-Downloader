"""Run a third-party extractor in a child process.

The child owns the process-wide DNS guard. The parent keeps the normal
resolver, so a local download can resolve 127.0.0.1 while the child runs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from umd.netpolicy import DnsError, ExtractError, PolicyError
from umd.secrets import (
    active_vault,
    default_vault,
    materialize_payload,
    scrub_text,
    seal_payload,
    signed_urls_in,
    text_contains_secret,
)

_REF_IDS = re.compile(r"umdref://([0-9a-f]{32})")


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
    vault = active_vault() or default_vault()
    sealed, secrets, refs = seal_payload(payload)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "umd.net.child"],
            input=json.dumps({"op": op, "payload": sealed}, ensure_ascii=False).encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    finally:
        vault.drop_many(refs)
        vault.sweep_expired_outbound()
    raw_out = proc.stdout.decode("utf-8", errors="replace")
    raw_err = proc.stderr.decode("utf-8", errors="replace")
    if (
        text_contains_secret(raw_out, secrets)
        or text_contains_secret(raw_err, secrets)
        or signed_urls_in(raw_out)
        or signed_urls_in(raw_err)
    ):
        raise ExtractError("격리 프로세스가 실패했습니다")
    text = raw_out.strip()
    line = text.splitlines()[-1] if text else ""
    try:
        body = json.loads(line) if line else {}
    except json.JSONDecodeError as exc:
        detail = scrub_text((raw_err or text)[-400:], secrets)
        if text_contains_secret(detail, secrets) or signed_urls_in(detail):
            detail = ""
        raise ExtractError(detail or "격리 프로세스가 결과를 반환하지 않았습니다") from exc
    if proc.returncode != 0 or not body.get("ok"):
        kind = str(body.get("kind") or "ExtractError")
        message = scrub_text(str(body.get("error") or "격리 프로세스가 실패했습니다"), secrets)
        if text_contains_secret(message, secrets) or signed_urls_in(message):
            message = "격리 프로세스가 실패했습니다"
        if kind == "TransferStop":
            raise IsolatedStop(message)
        raise _KINDS.get(kind, ExtractError)(message)
    result = body.get("result")
    if not isinstance(result, dict):
        return {}
    found = _REF_IDS.findall(json.dumps(result, ensure_ascii=False))
    enriched = dict(result)
    enriched["vaultRoot"] = str(vault.root)
    try:
        materialized = materialize_payload(enriched)
    finally:
        vault.drop_many(found)
        vault.sweep_expired_outbound()
    return materialized if isinstance(materialized, dict) else {}
