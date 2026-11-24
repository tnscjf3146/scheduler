"""Approval documents. Agents submit them through a small MCP endpoint (/mcp/{agent_id}); I decide in the UI."""

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError

from . import db, todos

router = APIRouter(tags=["approvals"])


def _get(conn, approval_id: str) -> dict:
    row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    if not row:
        raise HTTPException(404, "결재 문서가 없습니다")
    return {**dict(row), "attachments": json.loads(row["attachments"])}


@router.get("/api/approvals")
def list_approvals(status: str | None = None) -> list[dict]:
    with db.connect() as conn:
        if status:
            cur = conn.execute("SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC", (status,))
        else:
            cur = conn.execute("SELECT * FROM approvals ORDER BY created_at DESC")
        return [{**a, "attachments": json.loads(a["attachments"])} for a in db.rows(cur)]


@router.get("/api/approvals/{approval_id}")
def get_approval(approval_id: str) -> dict:
    with db.connect() as conn:
        return _get(conn, approval_id)


class Decision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    reason: str | None = Field(default=None, max_length=2000)


@router.post("/api/approvals/{approval_id}/decision")
def decide(approval_id: str, body: Decision) -> dict:
    if body.decision == "rejected" and not (body.reason or "").strip():
        raise HTTPException(400, "반려 사유를 입력하세요")
    with db.connect() as conn:
        doc = _get(conn, approval_id)
        if doc["status"] != "pending":
            raise HTTPException(409, "이미 처리된 결재입니다")
        conn.execute(
            "UPDATE approvals SET status = ?, reason = ?, decided_at = ? WHERE id = ?",
            (body.decision, (body.reason or "").strip() or None, db.now(), approval_id),
        )
        return _get(conn, approval_id)


# ---- MCP (Streamable HTTP, JSON responses only) -------------------------------------------------

TOOLS = [
    {
        "name": "submit_approval",
        "description": (
            "사용자가 정해야 하는 사항을 결재 문서로 올린다. 예: 클라이언트에게 제출할 결과물 확정, 클라이언트에게 알릴 내용. "
            "명령 실행 허락에는 쓰지 않는다. 반환된 id로 get_approval을 불러 결과(승인/반려와 사유)를 확인한다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "결재 문서 제목"},
                "background": {"type": "string", "description": "배경: 지금까지 한 일과 상황"},
                "decision": {"type": "string", "description": "결정할 사항: 사용자가 승인/반려할 질문"},
                "attachments": {"type": "array", "items": {"type": "string"}, "description": "첨부 파일 경로"},
            },
            "required": ["title", "decision"],
        },
    },
    {
        "name": "get_approval",
        "description": "올린 결재 문서의 상태를 확인한다. status: pending(대기) | approved(승인) | rejected(반려, reason에 사유).",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
    {
        "name": "list_todos",
        "description": "사용자의 할 일 목록을 본다. 마감일(due_at)이 있는 할 일은 대시보드 달력에도 보인다. 모든 조건은 선택이다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from": {"type": "string", "description": "이 날짜(YYYY-MM-DD) 이후 마감만"},
                "to": {"type": "string", "description": "이 날짜(YYYY-MM-DD) 이전 마감만"},
                "done": {"type": "boolean", "description": "true면 완료한 것만, false면 안 한 것만"},
            },
        },
    },
    {
        "name": "add_todo",
        "description": "할 일을 추가한다. due_at을 주면 달력의 그 날짜에 표시된다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "할 일 (40자 이내, 대시보드에서 두 줄을 넘지 않게)"},
                "due_at": {"type": "string", "description": "마감 일시 YYYY-MM-DDTHH:MM (현지 시간). 없으면 생략"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "update_todo",
        "description": "할 일의 제목, 마감 일시, 완료 여부, 메모, 하위 할 일을 바꾼다. 준 값만 바뀐다. due_at에 null을 주면 날짜를 지운다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "due_at": {"type": ["string", "null"], "description": "YYYY-MM-DDTHH:MM"},
                "done": {"type": "boolean"},
                "memo": {"type": "string", "description": "메모 (2000자 이내). 기존 메모를 통째로 바꾼다"},
                "subtasks": {
                    "type": "array",
                    "description": "하위 할 일 목록 전체 (30개 이내). 기존 목록을 통째로 바꾸므로 list_todos로 읽은 뒤 고쳐서 보낸다",
                    "items": {
                        "type": "object",
                        "properties": {"title": {"type": "string"}, "done": {"type": "boolean"}},
                        "required": ["title"],
                    },
                },
            },
            "required": ["id"],
        },
    },
    {
        "name": "delete_todo",
        "description": "할 일을 지운다. 되돌릴 수 없으니 사용자가 지우라고 한 것만 지운다.",
        "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
    },
]


