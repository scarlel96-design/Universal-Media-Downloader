# WO-04-S3 결과 보고

작업일: 2026-11-02

작업명: Windows 네이티브 크래시 및 네트워크 테스트 안정화

개발 도구: Grok Build

공식 저장소: https://github.com/scarlel96-design/Universal-Media-Downloader

대상 PR: https://github.com/scarlel96-design/Universal-Media-Downloader/pull/4

PR 상태: OPEN. 이 작업에서 병합하지 않았다. PR #5도 병합하지 않았다.

기준 브랜치: `feat/wo04-browser-extraction`

기준 HEAD: `ca20defff8804d2c4a1e22de6658a88114b45b63`

구현 커밋: `e7b6df3a805181840366c350cf7d0fd2b03b4993`

환경: 로컬 Windows, Python 3.12.10, pytest 9.2.0. 저장소 가상환경. `QT_QPA_PLATFORM=offscreen`. CI 결과와 로컬 결과를 같은 PASS로 적지 않는다.

안정화 판정: 미충족. GO가 아니다.

병합 판정: NO-GO. PR #4는 열린 상태로 둔다.

정식 공개 릴리스: NO-GO. Windows 실환경 UI와 프로젝트 `LICENSE` 없음은 계속 출시 차단이다. 기능 안정화 GO와 정식 릴리스 GO는 따로 둔다.

## 판정 요약

| 완료 조건 | 결과 |
| --- | --- |
| 원인 미확인 네이티브 크래시 없음 | 원인은 확인했다. 재현은 더 이상 `0xC0000409`로 죽지 않는다. |
| 정상 EOF 잘린 본문 30회 | FAIL. 26 PASS, 4 FAIL. 실패는 WinError 10054이고 잘림으로 바꾸지 않았다. |
| TCP RST 30회 | PASS. 30/30. 오류는 10054이고 `잘렸`이 아니다. |
| 실제 타임아웃 10회 | PASS. 10/10. 호출 제한은 1초이고 제품 기본값 30초는 그대로다. 오류는 `timed out`이다. |
| 정상 파일 30회 | PASS. 30/30. |
| 기존 test_11 30회 | PASS. 30/30. 404, 500, 형식 검사는 그대로다. 짧은 본문은 잘림 또는 10054를 각각 실패로 둔다. |
| 고속 프리셋 24 30회 | PASS. 30/30. 1.8초 한계는 그대로다. 이전 실패 시각은 아래에 남긴다. |
| lazy.html 30회 | PASS. 오리진 종료를 고친 뒤 30/30. 고치기 전 24/30은 실패로 남긴다. |
| 전체 단위 테스트 3회 연속 | PASS. 오리진 수정 뒤 123 passed를 3회 연속. 수정 전 3회는 1회만 exit 0이었다. |
| 5,000장 부하 테스트 | PASS. 로컬 1회. |
| 바이트 무결성 불일치 0 | PASS. `integrity_mismatches` 0. |
| 인증 정보 보호 | 유지. 세션 ACL 실패 시 삭제 동작은 바꾸지 않았다. 전체 단위 테스트에 그 검사가 포함된다. |
| GitHub Actions 테스트 잡 | PASS. 테스트 잡만. 부하 잡은 건너뜀. 로컬 EOF 4실패와 별개다. |
| 해결되지 않은 필수 FAIL 없음 | FAIL. EOF 30회가 26/30이다. |

## 수정 파일

새 제품 기능은 없다. `download_one()`은 삭제하지 않았고 HTTPX로 바꾸지 않았다. 제품 기본 시간 제한 30초와 프리셋 판정 `hold * 4`(1.8초)는 바꾸지 않았다. 오류 문자열을 일괄로 바꾸지 않았다. WinError 10022 필터는 건드리지 않았다. 보안 정책을 끄지 않았다. `pull_request` 트리거는 켜지 않았다.

