"""WO-04A. gallery-dl saves only the files the user selected."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest

from umd.download.gallery_job import GalleryBatch, SelectiveDownloadJob, download_selected, place_file

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
OTHER = PNG + b"\x00more"


def _job(tmp_path: Path, only: set[str], should_stop=None) -> SelectiveDownloadJob:
    staging = tmp_path / "staging"
    staging.mkdir()
    job = SelectiveDownloadJob.__new__(SelectiveDownloadJob)
    job.only_urls = set(only)
    job.should_stop = should_stop
    job.batch = GalleryBatch()
    job.staging = staging
    job.rejected = []
    job._job = type("Fake", (), {"pathfmt": None})()
    return job


def test_empty_selection_saves_nothing(tmp_path: Path):
    batch = download_selected("https://example.com/album", tmp_path, set(), isolated=False)
    assert batch.files == []
    assert list(tmp_path.iterdir()) == []


def test_one_selected_image_is_the_only_saved_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    chosen = "https://cdn.example/a.png"
    other = "https://cdn.example/b.png"
    job = _job(tmp_path, {chosen})

    def fake(self, url, kwdict):
        (job.staging / "a.png").write_bytes(PNG)

    monkeypatch.setattr("gallery_dl.job.DownloadJob.handle_url", fake)
    job.handle_url(other, {})
    job.handle_url(chosen, {})
    saved = [path.name for path in tmp_path.iterdir() if path.is_file()]
    assert saved == ["a.png"]
    assert job.rejected == [other]
    assert (tmp_path / "a.png").read_bytes() == PNG
    assert job.batch.files[0].state == "new"
    assert job.batch.files[0].sha256 == hashlib.sha256(PNG).hexdigest()
    assert job.batch.files[0].url == chosen


def test_multi_gallery_keeps_only_the_selected_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    first = "https://cdn.example/a.png"
    second = "https://cdn.example/b.png"
    skipped = "https://cdn.example/c.png"
    job = _job(tmp_path, {first, second})
    bodies = {first: PNG, second: OTHER}

    def fake(self, url, kwdict):
        name = "a.png" if url == first else "b.png"
        (job.staging / name).write_bytes(bodies[url])

    monkeypatch.setattr("gallery_dl.job.DownloadJob.handle_url", fake)
    job.handle_url(skipped, {})
    job.handle_url(first, {})
    job.handle_url(second, {})
    saved = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    assert saved == {"a.png": PNG, "b.png": OTHER}
    assert skipped in job.rejected
    assert {item.url for item in job.batch.files} == {first, second}
    assert [item.state for item in job.batch.files] == ["new", "new"]


def test_every_gallery_file_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    urls = [f"https://cdn.example/{index}.png" for index in range(3)]
    job = _job(tmp_path, set(urls))

    def fake(self, url, kwdict):
        index = url.rsplit("/", 1)[-1]
        (job.staging / index).write_bytes(PNG + index.encode("ascii"))

    monkeypatch.setattr("gallery_dl.job.DownloadJob.handle_url", fake)
    for url in urls:
        job.handle_url(url, {})
    assert len(job.batch.files) == 3
    for item in job.batch.files:
        body = Path(item.path).read_bytes()
        assert item.size == len(body)
        assert item.sha256 == hashlib.sha256(body).hexdigest()
        assert item.state == "new"
        assert item.error == ""


def test_an_existing_identical_file_is_not_written_again(tmp_path: Path):
    target = tmp_path / "a.png"
    target.write_bytes(PNG)
    source = tmp_path / "incoming.png"
    source.write_bytes(PNG)
    placed, state, digest = place_file(tmp_path, source, "a.png")
    assert state == "existing"
    assert placed == target
    assert digest == hashlib.sha256(PNG).hexdigest()
    assert not source.exists()
    assert target.read_bytes() == PNG


def test_a_filename_collision_keeps_both_byte_streams(tmp_path: Path):
    original = tmp_path / "a.png"
    original.write_bytes(PNG)
    source = tmp_path / "incoming.png"
    source.write_bytes(OTHER)
    placed, state, digest = place_file(tmp_path, source, "a.png")
    assert state == "new"
    assert placed.name == "a-2.png"
    assert digest == hashlib.sha256(OTHER).hexdigest()
    assert original.read_bytes() == PNG
    assert placed.read_bytes() == OTHER


def test_cancel_records_the_file_as_cancelled_and_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    chosen = "https://cdn.example/a.png"
    job = _job(tmp_path, {chosen}, should_stop=lambda: True)

    def fake(self, url, kwdict):
        raise AssertionError("cancelled url must not be saved")

    monkeypatch.setattr("gallery_dl.job.DownloadJob.handle_url", fake)
    with pytest.raises(Exception):
        job.handle_url(chosen, {})
    assert job.batch.cancelled is True
    assert job.batch.files == []
    assert [path.name for path in tmp_path.iterdir() if path.is_file()] == []


def test_a_save_error_is_recorded_on_that_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    chosen = "https://cdn.example/a.png"
    job = _job(tmp_path, {chosen})

    def fake(self, url, kwdict):
        raise RuntimeError("disk full")

    monkeypatch.setattr("gallery_dl.job.DownloadJob.handle_url", fake)
    job.handle_url(chosen, {})
    assert job.batch.files[0].state == "failed"
    assert "disk full" in job.batch.files[0].error
    assert [path.name for path in tmp_path.iterdir() if path.is_file()] == []
