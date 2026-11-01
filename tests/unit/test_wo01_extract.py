import json
from pathlib import Path
from urllib.parse import urljoin

from umd.extract.html_images import extract_images, normalize_url

POSTS = Path(__file__).resolve().parents[1] / "fixtures" / "posts"
HTML = (POSTS / "article.html").read_text(encoding="utf-8")
EXPECTED = json.loads((POSTS / "expected.json").read_text(encoding="utf-8"))
PAGE = "http://127.0.0.1:8765/article.html"


def _candidates():
    return extract_images(HTML, PAGE)


def _by_class(candidates, classification):
    return [item for item in candidates if item.classification == classification]


def _url(path: str) -> str:
    return urljoin(PAGE, path)


def test_01_extracts_only_article_images():
    content = _by_class(_candidates(), "content")
    assert [item.url for item in content] == [_url(item["file"]) for item in EXPECTED["content"]]
    assert [item.title for item in content] == [item["title"] for item in EXPECTED["content"]]


def test_02_excludes_ads_related_and_chrome():
    excluded = _by_class(_candidates(), "excluded")
    assert [item.url for item in excluded] == [_url(item["file"]) for item in EXPECTED["excluded"]]
    for item, spec in zip(excluded, EXPECTED["excluded"], strict=True):
        text = " ".join(item.reasons)
        for needle in spec["reasons"]:
            assert needle in text
        assert "크기" not in text


def test_03_keeps_small_images_inside_the_article():
    content = {item.url: item for item in _by_class(_candidates(), "content")}
    panel = content[_url("photos/panel.png")]
    dot = content[_url("photos/dot.png")]
    assert panel.width == 40 and panel.height == 40
    assert dot.width == 1 and dot.height == 1
    assert "작지만" in " ".join(panel.reasons)
    assert "작지만" in " ".join(dot.reasons)
    tiny = next(item for item in _candidates() if item.url.endswith("/photos/tiny.png"))
    assert tiny.classification == "uncertain"
    assert tiny.width == 8 and tiny.height == 8


def test_04_srcset_lazy_and_picture():
    by_url = {item.url: item for item in _candidates()}
    assert "srcset에서 가장 넓은" in " ".join(by_url[_url("photos/lake-1200.jpg")].reasons)
    assert "data-src" in " ".join(by_url[_url("photos/lazy.png")].reasons)
    assert "data-original" in " ".join(by_url[_url("photos/panel.png")].reasons)
    assert "picture source" in " ".join(by_url[_url("photos/pic-800.webp")].reasons)
    assert "원본 파일" in " ".join(by_url[_url("photos/original.png")].reasons)


def test_05_normalizes_relative_and_absolute_urls():
    for group in ("content", "excluded", "uncertain"):
        for spec in EXPECTED[group]:
            assert any(item.url == _url(spec["file"]) for item in _candidates())
    page = "http://127.0.0.1:8765/nested/article.html"
    html = """
    <article>
      <img src="photos/coast.png#part">
      <img src="/photos/logo.png">
      <img src="https://cdn.example.com/a.png">
      <img src="//cdn.example.com/b.png">
    </article>
    """
    found = [item.url for item in extract_images(html, page)]
    assert found == [
        "http://127.0.0.1:8765/nested/photos/coast.png",
        "http://127.0.0.1:8765/photos/logo.png",
        "https://cdn.example.com/a.png",
        "http://cdn.example.com/b.png",
    ]
    assert normalize_url("http://127.0.0.1/a.html", "http://127.0.0.1:80/x.png") == "http://127.0.0.1/x.png"


def test_06_merges_duplicate_candidates():
    candidates = _candidates()
    urls = [item.url for item in candidates]
    assert len(urls) == len(set(urls))
    assert urls.count(_url("photos/coast.png")) == 1
    assert len(candidates) == 15
    absent = {_url(path) for path in EXPECTED["absent"]}
    assert absent.isdisjoint(urls)
