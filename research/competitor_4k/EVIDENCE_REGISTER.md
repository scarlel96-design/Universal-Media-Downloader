# 증거 레지스터

수준: VERIFIED는 이 세션에서 명령이나 페이지로 확인한 사실이다. INFERRED는 그 사실에서 한 단계 추론한 것이다. UNKNOWN은 확인하지 않은 것이다. BLOCKED는 하지 않기로 한 것이다.

| ID | 관찰 | 수준 | 출처 |
|---|---|---|---|
| E-001 | 설치 경로가 존재한다 | VERIFIED | `Test-Path` |
| E-002 | 메인 실행 파일 FileVersion 26.3.5.0396, Product 26.3, 설명 4K Video Downloader+, 회사 InterPromo GMBH | VERIFIED | FileVersionInfo |
| E-003 | 메인 exe, Qt6Core.dll, lalalai_proc.dll, onnxruntime_omnisale.dll, QtWebEngineProcess.exe 서명이 Valid이고 주체가 InterPromo GMBH, Baden-Baden, DE | VERIFIED | Get-AuthenticodeSignature |
| E-004 | 파일 1,602개, 505,147,855 bytes. QML 518개는 Qt 프레임워크 디렉터리에만 있다 | VERIFIED | 디렉터리 열거 |
| E-005 | 주요 바이너리 SHA-256 | VERIFIED | INSTALL_INVENTORY.md |
| E-006 | PE32+, AMD64, WINDOWS_GUI, ASLR/NX/High-Entropy VA | VERIFIED | PE 헤더 |
| E-007 | 리소스 루트는 ICON, GROUP_ICON, VERSION, MANIFEST뿐 | VERIFIED | 리소스 디렉터리 개수. 페이로드 미추출 |
| E-008 | readme는 영상·음성 저장을 말하고, thirdparty는 Qt, FFmpeg, OpenSSL, LAME, Boost를 고지한다. eula.txt 6항은 reverse compile, translate, disassemble을 금지한다 | VERIFIED | 동봉 텍스트 |
| E-009 | 공개 제품 페이지의 기능 목록과 라이선스 등급 | VERIFIED | 2026-11-01 조회, <https://www.4kdownload.com/products/videodownloader-42> |
| E-010 | 공개 약관의 역공학·우회 금지와 합법 사용 조항 | VERIFIED | <https://www.4kdownload.com/agreement/terms-of-use/8> |
| E-011 | 저작권법 제101조의4의 호환 목적·보충성·유사 프로그램 금지 | VERIFIED | 법령 공개 텍스트. 이 사건에 대한 법원 판단은 아님 |
| E-012 | REA 6.7.0 doctor, client grok_build. healthy false. 등록 없음. Ghidra/Hopper/IDA/JADX/Kuna 없음. 스킬 42는 정렬됨 | VERIFIED | `npx -y rea-agents@6.7.0 doctor --client grok_build --json` |
| E-013 | setup dry-run은 `the local Grok user config file`에 REA MCP를 추가하고 백업을 만들 계획만 출력했다. appliedActions는 비어 있다. 쓰기는 하지 않았다 | VERIFIED | `setup --client grok_build --dry-run --json` |
| E-014 | Java Temurin 21.0.5가 있다. Ghidra 설치 디렉터리와 GHIDRA_INSTALL_DIR은 없다 | VERIFIED | `java -version`, 경로 검색 |
| E-015 | Node v24.16.0, npm 12.2.1. doctor의 node 검사는 이 버전을 healthy로 표시했다 | VERIFIED | `node --version`, doctor |
| E-016 | 이 세션의 MCP 도구 목록에 REA 도구가 없다 | VERIFIED | 세션 도구 검색 |
| E-017 | 경쟁 제품 성능 측정 | NOT RUN | 앱을 실행하지 않음 |
| E-018 | 경쟁 제품 UI 동작 관찰 | NOT RUN | 실행하면 업데이트 확인과 네트워크 접속이 생길 수 있어 승인 없이 실행하지 않음 |
| E-019 | 코드 역분석 | BLOCKED | LEGAL_LIMITS.md |
| E-020 | Qt 6.8.3 DLL과 QtQuick/WebEngine 파일명, FFmpeg 계열 DLL 파일명, ONNX Runtime·DirectML 파일명 | VERIFIED | 파일명과 버전 리소스 |
| E-021 | 인앱 브라우저가 Qt WebEngine이다 | INFERRED | E-020과 공개 "Built-In Browser" 문구. 런타임으로 연결을 보지 않음 |
| E-022 | 미디어 처리가 동봉 FFmpeg를 호출한다 | INFERRED | thirdparty 고지와 avcodec 파일명. 호출 경로는 미확인 |
| E-023 | 로컬 AI 음성 처리가 ONNX Runtime, DirectML, lalalai_proc.dll을 쓴다 | INFERRED | 공개 AI 문구와 파일명. 모델과 호출 경로는 미확인 |
| E-024 | 앱 자신의 QML 소스 위치와 다운로드 스케줄러 알고리즘 | UNKNOWN | 추출하지 않음 |
| E-025 | 공개 페이지의 최신 버전 문자열 25.3.4.0241과 설치본 26.3.5.0396의 차이 이유 | UNKNOWN | 두 출처가 다름 |

개인정보와 라이선스 키는 수집하지 않았다. 로그에 넣은 식별자는 파일 경로, 버전, 서명 주체, 해시뿐이다.
