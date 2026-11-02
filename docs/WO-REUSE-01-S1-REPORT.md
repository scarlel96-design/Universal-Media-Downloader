# WO-REUSE-01-S1 결과 보고

작업일: 2026-11-02

작업명: 비밀 URL 참조 수명주기 보완 및 비정상 종료 후 정리

개발 도구: Grok Build

공식 저장소: https://github.com/scarlel96-design/Universal-Media-Downloader

대상 PR: https://github.com/scarlel96-design/Universal-Media-Downloader/pull/4

PR 상태: OPEN. 이 작업에서 PR #4와 PR #5를 병합하지 않았다.

기준 브랜치: `feat/wo04-browser-extraction`

환경: 로컬 Windows, Python 3.12.10, pytest 9.2.0. 저장소 밖 가상환경에 `PYTHONPATH=src`. Qt 테스트는 `QT_QPA_PLATFORM=offscreen`. CI 결과와 로컬 결과를 같은 PASS로 적지 않는다.

WO-REUSE-01의 기능 안정화 GO 기록은 바꾸지 않았다. 이 판정은 S1만 다룬다.

기능 안정화: GO. 정식 출시: NO-GO. PR #4는 병합하지 않았다.

## 1. 기준 HEAD 및 구현 커밋

작업 시작 HEAD: `c57f76c4dcc244a3b525169de413e2005a7c0500`

작업 트리는 깨끗했다. 그 위에 다른 작업의 변경은 없었다.

WO-REUSE-01 구현 커밋: `ba077d667099b73567bd1f4c8e60679724596c6a`

S1 구현 커밋: `a046199a81da163610f8063fcbbaba0465a99912`

기록 커밋이 이 보고서만 추가하면, GitHub Actions가 실행한 SHA는 구현 커밋이다. 기록 커밋은 실행 SHA가 아니다.

## 2. 수정한 파일

- `src/umd/secrets.py`
- `src/umd/storage/database.py`
- `src/umd/net/isolated.py`
- `tests/unit/test_wo_reuse_01_lifecycle.py` 추가

바꾸지 않은 경로: 다운로드 엔진, `download_one()`, `netpolicy.py`, `child.py`, `jobs.py`, `shell.py`, 스키마 버전 3, WO-REUSE-01 보고서, Booru Studio. WO-REUSE-02와 WO-REUSE-03은 시작하지 않았다.

## 3. jobs.secret_ref 정리 방식

작업 상태가 `완료`, `취소`, `실패`이고, 항목 중에 `일시정지`, `다운로드 중`, `대기`, `재인증 필요`가 없을 때만 페이지 참조를 지운다.

`추출 완료`, `추출 중`, `일시정지`, `다운로드 중`, `대기`, `재인증 필요`는 페이지 참조를 유지한다.

허용된 경우에는 완료·취소 항목의 참조 파일을 먼저 지우고, 이어서 작업 참조 파일을 지운다. 파일이 실제로 없어진 뒤에만 SQLite `secret_ref`를 비우고 commit한다. 삭제가 실패하면 SQL을 비우지 않고 `작업 참조를 지우지 못했습니다`를 올린다. 실패를 성공으로 적지 않는다.

같은 정리를 다시 호출하면 참조가 이미 없으므로 오류 없이 끝난다.

## 4. outbound 참조 만료 정리 방식

`SecretVault.sweep_expired_outbound()`는 한 번에 최대 64개 항목만 본다. 하위 디렉터리를 재귀 탐색하지 않는다.

지우는 파일은 이름이 32자리 hex JSON이고, vault 루트 안에 있으며, symlink나 reparse point가 아니고, `job_id`가 `outbound`이며, `expires_at`이 숫자이고, 현재 시각이 그 시각 이상이며, 이 프로세스가 사용 중으로 표시하지 않은 참조뿐이다.

`expires_at`이 null인 작업·항목 참조, 다른 작업의 파일, 확인되지 않은 JSON, 다른 디렉터리의 파일은 만료 시간만으로 지우지 않는다. 기본 만료는 3600초다. 테스트는 시계를 주입하고 이 값을 줄이지 않았다.

호출 시점: vault를 만들 때, outbound 참조를 만들기 전과 후, 자식 프로세스가 끝난 뒤 `isolated.call`의 정리, 다음 `Library` 시작 때 vault가 다시 만들어질 때.

## 5. 정상 완료, 실패, 취소, 일시정지 정책

