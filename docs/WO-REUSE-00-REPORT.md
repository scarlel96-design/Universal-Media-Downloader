# WO-REUSE-00 — Booru Studio V10 ↔ Universal Media Downloader 재사용 감사

감사일: 2026-11-02

이 문서는 두 저장소의 소스를 읽은 결과다. 제품 코드는 수정하지 않았다. PR은 병합하지 않았다. Booru Studio의 Sprint 보고서와 `REVIEW_20261009_REPORT.md`는 현재 PASS의 근거로 쓰지 않았다. 이 감사에서 두 프로젝트의 테스트와 성능 비교는 실행하지 않았다.

## 1. 확인한 커밋

| 저장소 | 역할 | 확인한 SHA | 비고 |
| --- | --- | --- | --- |
| Universal Media Downloader | 지시서가 적은 기준 | `e555b9ba4d38d917c54e0ea4cb6b4b43dcbf2e40` | WO-04-S3 기록 커밋. 그 뒤 S4가 있다. |
| Universal Media Downloader | 비교에 사용한 브랜치 팁 | `9e2ee635458791a6b4a5e67c4337e51721734778` | `feat/wo04-browser-extraction`. 작업 트리는 깨끗했다. |
| Universal Media Downloader | 현재 구현 | `58091cff931d0c079a995319c65f23173e5876b0` | S4 구현. `9e2ee63`은 Actions URL 기록만 추가한다. |
| Booru Studio V10 | 지시서 기준이자 확인한 `main` | `25f307c33ff04334ec18f97dc2d4d7c3ae6a307a` | 작업 트리는 깨끗했다. |

UMD `main`은 읽지 않았다. PR #4 구현은 위 브랜치 팁이다. 비교는 `e555b9b` 이후의 S4 구현을 포함한다. S4가 다운로드 취소, 소켓 종료, EOF 분류, 종료 대기를 바꿨기 때문이다.

로컬 클론:

- `C:\Users\scarl\.pwragent\profiles\default\projects\Universal-Media-Downloader-git`
- `C:\Users\scarl\.pwragent\profiles\default\projects\Booru-Studio-V10-git`

두 클론 모두 접근했다. 소스 파일을 열지 못한 항목은 없다. 실행하지 않은 테스트와 측정하지 않은 성능은 아래 해당 절에서 추정으로 적지 않고 “실행하지 않음”으로 적는다.

## 2. 구현된 기능과 미구현 기능

### UMD, `58091cf` / 팁 `9e2ee63`

구현되어 있다.

- 공개 URL 라우터: gallery-dl, yt-dlp, HTML, 조건이 맞을 때만 Playwright. `src/umd/extract/router.py`
- HTML 이미지 분류. JSON-LD 파서는 없다.
- 단일 영상 형식 목록, 기본 화질 선택, 자막 언어 이름 표시. 재생목록은 거부한다. `src/umd/extract/video.py`
- httpx 엔진의 Range, If-Range, ETag, Last-Modified, 길이 검사, 호스트 제한, 리다이렉트마다 정책 재검사, DNS pin. `src/umd/download/engine.py`, `pin.py`
- `download_one()`의 Content-Length 비교. Range 재개는 없다. `src/umd/download/images.py`
- yt-dlp 자식 프로세스 다운로드. 앱이 FFmpeg를 직접 호출하지 않는다. `src/umd/download/video_job.py`
- SQLite 3테이블. `src/umd/storage/database.py`
- 쿠키는 호스트별 디렉터리의 `state.json`. ACL 실패 시 삭제. SQLite 컬럼은 없다.
- GUI 스레드의 QThread. 종료는 `terminate`가 아니다.
- 추출과 영상 다운로드의 별도 프로세스. `src/umd/net/isolated.py`

없다.

- JSON-LD 추출기
- HLS, DASH 파서. 프로토콜 이름만 보고 점진 다운로드와 구분한다.
- 자막 파일 저장
- 재생목록 다운로드
- FFmpeg 병합과 ffprobe 검증
- 파일 SHA-256 후 완료 판정. 갤러리 선택 저장만 해시를 계산한다.
- 매니페스트 서명, 설치 포인터, 업데이터
- 프로젝트 `LICENSE` 파일

### Booru Studio V10, `25f307c`

구현되어 있다.

