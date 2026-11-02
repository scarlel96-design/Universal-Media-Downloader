# WO-REUSE-01 이후 구현 지시서

이 지시는 WO-REUSE-00 감사가 끝난 뒤에 실행한다. 감사 보고서는 `docs/WO-REUSE-00-REPORT.md`다. 이 파일을 만드는 작업은 구현이 아니다.

## 유지

- 저장소는 Universal Media Downloader만 수정한다. Booru Studio 저장소는 읽기만 한다.
- 브랜치는 `feat/wo04-browser-extraction`다. 비교 시점 팁은 `9e2ee635458791a6b4a5e67c4337e51721734778`이다. 구현은 `58091cff931d0c079a995319c65f23173e5876b0`에 있다.
- PR #4와 PR #5를 병합하지 않는다.
- UMD `main`과 PR #4를 섞지 않는다.
- `src/umd/download/images.py`의 `download_one()`을 지우거나 재작성하지 않는다.
- `DownloadEngine` 파일을 Booru `DirectHttpWorker`로 바꾸지 않는다.
- Booru 소스 파일을 복사하지 않는다. `pyproject.toml` 라이선스 문구는 `UNLICENSED`이고 `LICENSE` 파일이 없다.
- gallery-dl, yt-dlp, Playwright, Qt, FFmpeg 소스를 벤더로 넣지 않는다.
- 제품 타임아웃 30초와 프리셋 예산 `0.45 * 4`를 올리지 않는다.
- `QThread.terminate`를 쓰지 않는다.
- 네트워크 정책을 끄고 테스트를 통과시키지 않는다.
- 프로젝트 `LICENSE` 파일을 이 작업에서 만들지 않는다. 소유자가 문구를 정하기 전에 만들지 않는다.
- 쿠키, Authorization, 서명 쿼리, SQLite, 개인 경로를 이슈와 로그에 올리지 않는다.
- 기능 안정화 GO와 정식 릴리스 GO를 섞지 않는다. 실기 Windows UI와 프로젝트 LICENSE 부재는 릴리스 차단으로 남긴다.
- 과거 Booru Sprint PASS를 현재 PASS로 적지 않는다.

## WO-REUSE-01 — 영속 저장에서 비밀 제거

목표: 서명된 URL 쿼리, 쿠키 값, Authorization 값이 SQLite, 로그, 진단 결과, IPC 출력에 남지 않게 한다.

구현:

- 저장하는 페이지 식별자에서는 쿼리와 프래그먼트와 userinfo를 뺀다. 키 허용 목록으로 서명 쿼리를 거르지 않는다.
- 전송이 끝나기 전에 필요한 URL은 기존 세션 디렉터리와 같은 방식으로 현재 사용자만 읽게 한다. ACL에 실패하면 그 파일을 지우고 실패로 남긴다.
- 재개와 yt-dlp 재추출은 그 임시 위치를 읽고, 완료·취소·실패 뒤에는 지운다.
- 오류 문자열을 저장하기 전에 쿠키 값, Authorization 값, URL userinfo, URL 쿼리를 제거한다.
- 기존 행을 마이그레이션할 때 쿼리를 제거한다. 행을 삭제하지 않는다.

하지 말 것:

- 세션 쿠키 기능을 제거하지 않는다. 엔진이 요청에 Cookie를 붙이는 동작은 유지한다.
- Booru `redaction.py`를 import하지 않는다. 규칙을 UMD 쪽에 새로 작성한다.

완료 조건:

- 테스트가 서명 쿼리를 넣고 SQLite와 캡처한 로그와 자식 프로세스 stdout에서 그 쿼리가 없음을 확인한다.
- 쿠키 파일이 ACL 실패 시 사라지는 기존 동작이 유지된다.
- 재개가 임시 URL로 이어지고, 완료 뒤에 그 파일이 없다.

예상: 1~2일. 아래 추가 검증이 끝나기 전에는 이 일로 완료를 적지 않는다.

### 추가 필수 검증

위 구현 문단은 유지한다. 아래 8개는 그 위에 더해지는 완료 조건이다. 더 좁은 조건이 이전 문장과 겹치면 아래 조건을 따른다. 비밀을 쓴 뒤에 ACL을 확인하고 실패 시 지우는 순서는 허용하지 않는다. 실패 직후 서명 URL만 지우고 재개 가능 상태로 남기는 것도 허용하지 않는다.

각 조건은 자동 테스트 하나로 확인한다. 테스트를 추가하지 않거나, 건너뛰거나, 실행 결과가 없으면 그 조건은 PASS가 아니다. 보고서에는 조건마다 테스트 이름, 실행 여부, 결과만 적는다. 코드를 읽고 맞을 것으로 보는 판단은 PASS가 아니다.