- `src/umd/app/shell.py`: `joinWorkers()`가 GUI 스레드에서 이벤트를 처리하며 기다린다. 기본 한계는 5초다. `None`이면 워커가 끝날 때까지 기다린다.
- `src/umd/__main__.py`: 종료 시 취소 뒤 `joinWorkers(None)`을 호출한다. 실행 중인 `QThread`를 바로 파괴하지 않는다.
- `tests/shell_hold.py`, `tests/conftest.py`: 테스트 함수가 끝나며 QML 엔진이 먼저 사라지지 않게 붙잡는다. 워커가 끝난 뒤 닫는다.
- `tests/unit/test_wo01_ui.py`, `tests/unit/test_wo02_ui.py`: 연 셸을 그 보관 목록에 넣는다.
- `tests/wo01_support.py`: 완전한 본문은 `shutdown` 없이 클라이언트가 닫을 때까지 기다린다. 짧은 본문은 요청을 읽은 뒤 바로 닫는다. `ProbeServer`가 EOF, RST, 지연, 정상 파일을 나눈다.
- `tests/unit/test_wo01_download.py`: 네 상황을 서로 다른 테스트로 검사한다.
- `tests/unit/test_wo04_browser.py`: 로컬 오리진이 본문을 보낸 뒤 `shutdown(SHUT_WR)`를 호출하지 않는다. 추적 로그는 `WO04S3_LAZY_LOG`가 있을 때만 남긴다. 쿠키와 인증 헤더는 적지 않는다.
- `docs/WO-04-S3-REPORT.md`: 이 문서.

`src/umd/download/images.py`는 바꾸지 않았다.

## 네이티브 크래시

수정 전 전체 단위 테스트 한 번이 종료 코드 `-1073740791`로 죽었다. 이 값은 `0xC0000409`다. faulthandler 파일은 0바이트였다. Python 트레이스백은 없었다. 마지막 flush는 `test_13_download_does_not_block_the_ui`의 CALL 실패(8.078초) 다음 테스트인 `test_11_shell_records_http_failure`의 SETUP 통과까지였다. 그 테스트의 CALL 기록은 없다.

같은 날 격리 실행은 죽지 않았다. UI 파일 6회, `test_13` 5회, `test_11_shell` 5회가 exit 0이었다. 그 뒤 전체 스위트 한 번은 119 passed, 58.55초, exit 0이었다. 크래시는 스위트 안의 순서에서 한 번 관찰됐다.

로컬 재현: 느린 이미지를 받기 시작한 뒤 QML 엔진을 바로 버리자 프로세스가 같은 종료 코드로 죽었다. 단계는 `다운로드 중`이었다. cdb로 자식 `python.exe`를 따라가 예외를 잡았다.

관찰된 디버거 기록:

- 예외: `c0000409` second chance
- 하위 코드: `0x7 FAST_FAIL_FATAL_APP_EXIT`
- 모듈: `Qt6Core!QtPrivate::sizedFree+0x58`
- Qt 메시지: `QThread: Destroyed while thread is still running`
- 그 직전에 QML이 `shell`이 null인 상태에서 속성을 읽었다

이것은 스택 쿠키 손상이 아니다. Chromium 충돌도 아니다. 다운로드 `QThread`의 부모가 셸이고, 셸이 스레드가 살아있는 동안 파괴되면 Qt가 `abort()`를 호출한다. Windows는 그 종료를 `0xC0000409`로 보고한다.

`QThread.wait()`를 GUI 스레드에서 호출하면 워커가 보낸 `thread.quit()`이 전달되지 않아 대기가 끝나지 않았다. 그래서 대기는 이벤트를 처리하는 루프다. 테스트를 일부러 실패 지점까지 보낸 뒤 엔진을 놓고 이 정리를 세 번 반복했다. 세 번 모두 `RELEASED` 뒤 `DONE`, exit 0이었다.

수정 뒤 전체 단위 테스트 세 번은 종료 코드 1, 1, 0이었다. 1은 브라우저 `net::ERR_FAILED`이고 네이티브 종료가 아니다. 오리진 수정 뒤 세 번은 모두 exit 0, 123 passed, 60.34초, 61.28초, 60.79초다. 이 세 번 사이에 Python, Chromium 자식은 남지 않았다. 프로세스 목록에 보인 `msedge`는 테스트가 띄운 프로세스가 아니다.

앱 종료 경로도 같은 파괴를 피하도록 워커가 끝날 때까지 기다린다. 취소만으로는 `urlopen`이 바로 돌아오지 않는다. 비디오 전송이 취소 확인 전에 오래 막히면 종료가 그 시간만큼 기다린다. 이 대기를 무한 재시도로 쓰지 않는다.

## Windows 네트워크 오류

제품 `download_one()`의 구분은 그대로다.

