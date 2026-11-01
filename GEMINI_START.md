# Gemini CLI 첫 작업 지시서 — Universal Media Downloader V1.1

역할: Windows 데스크톱 다운로드 프로그램의 수석 아키텍트, 합법적 역공학 분석가, Qt/QML UI 엔지니어.

필수 읽기:
- `docs/ARCHITECTURE.md`: 개발 설계 V1.1
- `docs/design/window-prototype.html`: macOS 고충실도/Windows caption 버튼 창 디자인 시안

## 우선순위

첫 단계는 `WO-00`(4K Video Downloader+ 분석 기반 확보)과 `WO-UI-00`(창/디자인 시스템 검증)이다. 두 작업이 끝나기 전 대규모 전체 기능 구현으로 넘어가지 마라. 단, 분석 기능이 특정 환경에서 차단된 경우 문서에 명시한 fallback을 적용하라.

## WO-00 — REA + 4K Video Downloader+ 제품 분석

분석 대상 경로: `C:\Program Files\4KDownload\4kvideodownloaderplus`.

사용자는 이 프로그램의 정품 라이선스를 보유한다. 그러나 소유권만으로 모든 역공학이나 코드 재사용이 허용되는 것은 아니다. EULA와 적용 법률을 확인하고 허용 범위에서만 조사하라.

1. 작업 이전에 기존 저장소/디자인 파일/기술 스택을 확인하라.
2. 대상 경로 존재 여부를 실제로 확인하라. 경로가 없으면 추측하지 마라.
3. 사용 중인 4K Video Downloader+ 버전, 실행 파일, DLL, 리소스, 서명을 읽기 전용으로 조사하라.
4. REA의 공식 배포원을 확인하고 `npx rea-agents setup`의 제안 변경 사항을 검토하라.
5. Gemini CLI에 REA MCP를 연결하고 실제 도구 목록·doctor·provider 상태를 확인하라.
6. Windows native 분석이 필요하면 호환되는 Ghidra/JDK의 설치 여부와 지원 범위를 먼저 확인하라.
7. 설치 과정에서 유료 결제, 관리자 권한, 시스템 변경이 요구되면 사용자 승인을 먼저 받아라.
8. 공개 기능, UI 흐름, 미디어 파싱, 큐 관리, 재시도, 포맷 선택, 인증, 다운로드 재개, 자원 사용을 근거 수준별로 분석하라.
9. 디컴파일 의사코드를 원본 소스코드라고 주장하지 마라.
10. 라이선스 검증, DRM, 보호장치, 계정 인증을 우회하거나 수정하지 마라.
11. 라이선스 키/토큰/쿠키/개인정보를 수집하거나 분석 로그에 노출하지 마라.
12. 4K의 상용 코드를 직접 복사하지 마라. 동작 계약과 검증 증거를 바탕으로 독립 구현 사양을 작성하라.
13. 해당 기능이 yt-dlp, gallery-dl, HTTPX, Playwright, FFmpeg에서 이미 제공되는지 비교하라.
14. 엔진 재구현을 피할 수 있는 영역과 독립 개발이 필요한 영역을 구분하라.
15. 동일 조건의 허가된 테스트 자료를 이용해 경쟁 제품 대비 성능 기준선을 측정하라. 측정할 수 없으면 NOT RUN으로 기록하라.
16. 결론을 `VERIFIED / INFERRED / UNKNOWN / BLOCKED`로 구분하라.

필수 산출물:
- `research/competitor_4k/INSTALL_INVENTORY.md`
- `research/competitor_4k/EVIDENCE_REGISTER.md`
- `research/competitor_4k/BEHAVIOR_MATRIX.md`
- `research/competitor_4k/ARCHITECTURE_HYPOTHESES.md`
- `research/competitor_4k/PERFORMANCE_BASELINE.md`
- `research/competitor_4k/CLEAN_ROOM_SPEC.md`
- `research/competitor_4k/LEGAL_LIMITS.md`
- `research/competitor_4k/COST_REDUCTION.md`

## WO-UI-00 — macOS 고충실도 UI + Windows 창 기능

1. `docs/design/window-prototype.html`의 시각 구조를 분석하라.
2. macOS Finder/Photos의 툴바, 사이드바, 콘텐츠 계층, 타이포그래피, 마이크로 인터랙션을 참조하라.
3. Apple 전용 저작물/상표/폰트를 무단 번들하지 마라. Windows에서 사용 가능한 대체 자산을 일관되게 사용하라.
4. PySide6 + Qt Quick/QML로 실제 화면 구조를 제작하라. HTML 프로토타입을 최종 앱으로 포장하지 마라.
5. 최소화, 최대화/복원, 닫기 버튼을 우측 상단 Windows 순서로 유지하라.
6. Windows Snap Layouts, Win+Z, Alt+Space, Alt+F4, resize, 드래그 스냅, 다중 모니터 DPI 전환을 보존하라.
7. 우선 시스템 창 제어 버튼을 유지하는 통합 툴바를 검토하라. Frameless 방식은 실제 동작 검증 후에만 적용하라.
8. native window 동작을 복구할 수 없으면 Windows 기본 제목 표시줄로 fallback하라.
9. 독립된 디자인 토큰, 모션 토큰, QML 컴포넌트를 작성하라.
10. Spring 기반 패널 전환, 포커스 반응, 콘텐츠 확대, 절제된 유리 효과를 구현하라.
11. 애니메이션 인터럽트와 Reduce Motion 대응을 검증하라.
12. 라이트/다크, 100/125/150/200% DPI, 1440×900/1280×800/1024×768 크기를 검증하라.
13. 실제 앱 캡처와 실제 참조 UI를 비교하라. 픽셀 정합을 주장하려면 근거를 남겨라.

필수 산출물:
- `docs/design/APPLE_REFERENCE_MATRIX.md`
- `docs/design/WINDOW_HOST_CONTRACT.md`
- `docs/design/MOTION_TOKENS.md`
- `docs/design/UI_REVIEW.md`
- 실제 실행 가능한 QML 디자인 시스템 코드와 테스트 결과

## 종료 보고서 규칙

- 결과: `PASS / FAIL / NOT RUN / BLOCKED`를 구분하라.
- 구현·관찰·가설·미확인을 분리하라.
- 실행 명령, 파일 변경사항, 시험 환경, 실제 스크린샷, 실패 원인, 롤백 절차를 보고하라.
- 유료 지출 금지: 비용 발생 전 승인 요청.
- WO-01 진입 여부를 GO / CONDITIONAL GO / NO-GO로 판정하라.