1. 비밀정보를 기록하기 전에 디렉터리 접근권한을 제한한다. ACL 검증에 실패하면 비밀정보를 기록하지 않는다.

   서명 URL을 담는 디렉터리와 기존 세션 디렉터리 모두, 파일을 만들기 전에 제한하고 그 결과를 확인한다. 확인에 실패하면 비밀 파일을 만들지 않는다. 빈 디렉터리가 남으면 지운다.
   테스트 `test_secret_is_not_written_when_acl_check_fails`: 제한 함수가 실패하면 서명 쿼리와 쿠키 값이 디스크에 없다.
   Windows에서는 같은 테스트가 실제 `icacls` 경로를 한 번 탄다. 그 실행이 없으면 이 조건은 PASS가 아니다. 모의 객체만 통과한 결과는 PASS로 적지 않는다.

2. SQLite의 `page_url`, `media_url`, `original_url`, `thumbnail_url`, `media_reference`, `error`, `note`를 검사한다. 이외의 URL 저장 경로도 확인한다.

   현재 스키마에서 함께 검사할 경로는 `jobs.page_url`, `media_items`의 `reasons`, `saved_path`, `part_path`, `title`, `subtitles`, `format`, `classification`, `host_status.host`다. 마이그레이션이 `media_url`을 `original_url`과 `media_reference`로 복사하는 경로도 포함한다.
   SQLite 밖의 경로도 같은 테스트에서 확인한다. 진행 JSON, `.umd-cancel`, `.umd-video-*`, `.umd-progress-*`, 자식 프로세스에 넘기는 페이로드, 로그로 남기는 예외 문자열이다.
   테스트 `test_signed_query_is_absent_from_sqlite_and_other_stores`: 위 컬럼과 파일을 모두 읽어 서명 쿼리, 쿠키 값, Authorization 값이 없음을 확인한다. 목록에 없는 문자 컬럼이 더 있으면 그 컬럼도 검사하고 보고서에 이름을 적는다.

3. 쿼리를 제거하더라도 서로 다른 원본 항목의 식별자가 충돌하지 않게 한다.

   경로가 같고 서명 쿼리만 다른 두 항목은 마이그레이션 뒤에도 두 행이다. `item_id`는 서로 다르고, 각 행의 `job_id`는 원래 잡을 가리킨다. 쿼리를 뺀 URL만으로 행을 합치지 않는다.
   테스트 `test_distinct_signed_items_keep_separate_ids`.

4. 실패 또는 재시작 후 서명 URL을 다시 확보할 수 있는지 검증한다. 복구할 수 없는 작업은 재인증 필요 상태로 구분한다.

   라이브러리를 닫았다 연 뒤, 서명 URL을 다시 읽을 수 있는 항목만 재개를 시도한다. 읽을 수 없으면 상태는 `재인증 필요`다. 그 상태를 `실패`, `취소`, `완료`, `일시정지`, `다운로드 중`과 같은 값으로 두지 않고, 재개를 시작하지 않는다.
   페이지 URL만으로 추출기를 다시 호출해 받는 경로는 그 사실을 테스트가 구분한다. 이전 서명 쿼리를 SQLite에 다시 쓰지 않는다.
   테스트 `test_restart_reauth_when_signed_url_cannot_be_restored`. 복구되는 경우와 복구되지 않는 경우를 한 테스트 안에 각각 단정한다.

5. 자식 프로세스의 stdout, stderr, 예외 문자열에 비밀정보가 노출되지 않게 한다.

   `src/umd/net/child.py`는 실패 시 stdout JSON에 `error`와 `trace`를 쓴다. 구현 뒤에는 그 문자열과 stderr에 서명 쿼리, 쿠키 값, Authorization 값이 없어야 한다.
   테스트 `test_child_stdio_and_exceptions_omit_secrets`: `python -m umd.net.child`를 실제로 띄우고 stdout과 stderr를 모두 캡처한다. 예외 객체의 문자열도 별도로 확인한다. 부모 프로세스 안에서 함수만 호출하고 파이프를 보지 않은 결과는 이 조건의 PASS가 아니다.

6. 기존 SQLite 데이터 마이그레이션에서 행과 작업 관계를 보존한다.

   비밀이 들어 있는 기존 버전 데이터베이스를 연다. `jobs`와 `media_items`의 행 수, `jobs.id`, `media_items.id`, `media_items.job_id`는 그대로다. 행을 삭제하거나 잡에 다시 붙이지 않는다. 검사 대상 문자열에서 비밀만 제거한다.
   테스트 `test_migration_keeps_job_item_links_while_removing_secrets`.

