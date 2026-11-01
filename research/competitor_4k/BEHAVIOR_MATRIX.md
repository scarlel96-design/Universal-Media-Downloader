# 동작 비교 매트릭스

런타임 비교는 NOT RUN이다. 4K 열의 "공개"는 제품 페이지에서 읽은 기능 설명이고, 설치된 프로그램에서 그 화면을 본 것이 아니다. 내부 구현은 UNKNOWN이다.

| 영역 | 4K에서 확인한 것 | 수준 | 새 앱에서 쓸 구현 | 이미 있는 엔진 |
|---|---|---|---|---|
| URL 입력 | 링크를 붙여 넣고 받는 4단계 안내가 페이지에 있다 | 공개 VERIFIED. 실제 분기 UNKNOWN | 스킴·호스트 검사 후 라우터 | 자체 경량 코드. 추출은 아래 엔진 |
| 지원 사이트 | YouTube, Vimeo, TikTok, SoundCloud, Facebook, Twitch, Bilibili, Flickr, Dailymotion, Naver TV, Tumblr 등을 페이지가 나열한다 | 공개 VERIFIED. 설치본의 추출기 목록 UNKNOWN | 사이트별 코드를 새로 쓰지 않고 어댑터로 위임 | yt-dlp, gallery-dl |
| 재생목록·채널 | 재생목록, 채널, 검색 결과, Watch Later, 좋아요, Shorts를 한 번에 받는다고 페이지가 적는다 | 공개 VERIFIED. 페이지 단위 처리 UNKNOWN | 후보를 페이지 단위로 DB에 넣는다 | yt-dlp 재생목록 추출 |
| 화질·포맷 | 720p, 1080p, 4K, 8K. 영상 MP4/MKV. 음성 MP3/M4A/OGG. 자막 SRT. 더빙 트랙. 3D, 360° | 공개 VERIFIED. 병합 파이프 UNKNOWN | 포맷 목록을 보여주고 선택값을 엔진에 전달 | yt-dlp 포맷, FFmpeg 병합 |
| Smart Mode | 화질·형식·자막·폴더를 한 번 정해 다음 다운로드에 적용. 툴바 전구 아이콘이라고 페이지가 설명한다 | 공개 VERIFIED. UI 위치는 설치본에서 미확인 | 작업 프리셋 | 자체 설정. 엔진 옵션으로 매핑 |
| 동시 다운로드 | 판매 페이지는 Lite/Personal 3, Pro 최대 7이라고 적는다 | 공개 VERIFIED. 호스트별 제한과 백오프 UNKNOWN | 전체/호스트 상한을 둔다. 기본 이미지 12/호스트 3, 영상 2는 우리 설계값이며 4K 실측이 아니다 | HTTPX, yt-dlp `-N` |
| 재개·이어받기 | 공개 페이지에서 재개 규칙을 확인하지 못했다 | UNKNOWN | ETag, Last-Modified, 길이 검사 후에만 Range를 이어 붙인다 | HTTPX, yt-dlp `--continue` |
| 인앱 브라우저·로그인 | 비공개 영상은 접근 권한이 있을 때, 인앱 로그인 후 받는 프리미엄 기능이라고 페이지가 적는다 | 공개 VERIFIED. 쿠키 저장 방식 UNKNOWN | 사용자가 브라우저에서 로그인한 뒤 그 도메인만 승인 | Playwright. 쿠키 파일 상시 보관은 하지 않음 |
| 프록시 | ISP·지역 제한을 인앱 프록시로 우회할 수 있다고 페이지가 적는다 | 공개 VERIFIED. 구현 UNKNOWN | 사용자가 켠 SOCKS만 사용. 실패하면 직접 연결로 떨어지지 않음 | HTTPX, yt-dlp `--proxy` |
| 자동 구독 다운로드 | 재생목록·채널의 새 영상을 자동으로 받는 Pro 기능이라고 페이지가 적는다 | 공개 VERIFIED | V1 범위 밖. 사용자 스케줄이 필요하면 이후 작업 | yt-dlp 반복 호출 |
| 가져오기·내보내기 | 링크를 JSON으로 내보내고 가져온다고 페이지가 적는다 | 공개 VERIFIED. 스키마 UNKNOWN | 우리 스키마의 작업 목록. 4K JSON을 호환 형식으로 만들지 않는다 | 자체 |
| AI 음성 | 받은 파일의 보컬·음성·에코·배경음을 기기 안에서 처리하고, 파일을 서버로 올리지 않는다고 약관과 페이지가 적는다 | 공개 VERIFIED. 어떤 DLL이 그 일을 하는지는 INFERRED (E-023) | V1 비목표. 필요하면 나중에 공개 모델 | FFmpeg 필터는 대체가 아님 |
| 큐 UI | 정렬, 필터, 진행 표시가 있다고 페이지가 적는다 | 공개 VERIFIED. 상태 이름 UNKNOWN | QUEUED부터 COMPLETED까지 우리 상태 기계 | 자체 |
| 오류 처리 | 페이지 FAQ를 이번 조사에서 단계별로 재현하지 않았다 | UNKNOWN | 401, 403, 404, 429를 구분해 표시 | HTTPX, yt-dlp 종료 코드 |
| 메모리 | 대량 목록의 사용량은 측정하지 않았다 | NOT RUN | 가상화 그리드. 5,000개는 WO-02 | Qt Quick GridView |
| 창 | 설치본 창 버튼을 보지 않았다 | NOT RUN | Windows 기본 캡션 | Qt 네이티브 프레임 |
| 라이선스 잠금 | 등급별 장치 수와 기능 차이가 판매 페이지에 있다 | 공개 VERIFIED. 검사 코드 UNKNOWN, 분석 BLOCKED | 우리 앱에 4K 라이선스를 넣지 않는다 | 해당 없음 |

구현 결정: 4K의 내부 추출기를 다시 만들지 않는다. 공개 기능 이름만 우리 작업 흐름의 체크리스트로 쓴다.
