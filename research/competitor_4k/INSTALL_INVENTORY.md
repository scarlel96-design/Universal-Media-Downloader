# 설치본 인벤토리

조사일: 2026-11-01. 읽기 전용. 설치 파일은 변경하지 않았다.

## 대상

| 항목 | 값 | 수준 |
|---|---|---|
| 경로 | `C:\Program Files\4KDownload\4kvideodownloaderplus` | VERIFIED, `Test-Path` True |
| 실행 파일 | `4kvideodownloaderplus.exe` | VERIFIED |
| FileVersion | 26.3.5.0396 | VERIFIED, FileVersionInfo |
| ProductVersion | 26.3 | VERIFIED |
| FileDescription | 4K Video Downloader+ | VERIFIED |
| CompanyName | InterPromo GMBH | VERIFIED |
| 서명 | Valid, `CN=InterPromo GMBH, O=InterPromo GMBH, L=Baden-Baden, C=DE` | VERIFIED, Authenticode |
| 파일 수 | 1,602 | VERIFIED |
| 합계 크기 | 505,147,855 bytes | VERIFIED |

공개 제품 페이지를 같은 날 조회했을 때 표시된 최신 버전 문자열은 25.3.4.0241 (October 23, 2025)였다. 설치된 FileVersion과 다르다. 어느 쪽이 배포 채널의 최신인지는 **UNKNOWN**. 설치본 버전은 파일 버전 리소스를 기준으로 한다.

## PE 헤더 (메인 실행 파일)

코드 섹션은 디스어셈블하지 않았다. 헤더 필드만 읽었다.

| 필드 | 값 | 해석 |
|---|---|---|
| Machine | 0x8664 | AMD64 |
| Magic | 0x020B | PE32+ |
| Subsystem | 2 | WINDOWS_GUI |
| Characteristics | 0x0022 | EXECUTABLE_IMAGE, LARGE_ADDRESS_AWARE |
| DllCharacteristics | 0x8160 | HIGH_ENTROPY_VA, DYNAMIC_BASE, NX_COMPAT, TERMINAL_SERVER_AWARE |
| TimeDateStamp | 1790612800 | 2026-09-28T16:26:40Z |
| 섹션 수 | 12 | .text, .rdata, .data, .pdata, .idata, .didat, .tls, .qtversi, .00cfg, minATL, .rsrc, .reloc |
| .text 가상 크기 | 57,681,295 | 내용 미열람 |
| .rdata 가상 크기 | 114,562,090 | 내용 미열람 |
| 리소스 디렉터리 | RVA 0xAA4C000, 231,980 bytes | 타입만 열거 |

리소스 타입 개수: ICON 8, GROUP_ICON 1, VERSION 1, MANIFEST 1. 이름 있는 엔트리는 0. Win32 DIALOG/MENU 리소스는 루트에 없다. 아이콘 비트맵은 추출하지 않았다.

## 동봉 고지

- `readme.txt`: 제품이 YouTube 등에서 영상·음성을 받아 컴퓨터에 저장한다고 적고, 저작권은 InterPromo GMBH, 조건은 eula 파일을 보라고 한다.
- `thirdparty.txt`: Qt(LGPL 3.0 표기), Boost, FFmpeg(LGPL 2.1), LAME(LGPL 2.1), OpenSSL을 사용한다고 고지한다. Qt 고지의 URL은 GPL 3.0 문서를 가리킨다. 실제 Qt 라이선스 조합은 고지 문장과 URL이 섞여 있어, 재배포 의무는 별도 확인이 필요하다. 우리 앱은 이 바이너리를 재배포하지 않는다.
- `conaninfo.txt`: `arch=x86_64`, `os=Windows`만 있다.
- `eula.txt` / `eula.rtf`: 역공학 금지 문장만 LEGAL_LIMITS.md에 인용했다.

디스크의 QML 518개는 모두 `QtQuick`, `Qt5Compat`, `QtWebEngine` 아래의 프레임워크 파일이었다. 애플리케이션 전용 QML 디렉터리는 보이지 않았다. 앱 UI 소스가 바이너리 안에 컴파일돼 있는지는 **UNKNOWN**. 그 내용을 추출하지 않았다.

## 상위 구성

