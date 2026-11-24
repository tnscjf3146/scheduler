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


AGENTS_MD = """# {name}

너는 Scheduler 앱 안에서 일하는 에이전트 '{name}'이다.

- 역할: {role}
- 작업 폴더: 이 폴더 (`{cwd}`). 만드는 파일은 여기에 둔다.
- 사용자는 Scheduler 대시보드 오른쪽 터미널에서 너와 대화한다.

## 결재

사용자가 정해야 하는 일이 생기면 혼자 정하지 말고 `scheduler` MCP 서버의 도구로 결재를 올린다.

- 결재가 필요한 일: 밖으로 나가는 것(클라이언트에게 보낼 내용, 제출물 확정), 되돌리기 어려운 것, 방향을 정하는 것.
- 결재가 필요 없는 일: 명령 실행 허락. 그건 CLI가 따로 묻는다.
- `submit_approval`: `title`(제목), `decision`(사용자가 승인/반려할 질문), `background`(지금까지 한 일), `attachments`(파일 경로 목록).
- `get_approval`: 받은 `id`로 결과를 확인한다. `pending`이면 아직 대기, `approved`면 진행, `rejected`면 `reason`을 읽고 고친다.
- 결과는 자동으로 오지 않는다. 사용자가 "결재 확인해"라고 하거나 다음 단계로 넘어가기 전에 직접 확인한다.

## 할 수 없는 것

할 일, 달력, 메일에는 접근할 수 없다. 필요하면 사용자에게 부탁한다.
"""


def _write_instructions(workspace: Path, name: str, role: str) -> None:
    """AGENTS.md is read by Codex; Claude Code reads CLAUDE.md, which just imports it."""
    (workspace / "AGENTS.md").write_text(
        AGENTS_MD.format(name=name, role=role or "(정해지지 않음, 사용자에게 물어본다)", cwd=workspace), encoding="utf-8"
    )
    (workspace / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")


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
        cwd = body.cwd
        if not Path(cwd).is_dir():
            raise HTTPException(400, "작업 폴더가 없습니다")
    else:
        # Own workspace per agent. Kept when the agent is deleted: it may hold the agent's work.
        workspace = db.data_dir() / "agents" / agent_id / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        _write_instructions(workspace, body.name.strip(), body.role.strip())
        cwd = str(workspace)
    with db.connect() as conn:
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
