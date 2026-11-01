"""Extract image candidates from static HTML and classify them.

The parser reads the markup it is given. It does not run JavaScript and it does
not know about any particular website. Size is recorded as a note. It is never
the only reason an image is excluded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit, urljoin

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".bmp", ".jfif"}
_CONTENT_TAGS = {"article", "main"}
_CHROME_TAGS = {"header", "nav", "footer"}
_CONTENT_HINTS = {"post-body", "article-body", "entry-content", "post-content", "story-body", "article", "main"}
_RELATED_HINTS = {"related", "recommend", "recommended", "suggestions", "related-posts", "more-posts"}
_AD_HINTS = {"ad", "ads", "advert", "sponsor", "advertisement", "sponsored", "ad-sponsor"}
_AVATAR_HINTS = {"avatar", "author-avatar", "profile-photo", "author-photo"}
_LOGO_HINTS = {"logo", "site-logo"}
_ICON_HINTS = {"icon", "sprite", "nav-icon"}
_TRACKER_HINTS = {"tracker", "pixel", "beacon", "tracking"}
_VOID = {"img", "source", "br", "hr", "meta", "link", "input", "area", "base", "col", "embed", "wbr"}

CLASS_LABELS = {
    "content": "본문 이미지",
    "uncertain": "판단 불확실",
    "excluded": "기본 제외",
}


@dataclass
class Candidate:
    url: str
    classification: str
    reasons: list[str]
    title: str
    origin: str
    width: int | None = None
    height: int | None = None

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "classification": self.classification,
            "reasons": list(self.reasons),
            "title": self.title,
            "origin": self.origin,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class _Frame:
    tag: str
    in_content: bool = False
    in_related: bool = False
    in_ad: bool = False
    in_chrome: bool = False
    in_avatar: bool = False
    in_logo: bool = False
    in_icon: bool = False
    in_tracker: bool = False


@dataclass
class _Picture:
    frame: _Frame
    best_url: str = ""
    best_score: float = -1.0
    alt: str = ""
    width: int | None = None
    height: int | None = None
    origin: str = "picture"


def _hints(value: str) -> set[str]:
    raw = (value or "").lower()
    found = {raw.strip()} if raw.strip() else set()
    for piece in raw.split():
        found.add(piece)
        found.update(part for part in re.split(r"[^a-z0-9]+", piece) if part)
    return found


def _number(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"\s*(\d+)", value)
    if not match:
        return None
    return int(match.group(1))


def _is_small(width: int | None, height: int | None) -> bool:
    if width is None or height is None:
        return False
    return width <= 64 and height <= 64


def normalize_url(base: str, raw: str) -> str | None:
    text = (raw or "").strip()
    if not text or text.startswith(("#", "data:", "javascript:", "mailto:", "blob:")):
        return None
    absolute = urljoin(base, text)
    parts = urlsplit(absolute)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https", "file"}:
        return None
    hostname = (parts.hostname or "").lower()
    if scheme in {"http", "https"} and hostname:
        port = parts.port
        default = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        if port and not default:
            netloc = f"{hostname}:{port}"
        else:
            netloc = hostname
    else:
        netloc = parts.netloc
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def _looks_like_image(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return any(path.endswith(ext) for ext in _IMAGE_EXT)


def _best_srcset(value: str) -> tuple[str, float] | None:
    best_url = ""
    best_score = -1.0
    for part in (value or "").split(","):
        bits = part.strip().split()
        if not bits:
            continue
        url = bits[0]
        score = 0.0
        if len(bits) > 1:
            desc = bits[-1].lower()
            if desc.endswith("w") and desc[:-1].isdigit():
                score = float(desc[:-1])
            elif desc.endswith("x"):
                try:
                    score = float(desc[:-1]) * 10000.0
                except ValueError:
                    score = 0.0
        if score >= best_score:
            best_url = url
            best_score = score
    if not best_url:
        return None
    return best_url, best_score


def _classify(frame: _Frame, *, small: bool, original_link: bool, origin: str) -> tuple[str, list[str]]:
    if frame.in_ad:
        return "excluded", ["광고 영역"]
    if frame.in_tracker:
        return "excluded", ["추적 픽셀로 표시된 이미지"]
    if frame.in_related:
        return "excluded", ["추천 또는 관련 게시물 영역"]
    if frame.in_logo:
        return "excluded", ["로고"]
    if frame.in_avatar:
        return "excluded", ["작성자 프로필"]
    if frame.in_icon and not frame.in_content:
        return "excluded", ["아이콘"]
    if frame.in_chrome and not frame.in_content:
        return "excluded", ["페이지 장식 영역"]
    notes = _origin_notes(origin, original_link)
    if frame.in_content:
        reasons = ["본문 컨테이너 안의 이미지", *notes]
        if small:
            reasons.append("표시 크기가 작지만 본문 이미지로 유지")
        return "content", reasons
    return "uncertain", ["본문 컨테이너 밖이며 광고·장식 단서가 없음", *notes]


def _origin_notes(origin: str, original_link: bool) -> list[str]:
    notes: list[str] = []
    if origin == "srcset":
        notes.append("srcset에서 가장 넓은 후보를 선택")
    elif origin == "data-src":
        notes.append("지연 로딩 data-src를 사용")
    elif origin == "data-original":
        notes.append("data-original을 사용")
    elif origin == "picture":
        notes.append("picture source에서 가장 넓은 후보를 선택")
    if original_link or origin == "original-link":
        notes.append("이미지에 연결된 원본 파일 링크를 사용")
    return notes


def _child_frame(parent: _Frame, tag: str, attrs: dict[str, str]) -> _Frame:
    hinted = _hints(attrs.get("class", "")) | _hints(attrs.get("id", ""))
    return _Frame(
        tag=tag,
        in_content=parent.in_content or tag in _CONTENT_TAGS or bool(hinted & _CONTENT_HINTS),
        in_related=parent.in_related or tag == "aside" or bool(hinted & _RELATED_HINTS),
        in_ad=parent.in_ad or bool(hinted & _AD_HINTS),
        in_chrome=parent.in_chrome or tag in _CHROME_TAGS,
        in_avatar=parent.in_avatar or bool(hinted & _AVATAR_HINTS),
        in_logo=parent.in_logo or bool(hinted & _LOGO_HINTS),
        in_icon=parent.in_icon or bool(hinted & _ICON_HINTS),
        in_tracker=parent.in_tracker or bool(hinted & _TRACKER_HINTS),
    )


def _pick_img(attrs: dict[str, str]) -> tuple[str, str]:
    if attrs.get("data-original"):
        return attrs["data-original"], "data-original"
    if attrs.get("data-src"):
        return attrs["data-src"], "data-src"
    if attrs.get("srcset"):
        found = _best_srcset(attrs["srcset"])
        if found:
            return found[0], "srcset"
    if attrs.get("src"):
        return attrs["src"], "src"
    return "", ""


class _Extractor(HTMLParser):
    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.stack: list[_Frame] = [_Frame(tag="document")]
        self.anchor: str | None = None
        self.picture: _Picture | None = None
        self.found: list[Candidate] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs = {key.lower(): (value or "") for key, value in attrs_list}
        frame = _child_frame(self.stack[-1], tag, attrs)
        if tag == "a":
            href = normalize_url(self.page_url, attrs.get("href", ""))
            self.anchor = href if href and _looks_like_image(href) else None
        if tag == "picture":
            self.picture = _Picture(frame=frame)
        if tag == "source" and self.picture is not None:
            self._take_source(attrs)
        if tag == "img":
            self._take_img(frame, attrs)
        if tag not in _VOID:
            self.stack.append(frame)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "picture" and self.picture is not None:
            self._finish_picture()
        if tag == "a":
            self.anchor = None
        if tag in _VOID:
            return
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def _take_source(self, attrs: dict[str, str]) -> None:
        assert self.picture is not None
        raw = ""
        score = 0.0
        if attrs.get("srcset"):
            found = _best_srcset(attrs["srcset"])
            if found:
                raw, score = found
        elif attrs.get("src"):
            raw = attrs["src"]
        if raw and score >= self.picture.best_score:
            self.picture.best_url = raw
            self.picture.best_score = score
            self.picture.origin = "picture"

    def _take_img(self, frame: _Frame, attrs: dict[str, str]) -> None:
        width = _number(attrs.get("width"))
        height = _number(attrs.get("height"))
        alt = (attrs.get("alt") or "").strip()
        if self.anchor:
            self._emit(
                self.anchor,
                frame,
                alt=alt or _title_from_url(self.anchor),
                origin="original-link",
                width=width,
                height=height,
                original_link=True,
            )
            if self.picture is not None:
                self.picture.best_url = ""
            return
        if self.picture is not None:
            self.picture.alt = alt or self.picture.alt
            self.picture.width = width
            self.picture.height = height
            if not self.picture.best_url:
                raw, origin = _pick_img(attrs)
                self.picture.best_url = raw
                self.picture.origin = origin or "src"
            return
        raw, origin = _pick_img(attrs)
        if not raw:
            return
        self._emit(raw, frame, alt=alt, origin=origin, width=width, height=height, original_link=False)

    def _finish_picture(self) -> None:
        assert self.picture is not None
        picture = self.picture
        self.picture = None
        if not picture.best_url:
            return
        self._emit(
            picture.best_url,
            picture.frame,
            alt=picture.alt,
            origin=picture.origin,
            width=picture.width,
            height=picture.height,
            original_link=False,
        )

    def _emit(
        self,
        raw: str,
        frame: _Frame,
        *,
        alt: str,
        origin: str,
        width: int | None,
        height: int | None,
        original_link: bool,
    ) -> None:
        url = raw if origin == "original-link" else normalize_url(self.page_url, raw)
        if not url:
            return
        classification, reasons = _classify(
            frame,
            small=_is_small(width, height),
            original_link=original_link,
            origin=origin,
        )
        title = alt or _title_from_url(url)
        self.found.append(
            Candidate(
                url=url,
                classification=classification,
                reasons=reasons,
                title=title,
                origin=origin,
                width=width,
                height=height,
            )
        )


def _title_from_url(url: str) -> str:
    name = urlsplit(url).path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    return stem or "image"


def _merge(found: list[Candidate]) -> list[Candidate]:
    rank = {"content": 3, "uncertain": 2, "excluded": 1}
    order: list[str] = []
    merged: dict[str, Candidate] = {}
    for candidate in found:
        current = merged.get(candidate.url)
        if current is None:
            merged[candidate.url] = candidate
            order.append(candidate.url)
            continue
        if rank[candidate.classification] > rank[current.classification]:
            merged[candidate.url] = candidate
            continue
        if candidate.classification == current.classification:
            for reason in candidate.reasons:
                if reason not in current.reasons:
                    current.reasons.append(reason)
    return [merged[url] for url in order]


def extract_images(html: str, page_url: str) -> list[Candidate]:
    """Return deduplicated image candidates for one static page."""
    parser = _Extractor(page_url)
    parser.feed(html)
    parser.close()
    if parser.picture is not None:
        parser._finish_picture()
    return _merge(parser.found)
