# Universal Media Downloader — 시스템 설계 및 Gemini CLI 개발 지시서

버전: V1.1 (2026-11-01)
상태: 설계 제안. 4K Video Downloader+ 바이너리는 실제 분석하지 않았으며, 구현·실기기 테스트 결과가 아님.
기준: V1.0의 범용 추출·광고 필터·병렬·미리보기·Tor 설계 유지. REA 역공학 벤치마크와 macOS 고충실도/Windows 창 호환 설계를 추가.
개발 대상: Windows 10/11 x64 우선. macOS/Linux는 후속 포팅.
모델: Gemini CLI `gemini-3.1-pro-preview` (해당 계정에 모델 접근 권한이 있어야 함).

## 1. 목표 및 범위

### P0 필수
- URL 하나 또는 여러 개를 입력해 게시물 본문에 속한 이미지와 영상을 탐색한다.
- 전체 사이트 수집이 아닌 `현재 게시물`을 기본 범위로 한다. 게시판·연관 게시물·외부 링크로 자동 확장하지 않는다.
- 광고·배너·로고·프로필 이미지 등 주변 요소를 기본적으로 제외한다. 사용자는 제외된 항목도 미리보기에서 확인하고 복구할 수 있다.
- 다운로드 전 미리보기, 선택·선택 해제, 해상도 확인을 지원한다.
- 이미지 다량 다운로드와 중단·재시도·재개를 지원한다.
- 다운로드 작업마다 진행률·속도·상태·오류를 표시한다.
- macOS Finder/Photos 수준의 창 구조·계층·정밀 모션을 높은 충실도로 재현한다. 창 제어 버튼은 Windows 표준 위치·기능·접근성을 보존한다. Apple 독점 리소스와 상표는 무단 배포하지 않는다.

### P1 확장
- yt-dlp 및 gallery-dl 지원 사이트 통합.
- JavaScript 렌더링 페이지의 네트워크·DOM 분석.
- 사이트별 로그인 세션을 사용자가 직접 승인해 재사용.
- Google OAuth로 본인 YouTube 재생목록 메타데이터 불러오기.
- 사용자 선택 방식의 SOCKS 프록시와 Tor 마지막 대체 경로.
- 사용자 정의 필터 규칙과 도메인별 예외.

### 명시적 비목표
- 모든 사이트와 미디어에 대한 100% 성공률 보장.
- DRM 복호화, 유료벽·인증 우회, CAPTCHA 자동 무력화.
- 서비스 정책 또는 권한에 반하는 콘텐츠 다운로드 자동화.
- 사용자 승인 없는 사이트 전체 크롤링, 대규모 계정 검색.
- 계정 비밀번호 수집·저장.
- 4K Video Downloader+의 라이선스/DRM/보호장치 우회, 상용 코드 직접 복제·재배포, 내부 API 무단 사용.
- 분석 전 실제 내부 구조·속도·알고리즘을 확인했다고 주장하는 것.

## 2. 아키텍처

권장 기반: Python 3.12+ / PySide6 / Qt Quick(QML) / SQLite / HTTPX / asyncio.

UI(QML) → App Controller(PySide6 Signals/Slots) → Job Coordinator(asyncio worker) → Discovery Router → Extractor Adapter → Media Candidate Store → Filter & Ranker → Preview Cache → Download Scheduler → Storage.

외부 엔진: yt-dlp, gallery-dl, Playwright Chromium, FFmpeg/ffprobe. Tor는 별도 관리되는 선택형 SOCKS 서비스로 취급한다.

모든 네트워크 및 CPU 집중 작업은 UI 스레드에서 실행하지 않는다. UI로는 상태 이벤트와 제한된 빈도의 진척 이벤트만 전달한다.

### 모듈 경계
- `ui`: QML 화면, 토큰, 모션, 가상화된 그리드, 접근성.
- `app`: 화면-상태 연결, 사용자 명령, 작업 라이프사이클.
- `discovery`: URL 분류, 엔진 라우팅, 게시물 영역 탐지.
- `extractors`: yt-dlp/gallery-dl 어댑터와 범용 HTML/브라우저 어댑터.
- `ranking`: 본문 관련성 점수, 중복·광고 필터, 사용자 오버라이드.
- `preview`: 저해상도 썸네일, 동영상 포스터/메타데이터, LRU 캐시.
- `download`: 큐, 동시성, 재개, 청크 무결성, 원자적 저장.
- `network`: 요청 세션, DNS 정책, 인증 컨텍스트, 프록시.
- `auth`: OAuth 2.0 PKCE, OS 키 저장소, 사용자 브라우저 세션.
- `storage`: SQLite 스키마, 다운로드 이력, 설정, 캐시 인덱스.
- `tests`: 로컬 테스트 서버, 추출 fixture, UI·접근성·회복 시험.
- `research/competitor_4k`: 공개 기능 관찰·설치 파일 인벤토리·허용된 정적 분석의 증거와 비교 매트릭스. 배포 빌드와 분리.
- `ui/window_host`: Windows 네이티브 프레임·caption button·DPI·Snap Layout 호환 경계.
- `ui/design_system`: macOS 대응 구조·토큰·모션·아이콘 정합성/접근성 계약. 인가된 독립 제작 자산 사용.

## 3. 정품 4K Video Downloader+ 역공학 벤치마크 및 REA 활용

### 3.1 대상·목적·한계

