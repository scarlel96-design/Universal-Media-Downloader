# WO-00R REA와 법률 상태

조사일: 2026-11-01. 법률 자문이 아니다. 실행하지 않은 도구는 사용했다고 적지 않는다.

## 이번 세션의 REA

Grok Build에 연결된 MCP 서버는 cursor, pwragent, tasks다. REA 도구는 이 세션 도구 목록에 없다. `open_binary`와 doctor용 MCP 도구는 호출하지 못했다.

`npx -y rea-agents@6.7.0 doctor --client grok_build --json`을 실행했다. 종료 코드 1. `healthy`는 false다.

| 검사 | 결과 |
|---|---|
| 패키지 | rea-agents 6.7.0. CLI 명령 153, MCP 도구 207, 스킬 기대 버전 42 |
| Node | 24.16.0, 검사 ok |
| 호스트 | win32 x64 |
| 스킬 | 설치 버전 42, 도구 수 207, state aligned |
| `registration:grok_build` | missing. 대상은 사용자 Grok 설정의 `config.toml`. classification `config_drift` |
| live server | state unknown. 이 세션에 서버가 붙어 있지 않음 |
| Ghidra | `GHIDRA_INSTALL_DIR` 없음. missing_analysis_engine. doctor가 요구하는 버전은 12.1.x |
| IDA | MCP 등록 없음 |
| Hopper | missing_analysis_engine |
| JADX, Kuna | 호출자가 경로를 넣지 않음. REA는 이 둘을 받아 설치하지 않음 |

다른 클라이언트 등록은 이번 작업에서 고치지 않았다. doctor는 antigravity와 codex를 stale, claude_code와 gemini_cli를 missing으로 보고했다.

## 설정 변경 계획

등록이 없어서 `npx -y rea-agents@6.7.0 setup --client grok_build --dry-run --json`만 실행했다. 종료 코드 0. `appliedActions`는 비어 있다.

계획된 동작은 하나다.

- id: `configure_client:grok_build`
- 대상: 사용자 Grok 설정의 `config.toml`
- 동작: REA MCP 등록을 추가하고, 기존 다른 설정은 유지
- 명령: `npx -y rea-agents@6.7.0 mcp`
- 백업: 같은 폴더의 `config.toml.rea.backup`
- provider 환경 변수는 추가하지 않음

이 계획은 적용하지 않았다. 적용해도 Ghidra는 설치되지 않고, 세션을 다시 연결하기 전에는 도구가 보이지 않는다. 도구 설치는 승인된 경우에만 한다고 작업 지시가 정하고 있다. 승인은 없었다.

## 네이티브 엔진

PATH와 일반적인 설치 위치에서 `ghidra`, `ghidraRun`, `analyzeHeadless`, `ida`, `ida64`, `hopper`는 없다.

| 엔진 | 상태 | 비용 |
|---|---|---|
| Ghidra 12.1.x | 없음 | 구입 가격 0. Apache-2.0. 이번 실행에서 다운로드하지 않음. JDK는 이미 Temurin 21.0.5다. JDK 추가 비용 0 |
| IDA | 없음 | 상용. 가격을 조회하지 않음. 설치하지 않음 |
| Hopper | 없음 | 유료 설치 플래그는 dry-run에 넣지 않음. 가격을 조회하지 않음 |

Ghidra를 깔아도 아래 법률 판정 때문에 이 제품의 디스어셈블에는 쓰지 않는다. 그래서 설치를 요청하지 않는다.

## 약관

설치본 `eula.txt` 6항: "You agree that you will not attempt to reverse compile, modify, translate, or disassemble the Software in whole or in part."

1항의 Use에는 저장, 적재, 설치, 실행, 표시가 들어 간다. 역컴파일과 디스어셈블은 6항이 금지한다. 약관 전문은 저장소에 복사하지 않았다.

공개 이용약관 페이지는 이전 조사에서 같은 취지로 확인했다. 이번 작업에서 그 페이지를 다시 열지는 않았다. 설치본 6항은 이번 작업에서 다시 읽었다.

## 저작권법

저작권법 제101조의4 제1항은 호환에 필요한 정보를 쉽게 얻을 수 없고 그 획득이 불가피한 때에만, 그 부분에 한정해 프로그램코드역분석을 허용한다. 제2항은 그 정보를 호환 외 목적에 쓰거나, 대상과 표현이 실질적으로 유사한 프로그램을 개발·제작·판매하는 데 쓰는 경우를 금지한다.

이 작업의 목적은 4K Video Downloader+와 파일 형식을 맞추는 호환이 아니다. Universal Media Downloader의 성능과 개발 비용을 보는 것이다. 다운로드 경로는 yt-dlp, gallery-dl, httpx, Playwright라는 공개 구현으로 이미 연결되어 있다. 호환 정보의 보충 요건이 충족되지 않는다. 역분석 결과를 비슷한 다운로더를 만드는 데 쓰는 것도 제2항이 막는 사용에 들어갈 수 있다.

계약이 역분석을 막더라도 강행규정으로 무효인지는 여기서 단정하지 않는다. 무효여도 제101조의4 요건이 남는다.

## 이번 작업에서 한 것과 막은 것

한 것:

- 파일 크기, 버전 리소스, SHA-256, Authenticode
- PE 기계 종류, 서브시스템, 섹션 이름과 가상 크기, 임포트 DLL 이름, 일부 임포트 함수 이름, 익스포트 이름, 리소스 루트 타입 ID
- 이미 실행 중인 프로세스의 작업 집합, 스레드 수, 모듈 이름, I/O 누적 계수

BLOCKED:

- 디컴파일, 디스어셈블, 의사코드, 함수 본문, 문자열 덤프
- 라이선스 해제, 활성화 제한 제거, 암호 해제
- Ghidra, IDA, Hopper, Kuna 실행
- REA `open_binary`

작업 지시 9항은 디컴파일과 디스어셈블을 대상 제한 없이 수행하라고 적는다. 5항은 그 전에 약관과 법적 허용 범위를 확인하라고 적는다. 확인 결과가 금지이므로 9항의 코드 역분석은 수행하지 않았다. 고유 구현을 저장소에 복사하지 않았다.

## 정상 사용

실행 자체는 1항의 Use에 들어 간다. 다만 이미 떠 있는 세션에 URL을 넣으면 사용자의 다운로드와 약관 8항의 통계 통신에 손을 대게 된다. 그래서 UI 시나리오는 NOT RUN으로 두었다. 통계가 나갔는지는 패킷으로 확인하지 않았다.
