# WO-REUSE-01-S2 결과 보고

작업일: 2026-11-02

작업명: SecretVault 정리 누락 방지 및 대량 참조 안정화

개발 도구: Grok Build

공식 저장소: https://github.com/scarlel96-design/Universal-Media-Downloader

대상 PR: https://github.com/scarlel96-design/Universal-Media-Downloader/pull/4

PR 상태: OPEN. 이 작업에서 PR #4와 PR #5를 병합하지 않았다.

기준 브랜치: `feat/wo04-browser-extraction`

환경: 로컬 Windows, Python 3.12.10, pytest 9.2.0. 저장소 밖 가상환경에 `PYTHONPATH=src`. Qt 테스트는 `QT_QPA_PLATFORM=offscreen`. CI 결과와 로컬 결과를 같은 PASS로 적지 않는다.

WO-REUSE-01과 WO-REUSE-01-S1 보고서는 수정하지 않았다. S1의 기능 안정화 GO와 이 판정은 별개다.

기능 안정화: PARTIAL. 정식 출시: NO-GO. PR #4는 병합하지 않았다.

GO가 아닌 이유: 로컬 전체 단위 테스트가 FAIL 0이 아니다. 실패한 2건은 병렬 프리셋 시간 검사이고, 같은 검사는 수정 전 `secrets.py`에서도 실패했다. 다운로드 엔진은 바꾸지 않았다. 1.8초 한도는 올리지 않았다. Actions 로그는 14절에서 구현 커밋과 대조한다.

## 1. 기준 HEAD

작업 시작 HEAD: `7deab72cc9dc83ed8fb93fcea7e560583d6261d2`

이 커밋은 S1 기록 커밋이다. S1 Actions가 실행한 SHA는 `a046199a81da163610f8063fcbbaba0465a99912`이고, 이 보고서의 기준 HEAD가 아니다.

시작 시 작업 트리는 깨끗했고 `origin/feat/wo04-browser-extraction`와 같았다. 그 위에 다른 작업의 변경은 없었다. 기존 커밋은 고치거나 덮어쓰지 않았다.

## 2. 구현 커밋

S2 구현 커밋: `b90b3dfd7499fc78fb8d2ced707f7b2693a13e64`

메시지: Advance the outbound sweep past the first 64 names.

바꾼 파일:

- `src/umd/secrets.py`
- `tests/unit/test_wo_reuse_01_s2_sweep.py` 추가

`download_one()`, HTTPX 엔진, 영상 엔진, Booru Studio, 네트워크 정책, SQLite 스키마, 재생목록 정책, FFmpeg, LICENSE는 바꾸지 않았다. WO-REUSE-02는 시작하지 않았다. 새 외부 의존성은 없다.

이 보고서를 나중에 기록 커밋으로 올리면, Actions가 실행한 SHA는 구현 커밋이다. 기록 커밋은 실행 SHA가 아니다.

## 3. 기존 결함의 재현 결과

S1 보고서 13절은 "한 번의 정리는 64개까지만 본다. 그보다 많은 만료 파일은 다음 호출에서 이어서 지운다."라고 적었다. `7deab72`의 `sweep_expired_outbound()`는 `iterdir()` 순서로 64개 디렉터리 항목을 본 뒤 멈췄고, 다음 위치를 저장하지 않았다. 그 문장은 그 코드로는 보장되지 않았다. S1 보고서 파일은 그대로 두었다.

수정 전 `secrets.py`로 다시 실행했다. 시계는 `10_000_000`. 만료되지 않은 outbound JSON 70개를 먼저 만들고, 그 다음 만료 참조 `f` 32자를 만들었다.

결과:

- `REMOVED 0 0 0`
- `EXPIRED_STILL True`
- `FILE_COUNT 71`
- 임시 디렉터리: `C:\Users\scarl\AppData\Local\Temp\umd-s2-repro-g_7o7sd8`

세 번 모두 삭제 0건이었고 만료 파일은 남았다. 이어서 지운다는 S1 설명은 재현에서 성립하지 않았다.

## 4. 선택한 검사 진행 알고리즘

파일 이름 기준의 순환 커서를 선택했다. 호출마다 디렉터리 전체를 정렬하지 않는다. 파일 본문을 전부 읽지 않는다.

