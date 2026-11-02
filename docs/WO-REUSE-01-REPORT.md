# WO-REUSE-01 결과 보고

작업일: 2026-11-02

작업명: 영속 비밀정보 제거 및 안전한 재개 체계

개발 도구: Grok Build

공식 저장소: https://github.com/scarlel96-design/Universal-Media-Downloader

대상 PR: https://github.com/scarlel96-design/Universal-Media-Downloader/pull/4

PR 상태: OPEN. 이 작업에서 PR #4와 PR #5를 병합하지 않았다.

기준 브랜치: `feat/wo04-browser-extraction`

환경: 로컬 Windows, Python 3.12.10, pytest 9.2.0. 저장소 밖 가상환경에 `PYTHONPATH=src`. Qt 테스트는 `QT_QPA_PLATFORM=offscreen`. CI 결과와 로컬 결과를 같은 PASS로 적지 않는다.

기능 안정화: GO. 정식 출시: NO-GO. PR #4는 병합하지 않았다.

## 1. 기준 커밋과 구현 커밋

기준 HEAD: `dbff825d6c5c1ec2b71967ae123b803ce3d4074a`

구현 커밋: `ba077d667099b73567bd1f4c8e60679724596c6a`

구현 커밋의 부모는 기준 HEAD다. 기준 커밋 이후 다른 작업의 커밋은 없었다. 이 커밋을 수정하거나 이력을 다시 쓰지 않았다.

기록 커밋이 이 보고서만 추가하면, GitHub Actions가 실행한 SHA는 구현 커밋이다. 기록 커밋은 실행 SHA가 아니다.

## 2. 수정한 제품 파일

- `src/umd/auth/session.py`
- `src/umd/storage/database.py`
- `src/umd/net/child.py`
- `src/umd/net/isolated.py`
- `src/umd/extract/video.py`
- `src/umd/app/jobs.py`
- `src/umd/app/shell.py`

바꾸지 않은 제품 경로: `src/umd/download/engine.py`, `src/umd/download/images.py`의 `download_one()`, `src/umd/netpolicy.py`, gallery-dl과 yt-dlp의 역할, QThread 강제 종료 금지, 스키마 버전 3, 재생목록 미지원, 프로젝트 라이선스 파일. Booru Studio 저장소는 읽지 않은 채로 두었고 복사하지 않았다. WO-REUSE-02부터 WO-REUSE-05는 시작하지 않았다.

## 3. 새로 추가한 보안 모듈

`src/umd/secrets.py`

이 모듈은 비밀 URL의 참조 저장, 경로의 reparse 검사, 디렉터리 ACL, 부분 파일 기록, 문자열 정리다. 다운로드 엔진을 대체하지 않는다.

## 4. 실제 비밀정보 저장 구조

SQLite에 남는 URL은 userinfo, query, fragment를 뺀 주소다. 쿼리 키 허용 목록은 없다. 항목 ID와 작업 ID는 그대로다. 정리된 URL이 같아도 행을 합치지 않는다.

전송에 필요한 원문은 SQLite 옆의 `{데이터베이스 경로}.secrets` 디렉터리에 있다. 메모리 데이터베이스는 임시 디렉터리를 쓴다. 파일 이름은 `{32자리 hex}.json`이다. 참조 ID에는 URL, Cookie, Authorization, 토큰을 넣지 않는다. JSON 필드는 `job_id`, `item_id`, `urls`, `expires_at`다.

기록 순서:

1. 경로를 정한다.
2. 상위 경로의 symlink와 Windows reparse point를 거부한다.
3. 디렉터리를 만든다.
4. 현재 사용자, SYSTEM(`S-1-5-18`), Administrators(`S-1-5-32-544`)에 `(OI)(CI)F`를 준다.
5. `icacls` 출력에서 사용자 ACE와 SYSTEM ACE를 확인한다.
6. 확인에 성공한 뒤에만 `.이름.partial`을 쓰고 `os.replace`로 최종 이름을 만든다.
7. 확인에 실패하면 비밀 파일을 만들지 않는다. 이번 호출이 만든 빈 디렉터리만 지운다. 이미 참조가 있는 vault는 지우지 않는다.

세션 쿠키도 같은 `protect_directory`와 `write_private`를 쓴다. 쿠키 파일은 호스트별 디렉터리의 `state.json`과 `expires`다. SQLite에 쿠키를 넣지 않는다. 비밀을 명령줄 인자나 환경변수에 넣지 않는다.