- 대상 제품: 4K Video Downloader+ (사용자 소유 정품 설치본).
- 설치 기준 경로: `C:\Program Files\4KDownload\4kvideodownloaderplus`.
- 목표: UI 동작, 구성요소 경계, 다운로드 상태기계, 병렬 전송 전략, 포맷/자막/재생목록 처리, 실패 복구 방식의 **관찰 가능한 원리**를 파악한다.
- 실제 실행 파일 이름, 버전, 언어/런타임, DLL, CPU 사용률, 네트워크 동작, 내부 최적화 및 소스코드 수준 정보는 현재 **미확인**이다. 경로만으로 특정 기술 스택을 추정하지 않는다.
- 상용 정품을 소유해도 모든 역공학·코드 재사용 권한이 자동으로 생기지는 않는다. 관할 법률·EULA·서비스 약관을 확인한 범위에서 연구한다.
- 보안·인증·라이선스 보호 기능 제거 또는 변조, 키 추출, DRM 우회, 상용 코드 복제·재배포는 수행하지 않는다.
- 가장 안전한 기본 경로는 공개 문서 + 허가된 기능의 블랙박스 비교 + 독립 구현이다. 디컴파일은 허용 범위와 필요성을 확인한 후 진행한다.

### 3.2 REA 사용 전 준비 및 도구

공식 출처: `https://github.com/morluto/rea`; 설정 명령: `npx rea-agents setup`.
REA는 Gemini CLI MCP 연동을 지원한다. **스킬만 설치하는 것은 MCP 서버 설치와 다르다.**

- Node.js 충족 버전: 22.x >=22.23.4, 24.x >=24.22.1, 또는 26.12.1+ (공식 README 기준; 설치 시 재확인).
- REA 공식 배포원을 검증한 뒤 설치·등록. 설치 프로그램이 수정할 설정을 사전에 확인하고 백업.
- Windows 네이티브 심층 분석은 호환되는 Ghidra와 JDK를 별도로 준비해야 할 수 있다. REA의 Windows Ghidra 지원은 실험적이며 읽기 전용 지원 범위 등 제약이 있다.
- `rea doctor --json`/`rea providers --json`의 실제 결과를 기록한다. 요구된 공급자가 사용 불가하면 정적 파일 인벤토리와 블랙박스 관찰부터 진행한다.
- 디컴파일 결과는 **원래 소스가 아니다**. 의사코드, 함수 이름, 추론한 알고리즘에 증거 수준과 한계를 붙인다.
- REA 정적 분석은 로컬에서 진행되지만, 에이전트에게 전달한 결과는 모델 제공자의 데이터 정책을 따른다. 라이선스 키·계정 토큰·개인 쿠키를 프롬프트/로그에 포함하지 않는다.

```powershell
# Windows 사용자 환경에서 실행하는 준비 명령(미실행 안내)
$Target = 'C:\Program Files\4KDownload\4kvideodownloaderplus'
Test-Path -LiteralPath $Target
Get-ChildItem -LiteralPath $Target -Force | Select-Object Name, Length, LastWriteTime
node --version
npx rea-agents setup           # Gemini CLI MCP 등록을 선택하고 변경 사항 검토
# Gemini CLI 재시작 후 REA 연결 확인
# REA 명령을 사용할 수 있는 경우:
rea doctor --json
rea providers --json
```

설치 위치가 다르거나 실행 파일이 누락되면 추측하지 않고 결과를 `BLOCKED`로 기록한다. 읽기 권한만으로 조사한다. 시스템 설치 폴더의 파일을 변경하지 않는다.

### 3.3 조사 워크플로

1. **WO-00A: 공개 문서 조사.** 공식 기능 설명·지원 사이트·오류 처리·사용자 동작을 기록한다.
2. **WO-00B: 설치본 인벤토리.** 실제 경로·버전·파일 해시·디지털 서명·PE 헤더·DLL 목록·리소스 유형을 읽기 전용으로 수집한다.
3. **WO-00C: 구조 가설.** 바이너리별 역할, 실행 흐름, 네트워크/DB/브라우저 구성요소를 `증거/가설/미확인`으로 분리한다.
4. **WO-00D: 허가된 동작 비교.** 본인이 접근 가능한 테스트 미디어에서 URL 입력→메타데이터→큐→재시도→완료 흐름을 관찰한다.
5. **WO-00E: 제한적 심층 분석.** 법률·라이선스 확인 후, 필요한 바이너리에 한해 REA/Ghidra 정적 분석을 수행한다.
6. **WO-00F: 설계 추출.** 구조적 아이디어를 일반화하고 기존 yt-dlp/gallery-dl/FFmpeg/HTTPX 기능과 매핑한다.
7. **WO-00G: Clean-room 독립 구현.** 독자 코드로 동작 계약을 작성·구현하고 공개 샘플에서 비교 검증한다.

동작 관찰이 필요할 때는 사용자 세션으로 앱을 실행할 수 있다. 먼저 어떤 외부 연결·파일 변경이 발생하는지 알리고 테스트 전용 환경과 계정을 사용한다. 네트워크 캡처는 승인된 세션 및 비민감 데이터로 제한한다.

### 3.4 항목별 비교 매트릭스

| 영역 | 4K 관찰 질문 | 새 앱 구현 활용 | 증거 수준 |
|---|---|---|---|
| 초기 URL 분석 | 입력 즉시 도메인·미디어 유형을 어떻게 구분하나? | 경량 라우터 우선, 고비용 분석 후순위 | 미확인 |
| 미디어 추출 | 전용 추출기·내장 브라우저 중 언제 선택하나? | Adapter + fallback 구조 | 미확인 |
| 재생목록 | 대량 목록을 어떻게 페이지 단위 처리하나? | 스트리밍 후보 인덱싱·DB 저장 | 미확인 |
| 전송 스케줄러 | 파일별/호스트별 동시성·백오프 동작은? | 유한 큐·호스트 정책·조정 | 미확인 |
| 파일 재개 | 콘텐츠 변경·중단 후 무엇을 검증하나? | ETag/Range/길이 검증 계약 | 미확인 |
| FFmpeg | 어떤 포맷 변환·병합 단계가 보이나? | FFmpeg/ffprobe 재사용 | 미확인 |
| 인증 | 세션과 미디어 URL의 수명이 어떻게 작용하나? | 사용자 승인·최소 범위 보관 | 미확인 |
| 메모리 | 1,000개 이상 목록에서 자원 사용 양상은? | 가상화·lazy loading·batching | 미확인 |
| UI | 큐 진행·오류·재시도 표시 규칙은? | 사용자 경험 패턴 참고 | 공식 기능 확인, 내부 미확인 |