- 어댑터 6종과 프로토콜 계약. `src/booru_studio/engine/`
- DirectHTTP: 강한 ETag 또는 Last-Modified, Range, If-Range, Content-Range 대조, 200이면 부분 파일 덮어쓰기, 416 한 번 정리 후 재시도, 사이드카 체크섬, SHA-256, fsync. `engine/adapters/direct_http/transfer.py`
- FFmpeg stream-copy 병합과 remux, ffprobe로 스트림 존재 확인, 취소 시 프로세스 종료. `engine/adapters/ffmpeg/adapter.py`
- gallery-dl 발견과 DirectHTTP 핸드오프. UNSAFE 디스크립터는 핸드오프하지 않는다.
- yt-dlp 발견, 재생목록 평탄화, 점진 형식과 분리 형식의 경로 분리. 조각·시크릿 형식은 yt-dlp 관리 모드로 남긴다.
- Static Web HTML 파서와 Playwright 관찰. 브라우저 채널 기본값은 `msedge`. 영속 프로필을 만들지 않는다.
- 워커 프로세스, 32바이트 시크릿, 파일 커밋 허가, 최종 경로가 있으면 `FileExistsError`. `worker/staging.py`
- 스케줄러: 호스트 적응, 허가 풀, 내구성 있는 속도 제한과 재시도 예산
- SQLite 다수 테이블. 잡 안 `source_key` 부분 유니크. `artifact_id`당 파일 기록 하나.
- 캡슐 파일 크기·SHA-256 대조, 심볼릭 링크 거부, 설치 포인터의 `previous_capsule_id`
- 업데이트 단계 전이 함수. `update/__init__.py`가 런타임 업데이터는 없다고 적는다.
- 쿼리 없는 URL만 저장하는 `redact_input_for_storage`

없다. 설계 또는 목록만 있는 것은 구현으로 세지 않는다.

- JSON-LD 추출기. `src/booru_studio`에서 검색 결과 없음.
- HLS, DASH 미디어 파서. `.m3u8`, `.mpd`는 확장자 목록에만 있다.
- 업데이트 다운로드, 서명 검증, 캡슐 교체, 롤백 실행. `update/contracts.py`는 단계와 증거 검사만 한다.
- 매니페스트의 전자서명. `packaging/manifest.py`의 `verify_capsule`은 크기와 SHA-256이다.
- Gate 6.5 시나리오의 실행기. `reliability/release_gates.py`는 시나리오 튜플과 ID 중복 검사다.
- DirectHTTP의 연결 시점 DNS pin. 검사 뒤 `requests`가 다시 이름을 푼다.
- `docs/architecture.md`의 “Updater implementation is still deferred”는 코드와 일치한다. 이 문장을 구현 완료로 읽지 않는다.

`ipc/stream_connection.py`의 `NotImplementedError`는 기반 클래스와, Windows가 아닌 폴링 가능한 fd가 없을 때의 타임아웃 경로다. Windows QLocal 생성 코드는 `worker_launcher.py`에 있다. 이 감사가 그 경로를 실행하지 않았으므로 Windows 워커 스폰은 구현된 코드이지 이번 감사의 실행 PASS가 아니다.

## 3. 소스 파일 단위 비교