- `Content-Length`와 받은 바이트가 다르거나 `IncompleteRead.partial`이 있으면 `응답이 잘렸습니다`. 상태는 실패, 크기는 0, `.part`는 지운다.
- `ConnectionResetError`는 최대 4번 다시 시도한 뒤 그 예외 문자열을 반환한다. 여기에는 WinError 10054가 들어 있고 `잘렸`은 없다.
- `TimeoutError`는 `timed out`으로 남는다. 잘림으로 바꾸지 않는다.
- `read(크기)`는 짧은 EOF를 예외로 올리지 않고 짧은 버퍼를 반환한다. 잘림 판정은 그 다음의 길이 비교다.

이 호스트에서 짧은 본문 뒤의 즉시 `close`는 한 시도마다 갈린다. 유휴 측정 20회는 EOF 15회, WinError 10054 5회였다. 표준 라이브러리 핸들러 경로 20회는 EOF 11회, 10054 9회였다. `shutdown` 뒤 잠깐 기다리는 close는 타임아웃이 많았다. `SO_LINGER (1, 0)` RST는 20/20이었다. 닫기 전 50ms 또는 100ms 대기는 RST만 늘렸다. 그래서 짧은 본문은 대기 없이 닫고, RST 시나리오만 linger 0을 쓴다. 재시도 횟수를 늘려 RST를 잘림으로 흡수하지 않았다.

### A. 정상 EOF

서버는 `dot.png` 69바이트를 보내고 `Content-Length`는 109다. 차이 40바이트. 깨끗한 EOF가 보이면 첫 `read(65536)`가 69바이트, 다음 읽기가 빈 값이다. 그 관찰이 된 실행에서 제품 결과는 `응답이 잘렸습니다`, 상태 실패, 경로 빈 문자열, 크기 0, 디렉터리에 파일이 없다.

30회 별도 프로세스: PASS 26, FAIL 4. 실패 번호 8, 20, 29는 제품이 4번 재시도 뒤에도 `[WinError 10054] 현재 연결은 원격 호스트에 의해 강제로 끊겼습니다`를 반환했다. 실패 21은 원시 읽기 8번이 모두 10054라 69 대 109를 그 프로세스에서 관찰하지 못했다. 이 4회를 집계에서 빼지 않는다. 10054를 잘림으로 고쳐 30/30을 만들지 않았다.

### B. TCP RST

`SO_LINGER (1, 0)`으로 본문 일부를 보낸 뒤 닫는다. 30/30. 오류에 `10054`가 있고 `잘렸`과 `timed out`은 없다. 최종 파일과 `.part`는 없다. 크기는 0이다.

### C. 실제 타임아웃

서버는 요청을 읽고 3초 동안 응답하지 않는다. `download_one(..., timeout=1)` 10/10. 오류는 `timed out`이다. 10054와 잘림이 아니다. 파일은 없다. 제품 기본 인자 30초는 바꾸지 않았다. 이 10회는 그 기본값을 1초로 덮어 같은 예외 경로를 본 것이다.

### D. 정상 파일

선언 길이와 본문이 같다. 30/30. 상태 완료, 바이트는 `dot.png`와 같다. `.part`는 없다.

### 기존 test_11

404는 `HTTP 404`, 500은 `HTTP 500`, 잘못된 형식은 `형식`, 거부된 주소는 `허용되지 않은`이다. 짧은 `/short.png`는 실패여야 하고, 오류는 잘림 또는 10054이다. 타임아웃이면 실패다. 30/30 exit 0. 디렉터리는 비었다.

수정 전 이 세션의 test_11 30회는 27 PASS, 3 FAIL(3, 17, 21)이었다. 세 실패 모두 약 1.2초, 단언 줄 60, WinError 10054였다. 30초 타임아웃은 그 30회에 없었다. S2의 29/30과 그 1회의 10054도 기록으로 남는다. 이번 30/30은 그 실패를 지운 결과가 아니다. 짧은 본문의 두 오류를 서로 다른 실패로 받기 때문에 통과한다.

수정 전 전체 스위트 한 번은 `/boom.png`가 30.062초 만에 `timed out`이었다. 유휴 20회에서는 그 타임아웃이 재현되지 않았다. 완전한 본문에서 `shutdown(SHUT_WR)`를 뺀 뒤 test_11 30회와 전체 스위트에서는 그 30초 실패가 다시 나오지 않았다. 한 번의 관찰을 없는 일로 두지 않는다.

## 브라우저

