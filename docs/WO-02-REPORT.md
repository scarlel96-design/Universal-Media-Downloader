# WO-02 보고서 — 대량 병렬 다운로드 및 장애 복구

## 판정

**GO**

필수 테스트 FAIL은 없다. 5,000장 로컬 부하, 재시작 복구, 일시정지·재개, 실패 재시도, 연결 상한, SQLite v1 보존을 모두 실행했다. 숫자는 로컬 픽스처 실측이다. 인터넷 최고 속도가 아니다.

WO-00E 역컴파일은 BLOCKED다. 4K Video Downloader+는 실행하지 않았고 바이너리를 분석하지 않았다. 공개 사이트, JavaScript 렌더링, yt-dlp, gallery-dl, YouTube 인증, Tor, 프록시, DRM은 구현하지 않았다.

## 구현 요약

다운로드 큐는 HTTPX `AsyncClient` 하나와 asyncio 루프 하나다. 루프는 작업 스레드 하나에서 돈다. 요청마다 `QThread`를 만들지 않는다. UI 모델은 UI 스레드에서만 바꾸고, 진행 신호는 Qt signal로 넘긴다. 연결 풀을 재사용하고 본문은 64 KiB 청크로 디스크에 쓴다. 파일 전체를 메모리에 올리지 않는다.

단일 파일용 WO-01 `download_one()`(urllib)은 그대로 두었다. 큐는 그 함수를 반복 호출하지 않는다.

프리셋은 안정 4/2, 균형 12/3, 고속 24/4다. 기본값은 균형이다. 전역 슬롯은 호스트 슬롯을 얻은 뒤, 실제 요청 동안에만 잡는다. 대기 중인 호스트 제한이 전역 슬롯을 차지하지 않는다. 한도를 줄여도 이미 잡은 전송은 취소하지 않는다.

429와 503은 `Retry-After`를 상한 안에서 따른다. 그 외 일시 오류는 지수 백오프와 지터를 쓴다. 그 외 4xx와 일반 5xx는 재시도하지 않는다. 기본 재시도는 3회다. 같은 호스트에서 오류가 3회 쌓이면 그 호스트의 동시 수만 1까지 낮춘다. 실패가 나도 프록시나 Tor를 켜지 않고, `trust_env=False`라 환경의 프록시를 읽지 않는다.

큐는 시작, 일시정지, 재개, 개별 취소, 전체 취소, 실패 재시도, 완료 제외, 우선순위를 지원한다. 임시 파일은 `.umd-{uuid}.part`다. 최종 이름은 잠금 아래에서 `name.png`, `name-2.png` 순으로 예약한다. HTTP 상태, 길이, 이미지 서명을 통과하기 전에는 `os.replace`하지 않는다. 취소와 영구 실패는 부분 파일을 지운다.

이어받기는 `Range`와 `Content-Range`를 본다. 206의 시작 위치가 가진 바이트와 다르면 이어 붙이지 않는다. ETag나 Last-Modified가 바뀌면 부분 파일을 버리고 새로 받는다. 서버가 200으로 전체 본문을 주면 이어 붙이지 않고 `재개 불가`로 남긴다.

리다이렉트는 자동 추적하지 않는다. 처리할 때는 홉마다 주소를 다시 검사하고, 사용자 정보와 fragment는 제거한다. 허용 주소는 기존과 같이 `file:`와 `127.0.0.1` / `localhost`뿐이다.

SQLite 스키마는 2다. 버전 1은 행을 지우지 않고 컬럼을 추가한다. 쓰기는 `RLock`으로 직렬화한다. 프로세스가 최종 이름 변경과 DB 완료 기록 사이에서 끝나면, 파일이 있고 크기와 서명이 맞으면 완료로 복구한다.

화면은 기존 Apple형 토큰과 네이티브 Windows 제목 표시줄을 유지한다. 다운로드 중에는 전체 진행, 파일별 진행, 속도, 완료·실패 수, 남은 용량, 추정 시간, 일시정지, 모드를 보여 준다. 전체 크기를 모르면 퍼센트를 만들지 않고, 추정이 불안정하면 `계산 중`이다. 진행 표시는 약 10 Hz로 제한한다. 완료 체크는 Spring(2.0, damping 0.86, mass 0.8)이고 Reduce Motion이면 즉시 끝난다.

## 변경 파일과 커밋

이 작업 디렉터리는 git 저장소가 아니다. `git rev-parse`는 `fatal: not a git repository`다. 커밋 해시는 없다.

추가:

- `src/umd/download/engine.py`
- `src/umd/download/schedule.py`
- `tests/wo02_support.py`
- `tests/unit/test_wo02_engine.py`
- `tests/unit/test_wo02_ui.py`
- `tests/unit/test_wo02_load.py`
- `docs/design/captures/wo02-download.png`
- `docs/WO-02-REPORT.md`

수정:

