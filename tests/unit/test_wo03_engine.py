"""Public-mode downloads stay on the checked address and the existing queue."""

import asyncio
from pathlib import Path

import httpx
import pytest

from umd.download.engine import DownloadItem, run_job
from umd.download.pin import PinnedBackend, empty_pins
from umd.download.schedule import EngineConfig
from wo02_support import PNG, LabServer, Reply


def _resolver(host: str, _port: int) -> list[str]:
    if host == "example.com":
        return ["93.184.216.34"]
    return ["10.0.0.1"]


def test_pinned_backend_connects_to_the_pin_and_keeps_the_host_header(lab: LabServer):
    lab.mount("/pin.png", lambda _path, _query, _headers: Reply(body=PNG))

    async def fetch() -> bytes:
        pins = empty_pins()
        pins.remember("example.com", lab.port, "127.0.0.1")
        transport = httpx.AsyncHTTPTransport(trust_env=False, retries=0)
        transport._pool._network_backend = PinnedBackend(transport._pool._network_backend, pins)
        async with httpx.AsyncClient(transport=transport, trust_env=False, timeout=5) as client:
            response = await client.get(f"http://example.com:{lab.port}/pin.png")
            response.raise_for_status()
            return response.content

    assert asyncio.run(fetch()) == PNG
    host = lab.requests[-1]["host"]
    assert host.split(":")[0] == "example.com"


def test_public_redirect_to_loopback_is_refused_before_a_second_request(tmp_path: Path):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})

    engine = run_job(
        tmp_path,
        [DownloadItem("one", "http://example.com/a")],
        EngineConfig(
            network_mode="public",
            resolver=_resolver,
            transport=httpx.MockTransport(handler),
            max_retries=0,
            timeout=5,
        ),
    )
    failed = [event for event in engine.events if event.terminal]
    assert failed[-1].status == "실패"
    assert "리다이렉트" in failed[-1].error
    assert "내부" in failed[-1].error
    assert seen == ["http://example.com/a"]


def test_public_auth_failure_is_not_retried(tmp_path: Path):
    hits = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        hits["count"] += 1
        return httpx.Response(401)

    engine = run_job(
        tmp_path,
        [DownloadItem("one", "https://example.com/private.png")],
        EngineConfig(
            network_mode="public",
            resolver=_resolver,
            transport=httpx.MockTransport(handler),
            max_retries=3,
            timeout=5,
        ),
    )
    failed = [event for event in engine.events if event.terminal][-1]
    assert failed.status == "실패"
    assert "인증이 필요합니다" in failed.error
    assert hits["count"] == 1


def test_public_mode_saves_an_allowed_image_and_renames_a_collision(tmp_path: Path):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=PNG)

    engine = run_job(
        tmp_path,
        [
            DownloadItem("one", "http://example.com/coast.png"),
            DownloadItem("two", "http://example.com/coast.png"),
        ],
        EngineConfig(
            network_mode="public",
            resolver=_resolver,
            transport=httpx.MockTransport(handler),
            max_retries=0,
            timeout=5,
        ),
    )
    done = [event for event in engine.events if event.status == "완료"]
    assert len(done) == 2
    paths = sorted(path.name for path in tmp_path.iterdir() if path.is_file())
    assert paths == ["coast-2.png", "coast.png"]
    assert (tmp_path / "coast.png").read_bytes() == PNG
    assert list(tmp_path.glob("*.part")) == []


def test_local_mode_still_refuses_a_public_url_without_connecting(tmp_path: Path):
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("local mode must not open a public URL")

    engine = run_job(
        tmp_path,
        [DownloadItem("one", "https://example.com/a.png")],
        EngineConfig(transport=httpx.MockTransport(handler), max_retries=0, timeout=5),
    )
    failed = [event for event in engine.events if event.terminal][-1]
    assert failed.error == "허용되지 않은 주소입니다"


@pytest.fixture
def lab() -> LabServer:
    server = LabServer()
    yield server
    server.shutdown()
