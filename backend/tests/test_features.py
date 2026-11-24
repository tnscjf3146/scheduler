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
    assert {t["name"] for t in rpc(client, agent["id"], "tools/list")["result"]["tools"]} >= {"submit_approval", "get_approval"}

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


def test_agent_manages_todos_through_mcp(client, tmp_path):
    import json

    agent = client.post("/api/agents", json={"name": "비서", "cli": "shell", "cwd": str(tmp_path)}).json()
    call = lambda name, **args: rpc(client, agent["id"], "tools/call", {"name": name, "arguments": args})["result"]
    out = lambda res: json.loads(res["content"][0]["text"])

    todo = out(call("add_todo", title="보고서 제출", due_at="2026-12-01T09:00"))
    out(call("add_todo", title="날짜 없는 일"))
    assert [t["title"] for t in client.get("/api/todos").json()] == ["보고서 제출", "날짜 없는 일"]  # the UI sees it

    assert [t["title"] for t in out(call("list_todos", **{"from": "2026-12-01", "to": "2026-12-01"}))] == ["보고서 제출"]
    assert out(call("update_todo", id=todo["id"], done=True))["done"] is True
    assert [t["title"] for t in out(call("list_todos", done=False))] == ["날짜 없는 일"]

    detail = out(call("update_todo", id=todo["id"], memo="단가 확인", subtasks=[{"title": "비교"}, {"title": "PDF", "done": True}]))
    assert detail["memo"] == "단가 확인" and detail["subtasks"] == [{"title": "비교", "done": False}, {"title": "PDF", "done": True}]
    assert next(t for t in client.get("/api/todos").json() if t["id"] == todo["id"])["subtasks"][1]["done"] is True

    assert call("add_todo", title="x", due_at="내일")["isError"]  # bad date format is reported, not raised
    assert call("update_todo", id="nope", done=True)["isError"]
    out(call("delete_todo", id=todo["id"]))
    assert len(client.get("/api/todos").json()) == 1


def test_fire_keeps_folder_delete_removes_it(client, tmp_path):
    fired = client.post("/api/agents", json={"name": "a", "cli": "shell"}).json()
    deleted = client.post("/api/agents", json={"name": "b", "cli": "shell"}).json()
    custom = tmp_path / "mine"
    custom.mkdir()
    chosen = client.post("/api/agents", json={"name": "c", "cli": "shell", "cwd": str(custom)}).json()

    assert client.delete(f"/api/agents/{fired['id']}").status_code == 204
    assert client.delete(f"/api/agents/{deleted['id']}?purge=true").status_code == 204
    assert client.delete(f"/api/agents/{chosen['id']}?purge=true").status_code == 204
    assert client.get("/api/agents").json() == []

    assert (tmp_path / "agents" / fired["id"] / "workspace" / "AGENTS.md").exists()
    assert not (tmp_path / "agents" / deleted["id"]).exists()
    assert (custom / "AGENTS.md").exists()  # a folder the user chose is never deleted


def test_handover_hires_new_agent_into_same_folder(client, tmp_path):
    from app import sessions

    old = client.post("/api/agents", json={"name": "전임", "cli": "claude", "persona": "느긋하다"}).json()
    workspace = tmp_path / "agents" / old["id"] / "workspace"
    (workspace / "result.txt").write_text("작업 결과", encoding="utf-8")

    new = client.post(f"/api/agents/{old['id']}/handover", json={"name": "후임", "cli": "claude", "persona": "꼼꼼하다"})
    assert new.status_code == 201
    new = new.json()
    assert [a["name"] for a in client.get("/api/agents").json()] == ["후임"]  # the old one is fired
    assert new["cwd"] == old["cwd"]
    assert (workspace / "result.txt").read_text(encoding="utf-8") == "작업 결과"
    md = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert "후임" in md and "꼼꼼하다" in md and "느긋하다" not in md

    # First launch starts a new conversation even though the folder has the old one; later launches continue.
    (tmp_path / "agents" / new["id"]).mkdir(exist_ok=True)
    history = lambda _cwd: True
    sessions._has_claude_history, saved = history, sessions._has_claude_history
    try:
        launch = lambda: sessions._launch_script(new, "http://x/mcp").read_text(encoding="utf-8-sig")
        assert "--continue" not in launch()
        assert "--continue" in launch()
    finally:
        sessions._has_claude_history = saved

    # Deleting the successor removes the workspace too, though it sits under the first agent's folder.
    assert client.delete(f"/api/agents/{new['id']}?purge=true").status_code == 204
    assert not (tmp_path / "agents" / old["id"]).exists()


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


def test_imap_idle_wakes_on_new_mail():
    from app.mail import _wait_for_mail

    class FakeConn:
        def __init__(self, lines):
            self.lines, self.sent = list(lines), []
            self.sock = type("S", (), {"settimeout": lambda self, t: None})()

        def _new_tag(self):
            return b"A1"

        def send(self, data):
            self.sent.append(data)

        def readline(self):
            return self.lines.pop(0)

    conn = FakeConn([b"+ idling\r\n", b"* OK still here\r\n", b"* 5 EXISTS\r\n"])
    assert _wait_for_mail(conn) is True
    assert conn.sent == [b"A1 IDLE\r\n"]
    assert _wait_for_mail(FakeConn([b"A1 BAD no idle\r\n"])) is False
