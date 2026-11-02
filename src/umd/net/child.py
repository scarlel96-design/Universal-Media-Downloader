"""Isolated worker. The DNS guard lives only inside this process.

The parent starts it with ``python -m umd.net.child``. Stdin is one JSON
object. Stdout is one JSON object. The guard stays installed until exit.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

from umd.secrets import (
    SecretVault,
    collect_secrets,
    materialize_payload,
    scrub_text,
    seal_tree,
    signed_urls_in,
    text_contains_secret,
)

_GENERIC = {"ok": False, "kind": "ExtractError", "error": "작업을 완료하지 못했습니다", "trace": ""}


class _CapturedStream:
    """Hold third-party diagnostics until they can be scrubbed."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.encoding = "utf-8"

    def write(self, data: object) -> int:
        if isinstance(data, bytes):
            text = data.decode("utf-8", "replace")
        else:
            text = str(data)
        self.parts.append(text)
        return len(text)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False

    @property
    def buffer(self) -> "_CapturedStream":
        return self


def _write_json(stream, body: dict, secrets: list[str], vault: SecretVault | None = None) -> None:
    if body.get("ok"):
        public = {"ok": True, "result": seal_tree(body.get("result"), vault, secrets)}
    else:
        public = {
            "ok": False,
            "kind": str(body.get("kind") or "ExtractError"),
            "error": scrub_text(str(body.get("error") or ""), secrets)[:500],
            "trace": scrub_text(str(body.get("trace") or ""), secrets)[-800:],
        }
    text = json.dumps(public, ensure_ascii=False)
    if text_contains_secret(text, secrets) or signed_urls_in(text):
        text = json.dumps(_GENERIC, ensure_ascii=False)
    stream.buffer.write(text.encode("utf-8"))
    stream.buffer.write(b"\n")
    stream.buffer.flush()


def _emit_captured(capture: _CapturedStream, stream, secrets: list[str]) -> None:
    raw = "".join(capture.parts)
    if not raw:
        return
    try:
        cleaned = scrub_text(raw, secrets)
    except Exception:
        cleaned = "작업을 완료하지 못했습니다\n"
    if text_contains_secret(cleaned, secrets) or signed_urls_in(cleaned):
        cleaned = "작업을 완료하지 못했습니다\n"
    stream.write(cleaned)
    stream.flush()


def main() -> int:
    os.environ["UMD_IN_WORKER"] = "1"
    raw = sys.stdin.buffer.read()
    real_out = sys.stdout
    real_err = sys.stderr
    capture = _CapturedStream()
    sys.stderr = capture
    secrets: list[str] = []
    code = 1
    try:
        try:
            request = json.loads(raw.decode("utf-8"))
        except Exception:
            secrets = collect_secrets(raw.decode("utf-8", errors="replace"))
            raise
        secrets = collect_secrets(request)
        op = str(request.get("op") or "")
        payload = request.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}
        root = str(payload.get("vaultRoot") or "")
        vault = SecretVault(Path(root)) if root else None
        # Redirect extractor chatter before any third-party import prints.
        sys.stdout = capture
        from umd.netpolicy import public_resolution

        with public_resolution():
            result = _dispatch(op, materialize_payload(payload))
        sys.stdout = real_out
        _write_json(real_out, {"ok": True, "result": result}, secrets, vault)
        code = 0
    except BaseException as exc:
        sys.stdout = real_out
        kind = type(exc).__name__
        if kind not in {"PolicyError", "DnsError", "ExtractError", "AuthError", "TransferStop"}:
            kind = "ExtractError"
        try:
            message = scrub_text(f"{exc}\n{raw.decode('utf-8', errors='replace')}", secrets)[:500]
            trace = scrub_text(traceback.format_exc(), secrets)[-800:]
        except Exception:
            message, trace = "작업을 완료하지 못했습니다", ""
        if text_contains_secret(message + trace, secrets) or signed_urls_in(message + trace):
            message, trace = "작업을 완료하지 못했습니다", ""
        try:
            _write_json(real_out, {"ok": False, "kind": kind, "error": message, "trace": trace}, secrets)
        except Exception:
            pass
    finally:
        sys.stdout = real_out
        sys.stderr = real_err
        try:
            _emit_captured(capture, real_err, secrets)
        except Exception:
            pass
    return code


def _dispatch(op: str, payload: dict) -> dict:
    if op == "hold":
        import socket
        import time

        time.sleep(float(payload.get("seconds") or 0.4))
        socket.getaddrinfo(str(payload.get("host") or "127.0.0.1"), int(payload.get("port") or 9))
        return {"held": True}
    if op == "resolve":
        import socket

        socket.getaddrinfo(str(payload.get("host") or ""), int(payload.get("port") or 80))
        return {"resolved": True}
    if op == "gallery-download":
        from umd.download.gallery_job import download_selected

        flag = Path(str(payload.get("cancelFlag") or ""))
        batch = download_selected(
            str(payload.get("url") or ""),
            Path(str(payload.get("directory") or "")),
            set(payload.get("only") or []),
            should_stop=lambda: flag.is_file(),
            isolated=False,
        )
        return batch.as_dict()
    if op == "gallery-extract":
        from umd.extract.gallery import extract_gallery

        return extract_gallery(str(payload.get("url") or "")).payload()
    if op == "video-extract":
        from umd.extract.video import extract_video

        return extract_video(str(payload.get("url") or "")).payload()
    if op == "video-download":
        from umd.download.video_job import download_video

        flag = Path(str(payload.get("cancelFlag") or ""))
        progress = Path(str(payload.get("progressPath") or ""))

        def should_stop() -> str:
            if not flag.is_file():
                return ""
            return flag.read_text(encoding="ascii").strip() or "cancel"

        def on_progress(downloaded: int, total: int) -> None:
            if progress.parent:
                progress.write_text(
                    json.dumps({"downloaded": downloaded, "total": total}),
                    encoding="utf-8",
                )

        path, size = download_video(
            str(payload.get("url") or ""),
            Path(str(payload.get("directory") or "")),
            format_id=str(payload.get("formatId") or ""),
            should_stop=should_stop,
            on_progress=on_progress,
        )
        return {"path": str(path), "size": size}
    raise RuntimeError("지원하지 않는 격리 작업입니다")


if __name__ == "__main__":
    raise SystemExit(main())
