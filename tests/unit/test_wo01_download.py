import os
import threading
from pathlib import Path

import pytest

from umd.download import images
from umd.download.images import download_one
from umd.storage.database import SCHEMA_VERSION, Library
from wo01_support import EXPECTED, PHOTOS, ProbeServer, base_url, serve


@pytest.fixture(scope="module")
def server():
    httpd = serve()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def test_09_saved_bytes_match_the_fixture(server, tmp_path: Path):
    root = base_url(server)
    saved = []
    for spec in EXPECTED["content"]:
        result = download_one(f"{root}/{spec['file']}", tmp_path)
        assert result.status == "완료", result.error
        assert result.error == ""
        file = Path(result.path)
        assert file.is_file()
        assert file.stat().st_size == result.size
        assert file.read_bytes() == (PHOTOS / Path(spec["file"]).name).read_bytes()
        assert not file.name.endswith(".part")
        saved.append(file)
    assert not list(tmp_path.glob("*.part"))
    assert len(saved) == len(EXPECTED["content"])


def test_10_same_filename_gets_a_suffix(server, tmp_path: Path):
    root = base_url(server)
    reserved: set[str] = set()
    first = download_one(f"{root}/photos/coast.png", tmp_path, reserved=reserved)
    second = download_one(f"{root}/alias/coast.png", tmp_path, reserved=reserved)
    assert first.status == "완료" and second.status == "완료"
    names = sorted(path.name for path in tmp_path.iterdir())
    assert names == ["coast-2.png", "coast.png"]
    blobs = {path.read_bytes() for path in tmp_path.iterdir()}
    assert blobs == {(PHOTOS / "coast.png").read_bytes(), (PHOTOS / "twin.png").read_bytes()}
    assert Path(first.path).read_bytes() == (PHOTOS / "coast.png").read_bytes()
    assert Path(second.path).read_bytes() == (PHOTOS / "twin.png").read_bytes()


def test_11_http_errors_and_corrupt_bodies_leave_no_file(server, tmp_path: Path):
    root = base_url(server)
    missing = download_one(f"{root}/missing.png", tmp_path)
    boom = download_one(f"{root}/boom.png", tmp_path)
    corrupt = download_one(f"{root}/corrupt.png", tmp_path)
    short = download_one(f"{root}/short.png", tmp_path)
    refused = download_one("https://example.com/secret.png", tmp_path)
    assert missing.status == "실패" and missing.error.startswith("HTTP 404")
    assert boom.status == "실패" and boom.error.startswith("HTTP 500")
    assert corrupt.status == "실패" and "형식" in corrupt.error
    assert short.status == "실패" and short.path == "" and short.size == 0
    assert "timed out" not in short.error
    # This socket closes after a short body. On this host that is either a
    # clean EOF ("응답이 잘렸습니다") or WinError 10054. A reset is not rewritten
    # as a truncated body, and a timeout is not accepted as either.
    assert ("잘렸" in short.error) or ("10054" in short.error)
    assert refused.status == "실패" and "허용되지 않은" in refused.error
    assert list(tmp_path.iterdir()) == []
    for result in (missing, boom, corrupt, short, refused):
        assert result.status != "완료"
        assert result.path == ""
        assert result.size == 0


def _failed_clean(result, folder: Path) -> None:
    assert result.status == "실패"
    assert result.status != "완료"
    assert result.path == ""
    assert result.size == 0
    assert list(folder.iterdir()) == []
    assert list(folder.glob("*.part")) == []


class _EofStream:
    """One controllable body. No socket is opened.

    ``download_one`` still compares ``Content-Length`` with the bytes ``read``
    returns. S3 observed EOF on a different connection from the one
    ``download_one`` opened, and that run was 26/30. This stream is the
    contract for a clean EOF. The real TCP close stays in the early-close test.
    """

    def __init__(self, body: bytes, declared: int, url: str) -> None:
        self._body = body
        self._pos = 0
        self.headers = {"Content-Length": str(declared)}
        self.status = 200
        self._url = url

    def geturl(self) -> str:
        return self._url

    def getcode(self) -> int:
        return 200

    def read(self, amount: int = -1) -> bytes:
        if amount is None or amount < 0:
            amount = len(self._body) - self._pos
        if self._pos >= len(self._body):
            return b""
        chunk = self._body[self._pos : self._pos + amount]
        self._pos += len(chunk)
        return chunk

    def __enter__(self) -> "_EofStream":
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


