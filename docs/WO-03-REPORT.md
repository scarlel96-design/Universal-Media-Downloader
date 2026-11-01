# WO-03 보고서 — 공개 추출과 공식 저장소 기준선

## 판정

**GO**

WO-GIT-00 GO가 먼저 끝났다. 기존 51개 회귀와 WO-03 단위 테스트, 공개 HTML 추출, gallery-dl 목록, yt-dlp 조회, 허용된 이미지·영상 파일 저장, SQLite v2 행 보존, 네이티브 창 플래그, 내부 주소 거부를 이 트리에서 실행했다. GitHub Actions는 실행하지 않았으므로 CI는 NOT RUN이다. WO-00E는 BLOCKED다.

## 저장소

- 주소: https://github.com/scarlel96-design/Universal-Media-Downloader
- 기준 브랜치: main `6df39c48a55730e0df9e22adee1aa5e1daeaff3d`
- 작업 브랜치: `feat/wo03-public-extractors`
- 기능 커밋:
  - `4fcc05b6f215b46b6ccfe448fe12cd96e642f08a` 공개 HTTP 정책과 연결 고정
  - `c0a0a399f7c64e1a6634d782535f0e82402f3e47` 공통 미디어 레코드와 HTML 어댑터
  - `fb063d2c10961c255a8d62081a1ce6c806cad60c` gallery-dl 목록
  - `6fc8567b75fdbfc82cda37945ac7d1b2472a0a6b` yt-dlp 조회와 다운로드
  - `adddf6c65215f187bc1b747123189aceeea2ae70` 미리보기, 큐, SQLite v3
- 문서 커밋과 Pull Request 주소는 이 파일을 푸시한 뒤 PR 본문에 적는다. 머지 커밋은 머지 후에만 있다.
- Force push와 원격 브랜치 삭제는 하지 않는다.

## 네트워크

로컬 모드의 `is_allowed_url`은 그대로다. `file:`과 `127.0.0.1` / `localhost`만 허용한다. 공개 모드는 별도다.

공개 모드는 HTTP와 HTTPS만 연다. 이름 차단, 난독화 IP, CGNAT `100.64.0.0/10`, 루프백, 사설, 링크 로컬, IPv6 ULA를 거부한다. DNS 응답 중 하나라도 공개 주소가 아니면 그 이름을 거부하고 핀을 만들지 않는다. 연결은 검사한 핀으로만 하고, 핀이 없으면 다시 DNS하지 않는다. 리다이렉트마다 다시 검사한다. `socket.getaddrinfo`는 gallery-dl과 yt-dlp가 돌아가는 동안 같은 검사로 바뀌고, 끝나면 원래 함수로 되돌린다. TLS의 SNI와 Host는 사이트 이름을 유지한다.

사용자 정보는 화면과 저장 주소에서 뺀다. 응답 본문 상한은 2,000,000바이트, 공개 연결 제한은 10초다. 401은 `인증이 필요합니다 (HTTP 401)`, 403은 `접근이 거부되었습니다 (HTTP 403)`이고 재시도하지 않는다. 추출 실패와 다운로드 실패는 다른 예외 종류다. Tor와 프록시는 켜지 않는다. `trust_env=False`다.

식별용 User-Agent는 `UniversalMediaDownloader/0.1 (https://github.com/scarlel96-design/Universal-Media-Downloader)`다. 짧은 UA만 보냈을 때 Wikimedia는 HTTP 403을 돌려줬다.

## 추출

로컬 분석은 HTML만 사용한다. 공개 분석은 페이지를 검사한 뒤 gallery-dl, yt-dlp, HTML 순으로 고른다. yt-dlp의 Generic 추출기는 쓰지 않는다. 직접 받을 수 있는 png, jpg, gif, webp는 HTTPX 큐로 가고, 그 외 갤러리 파일은 gallery-dl `DownloadJob`으로 간다. 같은 페이지를 두 엔진에 다시 저장하지 않는다.

설치된 버전과 개수:

- gallery-dl 1.32.19, 추출 모듈 287
- yt-dlp 2026.10.26, 추출기 1747

영상은 다운로드 전에 `extract_info(download=False)`로 제목, 길이, 썸네일, 해상도, 영상·음성 형식, 파일 크기, 자막, 오류를 읽는다. 확인되지 않은 값은 `미확인`이다. `filesize_approx`는 파일 크기가 아니고 `예상 …` 노트다. 진행률은 `total_bytes`가 있을 때만 계산한다. DRM 형식은 버린다. 재생목록, YouTube 로그인, 쿠키, 개인 재생목록은 받지 않는다. 서명된 미디어 URL은 SQLite 키로 저장하지 않고, 받을 때 페이지 URL로 다시 조회한다.

## SQLite

스키마 버전은 3이다. 새 데이터베이스는 v3 컬럼으로 만든다. v1과 v2는 행을 지우지 않고 컬럼을 더한 뒤, 비어 있는 `original_url`, `media_reference`, `media_type`을 기존 URL과 `image`로 채운다. 버전 4 이상은 거부한다.

## UI

WO-UI-00 토큰, 사이드바 236/196, 도구막대 60, 열 4/3, 정보 패널 298/265, 최소 1024x680을 유지한다. 창 플래그는 `Window | WindowTitleHint | WindowSystemMenuHint | Minimize | Maximize | Close`다. `FramelessWindowHint`는 없다. `hostMode`는 `native-frame`다. 그리드 `cacheBuffer`는 한 줄이고 이미지 `cache`는 켜져 있다. 로컬/공개 선택은 그리드 헤더에 있다. 형식 선택과 메타, 오류 문장은 정보 패널 그리드 밖이다.