- 완료: 재개 항목이 없으면 작업 참조와 완료 항목 참조를 제거한다. 작업 ID와 항목 ID는 유지한다.
- 사용자 취소: 재개가 필요 없는 참조만 제거한다. 일시정지된 다른 작업의 참조는 남긴다. 취소된 항목 행은 남긴다.
- 최종 실패: 재인증이나 재개 항목이 없을 때만 작업 참조를 제거한다. 항목이 `재인증 필요`이면 작업 참조를 유지한다.
- 일시정지: 작업 참조와 항목 참조를 유지한다. 다시 열면 원문 URL을 읽는다.

## 6. 비정상 종료 복구 결과

데이터베이스를 열 때 작업 참조를 다시 검사한다.

- 파일이 없고 작업이 재개 상태이면 상태를 `재인증 필요`로 두고 `secret_ref`만 비운다. ID는 바꾸지 않는다.
- 파일이 없고 작업이 이미 `완료` 또는 `취소`이면 상태 없이 빈 참조만 지운다.
- SQL은 비웠는데 파일만 남은 완료 작업의 참조는, 그 작업 소유가 확인된 경우에만 지운다.
- 이전 프로세스가 남긴 만료 outbound 파일은 새 vault가 만들어질 때 지워진다. 만료가 없는 작업 참조와 사용자 파일은 남는다.

확인되지 않은 파일은 일괄 삭제하지 않는다.

## 7. 경합 및 중복 정리 결과

같은 작업 완료 정리를 두 번 호출했다. 두 번째는 오류 없이 끝났고, 다른 작업의 참조와 `notes.json`은 그대로였다.

삭제를 한 번 실패하게 한 뒤에도 `secret_ref`와 파일은 남았다. 상태만 `완료`로 기록됐다. 실패를 성공으로 처리하지 않았다. 이어서 다시 정리하면 파일과 SQL이 함께 비워진다.

만료 정리 함수를 스레드 8개에서 동시에 두 번씩 호출했다. 예외는 없었다. 일시정지 작업의 참조는 남았다.

만료 정리, 중복 정리, 재시작 복구 테스트 3개를 15회 반복했다. 실패는 0회다.

## 8. 신규 테스트 9개

파일: `tests/unit/test_wo_reuse_01_lifecycle.py`

| 테스트 | 판정 |
| --- | --- |
| `test_completed_job_releases_page_secret` | PASS |
| `test_cancelled_job_releases_page_secret` | PASS |
| `test_paused_job_retains_required_secret` | PASS |
| `test_expired_outbound_refs_are_removed` | PASS |
| `test_cleanup_preserves_active_refs` | PASS |
| `test_orphan_refs_recovered_after_restart` | PASS |
| `test_cleanup_is_idempotent` | PASS |
| `test_job_ref_recovery_after_interrupted_cleanup` | PASS |
| `test_cleanup_logs_contain_no_secrets` | PASS |

첫 실행: `9 passed in 1.93s`. FAIL 0, SKIP 0.

## 9. 기존 전체 테스트 결과

명령: `python -m pytest -o addopts= --ignore=tests/unit/test_wo02_load.py --ignore=tests/live`

결과: `145 passed in 74.76s`. 프로세스 벽시계 76.44초. 종료 코드 0. FAIL 0, SKIP 0.

WO-REUSE-01의 136건은 그대로 포함된다. 추가된 9건이 145건이다. 기존 테스트 파일은 수정하지 않았다.

`tests/live`는 실행하지 않았다. PASS로 적지 않는다.

같은 145건 안에 Windows ACL, SQLite 비밀 제거, 자식 stdout·stderr, v1–v3 마이그레이션, `재인증 필요`, 쿠키 세션, Range·ETag, EOF, TCP RST, 취소, S4 종료 3건이 들어 있다.

## 10. Windows ACL 회귀 결과

`test_secret_is_not_written_when_acl_check_fails`와 `test_failed_acl_does_not_keep_the_session`, `test_cookie_scope_expiry_and_leftover_files`는 145건 실행에 포함되어 통과했다. ACL 순서를 바꾸지 않았다. 비밀 파일은 접근 권한 확인 뒤에만 쓴다.

## 11. 5,000장 부하 검증

로컬 1회 실행했다. CI 부하 잡은 실행하지 않는다.

명령: `python -m pytest -o addopts= -s tests/unit/test_wo02_load.py`

pytest: `1 passed in 156.46s`. 프로세스 벽시계 158.02초. 종료 코드 0.