7. SQLite WAL과 기존 백업에 남을 수 있는 비밀정보의 처리 범위를 별도로 보고한다.

   현재 `Library`는 `journal_mode`를 WAL로 바꾸지 않고, 백업을 만드는 코드도 없다. 이 사실은 테스트로 확인한다. 확인해도 본 데이터베이스에서 비밀이 사라졌다는 결과와 묶어서 PASS로 적지 않는다.
   테스트 `test_wal_and_backup_scope_is_reported`: 연 연결의 `journal_mode`, 옆에 생긴 `-wal`과 `-shm`, 테스트가 일부러 만들어 둔 복사본을 기록한다. 마이그레이션이 본 파일만 고치고 WAL 파일과 복사본을 수정하지 않으면 보고서는 `본 데이터베이스`와 `WAL·백업`을 따로 적는다. 복사본에 비밀이 남아 있으면 WAL·백업 범위는 PASS가 아니다. 파일을 검사하지 않았으면 NOT RUN이다.

8. 기존 세션 쿠키, 다운로드 재개, S4 취소·종료 동작을 유지한다.

   다음 기존 테스트를 수정하지 않고 다시 실행한다.
   - `tests/unit/test_wo04s.py::test_cookie_scope_expiry_and_leftover_files`
   - `tests/unit/test_wo04s.py::test_failed_acl_does_not_keep_the_session`
   - `tests/unit/test_wo04_browser.py::test_sessions_stay_on_their_site_and_out_of_sqlite`
   - `tests/unit/test_wo02_engine.py::test_range_resume_etag_change_and_non_resumable`
   - `tests/unit/test_wo02_engine.py::test_cancel_and_pause_resume`
   - `tests/unit/test_wo02_engine.py::test_restart_reconciles_a_finished_file_and_resumes_a_partial`
   - `tests/unit/test_wo02_ui.py::test_ui_stays_responsive_and_pause_resumes`
   - `tests/unit/test_wo04_s4_shutdown.py`의 종료 3건
   쿠키는 요청에 계속 붙고, SQLite에는 계속 들어가지 않는다. Range 재개, 취소, 일시정지 후 재개, S4의 스레드 종료와 부분 파일 삭제는 유지한다. `download_one()`은 그대로 둔다.

새 테스트는 `tests/unit/test_wo_reuse_01_secrets.py`에 둔다. 조건 8은 새 단정을 그 파일에 복제하지 않고 위 기존 테스트를 실행한다. 조건 1부터 7은 그 파일의 해당 테스트가 통과해야 PASS다.

## WO-REUSE-02 — 기존 엔진의 재개와 무결성

목표: `src/umd/download/engine.py`에 완료 조건을 추가한다. 엔진을 교체하지 않는다.

구현:

- 강한 ETag만 If-Range에 쓴다. 약한 ETag는 검증자로 쓰지 않는다.
- 206이면 Content-Range 시작이 로컬 바이트 수와 같아야 한다. 아니면 부분 파일을 남기지 않고 실패한다.
- 검증자가 있는데 응답이 200이면 부분 파일에 이어 붙이지 않고 덮어쓴다.
- 416이면 부분 파일과 재개 상태를 지우고 처음부터 한 번만 다시 받는다. 무한 반복하지 않는다.
- Content-Length 또는 Content-Range 총길이와 받은 바이트가 다르면 완료로 기록하지 않는다. 타임아웃과 WinError 10054를 잘림으로 바꾸지 않는다.
- 호출자가 해시를 준 경우에만 SHA-256을 비교한다. 해시가 없으면 크기 계약만 적용한다.
- 취소로 닫힌 소켓의 오류를 잘림으로 기록하지 않는다. S4 동작을 유지한다.

하지 말 것:

- `requests`를 추가하지 않는다.
- Booru 스케줄러와 워커를 가져오지 않는다.
- `download_one()`의 재시도를 늘리지 않는다.

완료 조건:

- 206 일치, 200 덮어쓰기, 416 1회, 짧은 본문, 해시 불일치, 취소가 자동 테스트로 통과한다.
- S4의 EOF 계약, RST, 조기 종료 분류, 종료 대기 테스트가 유지된다.
- 같은 환경에서 엔진 교체의 속도 비교는 하지 않는다. 이 작업은 규칙 추가다.

예상: 3~5일. WO-REUSE-01 다음.

## WO-REUSE-03 — 한 항목의 완료는 한 번

