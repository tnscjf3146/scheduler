import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db


def frontend_dist() -> Path:
    # Inside the PyInstaller exe the build is unpacked next to the code (sys._MEIPASS).
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    yield


app = FastAPI(title="Scheduler", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    with db.connect() as conn:
        version = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()["value"]
    return {"status": "ok", "schema_version": version}


# Mounted last so /api routes win. Missing in dev (Vite serves the UI on its own port).
if frontend_dist().is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist(), html=True), name="frontend")