각 항목별 `evidence_id`, `observed_version`, `reproduction_steps`, `confidence`, `legal_review`, `implementation_decision`을 기록한다.

### 3.5 비용·개발 난이도 절감 규칙

- 이미 확보한 4K 라이선스를 **기술적 비교 대상**으로 이용한다. 라이선스를 새 앱에 재사용하거나 4K 기능을 자동 임베드한다고 가정하지 않는다.
- 새로운 영상 프로토콜 분석 엔진 개발보다 검증된 yt-dlp/gallery-dl + Playwright를 우선한다.
- 오디오/영상 병합·코덱 조사는 FFmpeg/ffprobe를 재사용한다.
- 4K 내부 코드를 직접 포팅하지 않는다. 확인된 성능 패턴을 독립 알고리즘 및 테스트 계약으로 변환한다.
- REA 조사 시간은 가설 검증 가치에 비례해 제한한다. 4K의 내부 구현이 추적 불가하면 즉시 공개 라이브러리 기반 설계로 복귀한다.
- 인건비 절감과 외부 유료 서비스 비용을 분리해 추적한다. 무료 오픈소스도 라이선스 의무와 배포 의무를 점검한다.
- 정적 분석에서 추정한 내용은 `측정됨`으로 표기하지 않는다. 실제 처리량·메모리는 동일 시험 조건에서 실측한다.

### 3.6 필수 산출물

`research/competitor_4k/`에 `INSTALL_INVENTORY.md`, `EVIDENCE_REGISTER.md`, `BEHAVIOR_MATRIX.md`, `ARCHITECTURE_HYPOTHESES.md`, `PERFORMANCE_BASELINE.md`, `CLEAN_ROOM_SPEC.md`, `LEGAL_LIMITS.md`, `COST_REDUCTION.md`를 작성한다.

WO-00은 분석에 의해 개발 구조가 바뀌는 시점이다. 실제 설치본 확인 없이 조사 완료를 선언하지 않는다.

## 4. URL 분석 및 미디어 추출 순서

1. 입력 URL을 검증한다. HTTP/HTTPS 외 스킴과 로컬/사설 IP 접속은 기본 차단한다.
2. 미디어 직접 URL이면 MIME/바이트 검사와 함께 미디어 후보를 만든다.
3. 지원 사이트라면 yt-dlp 또는 gallery-dl의 미리보기/메타데이터 추출을 우선 호출한다.
4. 나머지는 HTTP 응답으로 HTML, Open Graph, JSON-LD, `article`, `main`, `[role=main]`을 분석한다.
5. `img[src]`, `srcset`, `picture`, lazy-load 속성, `a[href]`, CSS background, `video/source`, 정당하게 접근 가능한 iframe 등을 조사한다.
6. JavaScript 필수 페이지는 Playwright로 렌더링한다. 선택된 게시물 범위만 조사한다.
7. 필요한 경우 사용자가 브라우저에서 직접 로그인한다. 인증 완료 후 승인된 세션만 해당 도메인에서 재사용한다.
8. 후보마다 본문 연관성·원본 URL·변형 URL·이미지 크기·형식·출처를 구조화한다.
9. 후보를 점수화하고 중복을 합친다. 제외 후보는 별도 섹션에 보존한다.
10. 사용자 선택이 끝나면 다운로드 큐를 구성한다.

### 후보 공통 데이터 계약
```
MediaCandidate {
  id, source_page_url, post_scope_id, canonical_url,
  fetch_url, preview_url, origin_engine,
  kind: image|video|animation,
  mime, width, height, file_size_estimate,
  title, page_order, dom_path, context_text,
  source_roles[], confidence, exclusion_reasons[],
  variants[], auth_context_id, referer, requires_browser,
  requires_user_action, selection_state
}
```

`blob:` URL은 독립 다운로드 URL로 간주하지 않는다. 네트워크에서 원본을 확인하지 못하면 브라우저 재생 미리보기만 제공한다.

## 5. 본문 이미지 식별 및 광고 필터

첫 단계에서 본문 컨테이너를 식별한다. `article`, `main`, Schema.org Article, 게시물 고유 ID 및 갤러리 반복 패턴을 근거로 사용한다.

아래 점수는 초기 휴리스틱의 예시이며 실사이트에서 조정한다.

| 신호 | 예시 점수 |
|---|---:|
| 게시물 본문 내부 | +45 |
| 본문 캡션·문단과 인접 | +15 |
| 갤러리 순서·원본 이미지 링크 | +20 |
| 충분한 실해상도(예: 600px 이상) | +10 |
| 명시적인 광고·후원 컨테이너 | -80 |
| 네비게이션·헤더·푸터 | -55 |
| 아바타·로고·아이콘 구역 | -45 |
| 미세한 추적 픽셀 | -100 |
| 게시물 외부 추천 카드 | -40 |

점수만으로 필터링하지 않는다. 원본 도메인, DOM 위치, 자연 크기, 이미지의 alt/캡션, 주변 링크, 반복되는 광고 슬롯을 함께 고려한다.