목표: 파일이 계약과 맞지 않으면 `완료`를 쓰지 않는다. 같은 항목이 완료 행을 두 개 만들지 않는다.

구현:

- 영상과 이미지 완료 전에 최종 경로의 크기가 기대한 크기와 같은지 확인한다. 기대한 크기가 없으면 파일이 비어 있지 않은지만 보고, 그 사실을 보고서에 적는다.
- 최종 경로가 이미 있고 이번 전송의 스테이징 파일이 아니면 덮어쓰지 않는다. 기존 파일을 이번 항목의 완료로 기록하지 않는다.
- 같은 `item_id`는 기존 행을 갱신한다. 완료를 이유로 행을 추가하지 않는다.
- 갤러리의 “이미 저장된 파일”은 완료로 두되, 그 경로의 크기가 0이면 완료로 두지 않는다.

하지 말 것:

- Booru 스키마로 SQLite를 바꾸지 않는다.
- 다른 잡에 있는 같은 영상을 자동으로 합치지 않는다. 그것은 별도 제품 결정이다.

완료 조건:

- 같은 항목을 두 번 끝내도 `media_items` 행 수가 늘지 않는다.
- 빈 파일과 길이 불일치는 `완료`가 아니다.
- 기존 파일 바이트가 두 번째 완료 시도에서 바뀌지 않는다.

예상: 2~3일. WO-REUSE-02 다음.

## WO-REUSE-04 — 시크릿 미디어는 관리 경로에 유지

목표: 서명 쿼리, Cookie, Authorization이 필요한 미디어 URL과 HLS·DASH 매니페스트를 httpx 단건 다운로드로 내리지 않는다.

구현:

- 추출 결과가 그런 URL이면 `delivery`를 일반 HTTP로 만들지 않는다.
- 영상은 지금처럼 페이지 URL을 yt-dlp에 다시 넘긴다.
- 갤러리의 안전하지 않은 항목은 실패로 보이고, 서명 URL을 SQLite에 쓰지 않는다.
- 재생목록은 계속 거부한다. 자막 파일 저장과 재생목록 지원을 이 작업에 넣지 않는다.

완료 조건:

- 시크릿 쿼리와 `m3u8`, `dash` 프로토콜이 이미지 엔진 항목이 되지 않는다.
- 기존 단일 영상과 갤러리 선택 저장 테스트가 유지된다.

예상: 2~3일. WO-REUSE-01과 병행할 수 있다. 02의 완료 판정보다 앞서 끝내도 된다.

## WO-REUSE-05 — 의존성 고정

목표: 선언 버전을 해시로 고정할 수 있는지 적고, 소유자 결정이 필요한 부분은 코드로 추측하지 않는다.

구현:

- yt-dlp와 gallery-dl의 현재 설치 버전과 파일 해시를 보고서 초안에 적는다. 2026.08.19로 내리지 않는다.
- 프로젝트 LICENSE는 소유자가 문구를 주기 전에는 추가하지 않는다.
- Booru 파일 복사가 필요해 보이면 멈추고 허가 문구가 없다고 보고서에 적는다.

예상: 1일. 기능 코드와 분리한다.

## 시작하지 않음

다음은 `WO-REUSE-00-REPORT.md`의 DEFER다. 이 지시서의 01~05가 끝나도 자동으로 시작하지 않는다.

- Booru 워커 프로세스와 QLocal을 UMD 셸에 넣기
- FFmpeg 어댑터를 제품에 넣기
- 스케줄러를 Booru 구현으로 바꾸기
- SQLite 스키마를 Booru 스키마로 바꾸기
- 업데이터, 매니페스트 서명, 롤백 실행
- 다운로드 엔진 교체. 같은 기계, 같은 파일, 같은 동시성에서의 측정이 더 나은 안정성이나 시간을 보여 주기 전에는 하지 않는다.

## 보고

각 WO는 `docs/WO-REUSE-0N-REPORT.md`를 남긴다. 테스트 통과와 릴리스 GO를 한 문장으로 합치지 않는다. CI를 돌리면 `workflow_dispatch`만 사용하고, 실행된 `headSha`를 적는다. 기록 커밋의 SHA를 구현 SHA로 적지 않는다.

WO-REUSE-01 보고서는 추가 필수 검증 8개를 각각 PASS, FAIL, NOT RUN으로 적는다. 테스트를 실행하지 않은 조건, 모의 객체만으로 대신한 ACL, 본 데이터베이스 결과만으로 넘긴 WAL·백업은 PASS가 아니다. 이 지시서의 수정만으로는 어떤 조건도 PASS가 아니다.
