"""Documents agents put in front of me: approvals (결재) and reports (보고), each filled into a form I define.
Agents submit them through a small MCP endpoint (/mcp/{agent_id}); I decide in the UI."""

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError

from . import agents, db, extensions, sessions, todos

router = APIRouter(tags=["approvals"])


def _doc(row) -> dict:
    return {**dict(row), "attachments": json.loads(row["attachments"]), "fields": json.loads(row["fields"])}


def _get(conn, approval_id: str) -> dict:
    row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    if not row:
        raise HTTPException(404, "결재 문서가 없습니다")
    return _doc(row)


@router.get("/api/approvals")
def list_approvals(status: str | None = None) -> list[dict]:
    with db.connect() as conn:
        if status:
            cur = conn.execute("SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC", (status,))
        else:
            cur = conn.execute("SELECT * FROM approvals ORDER BY created_at DESC")
        return [_doc(r) for r in cur.fetchall()]


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


# ---- Forms -------------------------------------------------------------------------------------

KIND_LABEL = {"approval": "결재", "report": "보고"}


class FormField(BaseModel):
    label: str = Field(min_length=1, max_length=20)
    long: bool = True


class FormIn(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    kind: str = Field(pattern="^(approval|report)$")
    fields: list[FormField] = Field(min_length=1, max_length=12)


def _form(row) -> dict:
    return {**dict(row), "fields": json.loads(row["fields"])}


@router.get("/api/forms")
def list_forms() -> list[dict]:
    with db.connect() as conn:
        return [_form(r) for r in conn.execute("SELECT * FROM forms ORDER BY created_at, name")]


def _save_form(conn, form_id: str, body: FormIn) -> dict:
    labels = [f.label.strip() for f in body.fields]
    if len(set(labels)) != len(labels) or not all(labels):
        raise HTTPException(400, "칸 이름이 비었거나 겹칩니다")
    if conn.execute("SELECT 1 FROM forms WHERE name = ? AND id != ?", (body.name.strip(), form_id)).fetchone():
        raise HTTPException(409, "같은 이름의 양식이 있습니다")
    fields = json.dumps([{"label": l, "long": f.long} for l, f in zip(labels, body.fields)], ensure_ascii=False)
    conn.execute(
        "INSERT INTO forms (id, name, kind, fields, created_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET name = excluded.name, kind = excluded.kind, fields = excluded.fields",
        (form_id, body.name.strip(), body.kind, fields, db.now()),
    )
    return _form(conn.execute("SELECT * FROM forms WHERE id = ?", (form_id,)).fetchone())


@router.post("/api/forms")
def create_form(body: FormIn) -> dict:
    with db.connect() as conn:
        return _save_form(conn, db.new_id(), body)


@router.put("/api/forms/{form_id}")
def update_form(form_id: str, body: FormIn) -> dict:
    """Documents already submitted keep the fields they were written with."""
    with db.connect() as conn:
        if not conn.execute("SELECT 1 FROM forms WHERE id = ?", (form_id,)).fetchone():
            raise HTTPException(404, "양식이 없습니다")
        return _save_form(conn, form_id, body)


@router.delete("/api/forms/{form_id}")
def delete_form(form_id: str) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM forms WHERE id = ?", (form_id,))


class FormRequest(BaseModel):
    agent_id: str
    instruction: str = Field(min_length=1, max_length=1000)


@router.post("/api/forms/{form_id}/request")
def request_document(form_id: str, body: FormRequest, request: Request) -> dict:
    """Asks an agent, in its terminal, to write a document in this form and submit it."""
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM forms WHERE id = ?", (form_id,)).fetchone()
    if not row:
        raise HTTPException(404, "양식이 없습니다")
    form = _form(row)
    labels = ", ".join(f["label"] for f in form["fields"])
    line = (f"'{form['name']}' 양식({KIND_LABEL[form['kind']]})으로 문서를 써서 scheduler MCP의 submit_approval 도구로 올려 주세요. "
            f"form은 '{form['name']}', fields에는 {labels} 칸을 모두 채워 주세요. 요청: {' '.join(body.instruction.split())}")
    return {"started": sessions.type_to_agent(body.agent_id, line, str(request.base_url).rstrip("/"))}


# ---- MCP (Streamable HTTP, JSON responses only) -------------------------------------------------

TOOLS = [
    {
        "name": "list_forms",
        "description": "사용자가 만든 문서 양식(결재서, 보고서 등)과 각 양식의 칸 이름을 본다. kind: approval(결재) | report(보고).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "submit_approval",
        "description": (
            "사용자에게 문서를 올린다. 결재(사용자가 정해야 하는 것: 클라이언트에게 낼 결과물 확정, 알릴 내용 등)와 "
            "보고(한 일 알리기) 모두 이 도구로 올린다. form에 양식 이름을, fields에 그 양식의 칸 이름별 내용을 넣는다. "
            "양식과 칸은 list_forms로 확인한다. form을 생략하면 '결재서' 양식으로 background/decision을 쓴다. "
            "명령 실행 허락에는 쓰지 않는다. 반환된 id로 get_approval을 불러 결과를 확인한다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "문서 제목"},
                "form": {"type": "string", "description": "양식 이름 (예: 결재서, 보고서)"},
                "fields": {"type": "object", "additionalProperties": {"type": "string"}, "description": "양식의 칸 이름 -> 내용"},
                "background": {"type": "string", "description": "form 생략 시: 배경, 지금까지 한 일과 상황"},
                "decision": {"type": "string", "description": "form 생략 시: 사용자가 승인/반려할 질문"},
                "attachments": {"type": "array", "items": {"type": "string"}, "description": "첨부 파일 경로"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "get_approval",
        "description": (
            "올린 문서의 상태를 확인한다. status: pending(대기) | approved(결재는 승인, 보고는 확인함) | "
            "rejected(결재는 반려, 보고는 보완 요청). reason에 사용자의 의견이나 사유가 있다."
        ),
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
    {
        "name": "list_extensions",
        "description": "사용자가 앱에 둔 스킬과 하네스(Claude Code 훅) 목록과, 각각이 붙은 에이전트 id(agent_ids)를 본다.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_skill",
        "description": (
            "스킬을 만들어 앱의 '스킬 & 하네스' 목록에 넣는다. 스킬은 Claude Code가 필요할 때 읽는 지시 묶음(SKILL.md)이다. "
            "만들기 전에 list_extensions로 'skill-writing-rules' 스킬을 읽고 그 규칙(이름, 언어, 설명 쓰는 법)을 따른다. "
            "에이전트에 붙이는 것은 사용자가 화면에서 한다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "이름 (40자 이내). skill-writing-rules를 따른다"},
                "description": {"type": "string", "description": "언제 쓰는지. Claude가 이 설명을 보고 스킬을 고른다"},
                "body": {"type": "string", "description": "스킬 내용 (마크다운). 따라야 할 규칙과 절차"},
            },
            "required": ["name", "description", "body"],
        },
    },
    {
        "name": "create_hook",
        "description": (
            "하네스(Claude Code 훅)를 만들어 앱의 '스킬 & 하네스' 목록에 넣는다. 훅은 정해진 시점에 명령을 자동으로 실행한다. "
            "에이전트에 붙이는 것은 사용자가 화면에서 검토한 뒤에 한다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "이름 (40자 이내)"},
                "event": {"type": "string", "enum": list(extensions.EVENTS), "description": "실행 시점"},
                "matcher": {"type": "string", "description": "PreToolUse/PostToolUse만: 대상 도구. 예: Bash, Edit|Write"},
                "command": {"type": "string", "description": "실행할 명령"},
                "description": {"type": "string", "description": "사용자에게 보일 설명: 무엇을 왜 하는지"},
            },
            "required": ["name", "event", "command"],
        },
    },
    {
        "name": "list_agents",
        "description": "Scheduler 앱의 에이전트 목록(id, 이름, 역할, CLI, 작업 폴더, 상태)을 본다.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_agent",
        "description": (
            "새 에이전트를 만든다. 대시보드 Agent 목록에 추가되고, 사용자가 누르면 터미널이 열린다. "
            "사용자가 만들라고 한 경우에만 쓴다. 앱의 기본 스킬만 붙는다. 다른 스킬과 하네스는 사용자가 화면에서 붙인다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "이름 (50자 이내)"},
                "role": {"type": "string", "description": "역할 (100자 이내)"},
                "persona": {"type": "string", "description": "성격과 일하는 방식. AGENTS.md에 들어간다"},
                "cli": {"type": "string", "enum": ["claude", "codex"]},
                "cwd": {"type": "string", "description": "작업 폴더 (이미 있는 폴더). 생략하면 전용 폴더를 만든다"},
            },
            "required": ["name", "cli"],
        },
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


def _agent_tool(caller: dict, name: str, args: dict):
    """Skills, harness and agents. Attaching skills or harness to an agent is left to the user on purpose."""
    if name == "list_extensions":
        return extensions.list_extensions()
    if name == "create_skill":
        return extensions.save(extensions.ExtensionIn(kind="skill", **args), created_by=caller["name"])
    if name == "create_hook":
        return extensions.save(extensions.ExtensionIn(kind="hook", **args), created_by=caller["name"])
    if name == "list_agents":
        return [{k: a[k] for k in ("id", "name", "role", "cli", "cwd", "status")} for a in agents.list_agents()]
    if name == "create_agent":
        if args.get("cli") not in ("claude", "codex"):
            raise HTTPException(400, "cli는 claude 또는 codex입니다")
        # Only the app's default skills: an agent may not attach anything else (hooks run without the CLI asking).
        return agents.create(agents.AgentIn(**{**args, "extensions": None}))
    return None


def _call_tool(agent: dict, name: str, args: dict) -> dict:
    result = _todo_tool(name, dict(args))
    if result is None:
        result = _agent_tool(agent, name, dict(args))
    if result is not None:
        return _text(result)
    with db.connect() as conn:
        if name == "list_forms":
            return _text([{"name": f["name"], "kind": f["kind"], "fields": [x["label"] for x in f["fields"]]} for f in list_forms()])
        if name == "submit_approval":
            if args.get("form"):
                row = conn.execute("SELECT * FROM forms WHERE name = ?", (str(args["form"]).strip(),)).fetchone()
                if not row:
                    names = [r["name"] for r in conn.execute("SELECT name FROM forms")]
                    return {**_text({"error": f"양식이 없습니다: {args['form']}", "forms": names}), "isError": True}
                form = _form(row)
                values = {str(k).strip(): str(v) for k, v in (args.get("fields") or {}).items()}
                unknown = set(values) - {f["label"] for f in form["fields"]}
                if unknown:
                    return {**_text({"error": f"양식에 없는 칸: {sorted(unknown)}", "fields": [f["label"] for f in form["fields"]]}), "isError": True}
                kind, form_name = form["kind"], form["name"]
                fields = [{**f, "value": values.get(f["label"], "")} for f in form["fields"]]
            else:
                kind, form_name = "approval", "결재서"
                fields = [{"label": "배경", "value": str(args.get("background", "")), "long": True},
                          {"label": "결정 사항", "value": str(args["decision"]), "long": True}]
            approval_id = db.new_id()
            conn.execute(
                "INSERT INTO approvals (id, agent_id, agent_name, title, background, decision, attachments, created_at, "
                "kind, form_name, fields) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (approval_id, agent["id"], agent["name"], str(args["title"]), str(args.get("background", "")),
                 str(args.get("decision", "")), json.dumps(list(args.get("attachments") or []), ensure_ascii=False), db.now(),
                 kind, form_name, json.dumps(fields, ensure_ascii=False)),
            )
            return _text({"id": approval_id, "status": "pending", "message": f"'{form_name}' 문서를 올렸습니다. get_approval로 결과를 확인하세요."})
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
