# WO-04 결과 보고

작업일: 2026-11-01

기준 브랜치 `main` HEAD: `56d8c0eff1fb9d4c15328fcd6d314897f7ebe6b8`

작업 브랜치: `feat/wo04-browser-extraction`

구현 커밋: 이 보고서를 저장하는 커밋의 부모. PR 주소는 PR을 만든 뒤 이 문서에 적는다.

WO-00E: BLOCKED. 유지한다.

개발 판정: CONDITIONAL GO

정식 공개 릴리스: NO-GO

## 구현한 기능

갤러리 저장은 사용자가 고른 URL만 쓴다. 파일마다 `new`, `existing`, `failed`, `cancelled`를 남긴다. 같은 바이트는 다시 쓰지 않고, 다른 바이트는 번호를 붙여 둘 다 남긴다.

gallery-dl과 yt-dlp는 자식 프로세스에서 실행한다. DNS 가드는 그 프로세스 안에만 설치한다. 부모의 HTML 수신과 추출 라우터는 전역 `socket.getaddrinfo`를 바꾸지 않는다. 브라우저의 로컬 페이지는 전달 프록시를 쓰지 않는다. 이 호스트에서 루프백을 프록시로 돌리면 연결이 끊겼다. 로컬 모드에서는 `127.0.0.1`과 `localhost`만 통과하고 그 밖은 요청을 끊는다. 공개 모드 브라우저는 검사한 주소로만 접속하는 프록시를 쓴다. 그 공개 브라우저 경로는 이번 자동 테스트에서 실제 사이트에 나가지 않았다.

JavaScript로 만든 이미지, SPA 해시, 지연 로딩, 최대 8회에서 멈추는 무한 스크롤을 로컬 페이지로 확인했다. 분류는 기존 HTML 분류기를 다시 쓴다. 광고, 추천, 로고, 프로필은 제외하고 본문의 작은 이미지는 남긴다. 크기 접미사가 다른 같은 그림은 큰 쪽만 저장 대상으로 두고 작은 쪽은 썸네일로 남긴다.

로그인은 사용자가 브라우저에서 직접 한다. 프로그램은 비밀번호를 넣지 않고 CAPTCHA를 풀지 않는다. 세션은 사이트별 임시 파일이며 SQLite에 쿠키를 쓰지 않는다. Windows 보안 저장소는 확인하지 못했으므로 영구 저장은 꺼 둔다.

미리보기는 원본 비율을 유지한다. 영상은 재생, 일시정지, 음소거 상태를 가진다. 공개 원격 영상은 미리보기만으로 받지 않는다. 창 버튼과 네이티브 제목 표시줄은 바꾸지 않았다.

## 테스트

| 항목 | 결과 |
| --- | --- |
| 단위 테스트 재실행 | PASS. 113 passed in 50.31s. 기존 88개와 WO-04 추가 25개가 들어 있다. |
| 같은 단위 테스트 첫 실행 | FAIL 1. `test_11_http_errors_and_corrupt_bodies_leave_no_file`가 `timed out`. 112 passed. |
| 그 테스트만 다시 실행 | PASS |
| 부하 테스트 직후 그 테스트 | PASS. 재현되지 않았다. 해결 완료로 적지 않는다. |
| 5,000장 부하, 측정 출력 | PASS. 1 passed in 191.33s. 아래 수치. |
| 5,000장 부하, 측정 없이 먼저 실행 | PASS. 1 passed in 174.37s. pytest가 측정 줄을 남기지 않았다. |
| 기존 공개 사이트 3개 | PASS. 3 passed in 43.54s. 2026-11-01. |
| 고속 프리셋 벽시계 | 앞선 실행에서 limit 24가 1.906s로 실패했다. WinError 10022 종료 콜백이 같이 찍혔다. 콜백 로그를 무시한 뒤 113개 실행에는 그 실패가 없었다. 영구 해결로 적지 않는다. |
| GitHub Actions 이번 워크플로 | NOT RUN. `workflow_dispatch`는 기본 브랜치의 파일을 읽는다. 이 브랜치의 Chromium 설치 단계는 main에 없다. |
| 실제 모니터의 Win+Z, Alt+Space, Alt+F4, DPI, 저장 대화상자, 고대비, 스크린 리더, 프레임 시간 | NOT RUN |
| 공개 사이트의 JavaScript 렌더링 | NOT RUN. 동적 검증은 로컬 고정 페이지다. |
| 디코딩되는 영상 프레임 | NOT RUN. 오프스크린에서 재생 상태는 켜졌고 오류 신호는 곧바로 오지 않았다. 재생 가능한 샘플을 만들지 못했다. |

부하 측정 (`-s` 실행, 로컬 픽스처):

