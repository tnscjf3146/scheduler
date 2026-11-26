import asyncio
import json
import os
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from . import db, defaults, extensions, sessions

router = APIRouter(prefix="/api/agents", tags=["agents"])

CLIS = ("claude", "codex", "shell")


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    role: str = Field(default="", max_length=100)
    persona: str = Field(default="", max_length=4000)  # part of the identity the agent starts with
    cli: str = Field(pattern="^(claude|codex|shell)$")
    cwd: str | None = None
    # Skill / harness ids to attach (Claude Code only). None: the app's default skills.
    extensions: list[str] | None = Field(default=None, max_length=50)


def write_agents_md(agent: dict, replace: bool = False) -> None:
    """Codex reads neither hooks nor skills, so it gets its identity and the app's rules as AGENTS.md in its work
    folder. An existing file is left alone (a user-chosen folder may be a project with its own) unless a handover
    replaces it. Claude Code agents get nothing in their folder: see extensions.build_plugin."""
    path = Path(agent["cwd"]) / "AGENTS.md"
    if replace or not path.exists():
        path.write_text(defaults.agents_md(agent), encoding="utf-8")


def _get(conn, agent_id: str) -> dict:
    row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if not row:
        raise HTTPException(404, "에이전트가 없습니다")
    return dict(row)


@router.get("")
def list_agents() -> list[dict]:
    with db.connect() as conn:
        agents = db.rows(conn.execute("SELECT * FROM agents ORDER BY created_at"))
    return [{**a, "status": sessions.status(a["id"])} for a in agents]


@router.post("", status_code=201)
def create(body: AgentIn) -> dict:
    agent_id = db.new_id()
    if body.cwd:
        workspace = Path(body.cwd)
        if not workspace.is_dir():
            raise HTTPException(400, "작업 폴더가 없습니다")
    else:
        # Own workspace per agent. Kept when the agent is deleted: it may hold the agent's work.
        workspace = db.data_dir() / "agents" / agent_id / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
    with db.connect() as conn:
        agent = _insert(conn, agent_id, body, workspace)
    if agent["cli"] == "codex":
        write_agents_md(agent)
    return agent


def _insert(conn, agent_id: str, body: AgentIn, workspace: Path) -> dict:
    conn.execute(
        "INSERT INTO agents (id, name, role, cli, cwd, created_at, extensions, persona) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (agent_id, body.name.strip(), body.role.strip(), body.cli, str(workspace), db.now(),
         json.dumps(extensions.builtin_ids() if body.extensions is None else body.extensions), body.persona.strip()),
    )
    return {**_get(conn, agent_id), "status": "stopped"}


@router.post("/{agent_id}/handover", status_code=201)
def handover(agent_id: str, body: AgentIn) -> dict:
    """Fires the agent and hires a new one into the same work folder (body.cwd is ignored).
    The new agent starts a fresh conversation with its own identity; the old conversation stays on disk."""
    with db.connect() as conn:
        workspace = Path(_get(conn, agent_id)["cwd"])
        sessions.stop(agent_id)
        new_id = db.new_id()
        (db.data_dir() / "agents" / new_id).mkdir(parents=True, exist_ok=True)
        (db.data_dir() / "agents" / new_id / sessions.FRESH_MARKER).touch()
        conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        agent = _insert(conn, new_id, body, workspace)
    if agent["cli"] == "codex":
        write_agents_md(agent, replace=True)  # the old one describes the agent that just left
    return agent


@router.post("/{agent_id}/restart")
def restart(agent_id: str) -> dict:
    # Stops the session; the terminal view starts a fresh one when it reconnects.
    with db.connect() as conn:
        agent = _get(conn, agent_id)
    sessions.stop(agent_id)
    return {**agent, "status": "stopped"}


@router.post("/{agent_id}/open-folder", status_code=204)
def open_folder(agent_id: str) -> None:
    """Shows the agent's working folder in File Explorer."""
    with db.connect() as conn:
        cwd = _get(conn, agent_id)["cwd"]
    if not Path(cwd).is_dir():
        raise HTTPException(404, f"작업 폴더가 없습니다: {cwd}")
    os.startfile(cwd)


@router.delete("/{agent_id}", status_code=204)
def delete(agent_id: str, purge: bool = False) -> None:
    """Without purge ("해고") the agent's folder stays. With purge ("삭제") the app's own folder for it goes too:
    the workspace it made and its launch files. A work folder the user chose is never touched."""
    with db.connect() as conn:
        agent = _get(conn, agent_id)
        sessions.stop(agent_id)
        if purge:
            agents_root = db.data_dir() / "agents"
            _remove_tree(agents_root / agent_id)
            # After a handover the workspace sits under the first agent's folder; it is still the app's own.
            cwd = Path(agent["cwd"])
            if cwd.is_relative_to(agents_root):
                _remove_tree(agents_root / cwd.relative_to(agents_root).parts[0])
        conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))


def _remove_tree(folder: Path) -> None:
    # The just-killed shell can hold the folder open for a moment on Windows.
    for _ in range(10):
        try:
            shutil.rmtree(folder)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            time.sleep(0.3)
    raise HTTPException(409, "폴더를 지우지 못했습니다. 열려 있는 파일을 닫고 다시 시도하세요")


@router.websocket("/{agent_id}/terminal")
async def terminal(ws: WebSocket, agent_id: str, cols: int = 100, rows: int = 30):
    """Client -> server: {"type":"input","data":...} | {"type":"resize","cols":..,"rows":..}. Server -> client: raw output."""
    await ws.accept()
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if not row:
        await ws.close(code=4404)
        return
    base_url = f"http://{ws.url.hostname}:{ws.url.port}"
    session = sessions.get_or_start(dict(row), base_url, cols, rows)
    session.resize(cols, rows)
    queue, snapshot = session.subscribe(asyncio.get_running_loop())

    async def pump():
        if snapshot:
            await ws.send_text(snapshot)
        while True:
            await ws.send_text(await queue.get())

    task = asyncio.create_task(pump())
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "input":
                session.write(msg["data"])
            elif msg.get("type") == "resize":
                session.resize(int(msg["cols"]), int(msg["rows"]))
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        session.unsubscribe(queue)