- 이미지의 원본 해상도와 썸네일 URL을 묶는다.
- 완전히 동일한 바이트는 SHA-256으로 식별한다. 리사이즈된 유사 이미지는 pHash로 그룹화하되 자동 삭제하지 않는다.
- `본문만`(기본), `본문+첨부`, `모든 후보` 세 가지 모드를 제공한다.
- 제외 사유를 설명한다. 사용자가 한 번의 클릭으로 후보를 복원한다.
- 게시물 본문 안의 작은 그림·만화 컷·텍스트 이미지를 무조건 제외하지 않는다.
- 기본값은 광고 오탐으로 인한 누락보다 사용자 검토 가능한 명시적 제외를 우선한다.

## 6. 미리보기 UX

- 첫 분석 화면에서 게시물 제목, URL, 이미지·영상·제외 후보 개수를 표시한다.
- 3~6열 가변 그리드를 제공한다. 5,000개 후보에서도 가상 스크롤을 적용한다.
- 미리보기는 우선 저해상도·저용량만 요청하고, 화면에 들어올 항목을 선행 로드한다.
- 이미지 클릭 시 고화질 프리뷰(저장과 분리)를 열고 방향키로 탐색한다.
- 영상은 썸네일·길이·해상도·사용 가능한 포맷을 우선 보여준다.
- 합법적으로 이용 가능한 임베드 플레이어 또는 지원되는 스트림만 재생한다.
- 서버가 Range를 지원하지 않거나 영상이 DRM 보호 상태라면 다운로드 전 영상 재생을 보장하지 않는다.
- 체크박스, 전체 선택, 범위 선택, 정렬, 해상도별 필터를 제공한다.
- 후보 썸네일 LRU 캐시를 사용하고 원본 이미지를 모두 메모리에 올리지 않는다.

## 7. 병렬 다운로드

기본 동시성 목표값(실측 후 재조정): 전체 이미지 작업 12개, 호스트당 3개, 영상 2개.

- 사용자 프리셋: 안정 4/2, 균형 12/3, 빠름 24/4 (전체/호스트별 이미지 작업 수).
- HTTP 429 또는 `Retry-After`를 받으면 해당 호스트 요청을 지연한다. 지수 백오프와 지터를 적용한다.
- HTTP 401은 인증 요청, 403은 서버 제한/권한 안내, 404는 소스 없음으로 구분한다.
- 서버가 `Accept-Ranges`와 유효한 `Content-Range`를 제공하는 대형 파일만 분할 다운로드 후보로 검토한다.
- 작은 이미지 파일은 파일당 한 연결을 기본으로 하고 다수 파일을 병렬 처리한다.
- 영상 HLS/DASH 조각 동시 다운로드는 yt-dlp 기능에 위임한다.
- `ETag`/`Last-Modified`/파일 길이를 이용해 안전한 재개 가능성을 검증한다. 원본 변경 시 무조건 이어붙이지 않는다.
- 스트리밍으로 `.part` 파일에 기록한 뒤 검증하고 원자적으로 최종 파일명으로 이동한다.
- 충돌하는 파일명, 특수 문자, Windows 예약어, 경로 길이, Unicode 정규화 문제를 처리한다.
- SQLite에 작업과 상태를 저장하고 앱 재시작 시 복원한다.
- `Cancel`은 실제 실행 중인 네트워크 요청 및 하위 프로세스를 취소해야 한다.
- 토큰 버킷으로 전체/호스트별 최대 속도를 제한할 수 있다.
- 프록시/Tor 사용 중에는 보수적인 연결 수로 전환한다.

작업 상태: `QUEUED → DISCOVERING → READY → RUNNING → VERIFYING → COMPLETED`. 중간 분기로 `PAUSED`, `RETRY_WAIT`, `AUTH_REQUIRED`, `ACCESS_LIMITED`, `FAILED`, `CANCELLED`를 둔다.

## 8. 접근 실패 및 대체 경로

1. 정상 HTTP/HTTPS 요청.
2. 사이트 전용 추출기와 공식적으로 제공되는 미디어 URL 경로.
3. 렌더링이 필요한 경우 실제 브라우저 실행.
4. 사용자가 직접 로그인한 세션 이용(필요한 도메인만).
5. 캐시·HTTP 헤더·일시적 네트워크 오류를 진단하고 안전하게 재시도.
6. 사용자가 지정한 프록시(선택).
7. Tor SOCKS 연결(사용자가 명시적으로 활성화한 경우만).

- Tor는 IP·네트워크 경로를 바꾸는 수단이지 인증·저작권·DRM 제한을 해제하지 않는다.
- Tor 연결은 `socks5h://127.0.0.1:9050`을 기본 예시로 삼되 실제 로컬 서비스 주소를 감지/설정한다.
- DNS 요청까지 프록시를 통과시키고 실제 Tor 경로를 테스트한다.
- 미리보기, 썸네일, 다운로드, 브라우저 요청이 서로 다른 경로로 새지 않도록 한 작업의 경로 정책을 통일한다.
- 실수로 직접 연결하는 fallback은 금지한다. Tor 작동 실패 시 중지 후 사용자에게 알린다.
- Tor 속도 저하, 사이트의 Tor 출구 차단, 계정 보안 알림 가능성을 명시한다.
- CAPTCHA는 사용자가 직접 수행한다. 자동 우회는 구현하지 않는다.
- 모든 실패는 HTTP 상태, 발생 단계, 복구 가능성, 사용자가 취할 조치를 구분해 표시한다.

## 9. YouTube 통합

