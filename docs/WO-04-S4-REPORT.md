# WO-04-S4 결과 보고

작업일: 2026-11-02

작업명: EOF 테스트 결정성 확보 및 안전한 애플리케이션 종료

개발 도구: Grok Build

공식 저장소: https://github.com/scarlel96-design/Universal-Media-Downloader

대상 PR: https://github.com/scarlel96-design/Universal-Media-Downloader/pull/4

PR 상태: OPEN. 이 작업에서 병합하지 않았다. PR #5도 병합하지 않았다.

기준 브랜치: `feat/wo04-browser-extraction`

기준 HEAD: `e555b9ba4d38d917c54e0ea4cb6b4b43dcbf2e40`

구현 커밋: `58091cff931d0c079a995319c65f23173e5876b0`

환경: 로컬 Windows, Python 3.12.10, pytest 9.2.0. 저장소 밖 가상환경에 `PYTHONPATH=src`. `QT_QPA_PLATFORM=offscreen`. 반복은 프로세스마다 새로 시작했다. CI 결과와 로컬 결과를 같은 PASS로 적지 않는다.

안정화 판정: GO. 로컬 필수 항목과 Actions 테스트 잡이 통과했다. 모의 EOF와 영상 시험 대역은 아래와 같이 제품의 모든 경로를 뜻하지 않는다.

병합 판정: 조건은 충족했다. 이 작업에서 병합하지 않았다. PR #4는 열린 상태다.

정식 공개 릴리스: NO-GO. Windows 실환경 UI와 프로젝트 `LICENSE` 없음은 출시 차단이다. 기능 안정화 GO와 정식 릴리스 GO는 따로 둔다.

## 판정 요약

| 완료 조건 | 결과 |
| --- | --- |
| 결정적 EOF 30회 | PASS. 30/30. 네트워크는 모의 스트림이다. |
| TCP RST 30회 | PASS. 30/30. 오류는 10054이다. |
| 실제 TCP 조기 종료 30회, 불완전 파일 0 | PASS. 30/30이 안전하게 실패했다. EOF 28, RST 2. 최종 파일과 `.part`는 없다. |
| 오류 종류의 구분 | PASS. 모의 EOF는 `응답이 잘렸습니다`. 같은 소켓의 RST는 10054이고 `잘렸`이 아니다. 시간 초과는 `timed out`이다. |
| 기존 test_11 30회 | PASS. 30/30. |
| 고속 프리셋 24 30회 | PASS. 30/30. 1.8초 한계는 그대로다. |
| lazy.html 30회 | PASS. 30/30. |
| 네이티브 크래시 재발 | 이 반복에서 `0xC0000409`는 없었다. 전체 단위 3회 종료 코드는 0이다. |
| 애플리케이션 종료 검증 | PASS. 정상 종료, 막힌 읽기, 지연된 영상 취소 확인. `QThread.terminate`는 쓰지 않았다. |
| 전체 단위 테스트 3회 연속 | PASS. 127 passed, 70.02초, 63.75초, 65.18초. 모두 exit 0. |
| 5,000장 부하 테스트 | PASS. 반복 행렬 1회 exit 0. 수치 줄은 아래의 추가 실행이다. |
| GitHub Actions 테스트 잡 | PASS. 테스트 잡만. 부하 잡은 건너뜀. |
| 필수 미해결 FAIL | 없음. |

## 테스트 구조를 바꾼 이유

S3의 `test_eof_short_body_reports_truncation_and_keeps_no_file`는 `_observe_eof_gap()`으로 한 연결의 EOF를 본 다음 `download_one()`이 새 연결을 열었다. 첫 연결의 EOF는 둘째 연결에 적용되지 않는다. 그 30회는 26 PASS, 4 FAIL(8, 20, 21, 29)이고 실패는 WinError 10054였다. 그 기록을 지우지 않는다. 10054를 `잘렸`으로 고쳐 30/30을 만들지 않았다.

이번 구조는 둘로 나뉜다.

