# WO-04-S 결과 보고

작업일: 2026-11-02

작업명: WO-04 안정화 및 병합 전 검증

공식 저장소: https://github.com/scarlel96-design/Universal-Media-Downloader

대상 PR: https://github.com/scarlel96-design/Universal-Media-Downloader/pull/4

PR 상태: OPEN. 이 작업에서 병합하지 않았다.

기준 브랜치: `feat/wo04-browser-extraction`

기준 `main`: `56d8c0eff1fb9d4c15328fcd6d314897f7ebe6b8`

이전 구현 커밋: `8323f80c3357d0c83a7a69c491774aed512d398f`

이전 기록 커밋: `9441c1762f6ba256e75b5ab1c607f7c0087932c6`

안정화 커밋: `25835f2277cfe9dfa9d166ef230ddb45433eeaab`

환경: 로컬 Windows, Python 3.12, 저장소 가상환경. CI 결과와 로컬 결과를 같은 PASS로 적지 않는다.

안정화 판정: 미충족. GO가 아니다.

병합 판정: NO-GO. PR #4는 열린 상태로 둔다.

정식 공개 릴리스: NO-GO.

WO-00R PR #5는 이 판정에 넣지 않는다. 검토하거나 병합하지 않았다.

## 판정 요약

| 완료 조건 | 결과 |
| --- | --- |
| 기존 113개 단위 테스트 PASS | FAIL. 아래 단위 재실행. |
| 기존 5,000장 부하 테스트 PASS | PASS. 같은 세션의 조용한 재실행. 그 앞의 비교 실패는 따로 적는다. |
| 네트워크 오류 처리 검증 | FAIL. 종료 콜백 가드는 PASS. 간헐 시간 초과는 재현됐고 원인은 미확인. |
| 공개 브라우저 접근 정책 검증 | PASS. 공개 CONNECT, 리다이렉트, 하위 리소스, 서비스 워커, WebSocket, 연결 상한. |
| 쿠키 전송 정책 검증 | PASS. |
| 선택 다운로드 무결성 | PASS. 이번 단위 재실행의 갤러리 테스트. |
| 디코딩된 영상 프레임 | PASS. 오프스크린 Qt Multimedia. |
| GitHub Actions 실행 결과 | NOT RUN. 푸시 뒤에 `workflow_dispatch`를 실행하고 이 표를 갱신한다. |
| 필수 실패 없음 | FAIL. `test_11`이 이번 전체 실행에서 실패했다. |

안정화 GO는 위 조건이 모두 맞을 때만 준다. 지금은 주지 않는다.

## 변경 범위

새 제품 기능은 추가하지 않았다. 네이티브 제목 표시줄과 `host.py`의 창 플래그는 바꾸지 않았다. `FramelessWindowHint`는 여전히 없다.

이번 작업에서 바뀐 파일:

- `src/umd/download/engine.py`: WinError 10022를 전부 삼키지 않는다. 프로액터 종료 콜백의 `shutdown` 줄에서 난 10022만 닫기 후 무시한다.
- `src/umd/auth/session.py`: 쿠키의 Secure, Path, Domain, 만료를 요청마다 검사한다. 영구 세션은 꺼 둔다.
- `src/umd/auth/login.py`: 로그인 창이 같은 페이지 가드와 서비스 워커 차단을 쓴다.
- `src/umd/net/policy_proxy.py`: 터널 상한, 403을 읽히게 한 뒤 닫기, 종료 시 수신 소켓과 스레드 정리.
- `src/umd/extract/browser.py`: 로컬 페이지는 프록시를 쓰지 않는다. 공개 모드만 핀 프록시를 쓴다. 로컬 리다이렉트는 페이지 안에서 읽고, 루프백이 아니면 브라우저에 넘기지 않는다. 로컬 WebSocket은 초기화 스크립트로 막는다.
- 테스트: `tests/unit/test_wo04s.py`, `tests/unit/test_wo04_browser.py`, `tests/fixtures/dynamic/policy.html`, `tests/fixtures/dynamic/ws.html`.