def test_eof_short_body_reports_truncation_and_keeps_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sent = (PHOTOS / "dot.png").read_bytes()
    assert len(sent) == 69
    url = "http://127.0.0.1/dot.png"
    seen: dict[str, object] = {}

    def opener(request: object, timeout: float = 30) -> _EofStream:
        seen["timeout"] = timeout
        seen["request"] = request
        stream = _EofStream(sent, len(sent) + 40, url)
        seen["stream"] = stream
        return stream

    monkeypatch.setattr(images, "urlopen", opener)
    result = download_one(url, tmp_path)
    stream = seen["stream"]
    assert isinstance(stream, _EofStream)
    assert stream._pos == len(sent)
    assert seen["timeout"] == 30
    assert int(stream.headers["Content-Length"]) - stream._pos == 40
    assert result.error == "응답이 잘렸습니다"
    _failed_clean(result, tmp_path)
    log_path = os.environ.get("WO04S4_CLASS_LOG")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write("contract-eof\n")
            handle.flush()


def _local_port(response: object) -> int | None:
    fp = getattr(response, "fp", None)
    raw = getattr(fp, "raw", None)
    sock = getattr(raw, "_sock", None)
    if sock is None and raw is not None:
        sock = getattr(getattr(raw, "raw", None), "_sock", None)
    if sock is None:
        return None
    try:
        return int(sock.getsockname()[1])
    except OSError:
        return None


class _TrackedResponse:
    """Log the reads of the socket ``download_one`` is using."""

    def __init__(self, inner: object, record: dict[str, object]) -> None:
        self._inner = inner
        self._record = record
        self.headers = inner.headers
        self.status = getattr(inner, "status", None)
        record["port"] = _local_port(inner)
        try:
            record["declared"] = int(inner.headers["Content-Length"])
        except (TypeError, ValueError, KeyError):
            record["declared"] = None

    def geturl(self) -> str:
        return self._inner.geturl()

    def getcode(self) -> int:
        return int(self._inner.getcode())

    def read(self, amount: int = -1) -> bytes:
        try:
            chunk = self._inner.read(amount)
        except TimeoutError:
            self._record["kind"] = "timeout"
            raise
        except ConnectionResetError:
            self._record["kind"] = "rst"
            raise
        except Exception as exc:
            partial = getattr(exc, "partial", None)
            if partial is not None:
                self._record["kind"] = "eof"
                self._record["received"] = int(self._record["received"]) + len(partial)
            else:
                self._record["kind"] = type(exc).__name__
            raise
        self._record["received"] = int(self._record["received"]) + len(chunk)
        if chunk == b"":
            self._record["kind"] = "eof"
        return chunk

    def __enter__(self) -> "_TrackedResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> object:
        return self._inner.__exit__(exc_type, exc, tb)


def _pair_sockets(probe: ProbeServer, attempts: list[dict[str, object]], before: int) -> None:
    fresh = probe.sockets[before:]
    used: set[int] = set()
    for attempt in attempts:
        port = attempt.get("port")
        match = None
        if port is not None:
            for record in fresh:
                if record["id"] in used:
                    continue
                if record.get("peer_port") == port:
                    match = record
                    break
        attempt["server_id"] = None if match is None else match["id"]
        if match is not None:
            used.add(int(match["id"]))
    missing = [item for item in attempts if item["server_id"] is None]
    if missing and len(fresh) == len(attempts):
        for attempt, record in zip(attempts, fresh):
            if attempt["server_id"] is None:
                attempt["server_id"] = record["id"]
    assert all(item["server_id"] is not None for item in attempts)
    assert len({item["server_id"] for item in attempts}) == len(attempts)


def test_tcp_early_close_is_classified_on_the_same_socket(tmp_path: Path):
    """A real short close is either clean EOF or RST on that same socket.

    The product result has to name the ending this download actually saw.
    A timeout is neither. S3's 26/30 is the separate-connection check, not
    this one.
    """

    sent = (PHOTOS / "dot.png").read_bytes()
    probe = ProbeServer("eof")
    attempts: list[dict[str, object]] = []
    real_open = images.urlopen

    def opener(request: object, timeout: float = 30):
        record: dict[str, object] = {"kind": None, "port": None, "declared": None, "received": 0, "server_id": None}
        try:
            response = real_open(request, timeout=timeout)
        except ConnectionResetError:
            record["kind"] = "rst"
            attempts.append(record)
            raise
        except Exception as exc:
            reason = getattr(exc, "reason", exc)
            record["kind"] = "rst" if isinstance(reason, ConnectionResetError) else type(exc).__name__
            attempts.append(record)
            raise
        tracked = _TrackedResponse(response, record)
        attempts.append(record)
        return tracked

    before = len(probe.sockets)
    images.urlopen = opener
    try:
        result = download_one(probe.url(), tmp_path)
    finally:
        images.urlopen = real_open
        probe.shutdown()
    _failed_clean(result, tmp_path)
    assert attempts
    _pair_sockets(probe, attempts, before)
    kinds = [str(item["kind"]) for item in attempts]
    assert "timeout" not in kinds
    assert "timed out" not in result.error
    last = attempts[-1]
    if last["kind"] == "eof":
        assert result.error == "응답이 잘렸습니다"
        assert last["declared"] == len(sent) + 40
        assert last["received"] == len(sent)
        assert int(last["declared"]) - int(last["received"]) == 40
    elif last["kind"] == "rst":
        assert kinds == ["rst"] * len(kinds)
        assert "10054" in result.error
        assert "잘렸" not in result.error
    else:
        raise AssertionError(f"unclassified {kinds} error={result.error}")
    log_path = os.environ.get("WO04S4_CLASS_LOG")
    if log_path:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"early-{last['kind']}\n")
            handle.flush()