오프스크린 캡처 `docs/design/captures/wo03-preview.png`는 1440x900, 26653바이트다. 클라이언트 영역만 담는다. OS 제목 표시줄, Win+Z, Alt+Space, Alt+F4, 실제 모니터 DPI, 고대비, 스크린 리더, 300ms 프레임, QFileDialog는 NOT RUN이다.

## 테스트

날짜는 2026-11-01이다.

| 묶음 | 결과 |
| --- | --- |
| 단위 테스트, 5,000장 부하 제외 | 88 passed in 29.03s. 여기에는 WO-02 부하 테스트를 뺀 기존 50개가 들어 있다. |
| 5,000장 로컬 부하 | 1 passed in 163.18s |
| 공개 사이트 3건 | 3 passed |

SKIP은 없다. 부하 테스트 직후 한 번은 WO-01 로컬 저장 두 건이 `timed out`으로 실패했다. 같은 파일을 바로 다시 실행하면 5 passed in 2.49s였고, 이어서 단위 전체는 88 passed in 29.03s였다. 그 타임아웃은 최종 통과 결과에 넣지 않는다.

5,000장 실측. 로컬 루프백이고 인터넷 처리량이 아니다. 균형 프리셋의 호스트 상한은 3이라 한 호스트에서는 전역 12가 보이지 않는다.

- 파일 5000, 154.441초, 약 32.4파일/초
- 엔진 동시 연결 최고 3, 서버 동시 연결 최고 3
- 불일치 0, 남은 `.part` 없음
- 작업 집합 시작 47,747,072바이트, 최고 103,411,712바이트
- 큰 파일 6,291,526바이트, tracemalloc 증가 874,346바이트
- 80장 순차 4.055초 최고 1, 병렬 2.147초 최고 3

공개 사이트. 미리보기만 한 항목은 다운로드 성공으로 세지 않았다.

- HTML: `https://www.w3.org/Graphics/PNG/inline-alpha.html`. gallery-dl과 yt-dlp 비범용 추출기가 이 URL을 맡지 않는다. 이미지 3개, 분류는 모두 판단 불확실, 본문 0, 기본 제외 0. 이 페이지에는 `article`/`main`이 없다. 파일은 저장하지 않았다.
- MDN `https://developer.mozilla.org/en-US/docs/Web/HTML/Element/img`는 `.../Reference/Elements/img`로 옮겨졌고 `<img>`가 없었다. `srcset`은 설명 문장에만 있었다. 추출 성공으로 세지 않는다.
- 갤러리: `https://commons.wikimedia.org/wiki/File:PNG_transparency_demonstration_1.png`. 페이지에서 `cc0`를 확인한 뒤 목록 17건. HTTPX 공개 모드로 `https://commons.wikimedia.org/wiki/Special:FilePath/PNG_transparency_demonstration_1.png`를 저장했다. PNG 서명, 224,566바이트.
- 영상: `https://commons.wikimedia.org/wiki/File:Short.ogv`. 페이지에서 `public domain`을 확인했다. yt-dlp 제목 `Short`, 길이 5.758548752834467초, 자막 `미확인`. 확정 파일 크기는 없었고 형식 `0`의 추정은 284,328바이트였다. 저장 파일은 284,779바이트다.

## GitHub Actions

`.github/workflows/ci.yml`은 `workflow_dispatch`만 있다. `pull_request`와 `push` 트리거는 없다. 두 잡 모두 `windows-latest`다. Qt는 `QT_QPA_PLATFORM=offscreen`, `QT_QUICK_CONTROLS_STYLE=Basic`, `QSG_RHI_BACKEND=software`다. 기본 잡은 5,000장 테스트와 `tests/live`를 제외한다. 부하 테스트는 입력 `load`가 참일 때만 돈다.

GitHub 문서 기준으로 공개 저장소의 표준 GitHub 호스트 러너는 무료다. 더 큰 러너는 공개 저장소에서도 과금된다. 이 워크플로는 표준 `windows-latest`만 쓴다. `workflow_dispatch`는 기본 브랜치의 워크플로 파일을 읽으므로, 이 파일이 main에 있기 전에는 실행할 수 없다. 이번 단계에서 실행하지 않았다. CI 상태는 **NOT RUN**이다.

## 비용과 업로드

추가 비용은 0이다. 유료 API는 호출하지 않았다. 공개 사이트 테스트는 받은 파일을 로컬 임시 디렉터리에 저장했다. 사용자 데이터를 외부로 올리지 않았다. 이 브랜치를 푸시하면 공식 저장소에 소스만 올라간다.

## 유지한 미완료

- WO-00E 역컴파일: BLOCKED
- Win+Z / Snap, Alt+Space, Alt+F4, 실제 DPI 전환, 고대비, 스크린 리더, 300ms 프레임 계측, QFileDialog: NOT RUN
- GitHub Actions 실행: NOT RUN
- YouTube 로그인, 개인 재생목록, DRM, Tor, 프록시: 구현하지 않음

## 다음 단계

이 보고서로 WO-03을 끝낸다. 다음 작업은 자동으로 시작하지 않는다. 이어서 할 수 있는 것은 사용자가 CI의 `pull_request` 트리거를 승인한 뒤의 자동 검사, 그리고 위 NOT RUN 항목의 실제 Windows 확인이다.