프로젝트 `LICENSE` 파일은 만들지 않았다.

## 네트워크 오류

가드 동작은 PASS다. `test_unrelated_winerror_10022_is_not_treated_as_shutdown`이 이번 단위 재실행에 포함되어 통과했다.

- 다운로드 태스크의 결과와 이벤트 루프 종료 콜백을 분리한다.
- 콜백이 WinError 10022를 내면 소켓을 닫고 서버에서 뗀다.
- 트레이스백의 모든 프레임을 본다. `proactor_events.py`의 `_call_connection_lost`이고, 그 소스 줄에 `shutdown`이 있을 때만 무시한다.
- 그 밖의 10022는 다시 올린다. 연결되지 않은 소켓의 WinError 10057도 다시 올린다.
- 테스트 함수 안에서 만든 10022는 종료 콜백으로 분류하지 않는다.

고속 프리셋 `test_parallel_presets_overlap_and_respect_the_cap[24]`의 한계는 `hold * 4`이다. `hold`는 0.45초이므로 한계는 1.8초다. 이 한계는 바꾸지 않았다.

같은 작업에서 프리셋 24만 반복한 결과:

- pytest 단독 5회: PASS 3, FAIL 2. 실패 시간은 1.925초, 1.808초.
- 계측 5회: 경과 2.210, 1.849, 1.755, 1.711, 1.774초. 새 10022 종료 이벤트 4, 4, 6, 2, 6. 실패 다운로드 0.
- 이벤트 수와 경과 시간은 같이 움직이지 않았다.
- 앞선 전체 실행 한 번은 2.276초로 실패했다.
- 2026-11-02 단위 재실행에서는 이 항목이 실패 목록에 없었다. 실패는 `test_11` 하나였다.

원인은 확인하지 못했다. 미해결이다. 해결로 적지 않는다.

`test_11_http_errors_and_corrupt_bodies_leave_no_file`도 미해결이다. 잘린 `short.png`의 정상 경로는 `IncompleteRead`이며 오류 문구는 `응답이 잘렸습니다`이다. 실패 경로는 약 30초 뒤 `timed out`이다. `timed out`을 잘림으로 바꾸면 실제 시간 초과가 가려지므로 그렇게 하지 않았다.

- 단독 5회: FAIL 2, PASS 3. 실패는 약 32초, 통과는 약 2.4초에서 3초.
- 2026-11-02 단위 재실행: FAIL. 상태 `실패`, 오류 문자열 `timed out`, 저장 경로 없음.

반닫힘이 urllib에 보이지 않는 이유와, 프리셋 경과가 약 0.5초 흔들리는 이유는 확인하지 못했다. 둘 다 미해결로 둔다.

## 인증 세션

결과: PASS. `tests/unit/test_wo04s.py`의 쿠키 테스트 2개가 이번 단위 재실행에서 통과했다.

- Secure 쿠키는 `https`에서만 보낸다. `http`에서는 보내지 않는다.
- Domain은 요청 호스트와 같아야 한다. 앞뒤의 점은 뺀다. 다른 사이트와 하위 도메인에는 붙이지 않는다.
- Path는 접두사로 맞춘다. `/media`는 `/media/a.png`에 맞고 `/other.png`에는 맞지 않는다.
- `expires`가 `-1`이 아니고 현재 시각 이하이면 보내지 않는다. `0`도 만료다. `-1`은 세션 쿠키로 보낸다.
- 만료된 저장본은 다음 열기에서 지우고 재인증 목록에 넣는다.
- `expires` 또는 `state.json`이 없는 비정상 종료 잔여 디렉터리는 `sweep()`이 지운다.
- Windows에서는 `icacls`로 현재 사용자 `(OI)(CI)F`만 남긴다. 출력은 바이트로 받고 텍스트로 디코드하지 않는다.
- `persistent_sessions_enabled()`는 `False`다. Windows 보안 저장소는 검증 전이므로 영구 세션을 켜지 않았다.
- 이 코드는 쿠키 값을 SQLite와 로그에 쓰지 않는다. 로그인 테스트의 SQLite 파일에 테스트 쿠키 이름이 없었다.