한 호출의 동작:

1. 볼트 루트가 디렉터리가 아니거나 reparse point면 0을 반환한다.
2. `.umd-sweep-cursor`를 읽는다. 내용은 파일 이름 하나다. 허용 문자는 `[A-Za-z0-9._-]{1,80}`이다. URL, Cookie, Authorization은 저장하지 않는다.
3. 없거나, symlink이거나, reparse point이거나, 내용이 깨졌으면 커서를 빈 문자열로 둔다. 깨진 경우에는 `sweep cursor reset`만 남기고 본문은 로그에 넣지 않는다.
4. `os.scandir`로 이름을 한 번 순회한다. 점이 있는 이름, symlink, reparse point, 디렉터리는 열지 않는다. Windows reparse는 `DirEntry`의 `st_file_attributes`에서 `0x400`을 본다.
5. 크기 64인 힙 두 개로, 커서보다 큰 이름 중 가장 작은 64개와 커서 이하인 이름 중 가장 작은 64개를 고른다.
6. 커서 다음 이름을 먼저 연다. 64개보다 적으면 앞쪽 이름으로 이어 붙여 한 바퀴를 돈다.
7. 고른 마지막 파일 이름을 커서에 다시 쓴다. 임시 파일 `.umd-sweep-cursor.partial`을 `os.replace`로 바꾼다. 쓰기에 실패하면 `sweep cursor update failed`를 남기고 성공으로 적지 않는다.
8. 같은 프로세스의 중복 호출은 `threading.Lock`으로 한 번에 하나만 돈다.

커서가 가리키는 파일이 없어도 이름 문자열로 다음 구간을 고르므로 순회가 멈춘 채로 남지 않는다. 볼트 전체를 지우거나 다시 만들지 않는다.

다른 프로세스의 `_active`는 보지 않는다. 그 보호는 기존 outbound TTL 3600초다. 자식 프로세스 제한시간은 180초다. 프로세스 간 잠금은 추가하지 않았다.

## 5. 검사 상한 64개의 실제 의미

`_SWEEP_LIMIT`는 64다.

수정 전 64는 `iterdir()`에서 처음 만난 디렉터리 항목 64개였다. 그 안에 만료 파일이 없으면 뒤쪽은 다음 호출에서도 같은 64개에 가려 있었다.

수정 후 64는 한 호출에서 여는 일반 파일 수다. `sweep_stats["opened"]`가 그 값이다. 본문을 읽기 전에 symlink와 reparse point를 제외한다. 점으로 시작하는 커서 파일은 이 64개에 들어가지 않는다.

이름 나열 `sweep_stats["listed"]`는 64로 자르지 않는다. 이름 나열을 64에서 끊으면 이번 결함이 그대로다. 나열은 호출당 `scandir` 한 번이고, 정렬된 전체 목록을 만들지 않는다. JSON을 여는 횟수는 최대 64다.

## 6. 대량 파일 순회 결과

`test_sweep_bounds_work_for_large_vault`가 만료되지 않은 참조 4999개와 맨 뒤 만료 참조 1개를 만들었다. 전체 단위 테스트 실행 안의 측정이다.

- 호출 수: 79
- 만료 파일 삭제: 1
- `opened` 최댓값: 64
- 한 호출 시간 최소: 0.5461초
- 한 호출 시간 최대: 2.1009초
- tracemalloc 최대: 65810바이트
- 첫 호출: 0.7748초, listed 5000, opened 64, removed 0, peak 65810
- 둘째: 1.8069초, listed 5001, opened 64, removed 0, peak 63566
- 셋째: 1.6766초, listed 5001, opened 64, removed 0, peak 63566
- 만료 파일을 지운 호출: 0.5461초, listed 5001, opened 64, removed 1, peak 64417

79번 모두 `opened <= 64`이고 한 호출이 5초 미만이었다. 앞쪽 비만료 파일 때문에 만료 파일이 남아 있지는 않았다. 79는 4999개를 64개씩 지난 뒤 마지막 만료 이름에 닿는 횟수다.

이름 5000개를 매 호출마다 한 번 훑으므로, 파일 수에 따라 나열 시간은 늘어난다. 본문 읽기는 64개에서 멈춘다.

