import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from . import db, sessions

router = APIRouter(prefix="/api/agents", tags=["agents"])

CLIS = ("claude", "codex", "shell")


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    role: str = Field(default="", max_length=100)
    cli: str = Field(pattern="^(claude|codex|shell)$")
    cwd: str | None = None


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
    cwd = body.cwd or str(Path.home())
    if not Path(cwd).is_dir():
        raise HTTPException(400, "작업 폴더가 없습니다")
    with db.connect() as conn:
        agent_id = db.new_id()
        conn.execute(
            "INSERT INTO agents (id, name, role, cli, cwd, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (agent_id, body.name.strip(), body.role.strip(), body.cli, cwd, db.now()),
        )
        return {**_get(conn, agent_id), "status": "stopped"}


@router.post("/{agent_id}/restart")
def restart(agent_id: str) -> dict:
    # Stops the session; the terminal view starts a fresh one when it reconnects.
    with db.connect() as conn:
        agent = _get(conn, agent_id)
    sessions.stop(agent_id)
    return {**agent, "status": "stopped"}


@router.delete("/{agent_id}", status_code=204)
def delete(agent_id: str) -> None:
    with db.connect() as conn:
        _get(conn, agent_id)
        sessions.stop(agent_id)
        conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))


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