def _todo_tool(name: str, args: dict):
    """The dashboard's own todo endpoints, so agents and the UI follow the same rules."""
    if name == "list_todos":
        due = lambda t: (t["due_at"] or "")[:10]
        return [
            t for t in todos.list_todos()
            if ("from" not in args or (t["due_at"] and due(t) >= args["from"]))
            and ("to" not in args or (t["due_at"] and due(t) <= args["to"]))
            and ("done" not in args or t["done"] == args["done"])
        ]
    if name == "add_todo":
        return todos.create(todos.TodoIn(**args))
    if name == "update_todo":
        todo_id = args.pop("id")
        return todos.update(todo_id, todos.TodoPatch(**args))
    if name == "delete_todo":
        todos.delete(args["id"])
        return {"deleted": args["id"]}
    return None


def _text(obj) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(obj, ensure_ascii=False)}]}


def _call_tool(agent: dict, name: str, args: dict) -> dict:
    result = _todo_tool(name, dict(args))
    if result is not None:
        return _text(result)
    with db.connect() as conn:
        if name == "submit_approval":
            approval_id = db.new_id()
            conn.execute(
                "INSERT INTO approvals (id, agent_id, agent_name, title, background, decision, attachments, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (approval_id, agent["id"], agent["name"], str(args["title"]), str(args.get("background", "")),
                 str(args["decision"]), json.dumps(list(args.get("attachments") or []), ensure_ascii=False), db.now()),
            )
            return _text({"id": approval_id, "status": "pending", "message": "결재 대기에 올렸습니다. get_approval로 결과를 확인하세요."})
        if name == "get_approval":
            row = conn.execute(
                "SELECT id, status, reason, decided_at FROM approvals WHERE id = ? AND agent_id = ?", (args["id"], agent["id"])
            ).fetchone()
            if not row:
                return {**_text({"error": "결재 문서를 찾을 수 없습니다"}), "isError": True}
            return _text(dict(row))
    return {**_text({"error": f"알 수 없는 도구: {name}"}), "isError": True}


@router.post("/mcp/{agent_id}")
async def mcp(agent_id: str, request: Request):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if not row:
        return JSONResponse({"error": "unknown agent"}, status_code=404)
    msg = await request.json()
    if "id" not in msg:  # notification, e.g. notifications/initialized
        return Response(status_code=202)

    method, params = msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        result = {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "scheduler", "version": "0.1.0"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        try:
            result = _call_tool(dict(row), params["name"], params.get("arguments") or {})
        except KeyError as e:
            result = {**_text({"error": f"필수 값이 없습니다: {e}"}), "isError": True}
        except ValidationError as e:
            result = {**_text({"error": "값이 올바르지 않습니다", "detail": e.errors(include_url=False, include_context=False)}), "isError": True}
        except HTTPException as e:
            result = {**_text({"error": e.detail}), "isError": True}
    elif method == "ping":
        result = {}
    else:
        return JSONResponse({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "Method not found"}})
    return JSONResponse({"jsonrpc": "2.0", "id": msg["id"], "result": result})


@router.get("/mcp/{agent_id}")
def mcp_no_stream():
    return Response(status_code=405)  # no server-initiated stream
