# WO-GIT-00 보고서 — 공식 저장소로 WO-02 기준선 이관

## 판정

**GO**

## 저장소

- 주소: https://github.com/scarlel96-design/Universal-Media-Downloader
- 공개 범위: Public
- 기본 브랜치: main
- 작업 시작 시 원격 HEAD: `300f4e8cfadff4fa6b07f84d150cbce848bd440d` (`Initial commit`, README만 있음)
- 이관 브랜치: `chore/import-wo02-baseline`
- 이관 커밋: `42f0ba721fa02dffc6fbca32217dc918c361785b` (`Import the WO-00 through WO-02 baseline.`)
- Pull Request: https://github.com/scarlel96-design/Universal-Media-Downloader/pull/1
- 제목: `[Baseline] Import WO-00 through WO-02`
- 병합: `gh pr merge 1 --merge --delete-branch=false`
- main 병합 커밋: `6df39c48a55730e0df9e22adee1aa5e1daeaff3d`

Force push는 하지 않았다. 원격 브랜치는 삭제하지 않았다. 다른 GitHub 저장소는 만들지 않았다.

## 로컬 기준선

원본 작업 트리는 Git 저장소가 아니다. `git init`하지 않았고 파일을 지우지 않았다.

- 원본 작업 트리와 백업은 이 클론 밖의 로컬 디렉터리다. 백업 디렉터리 이름은 `2026-11-01-a128f5-wo02-backup`이다.
- 백업 도구: robocopy `/E`, `.venv`, `__pycache__`, `.pytest_cache` 제외. 91 files, 541.3 KB. robocopy 종료 코드 1은 복사가 끝난 상태다.
- 이관은 공식 저장소를 clone한 별도 디렉터리에서 했다. 원본에는 `git init`하지 않았다.

복사 전에 원격 README와 로컬 README가 다르다는 것을 확인했다. 원격 README는 제목 한 줄이었다. 이관 커밋은 프로젝트 README로 바꿨고, 초기 커밋 `300f4e8`은 이력에 남아 있다.

## 테스트

이관 트리에서 WO-02와 동일한 51개 테스트를 실행했다.

- 결과: 51 passed in 254.66s, exit 0
- 이 숫자는 이관 당시 실행이다. WO-03 개발 뒤의 재실행 결과로 쓰지 않는다.

## 민감 정보

스테이징 diff에서 사용자 프로필 경로, GitHub 토큰 접두, 개인 키 표식을 찾았고 없었다. 원본 조사 노트 두 곳에 있던 로컬 Grok 설정 경로는 클론 복사본에서 “the local Grok user config file”로 바꿨다. 원본과 백업의 문장은 그대로다.

제외한 것: `.venv/`, `__pycache__/`, `.pytest_cache/`, `.env`, 쿠키, 세션, `*.part`, SQLite, 캐시, 빌드 산출물, DLL, EXE, MSI, `tests/load-output/`. 테스트 픽스처의 `s3cret-token` 문자열은 로그에 비밀이 남지 않는지를 보는 가짜 값이다.

## 비용과 업로드

추가 비용은 0이다. 유료 API는 호출하지 않았다. 업로드한 것은 이 공식 저장소로 보낸 프로젝트 소스다. 쿠키, 비밀번호, 토큰, 가상환경, SQLite, 부분 파일, 4K Video Downloader+ 바이너리는 올리지 않았다.

## 유지한 상태

- WO-00E 역컴파일: BLOCKED. 프로그램을 실행하거나 분해하지 않았다.
- Windows 기본 제목 표시줄: 유지.
- 네이티브 창 동작(Win+Z, Alt+Space, Alt+F4, 실제 DPI, 고대비, 스크린 리더, 300ms 프레임, QFileDialog): NOT RUN.