- 결정적 계약: `urlopen`만 모의 스트림으로 바꾼다. `Content-Length` 109, 본문 69바이트, 다음 읽기는 빈 바이트다. `_transfer`의 길이 비교는 그대로 돈다. 차이 40바이트다. 제품 기본 시간 제한 인자 30이 그 호출에 전달되는지도 확인한다.
- 실제 TCP: `ProbeServer`가 요청마다 소켓 번호와 상대 포트를 남긴다. 감싸 둔 응답은 `download_one`이 연 그 소켓의 읽기와 예외를 기록한다. 마지막 연결이 정상 EOF면 오류는 `응답이 잘렸습니다`다. 시도가 모두 RST면 10054이고 `잘렸`은 없다. 시간 초과면 실패다.

네트워크를 모의 처리한 것은 계약 테스트뿐이다. `src/umd/download/images.py`의 `download_one()`은 바꾸지 않았다.

## 정상 EOF와 RST

### 모의 EOF

30회 별도 프로세스, exit 0. 오류는 `응답이 잘렸습니다`. 상태 실패, 경로 빈 문자열, 크기 0, 디렉터리에 파일이 없다. 스트림 위치는 69바이트다. 선언 길이와의 차이는 40이다.

### TCP RST

`SO_LINGER (1, 0)` 30/30. 오류에 `10054`가 있고 `잘렸`과 `timed out`은 없다. 최종 파일과 `.part`는 없다.

### 실제 TCP 조기 종료

서버는 69바이트를 보내고 `Content-Length` 109 뒤에 소켓을 닫는다. 30/30 exit 0. 각 실행은 그 다운로드의 소켓을 서버 기록과 짝지었다.

| 관측 | 횟수 | 제품 오류 |
| --- | --- | --- |
| 정상 EOF | 28 | `응답이 잘렸습니다` |
| RST | 2 | WinError 10054, `잘렸` 없음 |

두 경우 모두 완료가 아니고 최종 파일과 `.part`는 없다. 시간 초과로 분류된 실행은 0이다. S3의 26/30을 이 30회에 섞지 않는다.

### 시간 초과와 정상 파일

시간 초과 10/10. 호출 제한은 1초이고 제품 기본값 30초는 그대로다. 오류는 `timed out`이다. 정상 파일 30/30. 상태 완료, 바이트는 `dot.png`와 같다.

### 기존 test_11

30/30 exit 0. 404, 500, 형식, 거부된 주소 검사는 그대로다. 짧은 `/short.png`는 잘림 또는 10054를 각각 실패로 둔다. 타임아웃이면 실패다.

## QThread 종료

`joinWorkers(None)`은 워커가 돌아올 때까지 기다린다. `QThread.terminate`는 호출하지 않는다. 앱 종료는 `shutdownForQuit()` 다음 `joinWorkers(None)`이다. 진입점은 `src/umd/__main__.py`다. `src/umd/main.py`는 없다.

종료를 시작하면 단계는 `종료 중`이고 상태 줄은 `종료를 기다리는 중`이다. 이 문자열은 기존 상태 줄에 나온다. 그 사이 `download()`, `analyze()`, `retryFailed()`, `resumeDownload()`는 새 작업을 시작하지 않는다. `joinWorkers`가 이벤트를 처리하는 동안에도 같다. 테스트는 `QTimer`로 그 재진입을 한 번 더 호출했다. 다운로드 스레드 객체는 바뀌지 않았고, 끝난 뒤에는 `isFinished()`다.

막힌 HTTP 읽기: 본문이 오기 전에 취소하면 엔진이 살아 있는 소켓을 닫는다. asyncio의 `TransportSocket`는 `close()`가 없어서 안의 소켓을 닫는다. 그 예외는 취소가 켜져 있을 때 잘린 본문으로 바꾸지 않고 취소로 끝낸다. 측정된 대기는 4초 미만이었다. 서버의 다음 조각 대기는 8초였다. `.part`는 없어졌고 SQLite 상태는 `취소`이며 저장 경로는 비어 있다.

정상으로 끝난 HTTP 파일은 종료 뒤에 그대로다. 바이트도 같다.