`/lazy.html` 문서 요청이 `net::ERR_FAILED`인 경우가 있었다. 로컬 모드는 프록시를 쓰지 않고 urllib로 본문을 읽은 뒤 `route.fulfill`한다. 읽기가 실패하면 `route.abort()`가 되고 Chromium은 그 원인을 `net::ERR_FAILED`로만 보여 준다. `_goto`는 `ERR_CONNECTION_RESET`만 다시 시도한다.

오리진은 본문 뒤에 `shutdown(SHUT_WR)`를 호출했다. 이 호스트에서 그 호출은 urllib 읽기를 끊는 경우가 있다. 추적 한 예: 서버는 `127.0.0.1:43092`, `goto` 시각 77921.140, 요청 77921.812, `requestfailed` 77921.890, 오류 `net::ERR_FAILED`. 약 80ms라 10초 타임아웃이 아니다.

수정 전 lazy 시나리오 30회: PASS 24, FAIL 6. 실패 번호 1, 18, 25, 28은 `/lazy.html`, 10은 `/spa.html`, 30은 `/js-added.html`이다. 전체 스위트 수정 전 1회차는 `ws.html`과 `login.html`에서 같은 `ERR_FAILED`, 2회차는 lazy의 `TimeoutError: timed out`과 `dedupe.html`, `policy.html`의 `ERR_FAILED`, 3회차는 123 passed였다.

수정: 오리진은 Content-Length까지 보낸 뒤 클라이언트가 닫을 때까지 받는다. `shutdown(SHUT_WR)`는 호출하지 않는다. 정책은 그대로다. `169.254.169.254`와 `local.adguard.org` 요청은 계속 `net::ERR_FAILED`로 거절된다. 호스트에 AdGuard가 Playwright Chromium에도 요청을 넣는다. 그 요청을 허용하도록 정책을 바꾸지 않았다. 페이지 문서가 200이면 테스트는 통과한다.

수정 뒤 lazy 30회: 30/30 exit 0. pytest 시간은 9.50초에서 10.51초. 로컬 문서의 `requestfailed`는 0건이다. 한 실행의 `/lazy.html`은 요청, 응답 200, `requestfinished`, `goto` 반환이 순서대로 남았다. 바인드 예는 `127.0.0.1:20428`이다. `extract_dynamic`은 `context.close()` 다음에 `browser.close()`를 호출한다. 이 순서는 바꾸지 않았다. 30회 뒤에 Chromium 자식은 프로세스 목록에 남지 않았다.

브라우저가 설치됐다는 사실만으로 스위트 통과를 주장하지 않는다. 수정 전 실패 6회와 전체 스위트 실패는 위에 남아 있다.

## 고속 프리셋

한계는 `0.45 * 4` = 1.8초다. 지우거나 늘리지 않았다. 과거 실패로 남은 시각은 1.808, 1.925, 2.210, 1.849, 2.276초다. S2의 30/30 PASS도 유지한다.

이번 공식 30회는 모두 exit 0이다. pytest가 보고한 시간은 1.30초에서 1.55초다. 이 시간은 픽스처를 포함한다. 테스트 안의 경과가 1.8초 이상이면 단언이 실패하므로, 30회 모두 예산 안이다. 기능 단언(실패 없음, peak, 겹침)과 시간 단언은 같은 함수에 있고 둘 다 통과했다.

계측 8회는 공식 30회와 별도다. `run_job` 벽시계 1.088초에서 1.253초, 모두 1.8초 미만, 실패 없음, `peak_connections` 24, 서버 `peak_active` 24. 서버가 0.45초 대기에 들어가기 전까지의 lead는 0.490초에서 0.645초다. `socket.socket.connect` 래퍼에는 연결이 1건만 잡혔다. httpx 풀의 24개 연결 시간과 Python 스케줄 시간을 그 래퍼로 분리하지 못했다. 분리됐다고 적지 않는다. 프리셋 전후 프로세서 부하 평균은 둘 다 9였다. 전체 매트릭스 시작은 10, 끝은 27이었다.

## 세션과 프로세스

`icacls`가 실패하면 세션 디렉터리를 지우고 `SessionProtectError`를 내는 S2 동작은 유지한다. 전체 단위 테스트 123개에 그 검사가 들어 있고, 수정 뒤 3회 모두 통과했다. 쿠키 값은 로그에 없다.

전체 스위트 각 회 전후에 Python과 Chromium 이름을 확인했다. 테스트가 남긴 프로세스는 없었다. 덤프와 cdb 로그는 저장소에 넣지 않았다.

## 5,000장

