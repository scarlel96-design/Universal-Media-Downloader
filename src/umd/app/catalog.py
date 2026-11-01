"""Design-sample media rows. These are not downloaded files."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SampleMedia:
    title: str
    kind: str
    selected: bool
    hue: int


# Titles follow the V1.1 visual prototype. Two rows are videos so the filter
# has a real branch. Nothing here is fetched from the network.
CATALOG: tuple[SampleMedia, ...] = (
    SampleMedia("Coastal Light", "image", True, 204),
    SampleMedia("Soft Morning", "image", True, 32),
    SampleMedia("Quiet Lake", "image", True, 168),
    SampleMedia("Solstice", "image", True, 338),
    SampleMedia("Highland", "video", True, 118),
    SampleMedia("Winter Tide", "image", False, 198),
    SampleMedia("Rose Horizon", "image", True, 348),
    SampleMedia("Stillness", "image", True, 252),
    SampleMedia("The Valley", "image", True, 96),
    SampleMedia("Warm Dusk", "video", False, 18),
    SampleMedia("Blue Hour", "image", True, 222),
    SampleMedia("Afterglow", "image", True, 14),
)


def accepts_kind(kind: str, mode: str) -> bool:
    if mode == "all":
        return True
    return kind == mode
