# WO-04-S2 결과 보고

작업일: 2026-11-02

작업명: Windows HTTP 종료 오류 및 병렬 다운로드 안정화

공식 저장소: https://github.com/scarlel96-design/Universal-Media-Downloader

대상 PR: https://github.com/scarlel96-design/Universal-Media-Downloader/pull/4

PR 상태: OPEN. 이 작업에서 병합하지 않았다. PR #5도 병합하지 않았다.

기준 브랜치: `feat/wo04-browser-extraction`

기준 HEAD: `f9a00d36c678a634eb05537a716ad34463a1d5eb`

구현 커밋: `fd93f1860387f60b8989d6c5cdb4b2477811d63a`

기록 커밋: `aabbffef49208225b255c4b14f5f0bf1d42c5f10`. 구현 커밋과의 차이는 이 문서에 SHA를 적은 것뿐이다.

로컬 반복 실험은 구현 커밋 직전의 같은 작업 트리에서 했다.

환경: 로컬 Windows, Python 3.12, 저장소 가상환경. CI 결과와 로컬 결과를 같은 PASS로 적지 않는다.

안정화 판정: 미충족. GO가 아니다.

병합 판정: NO-GO. PR #4는 열린 상태로 둔다.

정식 공개 릴리스: NO-GO. Windows 실환경 UI와 프로젝트 `LICENSE` 없음은 계속 출시 차단이다.

## 판정 요약

| 완료 조건 | 결과 |
| --- | --- |
| `test_11` 반복 30회 전부 PASS | FAIL. 29 PASS, 1 FAIL. 실패는 30초 시간 초과가 아니다. |
| 고속 프리셋 24 반복 30회 전부 PASS | PASS. 이번 30회는 모두 exit 0. 1.8초 한계는 그대로다. 이전 실패 기록은 유지한다. |
| 실제 원인 또는 검증된 수정 근거 | 부분. 30초 시간 초과의 원인은 확인했다. WinError 10054는 남았다. |
| 기존 단위 테스트 전체 PASS | FAIL. 3회 중 1회만 exit 0. |
| 전체 단위 테스트 3회 연속 PASS | FAIL. |
| 5,000장 부하 테스트 PASS | PASS. 로컬 1회. |
| 파일 바이트 불일치 0 | PASS. 부하 테스트 `integrity_mismatches` 0. |
| 부분 파일 정리 정상 | 부분. 통과한 `test_11` 29회는 디렉터리가 비었다. 실패 1회는 그 검사 전에 멈췄다. |
| Windows 소켓 오류 처리 검증 | PASS. 10022 필터는 종료 콜백의 `shutdown`만 무시한다. 전송 중 10054는 오류로 남았다. 필터 코드는 이번 작업에서 바꾸지 않았다. |
| 인증 파일 접근 권한 검증 | PASS. 권한 적용 실패 시 세션 디렉터리를 지우고 예외를 낸다. |
| GitHub Actions 테스트 잡 PASS | PASS. 테스트 잡만. 부하 잡은 실행하지 않았다. 로컬 FAIL과 별개다. |
| 해결되지 않은 필수 FAIL 없음 | FAIL. |

기능 개발 GO와 정식 릴리스 GO는 따로 둔다. 둘 다 NO-GO다.

## 수정 파일

새 기능과 UI 변경은 없다. `download_one()`과 `DownloadEngine`은 합치지 않았다. `download_one()`은 삭제하지 않았다. 제품의 30초 시간 제한과 프리셋 1.8초 한계는 바꾸지 않았다. `timed out`을 잘림으로 바꾸지 않았다. WinError 10022를 무조건 무시하지 않았다.

- `tests/wo01_support.py`: 선언 길이가 본문보다 긴 응답만 표준 라이브러리 핸들러로 끝낸다. 완전한 본문의 기존 종료는 그대로다.
- `src/umd/auth/session.py`: `icacls` 적용과 재조회가 실패하면 세션 디렉터리를 지우고 `SessionProtectError`를 낸다.
- `tests/unit/test_wo04s.py`: 권한 실패가 세션 파일을 남기지 않는지 검사한다. 메시지에 쿠키 값이 없는지도 검사한다.
- `docs/WO-04-S2-REPORT.md`: 이 문서.

## 확인된 오류 원인

기준 측정은 서버 코드를 바꾸기 전에 했다. `FixtureServer`는 HTTP/1.0으로 보내고 `shutdown(SHUT_WR)`를 호출한 뒤, 클라이언트가 닫을 때까지 `recv`로 기다렸다.

