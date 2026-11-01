# WO-01 보고서 — 본문 이미지 추출 및 다운로드

## Current

판정: **GO**

WO-00E 역컴파일은 그대로 BLOCKED다. 4K Video Downloader+는 실행하지 않았고, 바이너리를 분석하지 않았으며, 성능 비교도 하지 않았다.

이번 단계의 기준선은 고정 HTML 픽스처다. 추출기는 JavaScript를 실행하지 않고, 사이트별 추출기도 없다. 받을 수 있는 주소는 `file:`와 `127.0.0.1` / `localhost`뿐이다.

최종 자동 테스트는 `.\.venv\Scripts\python.exe -m pytest` 기준 **31 passed in 6.68s**다. 여기에는 WO-UI-00의 기존 13개가 들어 있다.

## 변경 파일

추가:

- `src/umd/extract/html_images.py`, `src/umd/extract/fetch.py`
- `src/umd/download/images.py`
- `src/umd/storage/database.py`
- `src/umd/app/jobs.py`
- `src/umd/netpolicy.py`
- `tests/fixtures/posts/article.html`, `slow.html`, `bad.html`, `expected.json`, `make_photos.py`, `photos/`
- `tests/unit/test_wo01_extract.py`, `test_wo01_download.py`, `test_wo01_ui.py`
- `tests/wo01_support.py`, `tests/conftest.py`
- `docs/design/captures/wo01-extracted.png`

수정:

- `src/umd/app/shell.py`
- `src/umd/__main__.py`
- `src/umd/ui/qml/components/MediaGrid.qml`, `InspectorPanel.qml`, `StatusStrip.qml`
- `README.md`

네이티브 제목 표시줄 플래그와 창 크기별 열 수는 바꾸지 않았다. 샘플 12개는 주소가 비어 있을 때의 기본 모델로 남아 있다.

## 구현 기능

HTML 추출은 `article`, `main`, 본문 클래스 안의 `img`를 본다. `src`, `srcset`, `data-src`, `data-original`, `picture`/`source`, 이미지를 감싼 원본 파일 링크를 읽고, 기준 주소에 상대 경로를 붙인 뒤 같은 URL은 하나로 합친다.

분류는 세 가지다.

- 본문 이미지: 본문 컨테이너 안. 40×40과 1×1도 본문이면 유지한다. 크기만으로 빼지 않는다.
- 판단 불확실: 본문 밖이고 광고·장식 단서가 없음. 그리드에 보이지만 기본 선택은 꺼져 있다.
- 기본 제외: 광고, 관련 게시물, 로고, 아이콘, 작성자 프로필, 추적 픽셀 표시. 기본 그리드에서는 숨긴다.

제외 항목은 "제외 표시"로 다시 볼 수 있고, 선택하면 `override=included`로 남아 다운로드 대상이 된다. 선택 상태와 다운로드 목록은 같은 모델 행이다.

저장은 UI 스레드 밖의 `QThread`에서 한다. 바이트는 목적지 안의 `.part`에 쓰고, HTTP 200, 길이, PNG/JPEG/GIF/WEBP 서명을 확인한 뒤에만 `os.replace`로 최종 이름이 된다. 실패와 취소는 `.part`를 지우고 완료로 기록하지 않는다. 같은 파일명은 `name-2`처럼 번호를 붙인다.

SQLite 스키마 버전은 1이다. 작업 ID, 페이지 URL, 미디어 URL, 분류, 선택, 다운로드 상태, 경로, 크기, 오류, 생성·완료 시각을 저장한다. 완료 행의 파일이 없거나 크기가 다르거나 경로가 `.part`이면 불일치로 보고한다.

화면 상태는 대기, 추출 중, 추출 완료, 다운로드 중, 완료, 실패, 취소를 구분한다. 미리보기는 `Image.asynchronous`다.

## 테스트

| # | 내용 | 결과 | 테스트 |
| --- | --- | --- | --- |
| 1 | 본문 이미지만 추출 | PASS | `test_01_extracts_only_article_images` |
| 2 | 광고·추천·장식 제외 | PASS | `test_02_excludes_ads_related_and_chrome` |
| 3 | 작은 본문 이미지 보존 | PASS | `test_03_keeps_small_images_inside_the_article` |
| 4 | srcset, 지연 로딩, picture | PASS | `test_04_srcset_lazy_and_picture` |
| 5 | 상대 URL 정규화 | PASS | `test_05_normalizes_relative_and_absolute_urls` |
| 6 | 중복 후보 통합 | PASS | `test_06_merges_duplicate_candidates` |
| 7 | 판단 불확실 이미지 복원 | PASS | `test_07_user_can_select_an_uncertain_image` |
| 8 | 개별·전체 선택, 제외 복원 | PASS | `test_08_individual_and_bulk_selection` |
| 9 | 저장 바이트 일치 | PASS | `test_09_saved_bytes_match_the_fixture`, `test_09_selected_preview_rows_save_matching_bytes` |
| 10 | 같은 파일명 | PASS | `test_10_same_filename_gets_a_suffix` |
| 11 | HTTP 오류·손상 응답 | PASS | `test_11_http_errors_and_corrupt_bodies_leave_no_file`, `test_11_shell_records_http_failure` |
| 12 | SQLite 재시작 | PASS | `test_12_sqlite_schema_and_restart`, `test_12_sqlite_restores_the_finished_job` |
| 13 | 다운로드 중 UI 응답 | PASS | `test_13_download_does_not_block_the_ui` |
| 14 | 기존 13개 회귀 | PASS | 같은 pytest 실행에 포함. 31개 전부 통과 |