스키마 버전은 3이다. `jobs.secret_ref`와 `media_items.secret_ref`는 기존 데이터베이스에 `ALTER TABLE`로 추가한다. 기본값은 빈 문자열이다.

## 5. URL 참조 생성, 읽기, 삭제

생성: 비밀이 있는 URL만 vault에 넣는다. 작업 페이지는 `jobs.secret_ref`, 항목은 `media_items.secret_ref`에 연결한다. 자식 프로세스에 넘기는 비밀 URL은 `umdref://{ref}`로 바꾸고, 그 참조의 작업 ID는 `outbound`, 만료는 3600초다.

읽기: 이름이 32자리 hex가 아니거나, 상위 디렉터리가 vault 루트가 아니거나, reparse point이거나, 작업 ID 또는 항목 ID가 다르거나, 만료 시각이 지났으면 `SecretUnavailable`이다. 다른 작업의 URL을 반환하지 않는다. 참조가 없으면 원문을 추측하지 않는다.

삭제:

- 완료, 사용자 취소, 최종 실패, 재인증 필요: 참조 파일을 지우고 `secret_ref`를 비운다.
- 비밀이 남아 있는 항목의 실패는 저장 전에 `재인증 필요`로 올린 뒤 참조를 지운다. 서명 없는 실패는 `실패`로 남는다.
- 일시정지, 다운로드 중, 대기: 참조를 유지한다.
- 자식 프로세스가 끝나면 부모가 outbound 참조를 지운다.

정상 추출 결과의 비밀 URL은 stdout에 그대로 나가지 않는다. 자식이 참조로 바꾸고, 부모가 결과를 메모리로 복원한 뒤 그 참조를 지운다. 복원된 주소만 이후 저장과 전송에 쓴다. SQLite에 다시 넣을 때는 정리된 주소와 새 항목 참조로 나뉜다.

## 6. SQLite 마이그레이션 결과

v1, v2, v3 파일을 `Library`로 열었다. 구조 마이그레이션 뒤 같은 트랜잭션에서 문자열 컬럼을 정리한다. 실패하면 rollback하고 예외를 올린다. 손상된 파일을 정상 버전으로 보고하지 않는다.

마이그레이션은 비밀을 vault로 복사하지 않는다. 행 수, 항목 ID, 작업 ID는 유지한다. `완료`와 `취소`는 상태를 유지하고 쿼리만 잃는다. 그 밖의 상태에서 URL 컬럼이 바뀌면 `재인증 필요`가 된다.

검사한 문자열 컬럼은 `jobs.page_url`, `media_items`의 `page_url`, `media_url`, `original_url`, `thumbnail_url`, `media_reference`, `error`, `note`, `reasons`, `title`, `subtitles`, `format`, `classification`, `saved_path`, `part_path`, `host_status.host`, 그리고 각 테이블의 다른 TEXT 컬럼이다. `id`, `job_id`, `secret_ref`는 대상이 아니다.

테스트 3개 버전 모두 스키마 3, 행 1, 같은 항목 ID와 작업 ID, 논리 덤프에 시험 토큰 없음, 상태 `재인증 필요`였다.

## 7. 재시작 및 재인증 동작

데이터베이스를 열 때 `secret_ref`가 있으면 vault를 읽는다.

- 참조가 유효하면 기존 상태를 유지한다. 일시정지는 일시정지로 남고, 전송 주소는 메모리에서 원문을 반환한다. Range와 ETag 정책은 엔진 그대로다.
- 참조가 없거나 만료되면 자동으로 재개하지 않는다. `download_status`는 `재인증 필요`이고, `completed_at`을 완료 시각으로 채우지 않는다. 노트는 `보호된 주소를 다시 열지 못했습니다`다.
- `완료`와 `취소`에 남은 참조 파일만 제거하고 상태는 바꾸지 않는다.
- 작업 상태에 `재인증 필요` 항목이 있고 다운로드 중, 일시정지, 대기가 없으면 작업 상태도 `재인증 필요`다.
- 셸은 이 항목을 다운로드 대상에서 뺀다. 선택 항목이 이 상태뿐이면 `다시 인증해야 받을 수 있습니다.`를 알리고 phase를 `재인증 필요`로 둔다. 다운로드가 끝나면 `실패`보다 `재인증 필요`를 먼저 표시한다.
- `retryFailed`는 상태가 `실패`인 행만 고른다. `재인증 필요`는 사용자가 다시 인증하거나 주소를 준 뒤에만 다시 시도한다.

