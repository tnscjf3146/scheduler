"""One terminal session (a ConPTY running PowerShell + the agent's CLI) per agent."""

import asyncio
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from winpty import PtyProcess

from . import db

SCROLLBACK = 256_000  # characters replayed to a newly opened terminal view
ANSI = re.compile(r"\x1b\[[0-9;?<>=]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][A-Z0-9]|\x1b[=>78]")
# Claude Code: "Yes, I trust this folder". Codex: "Do you trust the contents of this directory?"
TRUST_PROMPT = re.compile(r"trust\s*this\s*folder|trust\s*the\s*contents|do\s*you\s*trust", re.I)
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
        self.received = 0  # total characters ever printed (buffer is capped, this is not)
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
            self.received += len(data)
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

    def wait_until_quiet(self, quiet: float = 1.5, timeout: float = 20.0) -> None:
        """Waits until the CLI has drawn something and then stopped, i.e. its start-up screen is ready for input."""
        # ponytail: output silence as the ready signal; a CLI that keeps animating just waits for the timeout.
        end, last, since = time.monotonic() + timeout, -1, time.monotonic()
        while time.monotonic() < end and self.alive:
            if self.received != last:
                last, since = self.received, time.monotonic()
            elif last > 0 and time.monotonic() - since >= quiet:
                return
            time.sleep(0.2)

    def type_line(self, text: str) -> None:
        """Puts one line in the CLI's input and presses Enter. A TUI such as Claude Code reads a burst of characters
        as a paste and swallows an Enter that follows too closely, so the text goes in as a marked (bracketed) paste
        when the CLI asked for that, and Enter comes separately once the paste has been taken in."""
        if "\x1b[?2004h" in self.buffer:  # the CLI turned on bracketed paste
            text = f"\x1b[200~{text}\x1b[201~"
        self.write(text)
        time.sleep(1.0)
        self.write("\r")

    def screen_tail(self, chars: int = 3000) -> str:
        """The end of the output as plain text (escape codes removed), for checking what the CLI is showing."""
        return ANSI.sub("", self.buffer[-chars:])

    def at_shell_prompt(self) -> bool:
        """True when the agent's CLI has exited and PowerShell is waiting: typed text would run as a command."""
        lines = [l for l in self.screen_tail(1500).replace("\r", "").split("\n") if l.strip()]
        return bool(lines) and bool(re.search(r"PS [A-Za-z]:\\[^>]*>\s*$", lines[-1]))

    def type_when_ready(self, text: str, timeout: float = 300.0) -> bool:
        """Types the line once the CLI is idle. While its "trust this folder?" question is on screen it waits
        for the user to answer; Enter there would pick the default, which is "No, exit". False if it gave up."""
        self.wait_until_quiet()
        end = time.monotonic() + timeout
        shown = self.screen_tail()
        while TRUST_PROMPT.search(shown) and self.alive and time.monotonic() < end:
            mark = self.received
            while self.received - mark < 200 and self.alive and time.monotonic() < end:
                time.sleep(0.5)  # until the CLI redraws (the user answered, or e.g. the window was resized)
            self.wait_until_quiet()
            shown = ANSI.sub("", self.buffer[-(self.received - mark):])  # only what came after the question
        if not self.alive or time.monotonic() >= end or self.at_shell_prompt():
            return False
        self.type_line(text)
        return True

    def resize(self, cols: int, rows: int) -> None:
        if self.alive:
            self.pty.setwinsize(rows, cols)

    def kill(self) -> None:
        if self.alive:  # the whole tree: PowerShell, the CLI and whatever the CLI started under it
            subprocess.run(["taskkill", "/PID", str(self.pty.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
            try:
                self.pty.terminate(force=True)  # also closes the terminal itself
            except OSError:
                pass  # taskkill already ended the process


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


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def kill_strays(agent_ids: list[str]) -> None:
    """Ends processes whose command line names one of these agents (its folder or MCP config). Claude Code starts
    background helpers (a daemon, forked sessions) outside the terminal's process tree; they keep the agent's folder
    open, so it could not be deleted, and they outlive the app. An agent id is 32 random hex characters, so nothing
    else matches."""
    ids = [a for a in agent_ids if re.fullmatch(r"[0-9a-f]{32}", a)]
    if not ids:
        return
    script = (
        "$ids = $env:SCHEDULER_AGENT_IDS -split ','; Get-CimInstance Win32_Process | Where-Object { "
        "$cl = $_.CommandLine; $cl -and ($ids | Where-Object { $cl.Contains($_) }) } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env={**os.environ, "SCHEDULER_AGENT_IDS": ",".join(ids)},  # the ids are not in this command line
        capture_output=True, timeout=60, creationflags=NO_WINDOW,
    )


def stop(agent_id: str) -> None:
    with _guard:
        session = _sessions.pop(agent_id, None)
    if session:
        session.kill()
    kill_strays([agent_id])


def stop_all() -> None:
    with _guard:
        ids = list(_sessions)
        live = [_sessions.pop(i) for i in ids]
    for session in live:
        session.kill()
    kill_strays(ids)  # one sweep for all agents, so closing the app stays quick
