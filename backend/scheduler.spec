# Build: cd frontend && pnpm build, then cd backend && .venv\Scripts\pyinstaller scheduler.spec
from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ["desktop.py"],
    pathex=["."],
    datas=[("../frontend/dist", "frontend/dist")],
    hiddenimports=collect_submodules("uvicorn"),  # uvicorn picks its loop/protocol modules at runtime
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="Scheduler",
    icon="assets/scheduler.ico",
    console=False,
    upx=False,
)