이 상태를 완료, 실패, 취소, 일시정지, 다운로드 중으로 저장하지 않는다.

## 8. 자식 프로세스 출력 검증

실제 명령은 `python -m umd.net.child`다. stdin은 JSON이다. stdout과 stderr를 모두 캡처했다.

실패 경로: `video-extract`에 `http://127.0.0.1/watch?sig={TOKEN}`와 고유 Cookie, Authorization을 넣었다. 정책이 내부 주소를 거부한다. 예외 문자열은 원문 요청을 붙인 뒤 정리한다. 정리에 실패하면 `작업을 완료하지 못했습니다`만 낸다. stdout과 stderr, JSON의 `error`와 `trace`에 TOKEN, COOKIE, AUTH가 없었다. `ok`는 false였다.

성공 경로: 선택이 비어 있는 `gallery-download`에 같은 비밀을 넣었다. 네트워크를 열기 전에 빈 배치를 반환한다. stdout과 stderr에 세 시험 문자열이 없었다. `ok`는 true이고 `files`는 빈 목록이었다.

결과 봉인: 성공 JSON의 비밀 URL은 `umdref://`로 바뀐다. 시험 토큰은 stdout에 없고, `materialize_payload`가 메모리에서 원문을 복원했다. 쿼리가 없는 URL은 그대로다.

부모 `isolated.call`은 자식 stdout과 stderr에 요청 비밀이나 서명 URL이 남아 있으면 원문을 예외에 넣지 않고 `격리 프로세스가 실패했습니다`를 올린다.

## 9. Windows ACL 실검증

`test_secret_is_not_written_when_acl_check_fails`가 `umd.auth.session.subprocess.run`을 반환 코드 1로 바꿨다. 세션 저장과 vault 기록 모두 비밀 파일을 만들지 않았다. `files.example` 디렉터리는 없었다. 실패를 파일 삭제만으로 성공 처리하지 않는다.

같은 테스트가 monkeypatch를 푼 뒤 실제 `icacls`를 실행했다. 출력에 현재 `USERNAME`의 mbcs 바이트, `(OI)(CI)(F)`, `SYSTEM` 또는 `S-1-5-18`이 있어야 한다. 이 단언은 통과했다.

추가로 일회용 세션 디렉터리를 만들어 `icacls` 원문을 확인했다. 쿠키 값은 `1`이다.

```
BUILTIN\Administrators:(OI)(CI)(F)
NT AUTHORITY\SYSTEM:(OI)(CI)(F)
서브컴퓨터\scarl:(OI)(CI)(F)
```

상속 ACE는 보이지 않았다. SYSTEM과 Administrators를 무조건 빼지 않았고, 현재 사용자에게 `(OI)(CI)(F)`가 있다.

## 10. WAL 및 백업 검증 범위

새로 만든 데이터베이스에서 `durability_scope()` 결과:

- `journal_mode`: `delete`
- `wal`: false
- `shm`: false
- `physical_delete`: false

`-wal` 파일과 `-shm` 파일은 만들어지지 않았다. 이 빌드는 `PRAGMA journal_mode=WAL`을 설정하지 않는다. 과거에 WAL로 바꿔 둔 외부 파일은 이 검증의 대상이 아니다.

통제된 테스트 백업: 비밀이 들어 있는 v3 파일을 연 뒤가 아니라 열기 전에 `library-backup.sqlite`로 복사했다. 논리 행에서는 시험 토큰이 사라졌다. 백업 파일의 바이트에는 토큰이 남아 있다. 라이브 `library.sqlite`의 원시 바이트에도 토큰이 남아 있다. `UPDATE`가 옛 페이지를 지운다고 보지 않는다. VACUUM을 실행하지 않았고, 물리적 완전 삭제를 주장하지 않는다.

사용자의 기존 백업은 열지 않았고 지우거나 덮어쓰지 않았다. 검증한 범위는 이 테스트가 만든 백업과 그 실행의 라이브 파일뿐이다.

## 11. 필수 8개 조건

조건 8의 기존 테스트 파일은 수정하지 않았다.