잘린 `short.png`는 본문 69바이트, `Content-Length` 109다. 시각은 monotonic clock이다. 실패 1회의 상대 시각은 다음과 같다.

| 이벤트 | 초 |
| --- | --- |
| 서버 accept | 0.069559 |
| 요청 헤더 수신 완료 | 0.081817 |
| 응답 전송 완료 | 0.083508 |
| `shutdown` 호출 | 0.083525 |
| `shutdown` 반환 | 0.083567 |
| 서버 `recv`가 빈 값 반환 | 0.084760 |
| 서버 소켓 close | 0.084772 |
| 클라이언트 첫 수신 153바이트 | 0.084927 |
| 클라이언트 원 소켓 close | 0.085923 |
| 클라이언트 `TimeoutError` | 30.094413 |

`shutdown`은 바로 반환했다. 그 뒤 `recv`는 약 1.2ms 안에 빈 값을 반환했다. 서버는 그때 소켓을 닫았다. urllib은 원본 소켓으로 헤더와 69바이트를 받은 뒤 그 소켓을 닫고, 복제한 makefile 읽기는 30초 뒤 `TimeoutError`가 됐다. 제품 오류 문자열은 `timed out`이다. 저장 경로는 비어 있었다.

같은 기준 8회: 실패 2회가 30.095초, 30.035초. 통과 6회는 0.006초에서 0.027초이고 오류는 `응답이 잘렸습니다`였다. 원시 `urlopen`은 `IncompleteRead(69 bytes read, 40 more expected)` 1회와 `TimeoutError` 2회였다.

원인: 이 호스트에서 `shutdown(SHUT_WR)` 뒤의 블로킹 `recv`가 클라이언트가 닫기 전에 빈 값을 돌려준다. 그 직후 `close`가 urllib의 복제 읽기에 EOF를 안정적으로 전달하지 못한다. 그래서 잘린 본문이 길이 불일치로 끝나지 않고 시간 초과가 된다.

## 종료 방식 비교

비교 실험의 클라이언트 시간 제한은 2초다. 제품 기본값 30초는 그대로다. 같은 69바이트 본문과 선언 길이 109를 썼다. urllib과 HTTPX를 나눠 세었다.

| 방식 | urllib | HTTPX |
| --- | --- | --- |
| A. 기존 half-close와 drain, 12회 | 잘림 7, 시간 초과 5. drain 길이는 매번 0이고 1ms 미만 | `RemoteProtocolError` 6, 시간 초과 5, `ReadError` 1 |
| B. 전송 후 즉시 close, recv 없음, 12회 | 잘림 12 | `RemoteProtocolError` 9, `ReadError` 3 |
| B를 30회로 늘림 | 잘림 28, WinError 10054 2. 완전 본문 대조 15회는 모두 정상 | 이 30회 표본에는 없음 |
| C. 표준 라이브러리 HTTP 서버, 12회 | 잘림 12 | `RemoteProtocolError` 7, `ReadError` 5 |
| C를 늘림 | 잘림 50/50, 이후 199/200과 reset 1. 완전 본문 20/20, 이후 19 정상과 reset 1 | 이 긴 표본은 urllib |
| D. WO-02 LabServer 잘림 종료, 12회 | 잘림 1, `[WinError`로 시작하는 오류 11 | `ReadError` 12 |

추가로 본 방식:

- `shutdown` 후 지연 없이 close, 40회: 잘림 37, reset 3.
- `shutdown` 후 0.05초 뒤 close, 40회: 잘림 22, 시간 초과 18.
- `shutdown` 후 0.2초 뒤 close, 40회: 시간 초과 19, 잘림 21.
- FIN을 늦게 보내는 경우 urllib 40회: 대기 0.05초에서 시간 초과 34, 잘림 6. 대기 0.15초에서 시간 초과 35, 잘림 5. HTTPX 15회는 각 대기에서 느린 시간 초과 13, 짧은 예외 2.
- `TCP_NODELAY` 40회: 잘림 38, reset 2. `SO_LINGER`: 잘림 36, reset 4. 둘 다: 잘림 39, reset 1. linger만 쓰고 shutdown 없음: 시간 초과 40.
- `read1()`로 바꾼 짧은 close: 잘림 23, reset 17. 완전 본문 drain: 정상 14, reset 1. 제품 코드에 넣지 않았다.
- makefile만 재현, 100회: 잘림 95, reset 5. 논블로킹 drain 후 shutdown, 100회: 잘림 70, reset 30.

