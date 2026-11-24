# scheduler

나와 에이전트(터미널 세션)가 함께 일하는 개인용 대시보드 exe. 기획은 [docs/plan.md](docs/plan.md).

| 폴더 | 내용 |
|---|---|
| `backend/` | FastAPI + SQLite, exe 진입점(`desktop.py`) |
| `frontend/` | React + TypeScript + Vite + Tailwind |
| `docs/` | 기획서, 유저플로우, ERD, API |

데이터는 `%APPDATA%\Scheduler\scheduler.db`에 저장된다.

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
cd backend;  .venv\Scripts\uvicorn app.main:app --reload --port 8000
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
