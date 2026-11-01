# WO-00R 보고

작업: 4K Video Downloader+ 심층 구조 및 성능 분석
조사일: 2026-11-01
기준 커밋: `56d8c0eff1fb9d4c15328fcd6d314897f7ebe6b8`
저장소: https://github.com/scarlel96-design/Universal-Media-Downloader
판정: **CONDITIONAL GO**

이 판정은 인벤토리와 링크·로드 지도를 개발 참고로 써도 된다는 뜻이다. 코드 역분석과 같은 조건의 성능 비교는 끝나지 않았다. 다음 제품 작업은 시작하지 않는다. WO-04 브랜치도 이 보고로 병합하지 않는다.

## 분석 대상과 SHA-256

| 항목 | 값 |
|---|---|
| 제품 | 4K Video Downloader+ |
| 경로 | `C:\Program Files\4KDownload\4kvideodownloaderplus\4kvideodownloaderplus.exe` |
| FileVersion | 26.3.5.0396 |
| ProductVersion | 26.3 |
| 크기 | 179,314,432 bytes |
| SHA-256 | `50E3EA9303549D1700D2908AF6025F8C2CE5512C8F5A0682CCC1DEDBDE2CEBBC` |
| Authenticode | Valid, `CN=InterPromo GMBH, O=InterPromo GMBH, L=Baden-Baden, C=DE` |
| PE | PE32+, AMD64, WINDOWS_GUI, TimeDateStamp 2026-09-28T16:26:40Z |

설치 폴더는 있다. 원본은 수정하지 않았다. 바이너리 복사본은 만들지 않았다.

## 설치 패키지

`설치파일`을 제외하면 1,602개, 505,147,855 bytes다. 그 폴더에 파일이 둘 더 있다.

- MSI 136,818,688 bytes, SHA-256 `7C442B0B2182E5271FA4F27FFE0E0ED8C22FDC88ABC9AD888A04FC8A42518386`, 서명 Valid, ProductVersion **25.0.2.0185**
- DMG 278,526,864 bytes, SHA-256 `E1425DBD0E0B92929E6B28C21C454FEA819A37529120F52EA0AF9E0266FF7A7D`, 내용은 NOT RUN

MSI와 설치본의 버전이 다르다. MSI는 실행하지 않았다.

## 실행한 도구

| 도구 | 버전 또는 결과 |
|---|---|
| PowerShell `Get-FileHash`, FileVersionInfo, `Get-AuthenticodeSignature` | 실행함. EXE·DLL·MSI 114개 Valid |
| Python PE 파서 | 헤더, 섹션, 임포트·익스포트 이름, 리소스 타입 ID. 명령 디코딩 없음 |
| Windows Installer OpenDatabase 모드 0 | MSI 속성만 읽음 |
| `npx -y rea-agents@6.7.0 doctor --client grok_build --json` | 종료 코드 1, healthy false |
| `npx -y rea-agents@6.7.0 setup --client grok_build --dry-run --json` | 종료 코드 0, 적용하지 않음 |
| Node | 24.16.0 |
| Java | Temurin 21.0.5. Ghidra는 없음 |
| `Get-Process`, Win32_Process, 모듈 목록, `Get-NetTCPConnection` | 이미 떠 있던 PID만 |
| Ghidra, IDA, Hopper, REA `open_binary` | NOT RUN. 엔진은 BLOCKED(미설치). 이 제품 디스어셈블은 약관으로도 BLOCKED |
| UI 자동화, 로컬 다운로드 비교 | NOT RUN |

## REA

이 세션의 MCP 목록에 REA 도구가 없다. grok_build 등록은 `config.toml`에 없고 doctor가 missing으로 보고했다. dry-run은 그 파일에 MCP 명령을 추가하고 백업을 남기는 계획만 만들었다. 설정은 쓰지 않았다. 스킬 파일 버전 42는 doctor가 aligned로 보고했다.

Ghidra 12.1.x는 `GHIDRA_INSTALL_DIR`이 비어 있다. 라이선스 비용은 0이고, JDK 21은 이미 있다. 설치하지 않았다. 설치해도 `eula.txt` 6항과 저작권법 제101조의4 때문에 이 바이너리를 디스어셈블하지 않는다. 목적은 호환에 꼭 필요한 정보가 아니라 경쟁 다운로더의 구조와 비용이다.

## 정적 분석

확인:

