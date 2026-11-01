"""Concurrency gates and retry timing for the bulk downloader.

Limits count acquisitions that are held only while a socket is active.
Shrinking a limit does not cancel a transfer that already holds a slot.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

PRESETS: dict[str, tuple[int, int]] = {
    "안정": (4, 2),
    "균형": (12, 3),
    "고속": (24, 4),
}
DEFAULT_PRESET = "균형"
RETRYABLE_STATUS = frozenset({429, 503})


@dataclass
class EngineConfig:
    preset: str = DEFAULT_PRESET
    global_limit: int | None = None
    per_host: int | None = None
    timeout: float = 30.0
    max_retries: int = 3
    retry_after_cap: float = 30.0
    backoff_base: float = 0.25
    backoff_cap: float = 8.0
    per_file_cap: int | None = None
    total_cap: int | None = None
    chunk_size: int = 64 * 1024

    def limits(self) -> tuple[int, int]:
        if self.preset not in PRESETS and (self.global_limit is None or self.per_host is None):
            raise ValueError(f"알 수 없는 다운로드 모드입니다: {self.preset}")
        base_global, base_host = PRESETS.get(self.preset, (12, 3))
        global_limit = base_global if self.global_limit is None else self.global_limit
        per_host = base_host if self.per_host is None else self.per_host
        return max(1, int(global_limit)), max(1, int(per_host))


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return max(0.0, (when - current).total_seconds())


def retry_delay(
    attempt: int,
    retry_after: str | None,
    *,
    cap: float,
    base: float,
    rng: random.Random | None = None,
) -> float:
    """Honor Retry-After when it parses. Otherwise exponential backoff plus jitter."""
    parsed = parse_retry_after(retry_after)
    if parsed is not None:
        return min(max(0.0, cap), parsed)
    draw = rng or random
    raw = base * (2 ** max(0, attempt - 1))
    jitter = draw.uniform(0, raw * 0.25)
    return min(max(0.0, cap), raw + jitter)


class SlotGate:
    """Async limit on the number of holders. Waiters observe the live limit."""

    def __init__(self, limit: int) -> None:
        self._limit = max(1, int(limit))
        self._active = 0
        self.peak = 0
        self._cond = asyncio.Condition()

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def active(self) -> int:
        return self._active

    async def acquire(self) -> None:
        async with self._cond:
            while self._active >= self._limit:
                await self._cond.wait()
            self._active += 1
            if self._active > self.peak:
                self.peak = self._active

    async def release(self) -> None:
        async with self._cond:
            if self._active > 0:
                self._active -= 1
            self._cond.notify_all()

    async def set_limit(self, limit: int) -> None:
        async with self._cond:
            self._limit = max(1, int(limit))
            self._cond.notify_all()


class HostBook:
    """One gate per host. Repeated errors lower that host's limit, never below 1."""

    def __init__(self, per_host: int) -> None:
        self.per_host = max(1, int(per_host))
        self._gates: dict[str, SlotGate] = {}
        self._streak: dict[str, int] = {}
        self._penalized: set[str] = set()
        self._lock = asyncio.Lock()

    def stats(self, host: str) -> tuple[int, int, int]:
        gate = self._gates.get(host)
        active = gate.active if gate else 0
        limit = gate.limit if gate else self.per_host
        return active, limit, self._streak.get(host, 0)

    async def acquire(self, host: str) -> SlotGate:
        async with self._lock:
            gate = self._gates.get(host)
            if gate is None:
                gate = SlotGate(self.per_host)
                self._gates[host] = gate
        await gate.acquire()
        return gate

    async def penalize(self, host: str) -> None:
        async with self._lock:
            self._streak[host] = self._streak.get(host, 0) + 1
            gate = self._gates.get(host)
            if gate is not None and self._streak[host] >= 3 and gate.limit > 1:
                self._streak[host] = 0
                self._penalized.add(host)
                await gate.set_limit(gate.limit - 1)

    async def reward(self, host: str) -> None:
        async with self._lock:
            self._streak[host] = 0

    async def retarget(self, per_host: int) -> None:
        async with self._lock:
            self.per_host = max(1, int(per_host))
            for host, gate in self._gates.items():
                if host in self._penalized:
                    await gate.set_limit(min(gate.limit, self.per_host))
                else:
                    await gate.set_limit(self.per_host)
