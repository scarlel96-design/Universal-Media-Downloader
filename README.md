# Universal Media Downloader V1.1

Windows용 데스크톱 앱이다. WO-01은 고정 HTML 픽스처에서 본문 이미지를 고르고, 선택한 파일을 로컬 테스트 서버에서 저장한다. WO-02는 그 저장을 HTTPX 비동기 큐로 병렬 실행하고, 중단된 작업을 SQLite에서 복구한다. 공개 사이트와 영상 다운로드는 아직 범위 밖이다.

## 실행

Python 3.12와 프로젝트 가상환경이 필요하다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install PySide6 httpx pytest
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m umd
```

테스트는 저장소 루트에서 실행한다. pytest 설정이 `src`를 경로에 넣는다.

```powershell
.\.venv\Scripts\python.exe -m pytest
```

창 버튼은 Windows 기본 제목 표시줄에 있다. 샘플 그리드는 파일을 저장하지 않는다. 로컬 픽스처 주소를 분석한 뒤 고른 이미지만 저장한다.

## 문서

- `docs/ARCHITECTURE.md`: 설계 V1.1
- `GEMINI_START.md`: 첫 작업 지시
- `docs/design/window-prototype.html`: 시각 시안. 앱이 아니다
- `docs/design/WINDOW_HOST_CONTRACT.md`: 네이티브 창 계약
- `research/competitor_4k/`: 4K Video Downloader+ 조사. 역컴파일은 하지 않았다

## 현재 판정

WO-00 심층 역분석은 BLOCKED이고, 성능 비교는 NOT RUN이다. WO-01 본문 이미지 추출과 로컬 다운로드는 GO다. WO-02 대량 병렬 다운로드와 장애 복구는 GO다. 근거는 `docs/WO-01-REPORT.md`와 `docs/WO-02-REPORT.md`에 있다.