| 기능 | Booru | UMD | 판정 |
| --- | --- | --- | --- |
| URL 정책 | `engine/network_scope.py` | `netpolicy.py`, `download/pin.py` | KEEP_UMD. Booru의 혼합 DNS 거절은 이미 UMD 공개 모드에 있다. Booru 기본값 `ANY`는 가져오지 않는다. |
| 정적 HTML | `engine/adapters/static_web/adapter.py` | `extract/html_images.py`, `html_adapter.py` | KEEP_UMD |
| 브라우저 | `engine/adapters/playwright_browser/adapter.py` | `extract/browser.py` | KEEP_UMD |
| gallery-dl | `engine/adapters/gallery_dl/adapter.py` | `extract/gallery.py`, `download/gallery_job.py` | ADAPTER. 핸드오프 안전 판정만. 라이브러리 소스는 복사하지 않는다. |
| yt-dlp | `engine/adapters/yt_dlp/adapter.py` | `extract/video.py`, `download/video_job.py` | ADAPTER. 관리 모드 분류만. 다운로드 교체 아님. |
| DirectHTTP | `engine/adapters/direct_http/transfer.py` | `download/engine.py`, `images.py` | ADAPTER. 검증 규칙을 기존 엔진에 넣는다. 엔진 교체 아님. |
| FFmpeg | `engine/adapters/ffmpeg/adapter.py` | 없음. yt-dlp에 맡긴다. | DEFER |
| 재개 사이드카 | `worker/resume.py` | 엔진 메모리와 SQLite의 ETag, `.part` | ADAPTER |
| 완료 커밋 | `worker/staging.py` | `jobs.py`가 파일 반환만으로 `완료` | ADAPTER |
| 워커 프로세스 | `core/worker_launcher.py`, `worker/main.py` | `app/shell.py`의 QThread, `net/isolated.py` | DEFER |
| 스케줄러 | `scheduler/*.py` | `download/schedule.py` | DESIGN |
| 잡·발견 서비스 | `core/job_service.py`, `discovery_service.py`, `media_service.py` | `storage/database.py`, `app/jobs.py` | DESIGN |
| 저장소 스키마 | `persistence/schema.py` | `storage/database.py` | KEEP_UMD |
| 쿼리 삭제 | `common/redaction.py` | `netpolicy.strip_userinfo`. 쿼리는 남긴다. | ADAPTER |
| 쿠키 | DirectHTTP가 Cookie, Authorization을 제거 | `auth/session.py` 파일 저장, 엔진이 Cookie를 붙임 | KEEP_UMD 저장. Booru의 “SQLite에 넣지 않음”은 ADAPTER. |
| 설치·업데이트 | `packaging/manifest.py`, `install_state.py`, `update/contracts.py` | 없음 | DESIGN |
| UI | `ui/qml/pages/*.qml`, 코어와 IPC | `ui/qml/Main.qml`, 인프로세스 셸 | KEEP_UMD |

판정 의미: DIRECT 소스 그대로 이식, ADAPTER 인터페이스를 맞춘 뒤 필요한 규칙만 이식, DESIGN 설계만 참고, KEEP_UMD 현재 UMD 유지, DEFER 선행 조건 전 착수 금지, REJECT 재사용 부적합.

DIRECT는 없다. Booru `pyproject.toml`의 `license = { text = "UNLICENSED" }`이고 두 저장소 모두 `LICENSE` 파일이 없다. 같은 GitHub 소유자 표시는 라이선스가 아니다.

## 4. 중복 코드와 중복 아키텍처

같은 역할을 각자 구현했다.

- 공개 주소가 아닌 대상 거부, 리다이렉트 제한, 호스트별 동시성, 재시도, Range 재개, gallery-dl과 yt-dlp 분리, Playwright 관찰, Qt/QML, SQLite 잡 상태.
- 구현은 공유 모듈이 아니다. import 경로, HTTP 스택, 프로세스 경계가 다르다. UMD는 httpx와 asyncio다. Booru DirectHTTP는 `requests`와 스레드다.
- 추출 라우팅은 중복 아키텍처다. UMD는 `extract_page` 한 함수가 gallery-dl, yt-dlp, HTML, 브라우저 순서를 정한다. Booru는 어댑터와 `worker`의 gallery, media, web 파이프라인이 나뉜다. 한쪽으로 합치는 공통 패키지는 이번 단계에서 유리하지 않다. Python 요구 버전이 3.12와 3.13으로 갈리고, Booru 라이선스 문구가 UNLICENSED다.

겹치지 않는 쪽.

- UMD만 있다: 제품 셸의 종료 대기, 다운로드 소켓을 닫고 QThread를 죽이지 않는 경로, Windows 프레이밍 없는 창, 세션 파일 ACL, 연결 pin.
- Booru만 있다: 아티팩트 커밋 허가, 사이드카 체크섬, FFmpeg 구조 검증, 재생목록을 잡 컬렉션으로 남기는 모델, 캡슐 포인터, 업데이트 단계 기계.

## 5. 우선 재사용할 코드

공통 패키지 추출은 하지 않는다. Booru에서 UMD로의 단방향 이식이 맞다. UMD를 Booru에 거꾸로 넣지 않는다. 엔진 전체 교체의 성능·안정성 측정은 없다.

### 5.1 쿼리 제거 — ADAPTER

근거: `booru_studio/common/redaction.py`의 `redact_input_for_storage`. 서명 쿼리 키를 허용 목록으로 거를 수 없다는 주석이 코드에 있다.