`WO02_METRICS`:

- bulk files 5000, elapsed_s 147.08, peak_connections 3, server_peak 3
- working_set_before 48263168, working_set_peak 103882752, integrity_mismatches 0
- large_file_bytes 6291526, large_file_traced_bytes 835881
- sequential elapsed_s 4.23, completed 80, server_peak 1
- parallel elapsed_s 2.43, completed 80, server_peak 3

147.08초는 5,000장 구간이다. 156.46초는 pytest 전체다. WO-REUSE-01의 147.57초, 156.97초와 섞지 않는다. 로컬 픽스처이며 인터넷 속도가 아니다.

## 12. GitHub Actions

저장소는 public이다. `workflow_dispatch`만 사용했다. `runs-on`은 `windows-latest`다. `inputs.load`는 넘기지 않았다. CI 부하 잡은 NOT RUN이다.

실행 URL: https://github.com/scarlel96-design/Universal-Media-Downloader/actions/runs/41395696876

이벤트: `workflow_dispatch`

실행 SHA: `a046199a81da163610f8063fcbbaba0465a99912`

checkout 로그가 이 SHA를 fetch했다.

test 잡: success. 잡 URL: https://github.com/scarlel96-design/Universal-Media-Downloader/actions/runs/41395696876/job/125116429308

`Regression and WO-03 tests` 로그: `145 passed in 100.56s (0:01:40)`

load 잡: skipped. CI 부하 테스트는 NOT RUN이다. 로컬 147.08초와 섞지 않는다.

## 13. 비밀정보 잔존 위험

- 일시정지, 재인증, 진행 중 작업의 참조 파일에는 원문 URL이 남아 있다. 재개에 필요해서 남긴다.
- 만료 전 outbound 참조도 최대 3600초 동안 ACL 디렉터리에 남는다.
- 한 번의 정리는 64개까지만 본다. 그보다 많은 만료 파일은 다음 호출에서 이어서 지운다.
- 다른 프로세스가 만든 만료 참조는 그 프로세스의 활성 목록을 보지 못한다. 3600초가 지나기 전에는 지우지 않는다. 제품 자식 프로세스 제한시간은 180초다.
- SQLite `UPDATE`가 옛 페이지의 바이트를 지운다고 보지 않는다. 이번 작업은 VACUUM을 하지 않았다. WO-REUSE-01에서 본 파일 잔존은 그대로다.
- 사용자 백업은 열거나 지우지 않았다.
- 로그에는 참조 ID와 건수만 남긴다. 시험 토큰, Cookie, Authorization, 서명 URL은 로그와 예외에 없었다.
- Windows 실데스크톱 UI와 프로젝트 LICENSE 없음은 닫히지 않았다.

새로 확인한 P0는 없다.

## 14. 롤백 및 복구 절차

S1 구현 커밋 `a046199`을 revert한다. 이미 이 빌드로 비운 `secret_ref`와 지운 참조 파일은 revert만으로 돌아오지 않는다. 재개가 필요한 작업은 참조 파일이 남아 있는 동안 이전 빌드에서도 읽을 수 있다. 이미 지운 완료·취소 작업의 원문은 사용자 백업에만 있을 수 있다. 이번 검증은 임시 데이터베이스만 열었다. 사용자 백업은 건드리지 않았다.

`{데이터베이스}.secrets`에 남은 파일은 revert가 지우지 않는다. 소유자가 직접 처리한다.

## 15. 최종 GO/NO-GO 판정

기능 안정화: GO.

신규 9건 PASS, 로컬 단위 테스트 `145 passed in 74.76s`로 FAIL 0, 기존 136건 유지, 완료·취소 작업의 불필요한 참조 제거, 만료 outbound 정리, 활성 참조 유지, 일시정지 참조 유지, 중복 정리, 비정상 종료 복구, ID 유지, 로그 비밀 0건, ACL과 S4 종료 유지를 충족했다. Actions test 잡도 같은 구현 SHA에서 `145 passed in 100.56s`로 성공했다.

정식 출시: NO-GO. Windows 실환경 UI와 프로젝트 LICENSE 부재는 그대로다. 기능 안정화 GO가 정식 출시 GO는 아니다. PR #4는 열린 상태다. WO-REUSE-01 보고서의 GO 기록은 수정하지 않았다.

WO-REUSE-02는 이 보고서가 원격 브랜치에 올라간 뒤에만 검토한다. 이 작업에서 착수하지 않았다.
