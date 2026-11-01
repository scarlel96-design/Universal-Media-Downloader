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


def main() -> int:
    os.environ["UMD_IN_WORKER"] = "1"
    raw = sys.stdin.buffer.read()
    real_out = sys.stdout
    try:
        request = json.loads(raw.decode("utf-8"))
        op = str(request.get("op") or "")
        payload = request.get("payload") or {}
        # Redirect extractor chatter before any third-party import prints.
        sys.stdout = sys.stderr
        from umd.netpolicy import public_resolution

        with public_resolution():
            result = _dispatch(op, payload)
        sys.stdout = real_out
        real_out.buffer.write(json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode("utf-8"))
        real_out.buffer.write(b"\n")
        return 0
    except BaseException as exc:
        sys.stdout = real_out
        kind = type(exc).__name__
        if kind not in {"PolicyError", "DnsError", "ExtractError", "AuthError", "TransferStop"}:
            kind = "ExtractError"
        body = {"ok": False, "kind": kind, "error": str(exc)[:500], "trace": traceback.format_exc()[-800:]}
        try:
            real_out.buffer.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))
            real_out.buffer.write(b"\n")
            real_out.buffer.flush()
        except Exception:
            pass
        return 1


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
