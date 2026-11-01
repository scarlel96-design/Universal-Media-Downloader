# WO-00R 아키텍처

조사일: 2026-11-01. 확인된 사실과 추정을 구분한다. DLL이 디스크에 있다는 사실만으로 기능을 확정하지 않는다. 함수 본문은 디컴파일하지 않았다.

## 확인된 구조

메인 실행 파일은 PE32+, AMD64, Windows GUI다. FileVersion은 26.3.5.0396이다.

링크 시점의 일반 임포트에는 Qt 6.8.3 모듈, FFmpeg 4.x SONAME, OpenSSL 1.1.1s, WinHTTP, WinSock2, bcrypt, PortAudio가 있다. 지연 로드 임포트는 `lalalai_proc.dll` 하나다.

실행 중이던 프로세스의 모듈 목록에는 Qt6Qml, Qt6Quick, Qt6Network, Qt6WebEngineCore, Qt6WebEngineQuick, Qt6WebEngineWidgets, avcodec-58, avformat-58, avutil-56, swresample-3, swscale-5, WINHTTP, libssl, libcrypto, portaudio가 올라와 있었다. `postproc-55.dll`, `lalalai_proc.dll`, `onnxruntime_omnisale.dll`, `DirectML.dll`은 그 시점에 없었다.

같은 세션에 `QtWebEngineProcess` 자식이 2개 있었다. 작업 집합은 각 16,384 bytes, 스레드는 각 10, CPU 시간은 0.5초 미만이었다. 페이지를 그렸는지는 미확인이다.

지연 로드 사슬은 임포트 디렉터리에서 확인했다.

```
4kvideodownloaderplus.exe
  --delay-load--> lalalai_proc.dll
                    --delay-load--> onnxruntime_omnisale.dll
                                      --delay-load--> DirectML.dll
                                      --delay-load--> d3d12.dll
                                      --delay-load--> dxgi.dll
                                      --delay-load--> dxcore.dll
```

`onnxruntime_omnisale.dll`의 익스포트 이름은 `OrtGetApiBase`, `OrtSessionOptionsAppendExecutionProvider_CPU`, `OrtSessionOptionsAppendExecutionProvider_DML`, `OrtSessionOptionsAppendExecutionProviderEx_DML`이다. 이것은 ONNX Runtime C API와 DirectML·CPU 실행 공급자 진입점이다. 세션이 만들어졌는지는 미확인이다.

`lalalai_proc.dll` 익스포트 이름의 MSVC 장식은 다음 표면을 가리킨다. 본문은 읽지 않았다.

- `LalalaiProc` 생성자는 `LalalaiProcConfig`를 받는다.
- `initializeModel`은 문자열과 `ModelData`를 받는다.
- `isModelInitialized`, `deinitializeModel`, `deinitializeAllModels`가 있다.
- `maxInputSize`는 크기를 반환한다.
- `process`의 장식은 `float` 벡터를 받아 `float` 벡터와 bool을 다루는 형태다. 그 float가 오디오 샘플인지는 미확인이다.

설치 트리에는 `.onnx` 파일이 없다. 리소스 루트 타입은 ICON, GROUP_ICON, VERSION, MANIFEST뿐이다. 모델 바이트가 `.rdata` 안에 있는지는 미확인이다.

## 모듈 역할

| 구성 | 상태 | 근거 |
|---|---|---|
| Qt 6.8.3 Quick / QML | 확인, 프로세스에 매핑됨 | `Qt6Qml.dll`, `Qt6Quick.dll`이 모듈 목록에 있음 |
| Qt Widgets / Qt6Gui / Qt6Core | 임포트는 확인, 이번 모듈 필터에는 없음 | 매핑은 미확인 |
| Qt WebEngine | 확인, 코어 DLL과 자식 프로세스 존재 | 모듈 목록, 프로세스 목록 |
| FFmpeg avcodec, avformat, avutil, swresample, swscale | 확인, 매핑됨 | 모듈 목록 |
| FFmpeg postproc | 디스크에만 있음 | 모듈 목록에 없음 |
| WinHTTP | 확인, 매핑됨 | 임포트 7개와 모듈 목록 |
| WinSock2 | 링크됨 | `getaddrinfo`, `WSASocketW`, `WSASend`, `WSARecv` |
| Qt Network | 링크되고 매핑됨 | 임포트 28개. 그중 `QNetworkCookie`의 httpOnly 접근자가 있다 |
| OpenSSL 1.1.1s | 매핑됨 | 파일 버전과 모듈 목록 |
| PortAudio | 매핑됨 | 임포트와 모듈 목록 |
| Crashpad | 디스크에 있음 | 이번 스냅샷의 모듈 목록에는 없음. 별도 프로세스는 확인하지 않음 |
| ONNX Runtime / DirectML / lalalai | 지연 로드 관계만 확인 | 이번 프로세스에는 매핑되지 않음 |
| LAME | 고지 파일에만 있음 | 그 이름의 DLL은 설치 루트에서 보이지 않음. 정적 포함 여부는 미확인 |
| Boost | 고지 파일에만 있음 | 별도 DLL 이름은 없음 |

WinHTTP 정적 임포트는 `WinHttpOpen`, `WinHttpConnect`, `WinHttpOpenRequest`, `WinHttpSendRequest`, `WinHttpReceiveResponse`, `WinHttpQueryHeaders`, `WinHttpCloseHandle`이다. `WinHttpReadData`와 `WinHttpAddRequestHeaders`는 이 목록에 없다. `GetProcAddress`로 나중에 찾는지는 미확인이다.

KERNEL32 임포트 195개 중에는 `CreateFileW`, `ReadFile`, `WriteFile`, `SetFilePointerEx`, `LockFile`, `MoveFileExW`, `CreateFileMappingW`, `CreateThread`, `WaitForSingleObject`, `EnterCriticalSection`, `CreateMutexW`, `CreateSemaphoreA`가 있다. Qt와 CRT도 같은 DLL을 쓴다. 다운로드 저장 경로가 이 호출을 직접 쓰는지는 미확인이다.

## 추정

Qt Quick이 UI이고, WebEngine 자식이 페이지 표시에 쓰이며, FFmpeg가 컨테이너와 디코드에 쓰이고, WinHTTP 또는 Qt Network가 전송에 참여할 수 있다. 이 문장은 매핑된 라이브러리에서 한 단계 추정한 것이다. 호출 순서와 버퍼 크기는 확인하지 않았다.

`lalalai_proc`의 모델 API는 오디오 처리와 맞는 이름이다. 입력과 출력을 실행 중에 보지 못했으므로 업스케일, 음원 분리, 추출 자동화 중 어느 것인지는 단정하지 않는다. 이번 프로세스에서는 그 DLL이 로드되지 않았다.

## 미확인

- URL 입력 뒤의 큐, 호스트별 연결 수, 재시도, Range 재개
- HLS와 DASH를 어느 라이브러리가 처리하는지
- 작업 하나의 메모리 상한
- UI 스레드와 다운로드 스레드의 분리 방식
- 캐시 디렉터리와 부분 파일 형식
- 계정·업데이트 통신과 다운로드 통신의 구분
