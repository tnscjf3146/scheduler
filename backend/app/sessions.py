"""One terminal session (a ConPTY running PowerShell + the agent's CLI) per agent."""

import asyncio
import json
import re
import threading
from pathlib import Path

from winpty import PtyProcess

from . import db

SCROLLBACK = 256_000  # characters replayed to a newly opened terminal view
FRESH_MARKER = "fresh"  # in an agent's folder: start a new conversation next launch instead of continuing


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _has_claude_history(cwd: str) -> bool:
    """Claude Code saves each folder's conversations as ~/.claude/projects/<cwd, non-alphanumerics -> '-'>/*.jsonl."""
    # ponytail: mirrors Claude Code's folder naming; if that changes, agents just start a fresh conversation.
    return any((Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", cwd)).glob("*.jsonl"))


def _launch_script(agent: dict, mcp_url: str) -> Path:
    """Writes the PowerShell script that starts the agent's CLI with the approval MCP server attached.
    Continues the last conversation in the agent's folder when there is one, so closing the app loses nothing."""
    folder = db.data_dir() / "agents" / agent["id"]
    folder.mkdir(parents=True, exist_ok=True)
    mcp_json = folder / "mcp.json"
    mcp_json.write_text(json.dumps({"mcpServers": {"scheduler": {"type": "http", "url": mcp_url}}}), encoding="utf-8")

    # A handed-over agent shares its predecessor's folder, and so its saved conversation: skip that once.
    fresh = folder / FRESH_MARKER
    is_fresh = fresh.exists()
    fresh.unlink(missing_ok=True)

    lines = [f"Set-Location -LiteralPath {_ps_quote(agent['cwd'])}"]
    if agent["cli"] == "claude":
        cont = " --continue" if not is_fresh and _has_claude_history(agent["cwd"]) else ""
        lines.append(f"claude{cont} --mcp-config {_ps_quote(str(mcp_json))}")
    elif agent["cli"] == "codex":
        # Codex has no cheap "is there a session here?" check, so remember that it was started once.
        started = folder / "codex-started"
        resume = " resume --last" if started.exists() else ""
        started.touch()
        lines.append(f"codex{resume} -c \"mcp_servers.scheduler.url='{mcp_url}'\"")
    script = folder / "launch.ps1"
    script.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8-sig")
    return script


class Session:
    def __init__(self, agent: dict, base_url: str, cols: int, rows: int):
        script = _launch_script(agent, f"{base_url}/mcp/{agent['id']}")
        self.pty = PtyProcess.spawn(
            ["powershell.exe", "-NoLogo", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=agent["cwd"], dimensions=(rows, cols),
        )
        self.buffer = ""
        self.lock = threading.Lock()
        self.subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        while True:
            try:
                data = self.pty.read(4096)
            except EOFError:
                break
            if data:
                self._emit(data)
        self._emit("\r\n\x1b[90m[세션이 종료되었습니다. 에이전트 메뉴에서 다시 시작할 수 있습니다]\x1b[0m\r\n")

    def _emit(self, data: str) -> None:
        with self.lock:
            self.buffer = (self.buffer + data)[-SCROLLBACK:]
            for loop, queue in self.subscribers:
                loop.call_soon_threadsafe(queue.put_nowait, data)

    @property
    def alive(self) -> bool:
        return self.pty.isalive()

    def subscribe(self, loop) -> tuple[asyncio.Queue, str]:
        queue: asyncio.Queue = asyncio.Queue()
        with self.lock:  # snapshot and subscribe together so no output falls in between
            self.subscribers.append((loop, queue))
            return queue, self.buffer

    def unsubscribe(self, queue) -> None:
        with self.lock:
            self.subscribers = [s for s in self.subscribers if s[1] is not queue]

    def write(self, data: str) -> None:
        if self.alive:
            self.pty.write(data)

    def resize(self, cols: int, rows: int) -> None:
        if self.alive:
            self.pty.setwinsize(rows, cols)

    def kill(self) -> None:
        if self.alive:
            self.pty.terminate(force=True)


_sessions: dict[str, Session] = {}
_guard = threading.Lock()


def get_or_start(agent: dict, base_url: str, cols: int, rows: int) -> Session:
    with _guard:
        session = _sessions.get(agent["id"])
        if session is None or not session.alive:
            session = _sessions[agent["id"]] = Session(agent, base_url, cols, rows)
        return session


def status(agent_id: str) -> str:
    session = _sessions.get(agent_id)
    if session is None:
        return "stopped"
    return "running" if session.alive else "exited"


def stop(agent_id: str) -> None:
    with _guard:
        session = _sessions.pop(agent_id, None)
    if session:
        session.kill()


def stop_all() -> None:
    for agent_id in list(_sessions):
        stop(agent_id)
