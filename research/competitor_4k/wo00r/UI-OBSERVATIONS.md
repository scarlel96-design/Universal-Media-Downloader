# WO-00R UI 관찰

조사일: 2026-11-01.

창을 조작하지 않았다. 이미 `4kvideodownloaderplus`와 `QtWebEngineProcess` 둘이 실행 중이었다. 그 세션에 키 입력, URL 붙여넣기, 클릭을 하지 않았고 프로세스를 종료하지 않았다.

| 상황 | 상태 |
|---|---|
| 프로그램 시작 | NOT RUN. 기존 프로세스의 시작 시각만 읽음 |
| URL 입력 및 분석 | NOT RUN |
| 영상 메타데이터 표시 | NOT RUN |
| 다운로드 시작 | NOT RUN |
| 일시정지 | NOT RUN |
| 재개 | NOT RUN |
| 취소 | NOT RUN |
| 다중 다운로드 | NOT RUN |
| 다운로드 완료 | NOT RUN |
| 프로그램 종료 | NOT RUN |
| 화면 캡처 | NOT RUN |

정적 쪽에서 UI 스택으로 확인된 것은 Qt 6.8.3 Quick와 QML, 그리고 Qt WebEngine이 메인 프로세스에 매핑되어 있다는 점이다. Qt Widgets DLL은 임포트 표에만 있고, 이번 모듈 필터에는 없다. 네이티브 제목 표시줄인지, 프레임리스인지, 고대비와 DPI에서 어떻게 보이는지는 보지 못했다.

개인 정보와 인증 정보는 수집하지 않았다. 명령줄, 창 제목, 원격 주소는 기록하지 않았다.
