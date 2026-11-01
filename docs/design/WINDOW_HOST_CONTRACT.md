# Windows 창 호스트 계약

모드: `native-frame`. 코드는 `src/umd/app/host.py`와 `src/umd/ui/qml/Main.qml`.

## 선택한 방식

Qt `ApplicationWindow`에 다음 플래그만 둔다.

- `Qt.Window`
- `Qt.WindowTitleHint`
- `Qt.WindowSystemMenuHint`
- `Qt.WindowMinimizeButtonHint`
- `Qt.WindowMaximizeButtonHint`
- `Qt.WindowCloseButtonHint`

버튼 순서는 Windows가 그린다. 오른쪽의 최소화, 최대화/복원, 닫기다. 앱이 그 버튼을 다시 그리지 않는다.

`FramelessWindowHint`와 `CustomizeWindowHint`는 넣지 않는다. 후자는 시스템 메뉴와 Snap Layouts를 떨어뜨릴 수 있다. 드래그 이동과 크기 조절은 OS 프레임이 한다. `startSystemMove`를 직접 쓰지 않는다.

## 보존하려는 OS 동작

아래는 이 플래그가 유지할 때 Windows가 제공하는 동작이다. 이 세션에서 키를 눌러 확인하지 않은 항목은 NOT RUN이다.

| 동작 | 기대 | 이 세션 |
|---|---|---|
| 최소화, 최대화, 복원, 닫기 | 시스템 버튼 | 플래그 존재는 자동 검사. 클릭은 NOT RUN |
| 제목 표시줄 더블 클릭 | 최대화/복원 | NOT RUN |
| Alt+F4 | 닫기 | NOT RUN |
| Alt+Space | 시스템 메뉴 | 플래그에 `WindowSystemMenuHint`. 키 입력 NOT RUN |
| Win+Z, 최대화 버튼 끌기, Snap | 시스템 스냅 | NOT RUN. 프레임리스를 피한 이유 |
| Win+화살표 | 스냅 | NOT RUN |
| 네 모서리 크기 조절 | 시스템 | NOT RUN |
| 작업 표시줄 복원 | 시스템 | NOT RUN |
| 다른 모니터, DPI 전환 | Qt 논리 좌표 | 배율 프로세스 검사는 테스트가 담당. 실모니터 이동 NOT RUN |

실패하면 이 모드를 유지한다. 더 장식적인 제목 표시줄로 바꾸지 않는다.

## DPI

Qt 6 기본 스케일을 쓴다. 레이아웃 숫자는 논리 픽셀이다. 1440×900과 1280×800은 사이드바 236과 4열, 1024×768은 사이드바 196과 3열이다. 최소 크기는 1024×680이다.

100, 125, 150, 200퍼센트는 `QT_SCALE_FACTOR`로 프로세스를 나눠 논리 폭이 유지되는지만 본다. 모니터 사이 실제 DPI 전환은 NOT RUN이다.

## 접근성

URL 필드, 사이드바 항목, 필터, 카드, 다운로드 버튼에 이름을 붙였다. Ctrl+F는 주소 필드, Ctrl+A는 보이는 후보 전체 선택, Esc는 정보 패널을 닫는다. 주소 필드에 포커스가 있으면 Ctrl+A는 텍스트 선택을 빼앗지 않도록 비활성화한다. 고대비 테마 전용 팔레트는 아직 없다.
