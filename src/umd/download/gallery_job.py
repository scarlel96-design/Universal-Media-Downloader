"""Site download for gallery items that have no direct file URL.

Direct image URLs use the HTTPX engine instead, so this path is not used for
the same file.
"""

from __future__ import annotations
from pathlib import Path

from umd.netpolicy import public_resolution, require_public


def download_with_gallery(page_url: str, directory: Path) -> list[Path]:
    import gallery_dl.config as config
    from gallery_dl.job import DownloadJob

    require_public(page_url)
    directory.mkdir(parents=True, exist_ok=True)
    before = {path.resolve() for path in directory.rglob("*") if path.is_file()}
    config.set(("extractor",), "proxy-env", False)
    config.set(("extractor",), "proxy", None)
    config.set((), "base-directory", str(directory))
    job = DownloadJob(page_url)
    with public_resolution():
        job.run()
    after = [path for path in directory.rglob("*") if path.is_file() and path.resolve() not in before]
    return after