- `src/umd/download/__init__.py`
- `src/umd/storage/database.py`
- `src/umd/app/jobs.py`
- `src/umd/app/shell.py`
- `src/umd/app/motion.py`
- `src/umd/netpolicy.py`
- `src/umd/extract/fetch.py`
- `src/umd/ui/qml/components/MediaGrid.qml`
- `src/umd/ui/qml/components/StatusStrip.qml`
- `src/umd/ui/qml/components/InspectorPanel.qml`
- `docs/design/MOTION_TOKENS.md`
- `pyproject.toml` (`httpx>=0.27`)
- `tests/unit/test_wo01_ui.py` (스키마 기대값 2)
- `README.md`

WO-01의 동기 저장 구현 `src/umd/download/images.py`는 유지했다.

## 기능별 검증

아래 표는 구현 여부가 아니라 실행 결과다. 모두 같은 최종 pytest 실행에 포함된다.

| # | 요구 | 결과 | 테스트 |
| --- | --- | --- | --- |
| 1 | 4, 12, 24 병렬 | PASS | `test_parallel_presets_overlap_and_respect_the_cap` |
| 2 | 전역 연결 상한 | PASS | 같은 테스트. `per_host`를 전역 값과 같게 두고 서버 peak가 상한 이하, 상한-1 이상 |
| 3 | 호스트별 상한 | PASS | `test_per_host_cap`, `test_two_hosts_keep_independent_caps` |
| 4 | 요청 시간 중첩 | PASS | 위 병렬 테스트의 span overlap |
| 5 | 429와 Retry-After | PASS | `test_retry_after_429_and_503_and_no_retry_on_404` |
| 6 | 503 후 복구 | PASS | 같은 테스트 |
| 7 | 연결 시간 초과 | PASS | `test_timeout_truncated_body_and_bad_type` |
| 8 | 중간에 끊긴 본문 | PASS | 같은 테스트 |
| 9 | Content-Length 불일치 | PASS | 같은 테스트. 짧은 본문은 실패하고 최종 파일을 남기지 않음 |
| 10 | HTTP 206 범위 | PASS | `test_range_resume_etag_change_and_non_resumable` |
| 11 | 재개 불가 서버 | PASS | 같은 테스트. 노트 `재개 불가` |
| 12 | ETag 변경 | PASS | 같은 테스트. 노트 `원본 변경`, 새 본문만 저장 |
| 13 | 파일명 경합 | PASS | `test_filename_race_does_not_overwrite` |
| 14 | 다운로드 중 취소 | PASS | `test_cancel_and_pause_resume` |
| 15 | 종료 후 작업 복원 | PASS | `test_restart_reconciles_a_finished_file_and_resumes_a_partial` |
| 16 | SQLite v1에서 v2 | PASS | `test_sqlite_v1_migrates_without_dropping_rows` |
| 17 | 다운로드 중 UI 응답 | PASS | `test_ui_stays_responsive_and_pause_resumes`, `test_13_download_does_not_block_the_ui` |
| 18 | WO-01 31개 회귀 | PASS | 아래 회귀 절 |

추가 PASS: 일시정지·재개, 실패 항목은 재시도하지 않는 404, 크기 상한, 우선순위, 리다이렉트 재검사, URL 비밀번호가 오류 문자열에 없음, `HTTP_PROXY` 환경을 무시.

한 호스트만 쓰면 균형 프리셋의 실제 소켓 수는 호스트 상한 3이다. 전역 12와 24는 호스트 상한을 전역과 같게 둔 테스트에서 확인했다.

## 기존 테스트 회귀

WO-01과 창 호스트 테스트는 31개다.

- `test_dpi.py` 4
- `test_tokens_and_catalog.py` 5
- `test_window_host.py` 4
- `test_wo01_download.py` 5
- `test_wo01_extract.py` 6
- `test_wo01_ui.py` 7

결과: PASS. 스키마 기대값은 2로 맞춰 두었고, 완료 파일과 바이트, HTTP 404 기록, UI 스레드 밖 저장은 유지된다.

## 신규 테스트

WO-02 테스트는 20개다.

- `test_wo02_engine.py` 18
- `test_wo02_ui.py` 1
- `test_wo02_load.py` 1

최종 명령:

```powershell
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest tests/unit -p no:logging --tb=line -q
```

결과: **51 passed in 246.66s**. FAIL 없음. SKIP으로 뺀 필수 테스트 없음. 이 실행은 5,000장 부하 테스트를 포함한다. 부하 수치는 바로 앞의 단독 실행에서 출력한 `WO02_METRICS`다. 같은 코드로 1 passed in 191.99s였고, 통합 실행은 그 JSON을 다시 찍지 않았다.

사용한 HTTPX는 0.28.1이다.

## 병렬 다운로드 성능

로컬 루프백만 측정했다. 인터넷 처리량이 아니다.

5,000개의 서로 다른 작은 PNG를 `127.0.0.1`에서 균형 프리셋으로 받았다.

| 항목 | 실측 |
| --- | --- |
| 완료 | 5,000 |
| 바이트 불일치 | 0 |
| 남은 `.part` | 0 |
| 경과 | 181.220 s |
| 처리량 | 초당 약 27.6개 |
| 엔진 동시 연결 peak | 3 |
| 서버 동시 연결 peak | 3 |
| 작업 집합, 시작 | 46,665,728 bytes (44.5 MiB) |
| 작업 집합, 피크 | 99,819,520 bytes (95.2 MiB) |