채택한 종료는 잘린 응답에만 쓴다. 표준 라이브러리 `BaseHTTPRequestHandler`가 HTTP/1.0, `Content-Length`, `Connection: close`, 본문을 쓰고 핸들러를 끝낸다. 그다음 `shutdown(SHUT_WR)`와 `close`를 한다. 블로킹 `recv`는 하지 않는다. 이 형태로 `download_one` 200회는 잘림 199, reset 1이었다.

reset은 `urlopen` 안에서 나는 경우가 있고, 그때 읽은 본문 길이가 없다. 그 오류를 `응답이 잘렸습니다`로 바꾸면 관측하지 않은 길이를 잘림이라고 적게 된다. 그렇게 하지 않았다. 시간 초과는 시간 초과로 남긴다.

404, 500, 잘못된 서명은 `declared is None`이라 기존 전송 경로를 탄다. `test_11`의 실패는 그 세 검사 다음 줄인 잘린 본문 검사였다.

## 변경 후 재현

각 실행은 새 프로세스다. 실패한 실행을 빼지 않았다. 시각은 로컬 시각이다.

`test_11` 30회, 2026-11-02 09:32:15부터 09:32:49.

- PASS 29, FAIL 1.
- 실패는 13회차, exit 1, 프로세스 벽시계 1.111초.
- 오류는 `[WinError 10054] 현재 연결은 원격 호스트에 의해 강제로 끊겼습니다`.
- 상태 `실패`, `path` 빈 문자열, `size` 0.
- 단언은 `잘렸`이 없다는 지점에서 멈췄다. 디렉터리 비움 검사는 실행되지 않았다.
- 나머지 벽시계는 1.080초에서 1.371초다. 30초 시간 초과는 이 30회에 없다.
- 변경 전 같은 테스트의 실패는 약 30초 `timed out`이었다. 그 기록은 유지한다.

고속 프리셋 24, 30회, 09:32:52부터 09:33:55.

- 30회 모두 exit 0.
- 프로세스 벽시계 1.991초에서 2.532초. 이 값은 pytest 기동을 포함한다.
- 테스트 안의 1.8초 단언은 exit 0이므로 통과했다. 내부 경과를 이 벽시계로 대체하지 않는다.

전체 단위 테스트 3회. 부하 테스트와 라이브 테스트는 제외했다. 수집 표시는 119개다.

- unit-1, 09:34:17, exit `-1073740791` (`0xC0000409`), 22.537초. 진행 표시는 점 29개, `F` 1개, 점 4개 다음 프로세스가 죽었다. 실패 요약이 없다. 테스트 이름은 기록되지 않았다.
- unit-2, 09:35:27, exit 0, 70.189초. 진행 표시 119개, `F` 없음. `N passed` 줄은 캡처에 없다.
- unit-3, 09:36:27, exit 1, 59.126초. 실패는 `tests/unit/test_wo04_browser.py::test_javascript_images_spa_lazy_scroll_and_cleanup`. `Page.goto`가 `http://127.0.0.1:61831/lazy.html`에서 `net::ERR_FAILED`. 예외는 `src/umd/extract/browser.py:146`의 `ExtractError`. `test_11` 시간 초과가 아니다. 픽스처 변경이 원인이라고 확인하지 못했다.

5,000장 부하 1회, 09:39:03, exit 0, 프로세스 156.311초.

```text
files 5000
elapsed_s 146.161
peak_connections 3
server_peak 3
working_set_before 47841280
working_set_peak 103899136
integrity_mismatches 0
large_file_bytes 6291526
large_file_traced_bytes 870354
sequential elapsed_s 4.289 peak_connections 1
parallel elapsed_s 2.252 peak_connections 3
```

이 수치를 WO-04의 181.386초, WO-04-S의 242.862초와 섞지 않는다.

## 고속 프리셋 구간

한계는 `hold * 4`다. `hold`는 0.45초이므로 1.8초다. 바꾸지 않았다.

계측 8회. 엔진 `peak_connections` 24, 서버 `peak_active` 24, 겹침 True, 실패 0, 예산 PASS.

| 회 | wall | cpu | spread | hold | server | lead | tail | 10022 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 1.332 | 0.828 | 0.060 | 0.451 | 0.510 | 0.741 | 0.080 | 5 |
| 1 | 1.174 | 0.688 | 0.051 | 0.451 | 0.502 | 0.582 | 0.090 | 9 |
| 2 | 1.124 | 0.594 | 0.042 | 0.451 | 0.492 | 0.545 | 0.087 | 11 |
| 3 | 1.172 | 0.625 | 0.003 | 0.451 | 0.454 | 0.595 | 0.124 | 13 |
| 4 | 1.143 | 0.641 | 0.052 | 0.451 | 0.502 | 0.528 | 0.113 | 10 |
| 5 | 1.123 | 0.562 | 0.003 | 0.452 | 0.454 | 0.566 | 0.103 | 5 |
| 6 | 1.110 | 0.578 | 0.003 | 0.451 | 0.454 | 0.553 | 0.104 | 5 |
| 7 | 1.114 | 0.594 | 0.066 | 0.451 | 0.516 | 0.500 | 0.097 | 3 |