| 조건 | 테스트 | 판정 |
| --- | --- | --- |
| 1. ACL 실패 시 비밀 파일을 만들지 않음. 실제 icacls 포함 | `test_secret_is_not_written_when_acl_check_fails` | PASS |
| 2. SQLite 논리 값, 임시 파일, 로그에 서명 쿼리 없음 | `test_signed_query_is_absent_from_sqlite_and_other_stores` | PASS |
| 3. 쿼리만 다른 두 항목의 ID와 작업 관계 유지 | `test_distinct_signed_items_keep_separate_ids` | PASS |
| 4. 유효한 참조는 재개, 없는 참조는 `재인증 필요` | `test_restart_reauth_when_signed_url_cannot_be_restored` | PASS |
| 5. 실제 자식 stdout, stderr, 예외에 비밀 없음 | `test_child_stdio_and_exceptions_omit_secrets` | PASS |
| 6. v1, v2, v3 행 수와 작업 연결 유지, 비밀 제거 | `test_migration_keeps_job_item_links_while_removing_secrets` | PASS |
| 7. journal mode, WAL, SHM, 테스트 백업의 잔존 범위 | `test_wal_and_backup_scope_is_reported` | PASS |
| 8. 기존 쿠키, 재개, 종료 테스트 | 아래 목록 | PASS |

조건 8에 포함한 기존 테스트는 최종 단위 실행 안에 들어 있었고 실패가 없었다.

- `tests/unit/test_wo04s.py::test_cookie_scope_expiry_and_leftover_files`
- `tests/unit/test_wo04s.py::test_failed_acl_does_not_keep_the_session`
- `tests/unit/test_wo04_browser.py::test_sessions_stay_on_their_site_and_out_of_sqlite`
- `tests/unit/test_wo02_engine.py::test_range_resume_etag_change_and_non_resumable`
- `tests/unit/test_wo02_engine.py::test_cancel_and_pause_resume`
- `tests/unit/test_wo02_engine.py::test_restart_reconciles_a_finished_file_and_resumes_a_partial`
- `tests/unit/test_wo02_ui.py::test_ui_stays_responsive_and_pause_resumes`
- `tests/unit/test_wo04_s4_shutdown.py` 3건
- `tests/unit/test_wo01_download.py::test_eof_short_body_reports_truncation_and_keeps_no_file`
- `tests/unit/test_wo01_download.py::test_tcp_early_close_is_classified_on_the_same_socket`

같은 파일의 추가 테스트 2건도 통과했다. `test_child_success_stdout_omits_signed_url`, `test_signed_result_is_a_ref_on_stdout_and_restored_in_memory`.

## 12. 전체 회귀 테스트 결과

명령:

`python -m pytest -o addopts= --ignore=tests/unit/test_wo02_load.py --ignore=tests/live`

결과: `136 passed in 73.88s`. 프로세스 벽시계는 75.72초, 종료 코드 0.

기준 127건에서 9건이 늘었다. 필수 7건과 자식 성공, 결과 참조 왕복 2건이다. FAIL은 0건이다.

`tests/live`는 실행하지 않았다. 이 경로를 PASS로 적지 않는다.

단위 실행이 덮은 기존 동작: 일반 이미지 다운로드, 쿠키 범위, 갤러리 선택, 격리된 영상 및 갤러리 경로, 일시정지 후 재개, 재시작 재개, 취소, S4 종료 3건, EOF와 TCP RST. 고속 프리셋의 `hold * 4`(hold 0.45)와 제품 제한시간 30초는 바꾸지 않았다. Windows 실데스크톱 UI는 이 작업에서 실행하지 않았다.

## 13. 부하 테스트

로컬 1회 실행했다. CI 부하 잡은 실행하지 않았다.

명령: `python -m pytest -o addopts= -s tests/unit/test_wo02_load.py`

pytest: `1 passed in 156.97s`. 프로세스 벽시계는 158.80초, 종료 코드 0.

출력된 `WO02_METRICS` 한 줄:

- bulk files 5000, elapsed_s 147.57, peak_connections 3, server_peak 3
- working_set_before 48111616, working_set_peak 104841216, integrity_mismatches 0
- large_file_bytes 6291526, large_file_traced_bytes 855556
- sequential elapsed_s 4.099, completed 80, server_peak 1
- parallel elapsed_s 2.396, completed 80, server_peak 3

147.57초는 5,000장 전송 구간이다. 156.97초는 pytest 전체다. 이전 작업의 142.553, 146.161, 147.792, 152.51, 166.43과 섞지 않는다. 로컬 픽스처 결과이며 인터넷 속도가 아니다.

## 14. GitHub Actions

