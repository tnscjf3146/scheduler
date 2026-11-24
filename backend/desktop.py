"""exe entry point: run the API on a free local port and open it in a native window."""

import socket
import threading

import uvicorn
import webview

from app.main import app


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    port = free_port()
    # log_config=None: the windowed exe has no stdout/stderr, and uvicorn's default log handlers would crash on it.
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    threading.Thread(target=server.run, daemon=True).start()

    webview.create_window("Scheduler", f"http://127.0.0.1:{port}", width=1440, height=900, min_size=(1100, 700))
    webview.start()  # blocks until the window closes
    server.should_exit = True


if __name__ == "__main__":
    main()
