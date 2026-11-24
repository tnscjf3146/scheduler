"""exe entry point: run the API on a free local port and open it in a native window."""

import os
import socket
import threading

import uvicorn
import webview

from app import sessions
from app.main import app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class JsApi:
    """Called from the page as window.pywebview.api.* (only inside the exe window, not in a dev browser)."""

    def pick_folder(self) -> str | None:
        paths = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
        return paths[0] if paths else None


def main() -> None:
    # Claude Code's native installer puts claude.exe in ~/.local/bin, which is often missing from PATH
    # when the exe is started from Explorer. Agent terminals and mail summaries inherit this PATH.
    local_bin = os.path.expanduser(r"~\.local\bin")
    if os.path.isdir(local_bin):
        os.environ["PATH"] = local_bin + os.pathsep + os.environ.get("PATH", "")
    port = free_port()
    # log_config=None: the windowed exe has no stdout/stderr, and uvicorn's default log handlers would crash on it.
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    threading.Thread(target=server.run, daemon=True).start()

    webview.create_window("Scheduler", f"http://127.0.0.1:{port}", width=1440, height=900, min_size=(1100, 700), js_api=JsApi())
    webview.start()  # blocks until the window closes
    sessions.stop_all()  # end agent terminals with the window
    # Leftover pty reader / WinForms threads otherwise keep the process alive after the window is gone.
    # Nothing is lost: every database write is already committed.
    os._exit(0)


if __name__ == "__main__":
    main()
