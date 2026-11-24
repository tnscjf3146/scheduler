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

## exe 빌드

```powershell
cd frontend; pnpm build
cd ..\backend; .venv\Scripts\pyinstaller scheduler.spec --noconfirm
```

결과물: `backend\dist\Scheduler.exe`. 실행하면 로컬 포트에 API를 띄우고 앱 창(WebView2)으로 연다.

로고(`frontend/public/logo.svg`)를 바꿨으면 빌드 전에 exe 아이콘을 다시 만든다.

```powershell
cd frontend; pnpm icon   # -> backend/assets/scheduler.ico
```