저장소는 public이다. workflow는 기존 `workflow_dispatch`만 사용했다. `runs-on`은 `windows-latest`다. 유료 러너로 바꾸지 않았다. `inputs.load`는 넘기지 않았다. CI의 5,000장 잡은 NOT RUN이다.

실행 URL: https://github.com/scarlel96-design/Universal-Media-Downloader/actions/runs/41391674036

이벤트: `workflow_dispatch`

실행 SHA: `ba077d667099b73567bd1f4c8e60679724596c6a`

checkout 로그가 이 SHA를 fetch했다. `ba077d667099b73567bd1f4c8e60679724596c6a`

test 잡: success. 잡 URL: https://github.com/scarlel96-design/Universal-Media-Downloader/actions/runs/41391674036/job/125104224713

`Regression and WO-03 tests` 로그의 마지막 결과: `136 passed in 66.46s (0:01:06)`

설치 로그: Playwright 1.64.1, Chrome for Testing 156.0.8078.4, Playwright chromium v1248. pytest 9.2.0, PySide6 6.12.0, gallery-dl 1.32.19, yt-dlp 2026.10.26.

load 잡: skipped. CI 부하 테스트는 NOT RUN이다. 로컬 부하 결과와 섞지 않는다.

## 15. 남아 있는 보안 위험

- 논리 행에서 비밀을 지운 뒤에도 SQLite 파일의 옛 페이지에 시험 토큰 바이트가 남았다. `journal_mode=delete`라서 이번 검증에는 WAL 파일이 없었다. 물리적 삭제는 보장하지 않는다.
- 열기 전에 만든 테스트 백업에는 비밀이 남아 있다. 사용자가 이미 가진 백업은 검사하지 않았고 삭제하지 않았다.
- 마이그레이션은 서명 URL을 vault로 옮기지 않는다. 진행 중 항목은 `재인증 필요`가 되고, 이전 원문은 복구하지 않는다.
- 자식이 outbound 참조를 만든 뒤 부모가 지우기 전에 죽으면, 그 파일은 최대 3600초 동안 ACL 디렉터리에 남는다. SQLite에는 없다.
- URL이나 Cookie, Authorization, 알려진 비밀 목록 밖에 있는 임의 토큰은 식별하지 못한다.
- 자식의 손자 프로세스가 파일 디스크립터 2에 직접 쓰면 캡처 래퍼를 지나칠 수 있다. 부모는 그 출력에 비밀이 있으면 원문을 반환하지 않고 실패로 처리한다.
- Windows 실데스크톱 UI와 프로젝트 `LICENSE` 없음은 이번 수정으로 닫히지 않는다.

새로 확인한 P0는 없다. 위 항목은 검증 범위와 잔존 한계다.

## 16. 변경한 파일과 롤백

구현 커밋 `ba077d6`의 파일:

- `src/umd/secrets.py` 추가
- `src/umd/auth/session.py`
- `src/umd/storage/database.py`
- `src/umd/net/child.py`
- `src/umd/net/isolated.py`
- `src/umd/extract/video.py`
- `src/umd/app/jobs.py`
- `src/umd/app/shell.py`
- `tests/unit/test_wo_reuse_01_secrets.py` 추가

롤백은 그 커밋을 revert한다. 이미 이 빌드로 연 데이터베이스의 잘린 URL은 revert만으로 돌아오지 않는다. 이번 검증은 임시 테스트 데이터베이스만 열었다. `{데이터베이스}.secrets`와 세션 디렉터리는 revert가 지우지 않는다. 소유자가 직접 지운다. 사용자 백업은 건드리지 않았다.

## 17. 기능 안정화 판정

기능 안정화: GO.

로컬 필수 조건 1–8, Windows ACL, 논리 SQLite와 자식 출력의 시험 비밀 0건, 작업 및 항목 연결 손상 0건, 참조 복구와 만료, S4 취소 및 종료, 단위 테스트 FAIL 0, WAL 및 백업 범위의 명시를 충족했다. Actions test 잡도 같은 구현 SHA에서 `136 passed in 66.46s`로 성공했다.

정식 출시: NO-GO. Windows 실환경 UI와 프로젝트 LICENSE 부재는 별도 출시 차단으로 유지한다. 기능 안정화 GO가 정식 출시 GO는 아니다. PR #4는 열린 상태다.

WO-REUSE-02는 이 보고서가 원격 브랜치에 올라간 뒤에만 검토한다. 이 작업에서 착수하지 않았다.
