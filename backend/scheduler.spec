# Built by ..\build.ps1 (frontend first; output goes to ..\dist)
from PyInstaller.utils.hooks import collect_all, collect_submodules

# pywinpty starts OpenConsole.exe / winpty-agent.exe next to its module; PyInstaller would leave those out.
winpty_datas, winpty_binaries, winpty_hidden = collect_all("winpty")

a = Analysis(
    ["desktop.py"],
    pathex=["."],
    datas=[("../frontend/dist", "frontend/dist"), *winpty_datas],
    binaries=winpty_binaries,
    hiddenimports=[*collect_submodules("uvicorn"), *winpty_hidden],  # uvicorn picks its loop/protocol modules at runtime
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