## 7. 프로세스 재시작 후 진행 결과

`test_sweep_progress_survives_restart`는 첫 인스턴스가 앞쪽 64개만 본 뒤 커서를 남기는 상태를 만들었다. 만료 파일은 그 시점에 남아 있었다. 같은 디렉터리로 새 `SecretVault`를 만들자 생성 중 정리가 커서를 이어 받아 만료 파일을 지웠고, 커서 값은 바뀌었다.

이 테스트는 15회 모두 PASS다. 10절에 횟수를 적었다.

## 8. 동시 실행과 중복 정리 결과

`test_sweep_concurrent_calls_preserve_refs`는 사용 중인 outbound 참조의 `expires_at`을 과거로 바꾸고, 작업 참조와 `notes.json`, 만료 참조 30개를 둔 뒤 스레드 8개에서 정리를 동시에 호출했다.

- 예외: 0
- 사용 중인 참조: 유지
- 작업 참조: 유지
- `notes.json`: 본문 `user-file` 유지
- 그 다음 반복 정리로 만료 참조 30개는 제거

같은 파일을 두 번 지우는 호출은 `FileNotFoundError`로 넘어가고 다른 참조를 지우지 않는다. 삭제 중 `OSError`는 `outbound sweep kept {ref}`만 남긴다. ref는 32자리 hex다.

커서가 가리키던 파일을 지운 뒤의 다음 호출은 `test_sweep_recovers_from_missing_cursor_target`에서 만료 참조를 제거했다.

권한 거부로 커서 파일을 쓰지 못하면 진행이 그 자리에 남을 수 있다. 그 경우 `sweep cursor update failed`를 남기며 성공으로 숨기지 않는다. 볼트를 통째로 지우는 복구는 하지 않는다.

## 9. 새 테스트 9개 결과

파일: `tests/unit/test_wo_reuse_01_s2_sweep.py`

처음 8개는 9.87초에 PASS였다. 대량 테스트는 그 다음 단독 실행에서 1 passed in 154.49s였다. 전체 단위 테스트 안에서도 9개 모두 PASS였다. 전체 실행의 대량 수치가 6절이다.

| 테스트 | 결과 |
| --- | --- |
| `test_sweep_progresses_beyond_first_64_entries` | PASS |
| `test_sweep_visits_all_expired_refs_across_batches` | PASS. 만료 200개를 4번 호출로 모두 제거. 각 호출 `opened <= 64`. 커서는 매번 바뀜 |
| `test_sweep_preserves_nonexpired_and_durable_refs` | PASS. 만료 1개만 삭제. 비만료, 작업 참조, 항목 참조, `notes.json` 유지 |
| `test_sweep_progress_survives_restart` | PASS |
| `test_sweep_recovers_from_missing_cursor_target` | PASS |
| `test_sweep_concurrent_calls_preserve_refs` | PASS |
| `test_sweep_rejects_symlink_reparse_and_foreign_files` | PASS. `mklink /J` 정션을 만들었고 `is_reparse`가 참이었다. 정션과 볼트 밖 파일, 깨진 JSON은 남았다. 파일 symlink는 시도했다 |
| `test_sweep_bounds_work_for_large_vault` | PASS |
| `test_sweep_logs_do_not_expose_secrets` | PASS. 서명 URL, Cookie, Authorization 문자열이 로그와 예외 문자열에 0건 |

활성 참조 오삭제 0건, 작업·항목 참조 오삭제 0건, 사용자 파일 손상 0건, 비밀 로그 0건이다.

## 10. 15회 반복 검증 결과

각 테스트를 프로세스 15번으로 나누어 실행했다. 평균으로 실패를 지우지 않았다.

| 테스트 | PASS | FAIL | SKIP | 실패 회차 |
| --- | --- | --- | --- | --- |
| `test_sweep_progresses_beyond_first_64_entries` | 15 | 0 | 0 | 없음 |
| `test_sweep_progress_survives_restart` | 15 | 0 | 0 | 없음 |
| `test_sweep_concurrent_calls_preserve_refs` | 15 | 0 | 0 | 없음 |

## 11. 전체 단위 테스트 결과

명령:

`python -m pytest --ignore=tests/unit/test_wo02_load.py --ignore=tests/live -s`

