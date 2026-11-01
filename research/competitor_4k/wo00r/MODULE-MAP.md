# WO-00R 모듈 의존성

조사일: 2026-11-01. 간선은 PE 임포트 디렉터리에서 읽었다. "매핑됨"은 이미 떠 있던 PID의 모듈 목록이다. 함수 본문의 호출 그래프는 없다.

## 메인 실행 파일의 일반 임포트

| 대상 | 임포트 개수 | 이번 프로세스에 매핑 |
|---|---:|---|
| Qt6Core.dll | 이름 테이블에 있음 | 미확인. 이번 필터에 없음 |
| Qt6Gui.dll | 있음 | 미확인. 이번 필터에 없음 |
| Qt6Widgets.dll | 있음 | 미확인. 이번 필터에 없음 |
| Qt6Qml.dll | 있음 | 예 |
| Qt6Quick.dll | 있음 | 예 |
| Qt6Network.dll | 28 | 예 |
| Qt6Xml.dll | 있음 | 미확인 |
| Qt6WebEngineCore.dll | 있음 | 예 |
| Qt6WebEngineQuick.dll | 있음 | 예 |
| Qt6WebEngineWidgets.dll | 있음 | 예 |
| avformat-58.dll | 있음 | 예 |
| avcodec-58.dll | 있음 | 예 |
| avutil-56.dll | 있음 | 예 |
| swresample-3.dll | 있음 | 예 |
| swscale-5.dll | 있음 | 예 |
| libssl-1_1-x64.dll | 있음 | 예 |
| libcrypto-1_1-x64.dll | 있음 | 예 |
| portaudio_x64.dll | 있음 | 예 |
| WINHTTP.dll | 7 | 예 |
| WS2_32.dll | 28 | 시스템 DLL, 목록에서 따로 걸러 내지 않음 |
| IPHLPAPI.DLL | 있음 | 미확인 |
| bcrypt.dll | 3 | 미확인 |
| KERNEL32.dll | 195 | 시스템 DLL |
| USER32, GDI32, SHELL32, ADVAPI32, ole32, OLEAUT32 | 있음 | 시스템 DLL |
| MSVCP140, VCRUNTIME140, UCRT API set | 있음 | 런타임 |

`postproc-55.dll`은 메인 실행 파일의 일반 임포트 목록에 없고, 이번 모듈 목록에도 없다.

## 지연 로드

| 읽는 파일 | 지연 로드 대상 |
|---|---|
| `4kvideodownloaderplus.exe` | `lalalai_proc.dll` |
| `lalalai_proc.dll` | `onnxruntime_omnisale.dll` |
| `onnxruntime_omnisale.dll` | `DirectML.dll`, `d3d12.dll`, `dxgi.dll`, `dxcore.dll` |

지연 로드는 첫 호출 때 로드된다. 이번 프로세스 모듈 목록에 세 DLL이 없으므로, 그 시점까지 그 호출은 일어나지 않은 것으로 본다. 그 전에 로드했다가 내린 경우까지 배제하지는 못한다. 확률은 낮고, 증거는 없다.

## 다른 바이너리

| 파일 | 관찰 |
|---|---|
| `QtWebEngineProcess.exe` | Qt6WebEngineCore, Qt6Core를 임포트. 익스포트 54개. 샘플 이름은 Chromium 샌드박스 대상 래퍼(`TargetNtCreateFile`, `IsSandboxedProcess`)다. 자식 프로세스 2개가 존재했다 |
| `crashpad_handler.exe` | WINHTTP를 임포트. 크래시 보고와 제품 업데이트의 구분은 미확인 |
| `avcodec-58.dll` | 익스포트 238. 본문 미열람 |
| `avformat-58.dll` | 익스포트 175. 본문 미열람 |
| `onnxruntime_omnisale.dll` | 익스포트 4개, 모두 `Ort*` |
| `lalalai_proc.dll` | 익스포트 10개. 모델 초기화와 `process` |
| `DirectML.dll` | 익스포트 2개. 이번 프로세스에 없음. 서명은 Microsoft |

## 디스크에만 있는 Qt 플러그인

imageformats, platforms, tls, position, QtQuick 스타일 플러그인은 설치되어 있고 서명 Valid, FileVersion 6.8.3.0이다. 이번 모듈 스냅샷은 메인 프로세스에서 onnx·FFmpeg·WebEngine만 걸러 봤으므로, 각 플러그인의 로드 여부는 미확인이다. `qwindows.dll`과 `qopensslbackend.dll`은 GUI와 TLS에 필요할 것으로 추정한다. 추정이다.

## 데이터 파일

| 파일 | 크기 | 역할로 확정했는지 |
|---|---:|---|
| `icudtl.dat` | 10,717,680 | 아니요. Qt/Chromium ICU 데이터 파일 이름으로 추정 |
| `v8_context_snapshot.bin` | 679,317 | 아니요. V8 스냅샷 이름으로 추정 |
| `qtwebengine_resources*.pak` | 4개 | 아니요. WebEngine 리소스 팩 이름으로 추정 |
| `audio\alert.mp3`, `audio\alert.wav` | 존재 | 알림음으로 추정. 재생은 관찰하지 않음 |

애플리케이션 전용 QML 디렉터리는 보이지 않았다. QML 518개는 기존 인벤토리에서 Qt 프레임워크 경로로 세었다. 앱 UI가 바이너리 안에 컴파일돼 있는지는 미확인이고, 추출하지 않았다.