`cpu`는 프로세스 CPU 시간이다. 다른 프로세스의 시스템 부하는 별도 계수로 수집하지 않았다.

`lead`는 서버 핸들러 앞의 루프, 연결, 요청 읽기다. 0.500초에서 0.741초다. `tail`은 마지막 서버 구간 뒤의 루프와 프로액터 종료다. 0.080초에서 0.124초다. 흔들림은 hold 0.45초보다 lead에 있다.

10022 이벤트 수와 wall은 같이 움직이지 않았다. 이벤트가 13인 회차의 wall은 1.172초다. wall이 1.332초인 회차의 이벤트는 5다.

WO-04-S에 기록된 이전 실패는 유지한다. pytest 단독 실패 1.925초, 1.808초. 계측 실패 2.210초, 1.849초. 전체 실행 실패 2.276초. 이번 조용한 30회 통과가 그 실패를 없었던 일로 만들지 않는다. 한계를 늘리지 않았다.

기능 정확성(겹침, 상한 24, 실패 0)과 시간 예산은 같은 테스트 함수 안에 있다. 시간 예산 단언은 분리해 지우지 않았다.

## 두 전송 경로

`download_one()`은 urllib이다. `DownloadEngine`은 HTTPX다. 이번 작업에서 공통 경로로 합치지 않았다. 계약 테스트 `tests/unit/test_wo01_download.py`는 유지한다. 검증 없이 `download_one()`을 삭제하지 않았다.

| 항목 | `download_one()` | `DownloadEngine` |
| --- | --- | --- |
| HTTP 상태 | 200이 아니면 `HTTP {status}`. `HTTPError`도 같은 형식 | 공개 모드 401, 403은 별도 문구. 429와 503은 재시도. 그 외 4xx와 200, 206이 아닌 상태는 `HTTP {status}` |
| 길이 | `Content-Length`와 기록 바이트가 다르면 `응답이 잘렸습니다`. `IncompleteRead`의 `partial`도 같은 문구 | 전송 오류와 길이 불일치를 `응답이 잘렸습니다`로 재시도 |
| 서명 | PNG, JPEG, GIF, WEBP만 최종 이름으로 바꾼다 | 엔진의 이미지 커밋도 서명을 검사한다 |
| 임시 파일 | `.umd-{uuid}.part`. 검사 후 `os.replace` | 항목별 part. 실패 시 삭제하거나 재개 지점까지 자른다 |
| 오류와 취소 | 취소는 `취소`. reset은 4회 재시도 후 `str(exc)` | 취소, 일시정지, 재시도, 영구 실패를 구분한다 |
| 시간 초과 | 예외 문자열이 그대로 돌아간다. 기본 30초 | `시간이 초과되었습니다` |
| 연결 종료 | urllib이 응답 소켓을 닫는다 | 응답은 `aclose`. Windows 종료 콜백의 10022만 따로 닫는다 |

중복은 있다. 상태, 길이, 서명, 임시 파일을 두 곳이 각자 구현한다. HTTPX로 합치면 WO-01 호출부와 오류 문자열이 바뀐다. 이번 측정에서 남은 실패는 로컬 소켓 종료의 WinError 10054다. 공통 경로가 그 reset을 없앤다는 측정이 없다. 구조 변경은 하지 않았다.

## 소켓과 이벤트 루프

`install_windows_socket_close`는 이번 작업에서 수정하지 않았다.

- 다운로드 태스크 결과와 이벤트 루프 종료 콜백을 분리한다.
- 콜백에서 `OSError`가 나면 소켓을 닫고 서버에서 뗀 뒤, WinError 10022인지를 본다.
- 트레이스백의 `_call_connection_lost`가 `proactor_events.py`에 있고, 그 소스 줄에 `shutdown`이 있을 때만 무시한다.
- 그 밖의 10022는 다시 올린다. WinError 10057과 다른 소켓 예외도 다시 올린다.
- 전송 중 10054는 `download_one`의 오류 문자열로 남았다. 필터가 삼키지 않았다.