## 브라우저 접근 정책

결과: PASS. 로컬 자동 테스트와 공개 `example.com` CONNECT를 구분한다.

2026-11-02 공개 프록시 실측:

- `assess_public_url("https://example.com/")` 허용. 주소 `172.66.147.243`, `104.20.23.154`. 핀 `172.66.147.243`. 핀은 공개 주소.
- 실제 `PolicyProxy`에 `CONNECT example.com:443`. 응답 `HTTP/1.1 200 Connection Established`.
- 기록된 TCP 대상은 `(172.66.147.243, 443)` 하나이고 공개 주소다.
- `close()` 후 그 포트는 접속이 거절됐다. 이름 `umd-policy-proxy` 스레드는 1개에서 0개가 됐다.

단위 재실행에서 통과한 정책 항목:

- 사설 주소가 섞인 DNS 응답은 연결 전에 거절한다. 대상 목록은 비어 있다.
- 터널 상한을 넘기면 403 `연결 수가 한도를 넘었습니다`이고 추가 대상은 열지 않는다. 제품 상한은 16이다.
- 로컬 302 `http://10.1.2.3/secret`는 성공 추출이 아니고, `10.1.2.3`이 거부 목록에 들어간다.
- `policy.html`의 `http://10.9.8.7/secret`가 거부 목록에 들어간다.
- 컨텍스트 `service_workers`는 `block`이다.
- 로컬 `ws.html`의 `ws://10.9.8.7/socket`는 생성 시점에 막혀 `dataset.ws`가 `blocked`다. 루프백 WebSocket 판정은 허용, 공개 모드의 사설 `wss` 판정은 거부.
- 로컬 추출이 끝난 뒤 마지막 프록시 포트에 다시 접속하면 실패한다.

구현 중 확인한 제약. 해결로 숨기지 않는다.

- 이 호스트에서 루프백을 `PolicyProxy`로 돌리면 연결이 끊기거나 리다이렉트가 제한 시간을 넘긴다. 로컬 모드 페이지는 프록시를 쓰지 않는다.
- Playwright sync의 `page.route`는 브라우저가 따라간 리다이렉트 홉을 호출하지 않았다. 로컬 모드는 응답을 직접 읽고, 루프백이 아닌 `Location`은 브라우저에 넘기지 않는다.
- sync 라우트 핸들러 안의 `route.fetch()`는 드라이버가 끝나지 않았다. 그 호출은 넣지 않았다.
- `page.route_web_socket`으로 소켓을 닫으면 추출이 30초를 넘겼다. 그 라우트는 넣지 않았다. 로컬 모드는 문서 스크립트보다 먼저 실행되는 초기화 스크립트로 막는다.
- 화살표 함수만 등록하면 스크립트가 호출되지 않아 WebSocket이 열렸다. 즉시 실행 함수로 고친 뒤 같은 테스트가 통과했다.
- 접근 정책을 걸 수 없으면 `브라우저 접근 정책을 적용할 수 없어 분석을 하지 않습니다`로 분석을 하지 않는다.

## 미디어

로컬 JavaScript 추가, SPA 해시, 지연 로딩, 3장에서 멈추는 스크롤: PASS. `test_javascript_images_spa_lazy_scroll_and_cleanup`.

분류: PASS. `test_browser_classifier_keeps_small_body_images_and_drops_chrome`. 본문과 작은 본문은 `content`, 추천과 광고와 아바타와 로고는 `excluded`, 불확실 항목은 선택되지 않는다. 이번 실행은 고정 페이지의 기대값이고, 공개 페이지의 오탐과 미탐 건수는 세지 않았다.

원본과 썸네일: PASS. `test_browser_dedupes_thumbnail_and_reads_video_metadata`. 큰 URL만 원본으로 두고 크기 접미사가 다른 URL은 썸네일로 남긴다.