- Qt 6.8.3, FFmpeg SONAME(avcodec-58, avformat-58, avutil-56, swresample-3, swscale-5, postproc-55), OpenSSL 1.1.1s, WinHTTP, WinSock2, PortAudio, Qt WebEngine, ONNX Runtime 1.21.20250307.2.e0b66ca, DirectML 1.15.4
- 메인 실행 파일은 `lalalai_proc.dll`을 지연 로드한다. 그 DLL은 `onnxruntime_omnisale.dll`을 지연 로드한다. ONNX DLL은 DirectML과 D3D12를 지연 로드한다.
- ONNX 익스포트는 `OrtGetApiBase`와 CPU·DirectML 실행 공급자 등록 함수다.
- `lalalai_proc` 익스포트 이름은 모델 초기화와 `process`다. float 벡터 입출력으로 장식되어 있다. 역할은 미확인이다.
- 설치 트리에 `.onnx`와 JSON이 없다.
- WinHTTP 정적 임포트 7개에 `WinHttpReadData`는 없다.

추정:

- Quick/QML이 UI이고 WebEngine 자식이 페이지용이다.
- 매핑된 FFmpeg가 컨테이너 처리에 참여한다.
- lalalai 이름은 오디오 모델과 맞다. 업스케일·음원 분리·추출 자동화로는 단정하지 않는다.

## 동작 측정

이미 실행 중인 프로세스의 스냅샷만 있다. URL, 일시정지, 재개, 취소, 종료는 NOT RUN이다.

그 시점에 FFmpeg 다섯 개, WinHTTP, Qt Network, Qt WebEngine, OpenSSL, PortAudio는 매핑되어 있었다. lalalai, ONNX Runtime, DirectML, postproc는 매핑되어 있지 않았다. WebEngine 자식은 2개였다. TCP 행은 0건이다. 네트워크를 쓰지 않는다는 뜻은 아니다.

작업 집합은 5,877,760 bytes에서 14,761,984 bytes로 바뀌었고, 페이지 파일은 416,718,848 bytes로 같았다. 스레드 72, 핸들 2,740. 시작 이후 읽기 29,003,860 bytes, 쓰기 1,393,528 bytes. CPU 시간 228.921875초. 다운로드 한 건의 지표가 아니다.

## 성능 비교

비교 불가. Universal Media Downloader의 5,000파일 181.386초, 작업 집합 피크 99,864,576 bytes, 연결 피크 3은 로컬 픽스처다. 같은 입력을 4K Video Downloader+에 넣지 않았다.

## 미확인

- 작업 큐, 호스트 상한, 버퍼 크기, Range 재개, 재시도, HLS/DASH 분담
- 모델 파일의 위치와 입출력 의미
- UI 응답, 완료 후 메모리 회수
- DMG 내부 버전
- 업데이트 연결과 다운로드 연결의 구분

## 개선 권고와 비용

코드 변경 권고는 없다. MSI 25.0.2.0185를 실행하지 않는 것이 우선이다. ONNX, WinHTTP 이식, Qt WebEngine 도입은 별도 제안이며 구현하지 않는다. 추가 비용은 0이다. Hopper와 IDA 가격은 조회하지 않았고 구매하지 않았다.

## 외부 업로드

이 문서에는 상용 바이너리, 인증 정보, 복원한 함수 본문이 없다. 해시와 임포트·익스포트 이름, 프로세스 계수만 있다. 바이너리는 GitHub에 올리지 않는다. 문서를 푸시하면 그 커밋만 공개 저장소에 올라간다. 푸시 여부는 커밋 뒤에 이 파일 바깥의 최종 설명에 적는다.

## 완료 기준

| 기준 | 상태 |
|---|---|
| 대상 버전과 파일 무결성 | 확인. SHA-256 위와 같음 |
| 설치 패키지 구성 | 확인. MSI 버전이 설치본보다 낮음 |
| 정적 의존성 | 확인. 임포트와 지연 로드, 일부 런타임 매핑 |
| 다운로드 동작 흐름 | NOT RUN |
| 파일 I/O와 스레드 | 기존 프로세스의 누적값만. 통제 시험 NOT RUN |
| 메모리 패턴 | 스냅샷 두 번. 작업별 패턴 NOT RUN |
| ONNX 사용 | DLL과 익스포트는 확인. 모델 파일 없음. 이번 프로세스에서 미로드 |
| 비교 가능한 성능 시험 | 비교 불가, NOT RUN |
| 개선안 | 작성함. 측정되지 않은 속도 향상은 없음 |
| 코드 역분석 | BLOCKED. 약관 6항과 저작권법 제101조의4 |

## 판정

**CONDITIONAL GO.** 버전, 해시, 서명, 라이브러리 경계, ONNX를 지금 넣지 않을 이유는 확인되었다. 다운로드 엔진의 내부와 성능 우열은 확인되지 않았다. 그 공백을 사실로 채우지 않는다. WO-04 개발을 이 보고에서 시작하지 않는다.