UMD `media_items.media_url`, `page_url`, `original_url`은 쿼리를 그대로 저장한다. `engine._secret_in`은 userinfo만 본다. 서명된 쿼리가 SQLite와 오류 문자열에 남을 수 있다.

차이: 재개와 영상 재추출에는 아직 URL이 필요하다. 저장 직전에 쿼리를 지우면 재개가 깨진다. 영속 컬럼과 로그에서 지우고, 전송이 끝나기 전의 URL은 ACL된 임시 위치에만 둔다.

의존성: 표준 라이브러리만. Booru 패키지를 import하지 않고 같은 규칙을 UMD에 새로 적는다.

위험: 쿼리를 식별자로 쓰는 페이지를 서로 다른 항목으로 못 알아볼 수 있다. 항목 키는 쿼리를 뺀 URL과 추출기 ID로 다시 정해야 한다.

테스트: 서명 쿼리가 SQLite, 로그, IPC stdout에 없는지. 쿠키 값과 Authorization 값이 같은 경로에 없는지. 재개가 임시 위치의 URL로만 이어지는지.

예상: 1~2일. 선행 조건 없음. 공통 패키지보다 단방향 이식이 맞다.

### 5.2 DirectHTTP 검증 규칙 — ADAPTER

근거: `direct_http/transfer.py`의 206 Content-Range 대조, 강한 ETag, 200이면 이어 붙이지 않음, 416 한 번 정리, 길이 불일치 재시도, 선택적 SHA-256.

UMD `engine.py`는 Range와 If-Range와 길이 검사를 이미 한다. `images.download_one`은 Range가 없고 S4에서 수정하지 않았다. 셸의 이미지 경로는 `DownloadEngine`이다.

교체하지 않는 이유: 같은 환경의 성능 비교가 없다. UMD 엔진은 S4에서 취소와 EOF 분류를 맞춘 상태다. Booru는 `requests`이고 쿠키 헤더를 `_SECRET_HEADERS`로 제거한다. 그대로 바꾸면 UMD 세션 쿠키가 빠진다.

가져올 규칙: 강한 ETag만 If-Range에 쓰기. 206의 시작 오프셋이 로컬 크기와 같아야 함. 200이면 부분 파일을 덮어씀. 416은 부분 파일을 지우고 한 번만 처음부터. 완료 전에 크기와, 호출자가 준 경우 SHA-256. 쿠키는 UMD 세션 경로로 유지하고 DB에는 쓰지 않음.

의존성: 기존 httpx. Booru `RetryPolicy`, `NetworkAdmissionController`, `ArtifactId`는 가져오지 않는다.

위험: 약한 ETag를 버리면서 재개가 줄어들 수 있다. 416 정리가 정상 파일을 지우지 않는지 봐야 한다.

테스트: 206 일치, If-Range 불일치의 200, 짧은 본문, 해시 불일치, 취소, 쿠키가 DB에 없는지. S4 EOF·RST·종료 테스트를 유지한다. 30초 제품 제한은 그대로 둔다.

예상: 3~5일.

### 5.3 완료 조건 — ADAPTER

근거: `worker/staging.py` `perform_commit`. 최종 경로가 있으면 예외. 스테이징과 최종 파일의 크기·SHA-256이 허가와 같아야 한다. `schema.py`는 잡 안 `source_key`가 있으면 유일하고, `file_records.artifact_id`도 유일하다.

UMD `jobs.py` `_one_video`는 `download_video`가 경로를 돌려주면 그 행을 `완료`로 갱신한다. 해시 검사는 없다. `media_items`에 `media_url` 유니크는 없다. 같은 `item_id`는 행이 하나이고, 다시 받으면 그 행을 다시 `완료`로 쓴다. 다른 잡은 같은 영상으로 완료 행을 하나 더 만들 수 있다. `video_job._options`의 `overwrites`는 False다. `_finished_path`는 yt-dlp가 보고한 기존 경로를 그대로 완료 파일로 쓸 수 있다.

FFmpeg `merge_copy`는 출력에 비디오와 오디오 스트림이 있을 때만 프로브를 반환하고, 실패하면 출력을 지운다. 이것은 파일 커밋 전의 검사다. UMD는 이 검사를 가지고 있지 않다.

