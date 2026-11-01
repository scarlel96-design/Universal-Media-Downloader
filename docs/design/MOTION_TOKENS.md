# 모션 토큰

원본 값은 `src/umd/app/motion.py`다. QML은 `motion` 컨텍스트 객체를 읽는다. 시간은 밀리초다.

| 이름 | 시간 | spring | damping | mass | amplitude | 취소 | 동작 줄이기 |
|---|---:|---:|---:|---:|---:|---|---|
| button_hover | 110 |  |  |  |  | retarget | opacity-only |
| button_press | 100 |  |  |  |  | retarget | none |
| sidebar_select | 180 |  |  |  |  | retarget | instant |
| inspector | 300 | 2.4 | 0.78 | 1.0 | 0 | retarget | instant |
| popover | 180 |  |  |  | 0.03 | retarget | fade |
| preview | 260 |  |  |  |  | retarget | fade |
| thumbnail_in | 150 |  |  |  |  | drop | none |
| grid_select | 170 |  |  |  |  | retarget | instant |
| success | 190 | 2.0 | 0.86 | 0.8 | 0 | retarget | instant |

Qt `SpringAnimation`의 `spring`이 설계서의 stiffness 자리다. 300ms는 토큰의 목표 시간이고, 스프링이 그 시간에 정확히 멈추는지는 프레임 캡처로 재지 않았다.

연결된 동작:

- 사이드바 폭과 선택 색: `sidebar_select`
- 정보 패널 폭: `inspector` 스프링. `reduceMotion`이면 Behavior가 꺼져 즉시 바뀐다
- 버튼 호버 색, 카드 스케일: `button_hover`
- 카드 체크와 제목 투명도: `grid_select`
- 토스트 투명도: `button_hover` 시간을 재사용

동작 줄이기는 상태 표시줄의 "모션"과 `shell.setReduceMotion`으로 바꾼다. 시작 값은 Windows `SPI_GETCLIENTAREAANIMATION`이다. 애니메이션이 꺼져 있으면 줄이기가 켜진다. 이 값은 제어판의 전체 모션 설정과 항상 같지는 않다.

팝오버, 미리보기 공유 요소, 성공 체크, 썸네일 등장 토큰은 값만 있고 해당 화면은 아직 없다. 수천 개 스태거는 만들지 않는다.

중단: 스프링과 NumberAnimation은 목표가 바뀌면 현재 값에서 새 목표로 간다. 별도 타임라인을 쌓지 않는다.