선택 다운로드: PASS. `tests/unit/test_wo04_gallery.py` 8개가 이번 단위 재실행에서 통과했다. 빈 선택은 저장하지 않고, 한 장과 여러 장은 고른 URL만 저장한다. 파일마다 기록을 남긴다.

공개 JavaScript 게시물: NOT RUN. 공개 페이지에서 정적 HTML에 없는 미디어가 스크립트로만 삽입되는 경우를 이번 검증에서 확정하지 못했다. 로컬 고정 페이지 결과를 공개 게시물 결과로 적지 않는다.

디코딩된 프레임: PASS. 2026-11-02, `QT_QPA_PLATFORM=offscreen`. 64x48 MJPEG AVI 두 프레임을 `QMediaPlayer`와 `QVideoSink`로 재생했다. 상태는 재생이 끝난 `StoppedState`, 미디어 상태는 `EndOfMedia`, 오류 문자열은 비어 있다. `videoFrameChanged`로 받은 이미지는 2장이고 첫 장은 64x48, 픽셀 `0xff2342cc`이다. 원본 채움 `0xFF2244CC`와 다른 값은 JPEG 변환의 결과다. 재생 상태만 본 것이 아니다. QML `VideoOutput`이나 화면 캡처는 아니다. Qt가 찍은 av1, hevc MFT 메시지는 그 코덱의 인코더를 찾지 못한 로그이며, 이번 샘플의 MJPEG 디코드를 실패로 보지 않는다.

## 실제 Windows UI

오프스크린 창 플래그 테스트는 이번 단위 재실행에 들어 있고 실패 목록에 없다. 그것은 실제 데스크톱 조작이 아니다.

아래는 NOT RUN이다. 시스템 DPI, 고대비, 스크린 리더 설정은 바꾸지 않았다. 정식 릴리스의 별도 차단 항목으로 둔다.

- Win+Z와 Snap Layouts
- Alt+Space, Alt+F4
- 최소화, 최대화, 복원, 닫기의 실제 창 조작
- 실제 모니터 DPI 전환
- 네이티브 저장 폴더 대화상자
- 고대비와 스크린 리더
- 애니메이션 프레임 시간

Apple 스타일 화면은 유지한다. 기존 Windows 네이티브 제목 표시줄은 바꾸지 않았다.

## 테스트 기록

로컬 단위 재실행, 2026-11-02. 부하 테스트와 `tests/live`는 제외했다.

- 수집 118. 기존 113개에 WO-04-S 테스트 4개와 브라우저 정책 테스트 1개가 더해진 수다.
- 진행 표시는 118칸이고 실패 표시는 하나다. 그 실패는 `tests/unit/test_wo01_download.py::test_11_http_errors_and_corrupt_bodies_leave_no_file`.
- 117 passed, 1 failed. 프로세스 종료 코드 1. 명령 벽시계 144.89초. pytest 자체 요약의 `N passed in` 줄은 이 실행 로그에 남지 않았다.
- 프리셋 24는 이 실행의 실패가 아니다.

이 결과를 기존 WO-04 보고서의 `113 passed in 50.31s`와 합치지 않는다. 그 실행은 그 실행의 PASS다. 이번 재실행은 FAIL이다.

5,000장 부하, 로컬, 같은 작업 세션. CI가 아니다.

- 첫 실행 FAIL. 대량 전송 단언 뒤에서 순차 6.153초가 병렬 6.436초보다 짧지 않았다. 측정 줄은 출력되지 않았다. 병렬이 더 느린 원인은 단정하지 않는다.
- 조용한 재실행 PASS. 5,000 files, 242.862 s, peak_connections 3, server_peak 3, working_set_before 47620096, working_set_peak 78508032, integrity_mismatches 0, large_file_bytes 6291526, large_file_traced_bytes 798870, sequential 5.658 s peak 1, parallel 3.727 s peak 3.
- WO-04 보고서의 181.386초, working_set_peak 99864576과 이번 242.862초를 한 측정으로 적지 않는다. 느려진 원인도 단정하지 않는다.