이번 감사는 이중 커밋 테스트를 실행하지 않았다. 코드상 Booru는 같은 최종 경로의 두 번째 커밋을 거부한다. UMD는 같은 행을 다시 완료로 쓸 수 있다.

예상: 2~3일. 5.2의 해시 계산 다음이 자연스럽다.

### 5.4 yt-dlp 관리 모드 분류 — ADAPTER

근거: `yt_dlp/adapter.py` `plan_from_info`. 음성·영상이 한 점진 형식이고 핸드오프가 안전할 때만 DirectHTTP로 넘긴다. 조각, 매니페스트, 시크릿 헤더, 알 수 없는 파이프라인은 yt-dlp에 남긴다. 시크릿 헤더 집합과 쿼리 토큰 정규식이 있다.

UMD는 이미 페이지 URL을 다운로드 때 다시 추출하고, 재생목록이면 추출을 거부한다. 자막은 언어 이름 문자열이다. 자막 파일은 받지 않는다. 형식별 `protocol`에 `m3u8` 또는 `dash`가 있으면 기본 선택에서 점진 형식보다 뒤로 둔다.

가져올 것: 시크릿이 붙은 미디어 URL을 httpx 엔진으로 넘기지 않는 조건. 재생목록 지원 확대는 이번 재사용이 아니다. UMD가 재생목록을 거부하는 현재 계약을 유지한다.

의존성: 설치되어 있는 yt-dlp를 그대로 호출. Booru가 고정한 2026.08.19 타르볼로 내리지 않는다. UMD 선언은 `yt-dlp>=2026.10.26`이다.

위험: 핸드오프를 넓히면 서명 URL이 DirectHTTP 로그로 샌다. 기본은 관리 모드 유지다.

테스트: 시크릿 쿼리 형식이 `delivery=http`로 바뀌지 않는지. 재생목록이 여전히 거부되는지. DRM이 여전히 거부되는지.

예상: 2일. 5.1과 같이 갈 수 있다.

### 5.5 gallery-dl 핸드오프 거부 — ADAPTER

근거: `GalleryDirectHandoffPlanner.build`. `HandoffSafety.UNSAFE`면 DirectHTTP로 만들지 않는다. 주석이 그 dict를 저장하지 말라고 한다.

UMD `gallery_job.py`는 선택한 파일을 저장하고 SHA-256을 계산한다. 라우터는 공개 모드에서 gallery-dl을 yt-dlp보다 먼저 본다.

가져올 것: 안전하지 않은 갤러리 URL을 일반 HTTP 항목으로 만들지 않는 조건. gallery-dl 1.32.9 소스를 복사하지 않는다. UMD에 설치된 계열은 라이선스 문서 기준 1.32.19다. 이번 감사가 가상환경을 다시 조회하지 않았다.

예상: 1~2일. 5.4 다음.

## 6. 재사용하지 않을 코드와 이유