- Google OAuth 2.0 Authorization Code + PKCE로 외부 브라우저 로그인을 진행한다.
- `youtube.readonly` 최소 범위만 요청한다.
- `playlists.list(mine=true)`로 본인 재생목록을 조회한다.
- `playlistItems.list`로 영상 제목, ID, 썸네일, 순서를 페이지 단위로 조회한다.
- 비공개 영상·삭제된 영상은 불가용 상태로 표시한다.
- 조회한 재생목록은 앱 내에서 탐색·선택·링크 내보내기를 지원한다.
- YouTube Data API의 인증 토큰을 영상 원본 다운로드 권한으로 취급하지 않는다.
- YouTube API 개발자 정책은 사전 승인 없는 시청각 콘텐츠 다운로드·백업·캐시·오프라인 저장을 제한한다.
- 다운로드 기능은 권리 및 서비스 허용 조건을 충족하는 콘텐츠/경로에만 노출한다. 본인이 업로드한 YouTube 콘텐츠는 공식 Studio/Takeout 방식도 안내한다.
- 사용자 Google 비밀번호를 앱에 입력시키거나 저장하지 않는다.

## 10. UI/UX V1.1: macOS Finder/Photos 고충실도, Windows 네이티브 창 기능

### 10.1 디자인 기준 (기존 V1.0 시안 대체)

디자인 참조는 macOS Tahoe 계열 Finder/Photos의 **정보 밀도, 재질, 기하학, 타이포그래피, 탐색 구조, 모션 문법**이다. 일반적인 Windows 앱에 Apple식 둥근 카드만 적용하는 접근은 금지한다.

- 좌측의 풀높이 **반투명 Sidebar**, 오른쪽 콘텐츠 영역, 상단의 **연속된 통합 Toolbar**를 사용한다.
- 화면은 한 개의 데스크톱 애플리케이션 창으로 느껴지게 구성한다. 앱 내부에 또 다른 두꺼운 카드형 외곽 프레임을 넣지 않는다.
- 사이드바 너비의 초기값은 232px(제안), 펼침 216~280px, 숨김 가능. 창 폭이 좁으면 자동으로 축소/접는다.
- 툴바 높이의 초기값은 60px(제안). 주요 기능은 좌→우 탐색, 컨텍스트 제목, 중앙 URL 입력, 선택·보기 조작으로 배치한다.
- 콘텐츠 배경은 라이트에서 밝은 중성색, 다크에서 균일한 어두운 중성색을 사용한다. 카드 남용·두꺼운 그림자·과한 색상 강조 금지.
- 미디어 그리드는 Photos의 콘텐츠 우선 원칙을 적용한다. 썸네일 사이 간격·비율·크기 변화를 제어하고, 선택 상태만 강조한다.
- Inspector는 오른쪽에 300~340px 폭으로 열리며, 이미지 메타데이터·원본 URL·필터 근거를 포함한다.
- 하단 상태영역은 얇고 절제되게 유지한다. 다운로드 실행 시에만 필요한 상태를 확장한다.
- 아이콘 크기·스트로크·baseline을 전부 통일한다. 아이콘을 사이트마다 임의 혼합하지 않는다.
- Mac의 세 개 traffic-light 창 제어 버튼과 macOS 전용 전역 메뉴바를 흉내 내지 않는다. Windows 창 버튼은 반드시 오른쪽에 둔다.

### 10.2 창 프레임과 Windows 준수: 최우선 P0

**고충실도 Apple 미학과 Windows 네이티브 동작을 분리한다.**

- 기본 권장: Windows가 caption 버튼 영역을 소유하도록 한다. Qt/PySide6 호스트에서 통합 툴바의 나머지 영역만 맞춤 디자인한다.
- 고급 방식: 프레임 확장/커스텀 title bar를 선택하되 Win32 HWND, DWM, non-client hit-test, caption 버튼 동작을 보존한다. Qt의 nativeEvent/Win32 연동은 실제 검증 후에만 채택한다.
- 오른쪽 순서 **최소화 / 최대화·복원 / 닫기**. 최대화 버튼에 Windows 11 Snap Layout hover를 유지한다.
- `Win+Z`, `Win+←/→`, `Alt+Space`, `Alt+F4`, 타이틀바 더블클릭, 드래그 스냅, 네 모서리 resize, 멀티 모니터, 작업 표시줄 활성화/복원을 테스트한다.
- Windows 10/11 100/125/150/200% 배율 및 모니터 간 DPI 전환을 시험한다. fullscreen, maximized, normal 상태에서 클리핑 금지.
- Qt의 `startSystemMove`/`startSystemResize`를 우선 고려한다. 자체 마우스 좌표로 창을 강제 이동·리사이즈하는 방식은 피한다.
- Snap Layout 등 시스템 동작이 커스텀 타이틀바에서 완전하게 작동하지 않으면 **네이티브 타이틀바로 즉시 fallback**한다. 디자인을 위해 OS 기능을 희생하지 않는다.
- UI 테스트는 제목 표시줄 버튼 모양뿐 아니라 실제 입력·화면 전환·보조기술에서의 동작을 포함한다.

### 10.3 구성요소별 Mac 참조 계약

| UI 구역 | 참조 행동/외형 | 구현 요구 |
|---|---|---|
| Sidebar | Finder와 유사한 translucent sidebar | 그룹 헤더, 얇은 선택 하이라이트, 일관된 아이콘 |
| Toolbar | Finder의 공간 절약형 통합 도구막대 | 정렬된 pill/segmented controls, 가변 레이아웃 |
| URL 필드 | macOS 검색 입력 필드의 조용한 질감 | 약한 내부 채움, 명확한 포커스 링, 붙여넣기 지원 |
| 미디어 그리드 | Photos의 콘텐츠 중심 패턴 | 낭비 없는 여백, hover 오버레이, 부드러운 다중 선택 |
| Inspector | macOS 정보 패널 느낌 | 고정된 정보 계층, 부드러운 폭 전환, URL/필터 설명 |
| 다운로드 목록 | macOS 작업 목록 느낌 | 진행률 정확, 접근성 상태 음성, 오류별 명확한 조치 |
| Popover | macOS anchored popover | 부모 컨트롤 위치를 기준으로 발생, 외부 클릭 닫기 |
| Confirmation | 운영체제 대화상자 의미 구조 | 안전한 기본값, `Esc`, 키보드 포커스와 복귀 |