추가 PASS: `test_cancel_does_not_keep_a_partial_file`, `test_public_url_is_not_fetched`.

FAIL은 없다. 빼거나 SKIP으로 돌린 필수 테스트는 없다.

픽스처 기대값은 `tests/fixtures/posts/expected.json`이다. 본문 7개는 `coast.png`, `lake-1200.jpg`, `lazy.png`, `panel.png`, `dot.png`, `original.png`, `pic-800.webp`다. 빠지는 후보는 썸네일, `lake-400.jpg`, 지연 로딩 자리표시, `pic-200.webp`, picture 폴백이다.

## 실제 파일 저장

로컬 픽스처 서버에서 본문 7개를 받았다. 저장 파일의 바이트는 픽스처 원본과 같았다. 서명이 아닌 파일은 최종 이름으로 남지 않았다.

같은 이름의 `coast.png` 두 개는 `coast.png`와 `coast-2.png`로 저장됐고, 각각 원본과 다른 원본(`twin.png`)에 맞았다.

HTTP 404, HTTP 500, HTML 본문, 잘린 `Content-Length`는 상태 `실패`이고 디렉터리에 파일이 남지 않았다. 취소는 상태 `취소`이고 `.part`도 남지 않았다. 셸에서 `/missing.png` 한 장을 받으면 작업 상태가 `실패`이고 오류는 `HTTP 404`다.

UI 응답 테스트는 서버가 본문을 0.8초 붙잡고 있는 동안 테마 전환과 1440 폭 변경이 0.3초 안에 돌아왔고, 작업 스레드 id가 UI 스레드와 달랐다. 끝난 파일은 `panel.png` 바이트와 같았다.

## SQLite

스키마 버전은 1이다. 프로세스를 닫고 같은 파일을 다시 열면 작업 URL, 분류, 선택, `완료` 상태, 경로, 크기가 그대로다. 완료 파일을 지운 뒤 `integrity_issues()`는 `missing:<id>`를 반환했다. 불일치가 없을 때는 빈 목록이다.

## UI 증거

캡처: `docs/design/captures/wo01-extracted.png`

오프스크린 1440×900 클라이언트 영역이다. 추출 직후 값은 단계 `추출 완료`, 보임 9, 선택 7, 정보 패널 `Coast` / `본문 이미지`다. 그리드는 4열이고, 본문 7장에 선택 표시가 있으며, 불확실 2장에는 선택 없이 배지가 있다. PNG, JPEG, WebP 미리보기가 카드와 정보 패널에 그려졌다. OS 제목 표시줄은 이 캡처에 없다.

`hostMode`는 `native-frame`이다. 기존 레이아웃 테스트(1024에서 사이드바 196·3열, 1440에서 사이드바 236·4열, 툴바 60)는 통과했다.

## 미완료

- Windows Snap, Win+Z, Alt+Space, Alt+F4, 실제 모니터 DPI, 고대비, 화면 읽기, 300ms 프레임 계측: **NOT RUN**. WO-UI-00에서 넘긴 항목이며 이번에도 손대지 않았다.
- 저장 폴더 대화상자(`QFileDialog`): **NOT RUN**. 테스트는 `setDownloadDirectory`로 같은 저장 슬롯을 호출했다. 앱 실행 경로는 `QApplication`이라 대화상자를 열 수 있다.
- 공개 사이트 호환, JavaScript 렌더링, yt-dlp, gallery-dl, YouTube, Tor, 프록시, DRM, 수천 장 병렬: 구현하지 않음. 범위 밖이다.
- 실제 사용자 모니터에서 미리보기 스크롤을 눈으로 확인: **NOT RUN**. 자동 테스트와 오프스크린 캡처만 있다.

## 다음 작업

- 로컬 호스트 제한을 풀기 전에 리다이렉트, 용량, 취소의 사용자 흐름을 먼저 정한다.
- 저장 폴더 대화상자와 Windows 창 제어는 실제 데스크톱에서 따로 확인한다.
- 영상과 로그인 사이트는 이번 추출기에 붙이지 않는다.

## 비용과 업로드

추가 비용은 0이다. 결제나 외부 업로드는 없다.

픽스처 JPEG/WebP가 Qt에서 열리게 하려고 가상환경에 Pillow를 한 번 받아 바이트를 만든 뒤, 그 바이트를 `make_photos.py`에 넣었다. Pillow는 실행 의존성이 아니다.