peak가 3인 이유는 주소가 모두 한 호스트이고 균형의 호스트 상한이 3이기 때문이다. 전역 상한 12를 넘지 않았다.

대형 파일은 PNG 헤더에 6 MiB를 더한 6,291,526 bytes다. `tracemalloc` 피크 증가량은 870,747 bytes다. 파일의 절반(3,145,763 bytes)보다 작다. 본문을 한번에 올리지 않고 저장했다.

## 순차 대비 병렬

같은 프로세스에서 80개 파일, 응답 보류 0.02 s, 로컬 서버로 비교했다. 이 구간의 작업 집합은 5,000장 작업이 이미 끝난 뒤의 값이다.

| | 순차 (전역 1) | 병렬 (균형, 호스트 3) |
| --- | --- | --- |
| 완료 | 80 | 80 |
| 경과 | 4.660 s | 2.904 s |
| 엔진 peak | 1 | 3 |
| 서버 peak | 1 | 3 |
| 작업 집합 직후 | 116,764,672 bytes | 116,916,224 bytes |

병렬이 1.60배 짧았다. 보류 시간이 연결 비용보다 작아서 배율이 호스트 상한 3에 못 미친다. 이 차이를 회선 속도로 말하지 않는다.

## 파일 무결성

5,000개 파일은 인덱스별 기대 바이트와 모두 같았고, `integrity_issues()`는 비어 있었다. 12개 동일 파일명 경합은 서로 다른 이름으로 저장했다. 잘린 본문, 잘못된 이미지 서명, 취소는 최종 파일을 남기지 않는다. 206 범위가 어긋나면 부분 파일에 이어 붙이지 않는다.

## SQLite 마이그레이션

버전 1 데이터베이스에 컬럼을 `ALTER TABLE`로 추가하고 `schema_meta`와 `PRAGMA user_version`을 2로 올린다. 기존 작업 행은 삭제하지 않는다. 추가 컬럼은 전체 크기, 받은 바이트, 재시도 횟수, 마지막 HTTP 상태, ETag, Last-Modified, 재개 가능 여부, 우선순위, 부분 경로, 마지막 진행 시각, 노트다. `host_status`는 호스트별 마지막 상태, 오류 누적, 동시 상한, 진행 수, 갱신 시각을 저장한다.

복구 테스트는 디스크의 최종 파일이 있는데 상태가 `다운로드 중`인 행을 완료로 맞추고, 부분 파일은 URL·ETag와 함께 이어받기로 끝냈다. 완료 행의 파일이 없으면 기존 `integrity_issues()`가 불일치를 보고한다.

## UI 캡처

`docs/design/captures/wo02-download.png`

오프스크린 Qt 클라이언트 영역 1440×900이다. OS 제목 표시줄은 캡처에 없다. 캡처 시점의 셸 값은 다음과 같다.

`균형 · 받는 중 · 완료 0 · 실패 0 · 111.8 KB · 계산 중 · 계산 중`

전체 진행률은 36%였다. 헤더 이전에는 퍼센트가 -1이었고, 속도 표본이 짧아 추정 시간은 `계산 중`이었다. 다운로드 호출은 0.3초 안에 반환했고, 그 사이 테마 전환과 창 너비 변경도 0.3초 안에 처리됐다. 일시정지 후 재개해 파일이 완료됐다. 저장 스레드 식별자는 UI 스레드와 달랐다.

브라우저로 확인하지 않았다. Qt 오프스크린 grab이 대체 수단이다.

## 기존 NOT RUN

이번에도 실행하지 않았다.

- Win+Z / Snap, Alt+Space, Alt+F4
- 실제 모니터 DPI, 고대비, 스크린 리더
- 300 ms 프레임 타이밍
- `QFileDialog` 네이티브 대화상자
- 공개 웹, JavaScript 렌더링, yt-dlp, gallery-dl, YouTube 인증
- Tor, 프록시 동작, DRM
- 4K Video Downloader+ 실행과 역분석
- 실제 인터넷 다운로드 속도

Windows 루프백에서 소켓을 닫을 때 asyncio가 `WinError 10022`를 콜백 로그로 남기는 경우가 있다. 다운로드 결과와 테스트 판정에는 넣지 않았다.

## 추가 비용

0. 유료 API나 유료 서비스를 호출하지 않았다.

## 외부 업로드

사용자 파일과 작업 데이터를 외부에 올리지 않았다. `httpx` 0.28.1은 로컬 가상환경에 설치한 패키지다.

## 구현과 검증의 구분

구현해 두었고 테스트로 확인한 것: 비동기 큐, 세 프리셋, 호스트별 적응, 재시도, 이어받기, 원자적 상태와 부분 파일, SQLite v2 마이그레이션과 복구, 진행 UI, 로컬 5,000장과 대형 파일 스트리밍.

구현하지 않은 것: 공개 사이트 허용, JS 렌더링, yt-dlp, gallery-dl, YouTube, Tor, 프록시, DRM, 인터넷 속도 보장, 4K 역분석.
