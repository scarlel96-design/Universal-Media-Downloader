# Universal Media Downloader V1.1

Windows용 데스크톱 앱이다. 로컬 모드에서는 고정 HTML과 `127.0.0.1` 테스트 서버만 다룬다. 공개 모드는 별도의 HTTP/HTTPS 정책으로 공개 주소만 연다. 본문 이미지는 기존 HTML 추출기다. 갤러리 메타데이터는 gallery-dl, 영상 정보는 yt-dlp다. 직접 받을 수 있는 이미지는 WO-02 HTTPX 큐로 저장한다.

## 실행

Python 3.12와 프로젝트 가상환경이 필요하다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . pytest
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m umd
.\.venv\Scripts\python.exe -m pytest
```

화면의 `로컬` / `공개`로 네트워크 모드를 고른다. 기본값은 로컬이다. 창 버튼은 Windows 기본 제목 표시줄에 있다. 샘플 그리드는 파일을 저장하지 않는다. 공개 모드에서도 내부 주소, 비HTTP 스킴, 사설 DNS 응답은 거부한다. Tor와 프록시는 켜지 않는다. YouTube 로그인, 개인 재생목록, DRM은 이 단계에 없다.

## 문서

- `docs/ARCHITECTURE.md`: 설계 V1.1
- `GEMINI_START.md`: 첫 작업 지시
- `docs/design/window-prototype.html`: 시각 시안. 앱이 아니다
- `docs/design/WINDOW_HOST_CONTRACT.md`: 네이티브 창 계약
- `research/competitor_4k/`: 4K Video Downloader+ 조사. 역컴파일은 하지 않았다

## 현재 판정

WO-00 심층 역분석은 BLOCKED이고, 성능 비교는 NOT RUN이다. WO-01과 WO-02 기준선은 GO다. WO-GIT-00은 이 저장소의 `main`으로 그 기준선을 이관했다. WO-03 판정과 측정값은 `docs/WO-03-REPORT.md`에 있다. WO-04 측정과 판정은 `docs/WO-04-REPORT.md`에 있다. GitHub Actions 워크플로는 수동 실행만 두고, 실행 전에는 CI PASS로 적지 않는다. 프로젝트 LICENSE 파일은 없고, 정식 공개 릴리스는 NO-GO다.