def test_tcp_reset_stays_a_reset_and_keeps_no_file(tmp_path: Path):
    probe = ProbeServer("rst")
    try:
        result = download_one(probe.url(), tmp_path, timeout=2)
    finally:
        probe.shutdown()
    assert "잘렸" not in result.error
    assert "timed out" not in result.error
    assert "10054" in result.error
    _failed_clean(result, tmp_path)


def test_stalled_response_stays_a_timeout_and_keeps_no_file(tmp_path: Path):
    probe = ProbeServer("stall", hold=3)
    try:
        result = download_one(probe.url(), tmp_path, timeout=1)
    finally:
        probe.shutdown()
    assert result.error == "timed out"
    assert "잘렸" not in result.error
    assert "10054" not in result.error
    _failed_clean(result, tmp_path)


def test_matching_content_length_saves_the_file(tmp_path: Path):
    sent = (PHOTOS / "dot.png").read_bytes()
    probe = ProbeServer("ok")
    try:
        result = download_one(probe.url(), tmp_path)
    finally:
        probe.shutdown()
    assert result.status == "완료", result.error
    assert result.error == ""
    assert result.size == len(sent)
    saved = Path(result.path)
    assert saved.is_file()
    assert saved.read_bytes() == sent
    assert list(tmp_path.glob("*.part")) == []


def test_cancel_does_not_keep_a_partial_file(server, tmp_path: Path):
    root = base_url(server)
    cancel = threading.Event()

    def stop() -> None:
        cancel.wait(0.05)
        cancel.set()

    threading.Thread(target=stop, daemon=True).start()
    result = download_one(f"{root}/slow/cancel.png", tmp_path, cancel=cancel)
    assert result.status == "취소", result.error
    assert result.path == ""
    assert list(tmp_path.iterdir()) == []


def test_12_sqlite_schema_and_restart(tmp_path: Path):
    database = tmp_path / "library.sqlite"
    photo = PHOTOS / "dot.png"
    photo.parent.mkdir(parents=True, exist_ok=True)
    if not photo.exists():
        from wo01_support import ensure_photos

        ensure_photos()
    saved = tmp_path / "saved"
    saved.mkdir()
    target = saved / "dot.png"
    target.write_bytes(photo.read_bytes())
    library = Library(str(database))
    assert library.schema_version == SCHEMA_VERSION
    row = {
        "title": "Dot",
        "mediaUrl": "http://127.0.0.1/photos/dot.png",
        "classification": "content",
        "reasons": "본문 컨테이너 안의 이미지",
        "selected": True,
        "override": "",
        "status": "대기",
    }
    job_id = library.create_job("http://127.0.0.1/article.html", [row])
    library.update_download(row["itemId"], status="완료", path=str(target), size=target.stat().st_size, error="")
    library.set_job_status(job_id, "완료")
    library.close()

    restored = Library(str(database))
    job = restored.latest_job()
    assert job is not None
    assert job["id"] == job_id
    assert job["page_url"] == "http://127.0.0.1/article.html"
    assert job["status"] == "완료"
    assert job["created_at"] and job["completed_at"]
    items = restored.items(job_id)
    assert len(items) == 1
    assert items[0]["media_url"] == row["mediaUrl"]
    assert items[0]["classification"] == "content"
    assert items[0]["selected"] == 1
    assert items[0]["download_status"] == "완료"
    assert items[0]["saved_path"] == str(target)
    assert items[0]["byte_size"] == target.stat().st_size
    assert items[0]["error"] == ""
    assert restored.integrity_issues() == []
    target.unlink()
    assert restored.integrity_issues() == [f"missing:{items[0]['id']}"]
    restored.close()