### 10.4 시각 토큰 (시작점이며 픽셀 기준 검증 후 조정)

- 메인 타이포그래피: Windows에서 합법적으로 설치된 `Segoe UI Variable`을 기본 사용. Apple SF Pro/SF Symbols를 무단 번들하지 않는다.
- 기본 서체 크기: Sidebar/Toolbar 12~13px, 콘텐츠 설명 12~13px, 제목 21~26px. 굵기 400/500/600 중심.
- 모듈 여백: 4/8/12/16/20/24px. 과한 32~40px 간격으로 정보 밀도를 떨어뜨리지 않는다.
- 창 내 반경: 입력 10~12px, pill 12~16px, 팝오버 14~18px, 정보 패널 0~16px(위치별). 모든 요소를 16px로 획일화하지 않는다.
- 라이트: window `#F7F7F9`, canvas `#FFFFFF`, sidebar `rgba(241,242,246,.76)`, border `rgba(30,35,50,.09)`, text `#1D1D1F`, muted `#777780`.
- 다크: window `#16171B`, canvas `#1C1D21`, sidebar `rgba(38,39,45,.74)`, text `#F5F5F7`, muted `#A0A1AA`.
- accent 초기값: `#007AFF`. 사용자의 Windows accent/고대비 설정 고려. 포인트 색 사용을 선택 강조/주행동에 한정한다.
- Material: Sidebar/Toolbar/Popover에만 동적 반투명·블러·얇은 highlight border. 콘텐츠 레이어 전체에 유리 효과를 적용하지 않는다.
- Win11 환경에 따라 Mica/아크릴을 검토한다. 해당 효과가 없는 OS나 원격 데스크톱에서는 불투명 fallback.
- 모든 상태에서 WCAG 대비 및 Windows High Contrast 대응을 검사한다. Mac과 유사한 외형을 위해 가독성을 희생하지 않는다.

### 10.5 고급 모션/마이크로 인터랙션 계약

- `MotionToken`: duration, easing/spring stiffness, damping, mass, amplitude, cancelPolicy, reducedMotionAlternative를 필수로 정의한다.
- 버튼 hover: 90~130ms, opacity/tonal fill 위주. 클릭: 90~120ms, 지나친 scale down 금지.
- Sidebar 선택: 150~210ms, 하이라이트 위치와 opacity로 공간 연속성을 표현한다.
- Inspector open/close: 260~340ms, 감쇠 spring, 불필요한 과반동 방지. 진행 중 재조작 시 즉시 역방향 전환한다.
- 팝오버: 150~210ms, scale 0.97→1.0 및 4~6px 이동. 사용자 조작점 기준으로 앵커한다.
- 프리뷰 확대: 220~320ms, 썸네일의 실제 위치→확대 영역까지 연결되는 shared-element 느낌을 구현한다. 프리뷰 종료 시 복귀 위치를 유지한다.
- 썸네일 등장: 최초 viewport 내 페이드 120~180ms. 수천 장을 한 번에 stagger 애니메이션하지 않는다.
- 그리드 선택: 140~210ms, 체크 아이콘과 약한 outline 전환. 동일 프레임 내 다중 선택은 그룹화한다.
- 다운로드 중: 숫자·막대 상태는 실제 전송값을 평활 처리해 그린다. 무한 과장 애니메이션 및 가짜 진행률 금지.
- 성공 상태: 160~230ms 이내로 작은 check·색상 반응만 사용. 필요 없는 confetti/particle 금지.
- `Reduce Motion`: 위치 이동·spring·shared-element 대신 crossfade 또는 즉시 변경. 사용자의 설정을 존중한다.
- 애니메이션은 UI 스레드의 파일/네트워크 작업과 분리한다. 레이아웃 재계산·거대한 실시간 블러를 줄인다.
- 모션 품질은 단일 시간값이 아니라 입력 지연, 연속성, 방향, 감쇠, 인터럽트 처리로 평가한다.

### 10.6 창 레퍼런스 시안

- `docs/design/window-prototype.html`은 오프라인에서 열 수 있는 **UI 시각 시안**으로 제공한다. 실제 다운로드 엔진과 연결되지 않은 mock 데이터임을 표시한다.
- 뷰포트 1440×900, 1280×800, 1024×768 / DPI 100~200%에서 시각적 일관성을 비교한다.
- 실제 Qt 스크린샷을 공식 macOS Finder/Photos 레퍼런스와 나란히 검토한다. 유사도 평가는 툴바 배치, 여백·타이포 비율, 사이드바 재질, 모션 동작, 계층과 색상에 대해 실시한다.
- Pixel-perfect를 주장하려면 실제 네이티브 앱 렌더와 참조 환경 버전을 명시해야 한다. HTML 목업만으로 검증 완료 판정 금지.

### 10.7 키보드·접근성

- URL 붙여넣기 → 주소 인식 → 분석 → 썸네일 점진적 채움 → 다중 선택 → 다운로드.
- `Ctrl+A` 후보 전체 선택, `Ctrl+F` 검색, `Space` 프리뷰, `Esc` 패널 닫기/취소, `Ctrl+V` 붙여넣기.
- 키보드만으로 전체 기능에 접근. focus indicator, 화면 읽기용 이름·역할·상태·읽기 순서 보존.
- Windows 기본 대화상자와 충돌하지 않는 단축키 설계를 검증한다.

## 11. 보안·권한·개인정보