영상: 공개 사이트와 yt-dlp 자식은 띄우지 않았다. `download_video`를 시험 대역으로 바꿔, 취소가 보일 때까지 막힌 뒤 0.35초 후에 반환하게 했다. 취소가 그 함수에 들어갔고, 임시 파일은 지워졌고, 스레드는 스스로 끝났다. 실제 yt-dlp가 취소 파일을 보기 전에 오래 막히면 부모는 그 자식이 끝날 때까지 기다린다. 그 경우는 NOT RUN이다. 스레드를 죽여 그 대기를 없애지 않았다.

`jobs.py`의 취소 플래그와 `should_stop` 경로는 그대로다. 소켓을 닫는 쪽은 `DownloadEngine.request_cancel_all()`이다.

종료 시나리오 파일 1회는 exit 0, 벽시계 4.394초다. 같은 테스트가 전체 단위 3회에도 들어 있다.

## 수정 파일

새 다운로드 사이트와 새 화면은 없다. `download_one()`은 삭제하지 않았다. HTTPX로 바꾸지 않았다. 제품 기본 30초와 프리셋 `hold * 4`(1.8초)는 바꾸지 않았다. 오류 문자열을 일괄로 바꾸지 않았다. 보안 정책을 끄지 않았다. `pull_request` 트리거는 켜지 않았다.

- `src/umd/download/engine.py`: 전체 취소 때 살아 있는 소켓을 닫아 막힌 읽기가 반환되게 한다. 취소 중 전송 오류는 잘림으로 기록하지 않는다.
- `src/umd/app/shell.py`: `shutdownForQuit()`가 대기 상태를 보여주고 재진입으로 새 작업을 막는다.
- `src/umd/__main__.py`: 종료 시 그 함수 뒤 `joinWorkers(None)`을 호출한다.
- `tests/wo01_support.py`: `ProbeServer`가 연결마다 소켓 번호를 남긴다.
- `tests/unit/test_wo01_download.py`: 모의 EOF 계약과 같은 소켓의 TCP 분류. S3의 다른 연결 관찰은 뺐다.
- `tests/unit/test_wo04_s4_shutdown.py`: 정상 종료, 막힌 읽기, 지연된 취소 확인.
- `docs/WO-04-S4-REPORT.md`: 이 문서.

## 반복

아래 횟수는 구현 커밋 `58091cf`로 커밋되기 전의 작업 트리에서 돌렸다. 그 트리가 구현 커밋이다. Actions가 실행한 SHA도 `58091cf`다. 이 기록 커밋은 CI가 실행한 커밋이 아니다.

| 항목 | 결과 | 프로세스 벽시계 |
| --- | --- | --- |
| 모의 EOF | 30/30 exit 0 | 0.864–1.196초 |
| TCP RST | 30/30 exit 0 | 0.985–1.144초 |
| TCP 조기 종료 | 30/30 exit 0 | 0.963–1.131초 |
| 시간 초과 | 10/10 exit 0 | 1.889–2.181초 |
| 정상 파일 | 30/30 exit 0 | 0.909–1.242초 |
| test_11 | 30/30 exit 0 | 0.938–1.260초 |
| 종료 시나리오 | 1/1 exit 0 | 4.394초 |
| lazy.html | 30/30 exit 0 | 10.372–12.987초 |
| 고속 프리셋 24 | 30/30 exit 0 | 2.107–2.607초. pytest `passed in`은 1.39–1.70초 |
| 전체 단위 | 3/3 exit 0 | 71.022, 64.750, 66.049초 |
| 5,000장 | 1/1 exit 0 | 167.366초. pytest `1 passed in 166.43s` |

프리셋의 pytest 시간은 픽스처를 포함한다. 테스트 안 경과가 1.8초 이상이면 단언이 실패하므로 30회 모두 예산 안이다. 프로세스 벽시계 2.6초는 인터프리터 시작을 포함하므로 예산 수치가 아니다. 과거 실패 시각 1.808, 1.925, 2.210, 1.849, 2.276초와 S3의 30/30은 그대로 둔다. 프리셋 30회 직전 프로세서 부하 평균은 19, 직후는 14였다. 행렬을 시작하기 전에는 7이었다. 소켓 연결 시간과 Python 스케줄 시간은 이번에도 분리하지 않았다.

전체 단위 각 회 전후에 `python.exe`, `chrome.exe`, `chromium.exe`의 새 PID는 없었다.

