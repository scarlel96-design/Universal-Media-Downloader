"""HTML image extraction. No JavaScript rendering and no site-specific extractors."""

from umd.extract.html_images import Candidate, extract_images

__all__ = ["Candidate", "extract_images"]
