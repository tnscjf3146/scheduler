import time
from datetime import datetime, timedelta

from app.mail import parse_message


def at(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")


def test_todos_and_upcoming(client):
    later = client.post("/api/todos", json={"title": "later", "due_at": at(2)}).json()
    soon = client.post("/api/todos", json={"title": "soon", "due_at": at(1)}).json()
    client.post("/api/todos", json={"title": "past", "due_at": at(-1)})
    client.post("/api/todos", json={"title": "no date"})
    assert client.post("/api/todos", json={"title": "", "due_at": at(1)}).status_code == 422
    assert client.post("/api/todos", json={"title": "x", "due_at": "tomorrow"}).status_code == 422

    assert [t["title"] for t in client.get("/api/todos/upcoming").json()] == ["soon", "later"]

    client.patch(f"/api/todos/{soon['id']}", json={"done": True})
    assert [t["title"] for t in client.get("/api/todos/upcoming").json()] == ["later"]
    assert len(client.get("/api/todos").json()) == 4

    assert client.delete(f"/api/todos/{later['id']}").status_code == 204
    assert client.patch(f"/api/todos/{later['id']}", json={"done": True}).status_code == 404


def rpc(client, agent_id, method, params=None, id_=1):
    return client.post(f"/mcp/{agent_id}", json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}).json()


def test_approval_flow_through_mcp(client, tmp_path):
    agent = client.post("/api/agents", json={"name": "문서 정리", "cli": "shell", "cwd": str(tmp_path)}).json()

    assert rpc(client, agent["id"], "initialize", {"protocolVersion": "2025-06-18"})["result"]["serverInfo"]["name"] == "scheduler"
    assert {t["name"] for t in rpc(client, agent["id"], "tools/list")["result"]["tools"]} == {"submit_approval", "get_approval"}

    import json
    res = rpc(client, agent["id"], "tools/call", {"name": "submit_approval", "arguments": {
        "title": "견적서 제출", "background": "수정 반영", "decision": "제출할까요?", "attachments": ["a.pdf"]}})
    approval_id = json.loads(res["result"]["content"][0]["text"])["id"]

    pending = client.get("/api/approvals", params={"status": "pending"}).json()
    assert [(a["title"], a["agent_name"], a["attachments"]) for a in pending] == [("견적서 제출", "문서 정리", ["a.pdf"])]

    assert client.post(f"/api/approvals/{approval_id}/decision", json={"decision": "rejected"}).status_code == 400
    assert client.post(f"/api/approvals/{approval_id}/decision", json={"decision": "rejected", "reason": "단가 확인"}).json()["status"] == "rejected"
    assert client.post(f"/api/approvals/{approval_id}/decision", json={"decision": "approved"}).status_code == 409

    got = rpc(client, agent["id"], "tools/call", {"name": "get_approval", "arguments": {"id": approval_id}})
    assert json.loads(got["result"]["content"][0]["text"])["reason"] == "단가 확인"


def test_agent_gets_own_workspace(client, tmp_path):
    a = client.post("/api/agents", json={"name": "a", "cli": "shell", "persona": "말이 짧고 꼼꼼하다"}).json()
    b = client.post("/api/agents", json={"name": "b", "cli": "shell"}).json()
    assert a["cwd"] != b["cwd"]
    assert a["cwd"] == str(tmp_path / "agents" / a["id"] / "workspace")
    workspace = tmp_path / "agents" / a["id"] / "workspace"
    assert "submit_approval" in (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert "말이 짧고 꼼꼼하다" in (workspace / "AGENTS.md").read_text(encoding="utf-8")
    for shim in ("CLAUDE.md", "GEMINI.md"):
        assert (workspace / shim).read_text(encoding="utf-8") == "@AGENTS.md\n"

    custom = tmp_path / "mine"
    custom.mkdir()
    (custom / "AGENTS.md").write_text("내 프로젝트 규칙", encoding="utf-8")
    client.post("/api/agents", json={"name": "c", "cli": "shell", "cwd": str(custom)})
    assert (custom / "AGENTS.md").read_text(encoding="utf-8") == "내 프로젝트 규칙"  # never overwritten
    assert (custom / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
    assert (custom / "GEMINI.md").exists()


def test_terminal_session_echoes(client, tmp_path):
    agent = client.post("/api/agents", json={"name": "셸", "cli": "shell", "cwd": str(tmp_path)}).json()
    with client.websocket_connect(f"/api/agents/{agent['id']}/terminal?cols=80&rows=24") as ws:
        ws.send_json({"type": "input", "data": "echo scheduler-ok\r"})
        seen, deadline = "", time.time() + 20
        while "scheduler-ok\r\n" not in seen and time.time() < deadline:
            seen += ws.receive_text()
    assert "scheduler-ok\r\n" in seen
    assert client.get("/api/agents").json()[0]["status"] == "running"
    client.delete(f"/api/agents/{agent['id']}")


def test_parse_html_mail():
    raw = (
        "From: Kim <kim@a.com>\r\nSubject: =?utf-8?b?7JWI64WV?=\r\nDate: Tue, 24 Nov 2026 10:12:00 +0900\r\n"
        "Content-Type: text/html; charset=utf-8\r\n\r\n<p>Hello&nbsp;<b>there</b></p><script>x()</script>"
    ).encode()
    mail = parse_message(raw)
    assert mail["subject"] == "안녕"
    assert mail["sender"] == "Kim <kim@a.com>"
    assert mail["body"].split() == ["Hello", "there"]
    assert mail["received_at"].startswith("2026-11-24T10:12:00")


def test_launch_continues_previous_conversation(tmp_path, monkeypatch):
    from pathlib import Path

    from app import sessions

    monkeypatch.setenv("SCHEDULER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cwd = str(tmp_path / "work")
    read = lambda cli: sessions._launch_script({"id": cli, "cli": cli, "cwd": cwd}, "http://x/mcp").read_text(encoding="utf-8-sig")

    assert "--continue" not in read("claude")
    project = tmp_path / ".claude" / "projects" / __import__("re").sub(r"[^A-Za-z0-9]", "-", cwd)
    project.mkdir(parents=True)
    (project / "s.jsonl").write_text("{}")
    assert "claude --continue" in read("claude")

    assert "resume" not in read("codex")
    assert "codex resume --last" in read("codex")