| 대상 | 판정 | 이유 |
| --- | --- | --- |
| Booru 패키지 import | REJECT | `requires-python >=3.13,<3.14`. UMD는 `>=3.12`. 라이선스 문구 UNLICENSED. `requests`와 httpx가 둘 다 필요해진다. |
| DirectHTTP 엔진 교체 | REJECT | 성능·안정성 비교를 하지 않았다. 쿠키를 제거하고 기본 네트워크 범위가 `ANY`다. |
| `TransferDescriptor.network_scope_policy` 기본값 `ANY` | REJECT | `authorize_transfer_url`의 ANY는 오리진 형태만 보고 주소 분류를 하지 않는다. UMD 공개 모드는 비공개 주소를 거부하고 pin된 주소로만 연결한다. |
| Static Web 파서를 HTML 추출기 대체 | REJECT | 확장자 목록 수준이다. UMD `html_images.py`가 후보 분류를 이미 한다. JSON-LD는 양쪽 다 없다. |
| Playwright 어댑터 교체 | KEEP_UMD | Booru는 설치된 Edge 채널 관찰기다. UMD는 정책 게이트와 동적 추출이 있고, WO-04에서 Chrome for Testing 경로를 맞췄다. 브라우저 구현을 바꾸면 그 검증과 섞인다. |
| 스케줄러 교체 | DESIGN | `HostAdaptiveLimiter`와 `HostBook`은 둘 다 메모리 호스트 제한이다. Booru `DurableRateLimitRegistry`와 `DurableRetryBudget`은 SQLite가 더 필요하다. 어느 쪽이 빠른지 측정하지 않았다. |
| 코어 서비스와 스키마 교체 | DESIGN | `MediaService`는 전송 URL과 쿠키를 API에 받지 않는다. 그 경계는 남긴다. 테이블 전체를 UMD 3테이블 자리에 넣지 않는다. |
| 워커 프로세스 모델 | DEFER | 구조는 크다. Windows QLocal 스폰은 코드가 있으나 이번 감사에서 실행하지 않았다. `spawn_source_stdio`의 `pass_fds`는 Windows에서 빈 튜플이다. Windows가 아닐 때만 부트스트랩 fd를 넘긴다. UMD 종료 계약은 인프로세스 QThread에 맞춰 져 있다. |
| FFmpeg 어댑터 | DEFER | UMD는 병합을 yt-dlp에 맡긴다. 바이너리 라이선스 파일을 확인하지 못했다. 병합 실패를 제품에서 재현하지 않았다. |
| 업데이터, 서명, 롤백 런타임 | DESIGN | 단계 기계와 캡슐 해시, 이전 캡슐 ID 필드만 있다. 서명 검증 함수가 없다. `release_gates.py`는 시나리오 목록이다. 과거 보고서의 PASS로 완료 처리하지 않는다. |
| gallery-dl, yt-dlp, Playwright, Qt 소스 복사 | REJECT | 서드파티 소스를 저장소에 넣지 않는다. 라이브러리 호출만 유지한다. |
| Booru UI QML | KEEP_UMD | 페이지 구성이 다르다. UMD 셸이 현재 작업 상태를 보여 주고 S4 종료 문구를 갖고 있다. |

## 7. 의존성과 라이선스

| 항목 | Booru `25f307c` | UMD `9e2ee63` |
| --- | --- | --- |
| Python | `>=3.13,<3.14` | `>=3.12` |
| 프로젝트 라이선스 | `pyproject.toml` 문구 `UNLICENSED`. `LICENSE` 파일 없음 | `LICENSE` 파일 없음. `docs/DEPENDENCY-LICENSES.md`가 앱 라이선스를 정하지 않는다고 적는다. |
| HTTP | `requests>=2.32,<3` | `httpx>=0.27`. 문서에 적힌 설치본은 0.28.1, BSD-3-Clause. 이번 감사가 설치본을 다시 조회하지 않았다. |
| Qt | 선택 의존성 `PySide6==6.11.1` | `PySide6>=6.8`. 문서에 적힌 설치본은 6.12.0. 메타데이터는 LGPL-3.0-only 또는 GPL-2.0-only 또는 GPL-3.0-only. 휠의 상용 안내문이 따로 있다. |
| gallery-dl | `==1.32.9` | `>=1.32`. 문서의 설치본 1.32.19, GPL-2.0-only, 추출 모듈 287. |
| yt-dlp | 2026.08.19 타르볼과 sha256, `yt-dlp-ejs==0.8.0` | `>=2026.10.26`. 문서의 설치본 2026.10.26, Unlicense, 추출기 1747. |
| Playwright | `==1.62.0`, 기본 채널 `msedge` | `>=1.40`. WO-04-S4 CI는 Chrome for Testing 156.0.8078.4, Playwright chromium v1248을 설치했다. |
| FFmpeg | pip 의존성 아님. 어댑터가 실행 파일 경로를 받는다. | 제품 코드가 실행 파일을 호출하지 않는다. yt-dlp가 필요하면 그 도구가 찾는다. 바이너리 라이선스는 BLOCKED. 파일을 열지 못했다. |

복사와 배포.

