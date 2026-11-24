# scheduler

나와 에이전트(터미널 세션)가 함께 일하는 개인용 대시보드 exe. 기획은 [docs/plan.md](docs/plan.md), 지금 되는 것·안 되는 것은 [docs/features.md](docs/features.md).

| 폴더 | 내용 |
|---|---|
| `backend/` | FastAPI + SQLite, exe 진입점(`desktop.py`) |
| `frontend/` | React + TypeScript + Vite + Tailwind |
| `docs/` | 기획서, 유저플로우, 기능, ERD, API |

데이터는 `%APPDATA%\Scheduler\scheduler.db`에 저장된다. 메일 비밀번호는 Windows 자격 증명 관리자에 저장된다.

## 기능

| 위젯 | 하는 일 |
|---|---|
| 다가오는 일정 | 날짜가 지나지 않은 할 일을 가까운 순으로 |
| Agent | 역할별 에이전트. 에이전트 하나 = 터미널 세션 하나 (Claude Code · Codex · PowerShell). 누르면 오른쪽 터미널이 그 세션으로 바뀐다 |
| 할 일 · 일정(달력) | 할 일 추가·완료·삭제, 날짜가 있으면 달력에 표시 |
| 메일 검토 | IMAP으로 1분마다 새 메일 확인 → AI 요약 제목·요약·답장 초안. 전송은 버튼을 눌러야만 |
| 결재 대기 | 에이전트가 MCP 도구(`submit_approval`)로 올린 결재 문서를 승인·반려. 결과는 `get_approval`로 에이전트가 확인 |

필요한 것:

- **Claude Code CLI** (`claude`): 메일 요약과 Claude Code 에이전트에 쓴다. 로그인은 CLI가 처음 실행될 때 직접 한다.
- **Codex CLI** (`codex`): Codex 에이전트를 쓸 때만.
- **메일 앱 비밀번호**: Gmail은 2단계 인증 후 "앱 비밀번호", 네이버는 메일 환경설정에서 IMAP/SMTP를 켜고 (2단계 인증 시) 애플리케이션 비밀번호.

## 처음 세팅

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

cd ..\frontend
pnpm install
```

## 개발

터미널 두 개에서 실행하고 브라우저로 http://localhost:5173 을 연다. `/api` 요청은 Vite가 8000번으로 넘긴다.

```powershell
cd backend;  .venv\Scripts\uvicorn app.main:app --reload --reload-dir app --port 8000
cd frontend; pnpm dev
```

테스트:

```powershell
cd backend; .venv\Scripts\python -m pytest -q
```

## 빌드 (exe, 설치 파일)

필요: 위 세팅, [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup --scope user`)

```powershell
.\build.ps1
```

결과물은 `dist\`에 모인다.

| 파일 | 내용 |
|---|---|
| `Scheduler.exe` | 설치 없이 바로 실행하는 앱. 로컬 포트에 API를 띄우고 앱 창(WebView2)으로 연다 |
| `Scheduler-Setup-<버전>.exe` | 설치 파일. 관리자 권한 없이 `%LOCALAPPDATA%\Programs\Scheduler`에 설치하고 시작 메뉴·바탕화면 바로 가기와 제거 기능을 만든다. 제거해도 `%APPDATA%\Scheduler`의 데이터는 남긴다 |

버전은 `installer/scheduler.iss`의 `AppVersion`에서 바꾼다.

로고(`frontend/public/logo.svg`)를 바꿨으면 빌드 전에 exe 아이콘을 다시 만든다.

```powershell
cd frontend; pnpm icon   # -> backend/assets/scheduler.ico
```