- URL 검증, 최종 리다이렉트 목적지 검증. 기본적으로 `localhost`, 루프백, 사설 주소, 링크 로컬, 클라우드 메타데이터 IP 차단.
- 다운로드 전후 MIME과 실제 파일 시그니처를 확인한다. HTML 오류 페이지를 JPEG로 저장하지 않는다.
- 이미지/영상 미리보기는 샌드박스 또는 신뢰할 수 있는 디코더로 처리한다. 임의 웹 스크립트는 앱 프로세스 권한으로 실행하지 않는다.
- 인증 정보는 Windows DPAPI 또는 운영체제 키 저장소에 보관한다. SQLite에는 토큰 원문을 기록하지 않는다.
- 쿠키 내보내기 파일은 원칙적으로 사용하지 않는다. 불가피하면 명시적 동의·최소 권한·짧은 수명·안전한 삭제를 사용한다.
- 로그에 Authorization, Cookie, OAuth token, 민감한 쿼리 문자열을 출력하지 않는다.
- 외부 실행 파일/추출 엔진은 고정 버전·검증된 배포 소스·해시 확인을 이용한다.
- 프로그램 설치 시 관리자 권한을 요구하지 않는다. 사용자가 허용한 폴더에만 파일을 쓴다.
- 규정 준수: 콘텐츠 권리, 서비스 이용약관, 사이트의 접근 정책을 존중한다.

## 12. DB 스키마 제안

- `jobs(id, url, scope, status, engine, proxy_mode, created_at, updated_at, error_code)`
- `candidates(id, job_id, canonical_url, kind, metadata_json, score, selected, excluded_reason)`
- `downloads(id, job_id, candidate_id, destination, temp_path, total_bytes, completed_bytes, etag, status, sha256)`
- `settings(key, value_json)`
- `site_rules(hostname, rule_version, selectors_json, overrides_json)`
- `preview_cache(key, path, size_bytes, last_accessed)`
- `oauth_accounts(id, provider, label, token_keyring_ref, scopes)`

모든 다중 테이블 갱신은 트랜잭션으로 묶는다. 스키마 마이그레이션을 버전 관리한다.

## 13. 폴더 구조

```
universal-media-downloader/
  pyproject.toml
  README.md
  docs/
    architecture.md
    ui-motion-spec.md
    extraction-rules.md
    security.md
    reverse-engineering-4k.md
    design/
      window-prototype.html
      apple-reference-matrix.md
      windowing-windows.md
  src/umd/
    __main__.py
    app/
    ui/qml/
      Main.qml
      components/
      screens/
      tokens/
    core/
      types.py
      coordinator.py
      events.py
    discovery/
      router.py
      article_detector.py
      media_scanner.py
    extractors/
      ytdlp_adapter.py
      gallerydl_adapter.py
      html_adapter.py
      playwright_adapter.py
    ranking/
      relevance.py
      dedupe.py
    preview/
      cache.py
      thumbnails.py
    download/
      scheduler.py
      transfer.py
      resume.py
    network/
      client.py
      proxy.py
      url_policy.py
    auth/
      oauth_youtube.py
      secrets.py
    storage/
      database.py
      migrations/
  tests/
    fixtures/
    unit/
    integration/
    e2e/
  research/
    competitor_4k/
      INSTALL_INVENTORY.md
      EVIDENCE_REGISTER.md
      BEHAVIOR_MATRIX.md
      ARCHITECTURE_HYPOTHESES.md
      PERFORMANCE_BASELINE.md
      CLEAN_ROOM_SPEC.md
      LEGAL_LIMITS.md
      COST_REDUCTION.md
  tools/
    packaging/
```

## 14. 개발 단계·승인 기준 (V1.1)

### WO-00: REA 환경·4K 정품 제품 벤치마크

구현 전 조사: 문서 기능 목록, 설치본 인벤토리, 실행/정적 분석의 법적·기술적 가능 범위 검토, 기능별 증거 레지스터, 비용 절감 후보, clean-room 구현 사양.

검증: 원본 파일 무변경, 버전/해시/실제 실행 파일 목록 기록. REA 연결·Windows native provider 지원 상태 증거. 내부 구조 미확인 시 가설로 표시. 라이선스/개인정보 누출 0건. 다운로드 엔진 설계에 참고할 근거를 제시.

판정: REA 네이티브 분석이 불가능해도 UI 블랙박스/공개 문서 + 오픈소스 우선 계획이 완료되면 `CONDITIONAL GO`로 WO-01 진행 가능.

### WO-UI-00: 화면 정체성 및 Windows 창 기능 기준선

구현: high-fidelity window prototype, QML 디자인 토큰, 윈도우 기본 프레임/제어 버튼 결합 시험.

검증: Finder/Photos 구조와 비교한 시각 리뷰, Windows 10/11 최소화/복원/닫기/Snap/Alt+Space/멀티모니터/DPI. 기능 실패 시 네이티브 프레임 fallback.

판정: UI 설계는 WO-01부터 활용한다. WO-05에 전체 재디자인을 몰아 넣지 않는다.

### WO-01: 기능적 MVP

구현: QML 메인 화면, URL 입력, HTML 본문 스캐너, 후보 필터, 썸네일 그리드, 이미지 다운로드, SQLite, 기본 테스트.

검증: 고정 HTML fixture의 본문 이미지 수와 순서 일치. 광고·프로필 이미지가 기본 결과에서 제외되며 복원 가능. 다운로드 취소 가능. 앱 재시작 시 작업 이력 유지.

### WO-02: 다운로드 신뢰성

구현: HTTPX 비동기 스케줄러, 호스트별 동시성, 429 백오프, 재개, 무결성, 일괄 선택, 5,000개 가상화 리스트.