- Booru 소스를 UMD에 복사하는 권한을 저장소 메타데이터가 주지 않는다. 같은 소유자가 나중에 라이선스 또는 재사용 허가를 적기 전에는 DIRECT 복사를 하지 않는다. 아이디어를 UMD 파일에 새로 구현하는 것은 그 허가와 별도로 이번 보고서의 ADAPTER 항목에 한정한다.
- gallery-dl을 라이브러리로 import하는 결합물의 GPL-2.0 적용 여부는 `DEPENDENCY-LICENSES.md`가 법적 결론을 내리지 않는다고 적혀 있다. 이 감사도 결론을 내리지 않는다. 추출기 소스를 복사해 배포하는 것은 REJECT다.
- yt-dlp Unlicense 라이브러리 호출은 유지한다. Booru처럼 해시로 고정하는 것은 설계로만 적는다. 버전을 2026.08.19로 내리지 않는다.
- Qt를 배포할 때의 LGPL 또는 GPL 의무는 릴리스 절차의 일이다. 이번 감사가 그 고지를 작성하지 않는다.
- 두 프로젝트 모두 프로젝트 LICENSE가 없다. UMD 정식 릴리스 NO-GO의 기존 이유와 같다.

## 8. 보안과 테스트 공백

확인한 사실.

- UMD 쿠키는 SQLite가 아니라 `SessionStore` 디렉터리다. ACL에 실패하면 지우고 `SessionProtectError`를 낸다. 엔진은 요청 직전에 Cookie 헤더를 붙인다. `shell.py`는 쿠키가 있는지만 보고 값을 표시하지 않는 분기가 있다.
- UMD SQLite에는 페이지 URL과 미디어 URL이 쿼리까지 들어간다. 서명 쿼리의 영속 저장을 막는 코드는 없다.
- UMD 오류 정리는 userinfo와 타임아웃 문구다. 쿼리 서명, 쿠키, Authorization이 예외 문자열에 있으면 잘리지 않을 수 있다.
- UMD 격리 자식은 URL을 페이로드로 받는다. 그 URL에 서명이 있으면 IPC에 실린다. 자식이 그것을 SQLite에 다시 쓰는지는 다운로드 행이 이미 가지고 있는 값과 같다.
- UMD 공개 모드는 비공개, 루프백, 링크 로컬, CGNAT, 난독 IP를 거부한다. 이름이 하나라도 공개 주소가 아니면 거부한다. 연결은 검사한 주소로 pin한다. 리다이렉트마다 `assess_public_url`을 다시 한다. `follow_redirects`는 False다.
- Booru DirectHTTP는 Authorization, Cookie, X-Api-Key 등을 요청에서 제거한다. 저장용 URL은 쿼리를 뺀다. `TransferDescriptor.diagnostic_view`는 헤더 값과 쿼리를 빼라고 구현되어 있다.
- Booru DirectHTTP 기본 `network_scope_policy`는 `ANY`다. ANY는 사설 주소를 분류하지 않는다. Static Web과 Browser Assist가 만드는 디스크립터는 `PUBLIC_ONLY` 또는 `ROOT_OR_PUBLIC`이다. 실행 평면의 기본 폴백도 `ANY`다.
- Booru는 요청 전에 `authorize_transfer_url`을 호출하지만, 그 다음 `requests.get`이 이름을 다시 푼다. 연결 pin이 없다. 혼합 DNS는 검사 시점에는 거부한다.
- Booru 워커 시크릿은 부트스트랩 32바이트다. `worker_sessions` INSERT 컬럼에 시크릿은 없다. 시크릿이 로그에 찍히지 않는지는 실행으로 확인하지 않았다.
- Booru 업데이트 “서명”은 게이트 문구 `G65-UPD-REPLAY`에만 있다. 검증 코드는 없다.
- 메타데이터 주소와 AdGuard 차단은 UMD 정책에 있다. 이번 비교가 그 테스트를 다시 돌리지는 않았다.

실행하지 않은 것.

- 두 제품의 단위 테스트, 부하 테스트, 같은 파일·같은 망에서의 속도 비교
- Booru Windows QLocal 스폰, 실제 Edge, 실제 FFmpeg 바이너리
- UMD 실제 바탕 화면 UI. 기존 릴리스 NO-GO와 같다.
- 공개 인터넷만으로 되는 JS 미디어

그래서 보안 결론은 코드 대조다. “Booru가 더 안전하다” 또는 “UMD가 더 빠르다”는 이번 감사의 결론이 아니다.

## 9. 작업량과 우선순위

측정한 성능 차이가 없으므로 다운로드 엔진, 스케줄러, UI, 스키마는 유지한다.

