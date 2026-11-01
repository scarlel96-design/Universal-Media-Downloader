import threading
from pathlib import Path

import pytest

from umd.download.images import download_one
from umd.storage.database import SCHEMA_VERSION, Library
from wo01_support import EXPECTED, PHOTOS, base_url, serve


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
    assert short.status == "실패" and "잘렸" in short.error
    assert refused.status == "실패" and "허용되지 않은" in refused.error
    assert list(tmp_path.iterdir()) == []


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