결과: `2 failed, 152 passed in 278.69s (0:04:38)`

수집 154개. S1의 145개에 새 테스트 9개가 더해진 수다. SKIP은 요약에 없었다.

실패 2건, 둘 다 `tests/unit/test_wo02_engine.py::test_parallel_presets_overlap_and_respect_the_cap`:

- `[12]`: `elapsed 1.9179569999978412 < (0.45 * 4)` 실패
- `[24]`: `elapsed 2.2358454000059282 < (0.45 * 4)` 실패

한도는 1.8초다. 이 한도를 바꾸지 않았다.

같은 검사를 구현 커밋의 `secrets.py`로 따로 돌리면 `[24]`가 약 1.91초에서 2.12초로 실패했다. 수정 전 `7deab72`의 `secrets.py`로 되돌린 실행도 `[24]`가 `2.0794652000040514`로 실패했다. 측정 구간은 `run_job`이고, 다운로드 엔진은 `SecretVault`를 호출하지 않는다. 이번 작업이 만든 실패로 보지 않는다. 그래도 로컬 전체 결과의 FAIL은 0이 아니다.

이 실행 안에 들어 있어 PASS된 기존 검사:

- `tests/unit/test_wo_reuse_01_secrets.py`
- `tests/unit/test_wo_reuse_01_lifecycle.py`
- `tests/unit/test_wo04_s4_shutdown.py`
- `tests/unit/test_wo02_engine.py`의 프리셋 시간 검사 2건을 제외한 나머지
- `tests/unit/test_wo01_download.py`

Range·ETag 재개, TCP EOF·RST 분류, Cookie 세션, QThread 강제 종료 금지는 해당 테스트가 이 154개 안에 있고 실패 목록에 없다. 강제 종료 호출은 추가하지 않았다.

## 12. Windows ACL 회귀 결과

로컬 Windows에서 실제 `icacls` 검사가 전체 단위 테스트에 포함되어 통과했다. 실패 목록에 ACL 테스트는 없다.

- `test_secret_is_not_written_when_acl_check_fails`
- `test_cookie_scope_expiry_and_leftover_files`의 `icacls` 확인

ACL을 적용하기 전에 비밀을 쓰지 않는 순서와, SYSTEM 또는 `S-1-5-18`을 남기는 검사는 유지했다. 이번 수정은 ACL 부여 코드를 바꾸지 않았다.

## 13. 로컬 부하 테스트 결과

실행함. CI에는 `inputs.load`를 넘기지 않는다. CI 부하 잡과 이 숫자를 섞지 않는다. S1의 147.08초, WO-REUSE-01의 147.57초와도 섞지 않는다.

명령: `python -m pytest -o addopts= -s tests/unit/test_wo02_load.py`

`1 passed in 342.16s (0:05:42)`. 프로세스 wall clock은 345.83초다.

`WO02_METRICS`:

- bulk files 5000, elapsed_s 321.118, peak_connections 3, server_peak 3
- working_set_before 48177152, working_set_peak 76931072, integrity_mismatches 0
- large_file_bytes 6291526, large_file_traced_bytes 769463
- sequential elapsed_s 9.272, completed 80, peak_connections 1, server_peak 1, working_set_before 87425024, working_set_after 87433216
- parallel elapsed_s 4.307, completed 80, peak_connections 3, server_peak 3, working_set_before 87433216, working_set_after 87818240
- note: local fixture only; not an internet throughput claim

321.118초는 5,000장 구간이다. 342.16초는 pytest 전체다. 같은 세션에서 프리셋 24 검사가 수정 전 코드로도 1.8초를 넘겼으므로, 이 부하 숫자를 S1의 147.08초와 제품 성능 차이로 해석하지 않는다.

## 14. Actions 실행 SHA 및 결론

저장소는 public이다. `workflow_dispatch`만 사용했다. `runs-on`은 `windows-latest`다. `inputs.load`는 넘기지 않았다.

실행 URL: https://github.com/scarlel96-design/Universal-Media-Downloader/actions/runs/41399216513

이벤트: `workflow_dispatch`

checkout 로그: `fetch`가 `b90b3dfd7499fc78fb8d2ced707f7b2693a13e64`를 가져왔고, 그 다음 줄이 같은 SHA다.

