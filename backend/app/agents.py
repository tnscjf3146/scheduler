import asyncio
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from . import db, sessions

router = APIRouter(prefix="/api/agents", tags=["agents"])

CLIS = ("claude", "codex", "shell")


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    role: str = Field(default="", max_length=100)
    persona: str = Field(default="", max_length=4000)  # goes only into AGENTS.md, which the user edits from then on
    cli: str = Field(pattern="^(claude|codex|shell)$")
    cwd: str | None = None


AGENTS_MD = """# {name}

너는 Scheduler 앱 안에서 일하는 에이전트 '{name}'이다.

- 역할: {role}
- 작업 폴더: 이 폴더 (`{cwd}`). 만드는 파일은 여기에 둔다.
- 사용자는 Scheduler 대시보드 오른쪽 터미널에서 너와 대화한다.

## 성격과 일하는 방식

{persona}

## 결재

사용자가 정해야 하는 일이 생기면 혼자 정하지 말고 `scheduler` MCP 서버의 도구로 결재를 올린다.

- 결재가 필요한 일: 밖으로 나가는 것(클라이언트에게 보낼 내용, 제출물 확정), 되돌리기 어려운 것, 방향을 정하는 것.
- 결재가 필요 없는 일: 명령 실행 허락. 그건 CLI가 따로 묻는다.
- 사용자가 만든 양식(결재서, 보고서 등)에 맞춰 쓴다. `list_forms`로 양식 이름과 칸을 확인한다.
- `submit_approval`: `title`(제목), `form`(양식 이름), `fields`(칸 이름별 내용 `{{"배경": "...", ...}}`), `attachments`(파일 경로 목록).
- 한 일을 알릴 때는 보고 양식(`kind`가 `report`)으로 올린다.
- `get_approval`: 받은 `id`로 결과를 확인한다. `pending`이면 아직 대기, `approved`면 진행(보고는 확인함), `rejected`면 `reason`을 읽고 고친다(보고는 보완 요청).
- 결과는 자동으로 오지 않는다. 사용자가 "결재 확인해"라고 하거나 다음 단계로 넘어가기 전에 직접 확인한다.

## 할 일 · 달력

대시보드의 할 일 목록과 달력은 같은 데이터다. 마감 일시(`due_at`)가 있는 할 일이 달력의 그 날짜에 보이고, 날짜가 지나지 않은 것은 "다가오는 일정"에도 보인다. `scheduler` MCP 서버의 도구로 다룬다.

- `list_todos`: 목록 보기. `from`·`to`(YYYY-MM-DD)로 기간을, `done`으로 완료 여부를 거른다.
- `add_todo`: `title`, `due_at`(YYYY-MM-DDTHH:MM, 현지 시간, 선택).
- `update_todo`: `id`와 바꿀 값만. 완료 처리는 `done: true`. `memo`(메모)와 `subtasks`(하위 할 일 `[{{"title", "done"}}]`)는 통째로 바뀌니 읽은 뒤 고쳐서 보낸다.
- `delete_todo`: 되돌릴 수 없다. 사용자가 지우라고 한 것만 지운다.
- 사용자가 "내일", "다음 주 월요일"처럼 말하면 오늘 날짜를 기준으로 계산한다. 시간을 말하지 않았으면 09:00으로 둔다.

## 할 수 없는 것

메일에는 접근할 수 없다. 필요하면 사용자에게 부탁한다.
"""


def _write_instructions(workspace: Path, name: str, role: str, persona: str, replace_agents_md: bool = False) -> None:
    """AGENTS.md is the one source, read by Codex as is. Claude Code and Gemini CLI read their own file, which imports it.
    Files that already exist are left alone: a user-chosen folder may be a project with its own.
    A handover replaces AGENTS.md, since it describes the agent that just left."""
    files = {
        "AGENTS.md": AGENTS_MD.format(
            name=name,
            role=role or "(정해지지 않음, 사용자에게 물어본다)",
            persona=persona or "(정해지지 않음. 사용자가 이 부분을 직접 채운다)",
            cwd=workspace,
        ),
        "CLAUDE.md": "@AGENTS.md\n",
        "GEMINI.md": "@AGENTS.md\n",
    }
    for file, text in files.items():
        if not (workspace / file).exists() or (replace_agents_md and file == "AGENTS.md"):
            (workspace / file).write_text(text, encoding="utf-8")


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
    _write_instructions(workspace, body.name.strip(), body.role.strip(), body.persona.strip())
    with db.connect() as conn:
        return _insert(conn, agent_id, body, workspace)


def _insert(conn, agent_id: str, body: AgentIn, workspace: Path) -> dict:
    conn.execute(
        "INSERT INTO agents (id, name, role, cli, cwd, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (agent_id, body.name.strip(), body.role.strip(), body.cli, str(workspace), db.now()),
    )
    return {**_get(conn, agent_id), "status": "stopped"}


@router.post("/{agent_id}/handover", status_code=201)
def handover(agent_id: str, body: AgentIn) -> dict:
    """Fires the agent and hires a new one into the same work folder (body.cwd is ignored).
    The new agent gets its own AGENTS.md and starts a fresh conversation; the old conversation stays on disk."""
    with db.connect() as conn:
        workspace = Path(_get(conn, agent_id)["cwd"])
        sessions.stop(agent_id)
        _write_instructions(workspace, body.name.strip(), body.role.strip(), body.persona.strip(), replace_agents_md=True)
        new_id = db.new_id()
        (db.data_dir() / "agents" / new_id).mkdir(parents=True, exist_ok=True)
        (db.data_dir() / "agents" / new_id / sessions.FRESH_MARKER).touch()
        conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        return _insert(conn, new_id, body, workspace)


@router.post("/{agent_id}/restart")
def restart(agent_id: str) -> dict:
    # Stops the session; the terminal view starts a fresh one when it reconnects.
    with db.connect() as conn:
        agent = _get(conn, agent_id)
    sessions.stop(agent_id)
    return {**agent, "status": "stopped"}


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
