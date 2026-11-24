"""Approval documents. Agents submit them through a small MCP endpoint (/mcp/{agent_id}); I decide in the UI."""

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from . import db

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
]


def _text(obj) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(obj, ensure_ascii=False)}]}


def _call_tool(agent: dict, name: str, args: dict) -> dict:
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
    elif method == "ping":
        result = {}
    else:
        return JSONResponse({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "Method not found"}})
    return JSONResponse({"jsonrpc": "2.0", "id": msg["id"], "result": result})


@router.get("/mcp/{agent_id}")
def mcp_no_stream():
    return Response(status_code=405)  # no server-initiated stream