- 5,000 files, 181.386 s, peak_connections 3, server_peak 3
- working_set_before 48033792, working_set_peak 99864576, integrity_mismatches 0
- large_file_bytes 6291526, large_file_traced_bytes 768410
- sequential 4.238 s, peak 1
- parallel 2.358 s, peak 3

브라우저 시나리오 4개는 별도 실행에서 4 passed in 16.51s. Chromium 작업 집합의 별도 측정은 NOT RUN이다. 페이지 스크립트 힙 상한은 256 MB로 두었다.

## 필수 항목

1. 갤러리 한 장만 저장: PASS
2. 다중 선택만 저장: PASS
3. 파일별 기록: PASS
4. 부모와 자식의 동시 이름 해석: PASS. 자식은 `127.0.0.1`을 막고 부모는 해석한다.
5. 내부 주소 차단: PASS
6. DNS 재해석과 핀 접속: PASS. 사설 응답이 섞이면 핀을 만들지 않는다. TCP 대상은 핀 주소다.
7. JavaScript로 추가된 이미지: PASS
8. SPA 재분석: PASS
9. Lazy Loading: PASS
10. Infinite Scroll 종료: PASS. 3장에서 멈춘다.
11. 광고와 추천 제외: PASS
12. 작은 본문 이미지 유지: PASS. 사유에 작은 본문임을 남긴다.
13. 원본과 썸네일 중복 제거: PASS
14. 브라우저 종료 후 프록시 포트: PASS. 로컬 경로는 프록시 대신 요청 차단이다. 공개 프록시의 장시간 유지는 NOT RUN.
15. 가짜 로그인 세션: PASS. 비밀번호 입력 없음.
16. 사이트 간 쿠키 격리: PASS
17. 만료와 삭제: PASS
18. 동적 이미지 미리보기 분류: PASS. 오프스크린 캡처는 아래.
19. 허용된 영상 재생: 제어 상태 PASS. 실제 프레임 NOT RUN.
20. 다운로드 중 UI 응답: PASS. 느린 페이지를 받는 동안 테마 전환이 0.5초 안에 돌아왔다.
21. SQLite v1/v2/v3: PASS. 기존 테스트가 113개 안에 있다. 스키마는 3에서 바꾸지 않았다. 쿠키는 데이터베이스에 없다.
22. 기존 88개 회귀: PASS. 113개 재실행에 포함된다. 첫 실행의 `timed out` 1건은 위에서 따로 적는다.

## 캡처

오프스크린 클라이언트 영역 `docs/design/captures/wo04-preview.png`. 1440x900, 27109 bytes. 네이티브 제목 표시줄은 포함되지 않는다. 프레임 시간은 NOT RUN이다. 비교 대상은 `docs/design/captures/wo03-preview.png`다.

inspector 사진은 `PreserveAspectFit`이다. 그리드 썸네일은 기존처럼 잘린다. Reduce Motion이 켜지면 등장 애니메이션을 두지 않는다.

## 라이선스

프로젝트 `LICENSE` 파일은 없다. 임의로 만들지 않았다.

- gallery-dl 1.32.19: GPL-2.0-only. Python 라이브러리로 import 한다. 자식 프로세스만으로 GPL 의무가 사라진다고 보지 않는다.
- PySide6: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only. 휠에는 상용 고지가 있다.
- yt-dlp: Unlicense
- httpx: BSD-3-Clause
- playwright 1.64.1: Apache-2.0 (`License-Expression`). 설치 메타데이터에서 확인했다.

정식 공개 릴리스는 NO-GO다.

## GitHub Actions

기존 정책은 유지한다. `workflow_dispatch`만, `windows-latest`만, 5,000장 잡은 입력이 켜질 때만. pull_request 트리거는 넣지 않았다. 테스트 잡에 Chromium 설치를 추가했다. checkout는 `actions/checkout@v4`, Python 설정은 `actions/setup-python@v5` 그대로다. 올리지 않은 버전을 검증했다고 적지 않는다.

이번 브랜치의 CI 실행: NOT RUN.

이전 main 실행 `41312197710`은 WO-03 보고서의 결과이며 이번 작업의 PASS가 아니다.

## 비용과 업로드

추가 비용: 0. 유료 API와 대형 러너는 쓰지 않았다.

Playwright Chromium은 로컬 도구 설치다. 사용자 데이터 업로드가 아니다.

코드 업로드는 이 공식 저장소 브랜치와 PR뿐이다. 세션 파일, 쿠키, SQLite, `.venv`는 커밋하지 않는다.

## 판정

개발: CONDITIONAL GO. 필수 자동 테스트는 통과했다. CI, 실제 데스크톱 조작, 공개 동적 페이지, 영상 프레임 재생은 NOT RUN이다. 필수 FAIL은 남아 있지 않다.

릴리스: NO-GO.

WO-00E: BLOCKED.

다음 작업은 시작하지 않는다.
