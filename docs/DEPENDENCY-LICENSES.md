# 의존성 라이선스

이 저장소에는 프로젝트 자체 `LICENSE` 파일이 없다. 아래는 2026-11-01에 로컬 가상환경에서 읽은 배포 메타데이터와 라이선스 파일이다. 앱 전체의 라이선스를 이 문서가 새로 정하지 않는다.

| 패키지 | 설치 버전 | 메타데이터 | 라이선스 파일에서 확인한 내용 |
| --- | --- | --- | --- |
| PySide6 | 6.12.0 | `License: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` | 휠의 `LicenseRef-Qt-Commercial.txt`는 Qt 상용 라이선스 안내문이다. METADATA는 오픈 소스 조건으로 LGPLv3, GPLv2, GPLv3를 적는다. |
| httpx | 0.28.1 | `License: BSD-3-Clause` | `LICENSE.md`는 Encode OSS Ltd의 BSD 조건이다. |
| gallery-dl | 1.32.19 | `License: GPL-2.0-only` | `licenses/LICENSE`는 GNU GPL 버전 2 전문이다. 이 프로그램은 gallery-dl을 라이브러리로 import한다. |
| yt-dlp | 2026.10.26 | `License-Expression: Unlicense` | `licenses/LICENSE`는 “This is free and unencumbered software released into the public domain.”으로 시작한다. |

gallery-dl 1.32.19의 추출 모듈 수는 287이다. yt-dlp 2026.10.26의 추출기 클래스 수는 1747이다. 홈은 각각 gallery-dl 배포 메타데이터와 yt-dlp 패키지다. gallery-dl 업스트림 프로젝트 페이지는 https://codeberg.org/mikf/gallery-dl 이다.

PySide6를 배포할 때는 Qt의 LGPL 또는 GPL 의무를 따로 봐야 한다. gallery-dl을 함께 배포하면 GPL-2.0의 조건이 그 결합물 배포에 적용될 수 있다. 이 문서는 그 법적 결론을 대신하지 않는다.