| 순서 | 항목 | 방향 | 예상 | 선행 |
| --- | --- | --- | --- | --- |
| 1 | 영속 저장에서 서명 쿼리와 비밀 헤더 제거 | UMD에 단방향. Booru 파일 복사 아님 | 1~2일 | 없음 |
| 2 | 206, 강한 검증자, 416, 선택 해시 | 기존 `DownloadEngine`에 규칙 추가 | 3~5일 | 1의 저장 위치 |
| 3 | 완료는 크기 일치 뒤 한 행만. 최종 경로가 있으면 덮어쓰지 않음 | UMD `jobs.py`와 영상 경로 | 2~3일 | 2 |
| 4 | 시크릿 미디어 URL은 yt-dlp·gallery-dl 관리 경로에 유지 | 추출 결과의 `delivery` | 2~3일 | 1 |
| 5 | yt-dlp, gallery-dl 버전 고정과 프로젝트 라이선스 결정 | 문서와 선언. 코드 이식 아님 | 1일 | 소유자 결정 |
| 보류 | FFmpeg 직접 병합 | 새 바이너리 | 1주 이상으로 추정 | 병합 실패의 재현, 바이너리 라이선스 |
| 보류 | 워커 프로세스 분리 | 아키텍처 | 2~4주로 추정. 측정 전 추정이다. | Windows 스폰을 UMD에서 별도 증명 |
| 보류 | 내구성 스케줄러, 코어 스키마, 업데이터 | 설계 참고 | 정하지 않음 | 엔진 교체 근거가 생긴 뒤 |

양쪽 모두에 해당하는 개선.

- 연결은 검사한 IP로만 한다. UMD는 그렇게 한다. Booru DirectHTTP는 아직이다.
- 네트워크 기본값은 실패로 닫는다. Booru `ANY`를 기본으로 두지 않는다.
- 서명 URL과 쿠키는 SQLite, 로그, 진단 JSON에 두지 않는다. Booru 저장 규칙이 이쪽에 가깝다. UMD 전송은 쿠키가 필요하다.
- 업데이트 단계 이름이나 다운로드 100%를 설치 성공으로 쓰지 않는다. Booru 계약이 이미 그렇게 말한다. 런타임은 없다.
- 서드파티는 해시로 고정한다. Booru yt-dlp가 그렇게 한다. UMD yt-dlp 하한만 있다.
- 배포 전에 프로젝트 라이선스를 정한다. 둘 다 파일이 없다.

## 10. 후속 구현 단위

구현은 이 감사 다음에 따로 시작한다. 이 보고서의 작성은 그 시작이 아니다.

- WO-REUSE-01 영속 비밀 제거. 판정 5.1.
- WO-REUSE-02 기존 엔진의 재개·무결성 규칙. 판정 5.2. 엔진 파일 교체 금지.
- WO-REUSE-03 단일 항목 완료 계약. 판정 5.3.
- WO-REUSE-04 관리 모드 유지. 판정 5.4와 5.5.
- WO-REUSE-05 의존성 고정과 라이선스 결정. 코드 복사 전에 소유자가 허가 문구를 넣기 전에는 Booru 파일을 복사하지 않는다.
- WO-REUSE-06 이후는 DEFER다. 워커 분리, FFmpeg 내장, 업데이터, 스키마 교체, 스케줄러 교체. 각각 재현된 결함 또는 같은 환경의 측정이 생기기 전에 시작하지 않는다.

별도 지시서: `docs/WO-REUSE-00-NEXT.md`

## 아키텍처

UMD가 제품 프로세스로 남는다. 셸, QML, SQLite 3테이블, httpx 엔진, gallery-dl, yt-dlp, Playwright, 세션 파일은 유지한다.

Booru에서 오는 것은 모듈이 아니라 다음 네 경계다.

1. 영속 상태에는 쿼리와 헤더가 없다.
2. 바이트 전송은 지금 엔진이 하고, 완료 직전에 범위와 길이와 해시를 확인한다.
3. 시크릿이 있거나 조각 미디어인 URL은 그 엔진으로 넘기지 않는다.
4. 다른 프로세스로의 분리는 지금 하지 않는다. Booru의 코어·워커·커밋 허가는 그 분리의 참고 설계다.

`docs/architecture.md`의 업데이터 절, Sprint 7 미디어 경계, Sprint 8 브라우저 경계는 위 판정과 맞는 부분이 있다. 그 문서와 Sprint 6, Sprint 11, `REVIEW_20261009_REPORT.md`는 이번 소스 판정을 대신하지 않는다.