test 잡: success. 잡 URL: https://github.com/scarlel96-design/Universal-Media-Downloader/actions/runs/41399216513/job/125127236832

`Regression and WO-03 tests` 로그: `154 passed in 91.63s (0:01:31)`

load 잡: skipped. CI 부하 테스트는 NOT RUN이다. 로컬 321.118초와 섞지 않는다.

이 CI 성공은 로컬 `2 failed, 152 passed`를 지우지 않는다. 로컬 프리셋 실패는 11절 그대로다.

## 15. 잔존 위험

- UI 스레드: `ShellBundle`이 `Library`를 만들고, `Library`가 `SecretVault`를 만들 때 정리가 한 번 돈다. 이 생성은 셸을 만든 스레드에서 일어난다. `isolated.call`의 정리는 자식 프로세스가 끝난 뒤 호출자 스레드에서 돈다. 5,000개 이름에서 한 호출이 최대 2.1009초였다. 본문 전체 순회는 아니지만, 이름 나열은 호출마다 디렉터리 전체를 본다. 그보다 큰 볼트는 셸을 여는 스레드를 더 붙잡을 수 있다. 호출 위치를 다른 스레드로 옮기지 않았다. 생성 시 정리를 빼면 재시작 후 정리 재개가 지연된다.
- `database.py`의 고아 참조 정리는 여전히 `iterdir()` 처음 64개에서 멈춘다. 이번 결함의 대상인 `sweep_expired_outbound()`와 다른 경로다. 고아 정리는 이번에 바꾸지 않았다.
- 다른 프로세스의 활성 outbound 참조는 이 프로세스의 `_active`에 없다. 만료 시각이 지나면 지워질 수 있다. TTL 3600초는 유지했다.
- 커서 파일을 쓰지 못하는 동안에는 같은 64개 창을 다시 볼 수 있다. 실패 로그는 남긴다.
- 커서가 아직 지나가지 않은 새 파일은 한 바퀴가 돌아올 때 검사된다. 영구히 빠지지는 않는다.
- 로그에는 참조 ID와 건수만 남긴다. 사용자 백업은 열거나 지우지 않았다. VACUUM은 하지 않았다.
- Windows 실데스크톱 UI와 프로젝트 LICENSE 없음은 닫히지 않았다.
- 로컬 프리셋 24 시간 검사가 이 기계에서 1.8초를 넘긴다. 수정 전 코드에서도 같았다. P0 보안 결함으로 분류하지 않는다. 새로 연 P0는 없다.

## 16. 롤백 방법

S2 구현 커밋 `b90b3dfd7499fc78fb8d2ced707f7b2693a13e64`를 revert한다. 이력은 고치지 않는다.

revert는 이미 지운 만료 outbound 파일을 복구하지 않는다. 볼트에 남은 `.umd-sweep-cursor`는 파일 이름만 들어 있다. 옛 빌드는 그 파일을 정리 대상으로 보지 않는다. 사용자가 직접 지울 수 있고, revert가 사용자 파일을 지우지는 않는다.

## 17. 기능 안정화 판정

S2 기능 안정화: PARTIAL

정식 출시: NO-GO

S1 기능 안정화 GO는 유지한다. 이 판정으로 S1을 바꾸지 않는다.

PARTIAL인 조건:

- 앞쪽 64개 비만료 참조로 정리가 멈추는 현상은 재현했고, 반복 호출로 뒤쪽 만료 파일에 닿게 고쳤다.
- 재시작 후 진행, 신규 9개, 15회 반복 실패 0, 활성·작업·항목·사용자 파일 오삭제 0, 비밀 로그 0, 열기 상한 64, 대량 측정 기록, ACL과 S4 테스트 유지는 만족했다.
- 로컬 전체 단위 테스트 FAIL 0은 만족하지 못했다. 실패는 프리셋 시간 2건이고 수정 전에도 재현됐다.
- Actions는 구현 커밋에서 `154 passed in 91.63s`다. 이 결과만으로 로컬 실패를 해결된 것으로 보지 않는다.

WO-REUSE-02는 S2를 이 상태로 닫은 뒤 별도 검토다. 이번 커밋에 포함하지 않았다.