단위 재실행이 끝난 뒤 `chrome-headless-shell` 프로세스는 남아 있지 않았다.

## GitHub Actions

워크플로 파일 `.github/workflows/ci.yml`은 바꾸지 않았다.

- 트리거는 `workflow_dispatch`만이다. `pull_request`는 넣지 않았다.
- `windows-latest`만 쓴다.
- 테스트 잡은 Chromium을 설치한 뒤 부하 테스트와 `tests/live`를 제외하고 pytest를 실행한다.
- 5,000장 잡은 `inputs.load`가 켜질 때만 실행된다. 이번 수동 실행에는 그 입력을 켜지 않는다. 부하 결과는 위의 로컬 실행만 사용한다.
- `actions/checkout@v4`, `actions/setup-python@v5`는 그대로다.

이번 브랜치 실행: NOT RUN.

실행 주소: 아직 없다. 푸시 후 `gh workflow run ci.yml --ref feat/wo04-browser-extraction`으로 실행하고, 로그에 Chromium 설치와 이번 커밋 SHA가 보이는지 확인한 뒤 이 절을 갱신한다. 기본 브랜치 워크플로만 돈 실행은 이 브랜치의 PASS로 적지 않는다.

이전 main 실행 `41312197710`은 WO-03 결과다. 이번 PASS가 아니다.

## 라이선스

프로젝트 `LICENSE`는 없다. 이번에도 만들지 않았다. 라이선스가 없으므로 정식 공개 릴리스는 NO-GO다.

설치 메타데이터에서 다시 확인했다.

- gallery-dl 1.32.19: `License: GPL-2.0-only`. 라이브러리로 import 한다. 자식 프로세스 실행만으로 GPL 배포 의무가 없어진다고 보지 않는다.
- PySide6 6.12.0: `License: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`. `License-File: LicenseRef-Qt-Commercial.txt`.
- yt-dlp 2026.10.26: `License-Expression: Unlicense`.
- httpx 0.28.1: `License: BSD-3-Clause`.
- playwright 1.64.1: `License-Expression: Apache-2.0`.

배포 형태를 정하기 전에는 소스 공개 범위와 Qt 고지를 확정할 수 없다. 그 결정은 이 작업에서 하지 않는다.

## 비용과 업로드

추가 비용: 0. 유료 API와 대형 러너는 쓰지 않았다.

코드 업로드는 이 브랜치와 PR #4뿐이다. 세션 파일, 쿠키, SQLite, `.venv`, 부분 다운로드 파일, 임시 영상 파일은 커밋하지 않는다.

## 미해결

- 프리셋 24의 벽시계가 1.8초를 넘는 조건. 10022 가드와 상관은 보이지 않았다.
- `test_11`의 간헐적 `timed out`.
- 공개 페이지에서 JavaScript만으로 삽입된 미디어.
- 실제 Windows 데스크톱 UI 항목 전부.
- 프로젝트 `LICENSE`와 그에 따른 gallery-dl, PySide6 배포 의무의 최종 선택.
- Windows 보안 저장소를 확인하기 전의 영구 세션.
- 이번 커밋에 대한 GitHub Actions 결과.

## 다음 작업

다음 기능 작업은 시작하지 않는다.

- PR #4를 병합하지 않는다. 안정화 GO가 아니고, Actions 결과도 아직 없다.
- PR #5는 별도 검토로 둔다.
- `pull_request` 트리거를 켜지 않는다.
- 1.8초 한계를 늘리거나 `timed out`을 잘림으로 바꿔 실패를 지우지 않는다.
- 정식 릴리스 판단은 따로 유지한다. `LICENSE`가 생기고 데스크톱 차단 항목이 실행되기 전에는 릴리스 NO-GO다.
- Actions가 끝나면 실행 주소와 테스트 잡의 Chromium 설치 여부만 이 문서에 추가한다.