로컬 1회, exit 0, pytest 156.76초.

| 항목 | 값 |
| --- | --- |
| files | 5000 |
| elapsed_s | 147.792 |
| peak_connections | 3 |
| server_peak | 3 |
| working_set_before | 47968256 |
| working_set_peak | 108355584 |
| integrity_mismatches | 0 |
| large_file_bytes | 6291526 |
| large_file_traced_bytes | 852320 |
| sequential elapsed_s | 4.058, peak 1 |
| parallel elapsed_s | 2.038, peak 3 |

이전 부하 수치 181.386초, 242.862초, S2의 146.161초와 섞지 않는다. 이번 값은 147.792초다.

## 수정 전 전체 스위트

이 세션에서 코드를 바꾸기 전:

- 추적 1회: 118 passed, 1 failed. 실패는 test_11의 `/boom.png`, 오류 `timed out`, 30.062초. 벽시계 94.26초. lazy는 통과했다.
- 이어진 두 번: exit 0, 60.976초. 그리고 exit `-1073740791`, 19.548초.
- 그 다음 `-x` 1회: 119 passed, 58.55초.

수정 뒤, 오리진 `shutdown`을 빼기 전 전체 3회:

- exit 1, 61.537초, 2 failed, 121 passed
- exit 1, 65.394초, 3 failed, 120 passed
- exit 0, 60.653초, 123 passed, 59.66초

오리진 수정 뒤 전체 3회: 123 passed, 60.34초, 61.28초, 60.79초. 모두 exit 0. 네이티브 종료는 없다. 123은 기존 119에 EOF, RST, 타임아웃, 정상 파일 테스트 4개를 더한 수다.

## GitHub Actions

수동 실행만 했다. `inputs.load`는 주지 않았다. `pull_request`는 켜지 않았다.

실행: https://github.com/scarlel96-design/Universal-Media-Downloader/actions/runs/41379332972

이벤트: `workflow_dispatch`

headSha: `e7b6df3a805181840366c350cf7d0fd2b03b4993`

이 SHA는 구현 커밋과 같다. 테스트 잡은 성공했다. Install 로그에 `python -m playwright install chromium`이 있고, Chrome for Testing 156.0.8078.4, Playwright chromium v1248이 받아졌다. Regression 단계 로그의 pytest 결과는 `123 passed in 55.44s`다. 부하 잡은 skipped다.

이 CI PASS는 로컬 EOF 26/30을 지우지 않는다. 브라우저가 설치된 사실만으로 통과를 적지 않았다. S2 실행 `41368994899`의 headSha `aabbffe`도 이번 결과로 세지 않는다.

## 미해결

| 항목 | 상태 |
| --- | --- |
| EOF 시나리오 30회 | FAIL. 26/30. 4회는 10054. |
| 원인이 확인된 크래시 재현 | 수정 후 재현 스크립트와 전체 3회에서 재발하지 않음. |
| lazy.html 30회 | 수정 후 PASS. 수정 전 6실패는 유지. |
| 전체 단위 3회 연속 | 수정 후 PASS. 수정 전은 연속이 아님. |
| 5,000장 | PASS. |
| GitHub Actions 이번 SHA | PASS. 테스트 잡 123 passed, 55.44초. 부하 잡은 skipped. |
| 공개 인터넷에서만 보이는 JavaScript 미디어 | NOT RUN. |
| Windows 실환경 데스크톱 UI | NOT RUN. 출시 차단. |
| 프로젝트 LICENSE | 없음. 파일을 만들지 않음. 출시 차단. |
| 비디오 다운로드 도중 종료가 오래 기다리는 경우 | 관찰하지 않음. 무한 대기로 크래시를 피한다. |
| 24개 소켓의 연결 시간과 스케줄 시간 분리 | 측정하지 못함. lead만 기록. |

## 추가 비용

유료 API나 새 서비스는 쓰지 않았다. 로컬 반복과, 푸시 뒤 Windows Actions 테스트 잡 1회가 전부다. 부하 잡은 이번 워크플로에서 켜지 않는다.

## 병합과 릴리스

PR #4는 병합하지 않는다. EOF 30회가 필수 조건이고 4회가 실패로 남아 있다. Actions 테스트 잡이 통과해도 그 로컬 실패는 남는다. PR #5는 열린 채로 둔다. 다음 기능 개발은 시작하지 않는다.

기능 안정화 GO: NO-GO.

정식 릴리스 GO: NO-GO.