## 5,000장

반복 행렬의 1회는 exit 0이고 pytest는 `1 passed in 166.43s`다. 그 실행은 무결성 불일치 0을 단언으로 통과했다. pytest가 표준 출력을 잡아 두어 `WO02_METRICS` 줄은 로그에 남지 않았다.

같은 테스트를 `-s`로 한 번 더 실행해 그 줄만 읽었다. 이것은 두 번째 실행이다. 첫 실행의 166.43초와 섞지 않는다.

| 항목 | 두 번째 실행 |
| --- | --- |
| files | 5000 |
| elapsed_s | 142.553 |
| peak_connections | 3 |
| server_peak | 3 |
| working_set_before | 47931392 |
| working_set_peak | 108494848 |
| integrity_mismatches | 0 |
| large_file_bytes | 6291526 |
| large_file_traced_bytes | 876185 |
| sequential elapsed_s | 4.363, peak 1 |
| parallel elapsed_s | 2.651, peak 3 |
| pytest | `1 passed in 152.51s` |

이전 부하 수치 181.386초, 242.862초, S2의 146.161초, S3의 147.792초와 섞지 않는다.

## GitHub Actions

수동 실행만 했다. `inputs.load`는 주지 않았다. `pull_request`는 켜지 않았다.

실행: https://github.com/scarlel96-design/Universal-Media-Downloader/actions/runs/41383881435

이벤트: `workflow_dispatch`

headSha: `58091cff931d0c079a995319c65f23173e5876b0`

이 SHA는 구현 커밋과 같다. 테스트 잡은 성공했다. Install 로그에 `python -m playwright install chromium`이 있고, Chrome for Testing 156.0.8078.4, Playwright chromium v1248이 받아졌다. Regression 단계 로그의 pytest 결과는 `127 passed in 65.16s`다. 부하 잡은 skipped다.

이 CI PASS는 로컬 반복 표를 대신하지 않는다. 브라우저가 설치된 사실만으로 통과를 적지 않았다. S3 실행 `41379332972`의 headSha `e7b6df3`도 이번 결과로 세지 않는다.

## 미해결

| 항목 | 상태 |
| --- | --- |
| 모의 EOF 30회 | PASS. 네트워크는 모의다. |
| TCP RST 30회 | PASS. |
| TCP 조기 종료 30회 | PASS. EOF 28, RST 2. 불완전 파일 0. |
| S3 EOF 26/30 | 기록으로 유지. 이번 집계에 넣지 않음. |
| 종료 시나리오 | PASS. 공개 yt-dlp 자식의 긴 대기는 NOT RUN. |
| lazy.html 30회 | PASS. |
| 전체 단위 3회 | PASS. 127. |
| 5,000장 | PASS. 수치는 두 번째 실행. |
| GitHub Actions 이번 SHA | PASS. 테스트 잡 127 passed, 65.16초. 부하 잡은 skipped. |
| 공개 인터넷에서만 보이는 JavaScript 미디어 | NOT RUN. |
| Windows 실환경 데스크톱 UI | NOT RUN. 출시 차단. |
| 프로젝트 LICENSE | 없음. 파일을 만들지 않음. 출시 차단. |
| 영상 자식이 취소를 확인하지 않는 동안의 대기 | 스레드를 강제 종료하지 않는다. 공개 영상으로 재현하지 않음. |

## 추가 비용

유료 API나 새 서비스는 쓰지 않았다. 로컬 반복, 지표를 읽기 위한 부하 테스트 추가 1회, Windows Actions 테스트 잡 1회다. 부하 잡은 켜지 않았다.

## 병합과 릴리스

필수 조건은 충족했다. PR #4를 병합할 수 있다. 이 작업에서는 병합하지 않았다. PR #5는 열린 채로 둔다. 다음 기능 개발은 시작하지 않는다.

테스트가 통과한 것과 제품의 모든 경로가 확인된 것은 다르다. 모의 EOF는 소켓을 열지 않는다. 영상 종료 확인은 시험 대역이다. 정식 릴리스 차단은 남아 있다.

기능 안정화 GO: GO.

정식 릴리스 GO: NO-GO.
