"""Preview selection, format choice, and the local-mode gate."""

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from umd.app.host import native_window_flags, uses_frameless
from umd.app.shell import MediaListModel, ShellBundle, row_from_candidate

QML = __import__("pathlib").Path(__file__).resolve().parents[2] / "src" / "umd" / "ui" / "qml" / "Main.qml"


def test_excluded_image_can_be_selected_again():
    app = QGuiApplication.instance() or QGuiApplication([])
    assert app is not None
    model = MediaListModel()
    model.replace(
        [
            row_from_candidate(
                {
                    "url": "http://127.0.0.1/ad.png",
                    "classification": "excluded",
                    "reasons": ["광고"],
                    "title": "Ad",
                },
                "http://127.0.0.1/post",
            )
        ]
    )
    assert model.item(0)["selected"] is False
    model.toggle(0)
    assert model.item(0)["selected"] is True
    assert model.item(0)["override"] == "included"


def test_local_mode_rejects_a_public_url_and_the_window_stays_native(tmp_path):
    app = QGuiApplication.instance() or QGuiApplication([])
    bundle = ShellBundle(db_path=str(tmp_path / "library.sqlite"))
    shell = bundle.shell
    assert shell.networkMode == "local"
    shell.setUrl("https://example.com/post")
    shell.analyze()
    app.processEvents()
    assert "127.0.0.1" in shell.toast
    assert shell.jobPhase == "대기"
    shell.setNetworkMode("public")
    assert shell.networkMode == "public"
    flags = native_window_flags()
    assert uses_frameless(flags) is False
    engine = QQmlApplicationEngine()
    bundle.expose(engine)
    engine.load(QUrl.fromLocalFile(str(QML)))
    roots = engine.rootObjects()
    assert roots, "QML failed to load"
    assert roots[0].property("hostMode") == "native-frame"
    video = row_from_candidate(
        {
            "url": "https://example.com/watch",
            "classification": "content",
            "reasons": ["yt-dlp"],
            "title": "Clip",
            "mediaType": "video",
            "delivery": "yt-dlp",
            "formatId": "best",
            "format": "240p ogv",
            "formats": [
                {"id": "best", "label": "240p ogv", "filesize": 500},
                {"id": "large", "label": "480p webm", "filesize": None, "filesizeNote": "예상 1.0 MB"},
            ],
            "duration": None,
            "width": None,
            "height": None,
            "extractorId": "yt-dlp",
        },
        "https://example.com/watch",
    )
    shell._model.replace([video])
    shell._using_samples = False
    shell._show_detail(shell._model.item(0))
    assert "미확인" in shell.detailMeta
    assert shell.formatChoices
    shell._detail_id = ""
    video["itemId"] = "clip"
    shell._model.replace([video])
    shell._detail_id = "clip"
    shell.selectFormat("large")
    chosen = shell._model.item(0)
    assert chosen["formatId"] == "large"
    assert chosen["filesizeNote"] == "예상 1.0 MB"
    roots[0].close()


def test_ci_workflow_is_manual_and_uses_a_standard_windows_runner():
    text = (QML.parents[4] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "pull_request" not in text
    assert "push:" not in text
    runners = [line.strip() for line in text.splitlines() if line.strip().startswith("runs-on:")]
    assert runners == ["runs-on: windows-latest", "runs-on: windows-latest"]
    assert "QT_QPA_PLATFORM: offscreen" in text
    assert "test_wo02_load.py" in text