| 파일 또는 폴더 | 크기(bytes) | 관찰 |
|---|---:|---|
| 4kvideodownloaderplus.exe | 179,314,432 | 메인 GUI 실행 파일 |
| Qt6WebEngineCore.dll | 154,346,752 | Qt 6.8.3, The Qt Company, 같은 서명 |
| Qt6Core.dll / Qt6Qml.dll / Qt6Quick.dll | 6,074,624 / 5,243,136 / 6,300,928 | FileVersion 6.8.3.0 |
| avcodec-58.dll / avformat-58.dll / avutil-56.dll | 28,678,912 / 2,537,216 / 645,888 | 버전 리소스 없음. 파일명 SONAME |
| swresample-3.dll / swscale-5.dll / postproc-55.dll | 204,032 / 716,032 / 103,168 | FFmpeg 계열 파일명 |
| onnxruntime_omnisale.dll | 16,037,120 | ONNX Runtime, ProductVersion 1.21.20250307.2.e0b66ca, Microsoft 설명, InterPromo 서명 |
| DirectML.dll | 18,533,120 | DirectML 1.15.4, Microsoft 설명, InterPromo 서명 |
| lalalai_proc.dll | 412,416 | 버전 문자열 없음, InterPromo 서명 |
| libcrypto-1_1-x64.dll / libssl-1_1-x64.dll | 3,497,216 / 713,472 | OpenSSL 1.1 파일명 |
| portaudio_x64.dll | 184,064 | 파일명 |
| QtWebEngineProcess.exe | 697,600 | Qt WebEngine 자식 프로세스 파일명 |
| crashpad_handler.exe | 632,064 | 파일명 |
| QtQuick 디렉터리 | 8,168,021 | 프레임워크 QML·플러그인 |
| imageformats | 1,350,400 | qgif, qico, qjpeg, qsvg, qwebp |

확장자 상위: png 882, qml 518, dll 110, 확장자 없음 37, qmltypes 35, txt 7, pak 4, exe 3.

## SHA-256

| 파일 | SHA-256 |
|---|---|
| 4kvideodownloaderplus.exe | `50E3EA9303549D1700D2908AF6025F8C2CE5512C8F5A0682CCC1DEDBDE2CEBBC` |
| Qt6Core.dll | `1A2DF561EEF23DDCD0794D8072EAC1EF27556E5289591A0DE4A50DD847771773` |
| Qt6Qml.dll | `1E21B5CFF2C997D5A572AAD490A603FF4C594E1577887DB85C6208C54DAFDA36` |
| Qt6Quick.dll | `A20884F02ED84A0BDD08F7D167503B3CA4D15A21771C5376ADF19C7C51965202` |
| Qt6WebEngineCore.dll | `7D84820D74ECDB5813AFC26559CED4FD0527AA606650C346D2D059D50702234B` |
| avcodec-58.dll | `1E9745DE6B2ADFBA4C033D54E9E0F6D8BFDEFCE3A0F00F967D204480B82B5506` |
| avformat-58.dll | `9715CD4DC41308690A18120FA36CEFE182D4F4D1FEE5012C6BFDE7B22729F2A7` |
| avutil-56.dll | `539BB88FC9AB908BE8770415AEE5D074EF97180252C211FD29EB3B7624C140BC` |
| lalalai_proc.dll | `BEA9641CC5169CC41E1D386FA59876EB456CAF2C0893ED50333713EF695952A6` |
| onnxruntime_omnisale.dll | `65E9800B4040D0C1F6A2C01CBF99FDFC56E224074C8E4F035A6EB9E96B1B6FF9` |
| DirectML.dll | `E723B06CD64573CF5E1606AE308700153E8188193531710FA0F7E6B1AD048E7D` |
| libssl-1_1-x64.dll | `42818FB9488854019392F7507FCD672C2CD94E097DCAFC328872482D68C7FC0E` |
| libcrypto-1_1-x64.dll | `0D5B81952845493F2F3543650094B5E1489AE273ECE4B2E9D8371578922D07EB` |
| QtWebEngineProcess.exe | `73FE72312D1C161B889293D8AA96F9FCC691BF9E578792AEB9734BF67BCB1BE9` |
| crashpad_handler.exe | `4D07E5DDED4F564D4D86D234455940E3C3EF80B3CC3161F9506BFC2E9A49EF3F` |

1,602개 전체 해시는 만들지 않았다. png와 Qt QML은 프레임워크 자산으로 개수만 집계했다.
