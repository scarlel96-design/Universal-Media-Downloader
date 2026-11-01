# 구조 가설

디컴파일 결과가 아니다. 맞는 것으로 확인된 문장과 가설을 나눈다.

## 확인된 구성

설치본은 Windows x64 GUI 실행 파일이고, Qt 6.8.3 DLL(Core, Gui, Qml, Quick, QuickControls2, WebEngine, Network)을 같이 둔다. 서명 주체는 InterPromo GMBH다. 디스크의 QML은 Qt 프레임워크 것이다. 실행 파일 리소스에 Win32 대화상자 템플릿은 없다.

이 조합은 UI가 Qt Quick일 가능성이 높다. 그래도 앱 QML이 어디에 있는지는 확인하지 않았으므로 "Qt Quick이 화면을 그린다"는 **INFERRED**다. 근거는 E-004, E-007, E-020이다.

## 가설

| ID | 가설 | 근거 | 상태 |
|---|---|---|---|
| H-1 | 화면은 Qt Quick, 창은 Qt가 만든 네이티브 HWND | Qt6Quick, Qt6Gui, qwindows 플랫폼 플러그인 파일명. 런타임 미관찰 | INFERRED |
| H-2 | 로그인·일부 사이트 탐색은 Qt WebEngine 프로세스 | QtWebEngineCore.dll, QtWebEngineProcess.exe, 공개 인앱 브라우저 문구 | INFERRED |
| H-3 | 컨테이너 병합과 디코드에 FFmpeg 4.x SONAME DLL을 쓴다 | avcodec-58 등 파일명, thirdparty의 FFmpeg 고지 | INFERRED. 호출 여부 UNKNOWN |
| H-4 | TLS에 OpenSSL 1.1 DLL을 연결한다 | libssl-1_1, libcrypto-1_1 파일명, thirdparty 고지 | INFERRED |
| H-5 | 로컬 음성 AI는 ONNX Runtime과 DirectML, 그리고 lalalai_proc.dll 쪽에 있다 | 파일명·설명 리소스, 공개 AI 문구 | INFERRED. 모델 파일은 이번 목록에서 특정하지 않음 |
| H-6 | crashpad_handler.exe가 크래시 보고 자식 프로세스다 | 파일명. 전송 여부와 수집 항목은 모름 | INFERRED, 동작 UNKNOWN |
| H-7 | 다운로드 스케줄러는 별도 네트워크 스택을 갖고 호스트별 동시성을 제한한다 | 공개 동시 다운로드 개수뿐 | UNKNOWN |
| H-8 | 이어받기는 HTTP Range다 | 공개 문서에서 규칙을 찾지 못함 | UNKNOWN |
| H-9 | .rdata 114MB 안에 추출 규칙이나 압축 UI가 들어 있다 | 섹션 크기만 확인 | UNKNOWN. 열람하지 않음 |

H-7과 H-8은 설계에 반영하지 않는다. 우리 스케줄러는 HTTPX와 yt-dlp의 공개 동작을 기준으로 새로 정한다.

## 우리 구조에 미치는 점

Qt Quick + 네이티브 창이라는 선택은 4K 바이너리를 베끼는 결정이 아니다. 설계서 V1.1이 이미 PySide6와 Qt Quick을 지정했고, 설치본은 그 선택이 Windows에서 통한다는 정황만 준다. 창 버튼은 4K의 배치를 따르지 않고 Windows 기본 캡션을 유지한다.

추출 엔진은 가설 H-3의 FFmpeg 재사용과 공개 yt-dlp로 충분하다. WebEngine을 우리 기본 경로로 넣지 않는다. 자바스크립트 페이지는 이후 작업에서 Playwright로 연다. ONNX 음성 분리는 V1에 넣지 않는다.