검증: 로컬 모의 서버의 5,000개 파일을 누락·손상 없이 완료. 네트워크 중단 후 재개. 동일 이름 충돌 처리. 429 시 요청량 감소. 악의적인 경로 이름 차단.

### WO-03: 전문 엔진

구현: yt-dlp/gallery-dl 어댑터, FFmpeg, 포맷 선택, 썸네일·영상 메타데이터, 사이트별 오류 표시.

검증: 허가된 샘플 URL과 공개 테스트 미디어에서 엔진 진단 성공. 영상별 포맷 목록 정확. 지원하지 않는 미디어는 설명 가능한 오류로 종료.

### WO-04: 브라우저 및 인증

구현: Playwright, JS 갤러리 분석, 로그인 세션 수동 승인, OAuth 재생목록 조회, 프록시/Tor 선택 모드.

검증: SPA fixture 추출. 인증 누출 방지. Tor 프록시 미실행·DNS 실패 시 직접 연결로 떨어지지 않음. OAuth 재생목록 목록·페이지네이션 검증.

### WO-05: 디자인 품질/성능/배포

구현: macOS 고충실도 컴포넌트·모션 마감, 다크/라이트, 접근성, 리소스 최적화, Windows 패키징.

검증: 고정된 실제 macOS UI 레퍼런스와 구조/시각 비교. Windows 10/11 100/125/150/200% 배율, Win+Z·Snap Layouts, 5,000개 항목 스크롤, Reduce Motion, 키보드·화면 읽기, 설치/삭제/업데이트.

성능 목표(실측 전): 일반급 Windows PC에서 5,000개 후보 리스트 스크롤 평균 55 FPS 이상, 앱 메인 스레드 100ms 초과 중단 이벤트 0건. 테스트 환경·측정 방식·실패를 보고한다.

### 비용 추적

`cost/baseline.csv`에 항목별 신규 라이선스 구매액, 유지비, 외부 API 비용, 선택적 유료 분석기 비용, 무료 대체재, 구현 시간(실측)을 구분하여 기록한다. 기존 4K 정품 구매액은 기보유 비용으로 구분한다. **현재까지 비용·시간 절감률은 실측하지 않았다.**

## 15. 개발 지시 운영 규칙

- Gemini CLI는 각 WO를 한 번에 하나씩 처리한다. WO-00과 WO-UI-00은 기능 구현 이전에 우선한다.
- 상용 프로그램의 내부 아키텍처·최적화 방식은 실측과 근거가 나오기 전까지 전부 미확인으로 표기한다.
- REA의 디컴파일 의사코드는 직접 포팅·재배포하지 않는다. clean-room 설계 계약을 통해 독립 구현한다.
- 운영체제 창 제어 기능이 디자인과 충돌하면 Windows 네이티브 동작을 우선한다.
- 실제 macOS와 유사한 품질은 시각적 비교·실기기 동작 검증으로 확인한다.
- 작업 시작 전에 기존 코드·패키지·테스트를 확인한다.
- 새 엔진 작성보다 검증된 오픈소스 사용을 우선한다.
- UI 데모만 제작하고 기능을 완료로 보고하지 않는다.
- 네트워크/로그인/DRM 실패를 거짓 성공으로 표시하지 않는다.
- 각 단계마다 변경 파일, 실행 명령, PASS/FAIL/NOT RUN/BLOCKED, known limitations를 보고한다.
- 라이브 사이트 테스트는 명시적으로 접근 가능한 샘플만 사용한다.
- UI 테스트에서는 실제 렌더링 캡처, 모션 검증, 입력 접근성 검증을 수행한다.
- 단계 종료 시 다음 단계 진입 여부를 GO/NO-GO로 판정한다.

## 16. Gemini CLI 시작 명령

```powershell
npm install -g @google/gemini-cli@latest
gemini --version
gemini -m gemini-3.1-pro-preview
```

실제 모델 접근 가능 여부는 CLI `/model`의 Manual 목록에서 확인한다. 최신 모델 별칭과 사용 한도는 계정마다 달라질 수 있다.

## 17. 참고 공식 출처

- Gemini CLI 모델: https://geminicli.com/docs/get-started/gemini-3/
- yt-dlp: https://github.com/yt-dlp/yt-dlp
- gallery-dl: https://codeberg.org/gallery-dl/gallery-dl
- Playwright 네트워크: https://playwright.dev/python/docs/network
- Qt Quick 모션: https://doc.qt.io/qt-6/qtquick-statesanimations-animations.html
- Apple HIG Materials: https://developer.apple.com/design/human-interface-guidelines/materials
- Apple HIG Motion: https://developer.apple.com/design/human-interface-guidelines/motion
- YouTube OAuth: https://developers.google.com/youtube/data/guides/auth/installed-apps
- YouTube playlist 구현: https://developers.google.com/youtube/data/guides/implementation/playlists
- YouTube API 정책: https://developers.google.com/youtube/terms/developer-policies
- Tor SOCKS DNS 확인: https://support.torproject.org/little-t-tor/troubleshooting/check-for-leaks/

- REA official: https://github.com/morluto/rea
- REA Windows Ghidra (experimental): https://github.com/morluto/rea/blob/main/docs/windows-ghidra-p0.md
- 4K Video Downloader+ official: https://www.4kdownload.com/products/videodownloader-42
- Windows title bar: https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/title-bar
- Windows Snap Layouts: https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/apply-snap-layout-menu
- Qt Window startSystemMove/startSystemResize: https://doc.qt.io/qt-6/qml-qtquick-window.html
- Apple HIG sidebars: https://developer.apple.com/design/human-interface-guidelines/sidebars
- Apple HIG materials: https://developer.apple.com/design/human-interface-guidelines/materials
- Apple HIG toolbars: https://developer.apple.com/design/human-interface-guidelines/toolbars
