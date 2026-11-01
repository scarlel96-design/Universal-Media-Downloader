"""Image downloads. Single-file saves stay synchronous. Jobs use HTTPX."""

from umd.download.engine import DownloadEngine, DownloadItem, ItemEvent, run_job
from umd.download.images import DownloadResult, download_one, sniff_image
from umd.download.schedule import DEFAULT_PRESET, PRESETS, EngineConfig

__all__ = [
    "DEFAULT_PRESET",
    "PRESETS",
    "DownloadEngine",
    "DownloadItem",
    "DownloadResult",
    "EngineConfig",
    "ItemEvent",
    "download_one",
    "run_job",
    "sniff_image",
]