잘린 응답의 종료 순서는 핸들러 종료, `shutdown(SHUT_WR)`, `close`다. 엔진의 정상 응답은 스트림을 읽은 뒤 `response.aclose()`다. 프로액터 콜백은 그 다음에 온다. 이벤트 루프에 미완료 전송이 없는지는 프리셋 계측의 `failed=0`과 서버 구간이 wall 안에서 끝난 것으로 확인했다. 네이티브 크래시가 난 unit-1에서는 루프 종료 상태를 확인하지 못했다.

## 인증 파일

기존 쿠키 규칙은 유지한다. Secure는 `https`만, Domain은 점 제거 후 같은 호스트, Path는 접두사, `expires`가 `-1`이 아니고 현재 이하면 만료다. `0`은 만료다. `-1`은 세션 쿠키다. `persistent_sessions_enabled()`는 `False`다.

Windows에서는 `icacls /inheritance:r /grant:r {user}:(OI)(CI)F`의 종료 코드가 0이어야 한다. 그다음 `icacls` 재조회의 종료 코드가 0이고, 바이트 출력에 사용자 이름과 `(OI)(CI)(F)`가 있어야 한다. 하나라도 실패하면 세션 디렉터리를 지우고 `SessionProtectError("세션을 보호하지 못해 저장하지 않았습니다")`를 낸다. 로그인 스레드는 기존 `self._notify(str(exc)[:180])`로 이 문구를 보여 준다. UI는 바꾸지 않았다.

실패 테스트는 쿠키 값 `secret-value`가 예외 문구에 없고, 호스트 디렉터리가 없는지를 검사한다. unit-2가 exit 0이므로 이 테스트와 기존 ACL 바이트 검사가 그 실행에 포함되어 통과했다. 진단 로그에 쿠키 값을 찍지 않는다.

## GitHub Actions

- 주소: https://github.com/scarlel96-design/Universal-Media-Downloader/actions/runs/41368994899
- 이벤트: `workflow_dispatch`
- `--ref`: `feat/wo04-browser-extraction`
- `headSha`: `aabbffef49208225b255c4b14f5f0bf1d42c5f10`
- 로컬 기록 커밋과 같다. 구현 커밋 `fd93f1860387f60b8989d6c5cdb4b2477811d63a`와는 이 문서의 SHA 기록만 다르다.
- 테스트 잡: success. 로그에 `python -m playwright install chromium`이 있고, Chrome for Testing 156.0.8078.4 (playwright chromium v1248) 설치가 찍혀 있다.
- 테스트 잡 pytest: `119 passed in 58.96s`
- 부하 잡: skipped. `inputs.load`를 켜지 않았다.

CI 테스트 잡 PASS는 로컬 `test_11` 1회 실패, unit-1 크래시, unit-3 `lazy.html` 실패를 지우지 않는다. CI 성공만으로 GO를 주지 않는다.

## 잔여 항목

FAIL:

- `test_11` 30회 중 1회 WinError 10054. 미해결.
- 전체 단위 테스트 3회 연속 통과 실패. unit-1 네이티브 크래시, unit-3 `lazy.html` `net::ERR_FAILED`. 둘 다 미해결.
- 프리셋 24의 이전 1.8초 초과 기록. 이번 30회는 통과했다. 한계는 유지한다.

NOT RUN:

- `test_11` 실패 1회의 디렉터리 목록.
- 다른 프로세스의 CPU 부하 계수.
- unit-1에서 죽은 테스트의 이름.
- 공개 페이지에서 JavaScript만으로 삽입된 미디어.
- 실제 Windows 데스크톱 UI.

BLOCKED:

- 정식 릴리스. 프로젝트 `LICENSE`가 없다. Windows 실환경 UI 검증이 없다.
- PR #4 병합. 위 FAIL이 남아 있다.

## 비용

추가 비용 0. 유료 API와 대형 러너는 쓰지 않았다. GitHub 호스트 러너의 테스트 잡은 공개 저장소의 기본 Windows 러너다. 부하 잡은 실행하지 않는다.

업로드는 이 브랜치와 PR #4뿐이다. 세션 파일, 쿠키, SQLite, `.venv`, 부분 다운로드, 실험 스크립트는 커밋하지 않는다.

## 병합과 다음 단계

PR #4는 병합하지 않는다. PR #5도 병합하지 않는다. 다음 기능 작업을 시작하지 않는다. `pull_request` 트리거는 켜지 않는다.

다음에 할 일은 요청이 있을 때만 한다.

- 로컬 종료에서 반복되는 WinError 10054.
- unit-1의 `0xC0000409`와 unit-3의 `lazy.html` `net::ERR_FAILED`.
- 그 뒤에도 필수 FAIL이 있으면 병합하지 않는다.
- 정식 릴리스는 `LICENSE`와 Windows 실환경 UI가 남는다.
