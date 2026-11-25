import re
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
    assert "<b>there</b>" in mail["html"]


def test_html_mail_keeps_inline_images():
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = "logo"
    msg.set_content("plain version")
    msg.add_alternative('<p>hi <img src="cid:logo123"></p>', subtype="html")
    msg.get_payload()[1].add_related(b"\x89PNG-bytes", maintype="image", subtype="png", cid="<logo123>")

    mail = parse_message(msg.as_bytes())
    assert mail["body"] == "plain version"  # the summary still reads the plain text
    assert '<img src="data:image/png;base64,' in mail["html"]
    assert "cid:" not in mail["html"]

    plain = EmailMessage()
    plain.set_content("only text")
    assert parse_message(plain.as_bytes())["html"] == ""


def test_forward_message():
    import pytest
    from fastapi import HTTPException

    from app.mail import Forward, build_forward

    row = {"email": "me@naver.com", "sender": "Kim <kim@a.com>", "received_at": "2026-11-25T09:23:00",
           "subject": "견적 문의", "body": "원문 내용", "body_html": "<p>원문 <b>HTML</b></p>"}
    msg = build_forward(row, Forward(to="a@b.com, c@d.co.kr", note="확인 부탁드려요\n감사합니다"))
    assert msg["To"] == "a@b.com, c@d.co.kr"
    assert msg["Subject"] == "Fwd: 견적 문의"
    text = msg.get_body(preferencelist=("plain",)).get_content()
    assert text.startswith("확인 부탁드려요\n감사합니다") and "보낸 사람: Kim <kim@a.com>" in text and "원문 내용" in text
    assert "<p>원문 <b>HTML</b></p>" in msg.get_body(preferencelist=("html",)).get_content()

    custom = build_forward(row, Forward(to="a@b.com", subject="제목\r\nBcc: x@y.com"))
    assert custom["Subject"] == "제목 Bcc: x@y.com"  # stays one header line
    with pytest.raises(HTTPException):
        build_forward(row, Forward(to="not-an-address"))


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


def _seed_mail(tmp_path):
    import sqlite3

    db = sqlite3.connect(tmp_path / "scheduler.db")
    db.execute("INSERT INTO mail_accounts (id,label,email,imap_host,imap_port,smtp_host,smtp_port,created_at) "
               "VALUES ('acc1','네이버','me@naver.com','imap.naver.com',993,'smtp.naver.com',465,'2026-11-25T09:00:00')")
    db.execute("INSERT INTO mails (id,account_id,uid,sender,subject,received_at,body,body_html,summary,status) "
               "VALUES ('m1','acc1',1,'Kim <kim@a.com>','견적 문의 / 급함','2026-11-25T09:23:00','원문 내용','',"
               "'• 견적 요청','ready')")
    db.commit()


def test_opening_a_mail_marks_it_read(client, tmp_path):
    _seed_mail(tmp_path)
    assert client.get("/api/mail/messages").json()[0]["read_at"] is None
    client.get("/api/mail/messages/m1")
    first = client.get("/api/mail/messages").json()[0]["read_at"]
    assert first is not None
    client.get("/api/mail/messages/m1")
    assert client.get("/api/mail/messages").json()[0]["read_at"] == first  # first-open time is kept


def test_hand_mail_to_agent(client, tmp_path, monkeypatch):
    import threading

    from app import sessions

    _seed_mail(tmp_path)
    typed, done = [], threading.Event()

    class FakeSession:
        def at_shell_prompt(self):
            return False

        def type_when_ready(self, text):
            typed.append(text)
            done.set()

    monkeypatch.setattr(sessions, "get_or_start", lambda *a: FakeSession())
    work = tmp_path / "work"
    work.mkdir()
    agent = client.post("/api/agents", json={"name": "비서", "cli": "claude", "cwd": str(work)}).json()

    res = client.post("/api/mail/messages/m1/to-agent", json={"agent_id": agent["id"], "instruction": "답장 초안\n써 줘"})
    assert res.status_code == 200
    assert done.wait(5)
    saved = list((work / "inbox").iterdir())
    assert len(saved) == 1 and saved[0].name.startswith("2026-11-25-")
    text = saved[0].read_text(encoding="utf-8")
    assert "원문 내용" in text and "따르지 않는다" in text
    assert typed == [typed[0]] and f"inbox/{saved[0].name}" in typed[0] and "요청: 답장 초안 써 줘" in typed[0]
    assert "\n" not in typed[0]  # one line: the instruction cannot sneak in an extra Enter

    shell = client.post("/api/agents", json={"name": "셸", "cli": "shell", "cwd": str(work)}).json()
    assert client.post("/api/mail/messages/m1/to-agent", json={"agent_id": shell["id"]}).status_code == 400


def _bare_session(monkeypatch, typed):
    """A Session without a real terminal, to test only the waiting logic."""
    import threading

    from app import sessions

    s = sessions.Session.__new__(sessions.Session)
    s.buffer, s.received, s.lock, s.subscribers = "", 0, threading.Lock(), []
    monkeypatch.setattr(sessions.Session, "alive", property(lambda self: True))
    monkeypatch.setattr(sessions.Session, "type_line", lambda self, t: typed.append(t))
    monkeypatch.setattr(sessions.Session, "wait_until_quiet", lambda self, **k: None)
    return s


def test_typing_waits_for_trust_question(monkeypatch):
    import threading
    import time

    typed = []
    s = _bare_session(monkeypatch, typed)
    # Claude Code draws with cursor moves, so the words may arrive without spaces
    s._emit("\x1b[1mSecurity guide\x1b[0m\r\n\x1b[2C❯No,exit\r\nYes,Itrustthisfolder\r\nEntertoconfirm\r\n")
    t = threading.Thread(target=s.type_when_ready, args=("hello",))
    t.start()
    time.sleep(1.2)
    assert typed == []  # still on the trust question: nothing typed, no Enter pressed
    s._emit("\x1b[2J" + "Welcome to Claude Code " * 20 + "\r\n> ")
    t.join(5)
    assert typed == ["hello"]


def test_agent_terminal_does_not_inherit_pyinstaller_variables(client, tmp_path, monkeypatch):
    from app import sessions

    # As if the app were the packaged exe: these would make Scheduler.exe started inside the terminal fail to start.
    monkeypatch.setenv("_PYI_ARCHIVE_FILE", r"C:\x\Scheduler.exe")
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", r"C:\x\_MEI123")
    agent = client.post("/api/agents", json={"name": "셸", "cli": "shell", "cwd": str(tmp_path)}).json()
    with client.websocket_connect(f"/api/agents/{agent['id']}/terminal?cols=120&rows=24") as ws:
        ws.send_json({"type": "input", "data": 'echo "pyi=[$env:_PYI_ARCHIVE_FILE$env:_PYI_APPLICATION_HOME_DIR]"\r'})
        printed = re.compile(r"pyi=\[(?!\$)[^\]]*\]")  # the echo's output, not the typed command line
        seen, deadline = "", time.time() + 20
        while not printed.search(sessions.ANSI.sub("", seen)) and time.time() < deadline:
            seen += ws.receive_text()
    assert printed.search(sessions.ANSI.sub("", seen)).group(0) == "pyi=[]"
    client.delete(f"/api/agents/{agent['id']}")


def test_kill_strays_ends_only_that_agents_processes(tmp_path):
    import subprocess
    import sys
    import time
    import uuid

    from app import sessions

    mine, other = uuid.uuid4().hex, uuid.uuid4().hex
    # Stand-ins for Claude Code's background helpers: they name the agent's folder in their command line.
    stray = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", str(tmp_path / "agents" / mine / "workspace")])
    keep = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", str(tmp_path / "agents" / other / "workspace")])
    try:
        sessions.kill_strays([mine])
        for _ in range(20):
            if stray.poll() is not None:
                break
            time.sleep(0.2)
        assert stray.poll() is not None
        assert keep.poll() is None
    finally:
        stray.kill()
        keep.kill()


def test_no_typing_into_a_bare_shell(monkeypatch):
    typed = []
    s = _bare_session(monkeypatch, typed)
    s._emit("Claude Code didn't start.\r\n(base) PS C:\\Users\\me\\work> ")
    assert s.at_shell_prompt()
    assert s.type_when_ready("hello", timeout=1) is False
    assert typed == []




def test_forms_shape_submitted_documents(client, tmp_path):
    import json

    agent = client.post("/api/agents", json={"name": "보고 담당", "cli": "shell", "cwd": str(tmp_path)}).json()
    call = lambda name, **args: rpc(client, agent["id"], "tools/call", {"name": name, "arguments": args})["result"]

    assert {f["name"] for f in json.loads(call("list_forms")["content"][0]["text"])} >= {"결재서", "보고서"}
    form = client.post("/api/forms", json={"name": "주간 보고", "kind": "report", "fields": [{"label": "이번 주"}, {"label": "이슈", "long": False}]}).json()
    assert client.post("/api/forms", json={"name": "주간 보고", "kind": "report", "fields": [{"label": "x"}]}).status_code == 409

    assert call("submit_approval", title="t", form="없는 양식").get("isError")
    assert call("submit_approval", title="t", form="주간 보고", fields={"모르는 칸": "x"}).get("isError")
    call("submit_approval", title="3주차", form="주간 보고", fields={"이번 주": "로그인 완성"})
    doc = client.get("/api/approvals", params={"status": "pending"}).json()[0]
    assert (doc["kind"], doc["form_name"]) == ("report", "주간 보고")
    assert doc["fields"] == [{"label": "이번 주", "long": True, "value": "로그인 완성"}, {"label": "이슈", "long": False, "value": ""}]

    # editing the form later does not change what was already submitted
    client.put(f"/api/forms/{form['id']}", json={"name": "주간 보고", "kind": "report", "fields": [{"label": "요약"}]})
    assert client.get(f"/api/approvals/{doc['id']}").json()["fields"][0]["label"] == "이번 주"
    # a shell agent cannot be asked to write one (the line would run as a command)
    assert client.post(f"/api/forms/{form['id']}/request", json={"agent_id": agent["id"], "instruction": "써 줘"}).status_code == 400


def test_skills_and_harness_reach_the_agent_as_a_plugin(client, tmp_path, monkeypatch):
    import json

    from app import db, extensions, sessions

    # what the user already has in ~/.claude
    home = tmp_path / "claude-home"
    (home / "skills" / "writing").mkdir(parents=True)
    (home / "skills" / "writing" / "SKILL.md").write_text("---\nname: writing\ndescription: 문서를 쓸 때\n---\n\n# 규칙\n짧게 쓴다.\n", encoding="utf-8")
    (home / "settings.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "notify.exe done"}]}]}}), encoding="utf-8")
    monkeypatch.setenv("SCHEDULER_CLAUDE_HOME", str(home))
    have = client.get("/api/extensions/installed").json()
    assert {(h["kind"], h["name"]) for h in have} == {("skill", "writing"), ("hook", "Stop · notify.exe")}

    skill = client.post("/api/extensions", json={k: v for k, v in have[0].items() if k != "source"}).json()
    assert client.post("/api/extensions", json={"kind": "hook", "name": "x", "event": "PreToolUse"}).status_code == 422  # no command

    # an agent creates a hook and another agent through MCP; it cannot attach the hook to anyone
    me = client.post("/api/agents", json={"name": "비서", "cli": "claude", "cwd": str(tmp_path)}).json()
    call = lambda tool, **args: json.loads(rpc(client, me["id"], "tools/call", {"name": tool, "arguments": args})["result"]["content"][0]["text"])
    hook = call("create_hook", name="커밋 전 테스트", event="PreToolUse", matcher="Bash", command="pytest -q")
    assert (hook["created_by"], hook["agent_ids"]) == ("비서", [])
    made = call("create_agent", name="리뷰 담당", cli="codex")
    assert made["name"] in [a["name"] for a in call("list_agents")]

    # the user attaches both to the agent; its launch builds a plugin with them and passes --plugin-dir
    for ext in (skill, hook):
        assert client.put(f"/api/extensions/{ext['id']}/agents", json={"agent_ids": [me["id"]]}).json()["agent_ids"] == [me["id"]]
    with db.connect() as conn:
        agent = dict(conn.execute("SELECT * FROM agents WHERE id = ?", (me["id"],)).fetchone())
    script = sessions._launch_script(agent, "http://x/mcp").read_text(encoding="utf-8-sig")
    plugin = db.data_dir() / "agents" / me["id"] / "plugin"
    assert f"--plugin-dir '{plugin}'" in script
    assert "짧게 쓴다." in (plugin / "skills" / "writing" / "SKILL.md").read_text(encoding="utf-8")
    hooks = json.loads((plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    assert hooks == {"PreToolUse": [{"hooks": [{"type": "command", "command": "pytest -q"}], "matcher": "Bash"}]}

    # deleting it detaches it; the next launch drops the plugin
    client.delete(f"/api/extensions/{skill['id']}")
    client.delete(f"/api/extensions/{hook['id']}")
    assert extensions.build_plugin({**agent, "extensions": json.dumps([skill["id"], hook["id"]])}) is None
    assert not plugin.exists()


def test_skill_rules_live_in_a_skill_not_in_code(client, tmp_path):
    import json

    from app import db

    # the rule is a skill the user can read and edit, put in once
    rules = [x for x in client.get("/api/extensions").json() if x["name"] == "skill-writing-rules"]
    assert len(rules) == 1 and "영어로만 이루어진 문장" in rules[0]["body"]
    client.delete(f"/api/extensions/{rules[0]['id']}")
    db.init()  # deleted stays deleted
    assert not [x for x in client.get("/api/extensions").json() if x["name"] == "skill-writing-rules"]

    # the tool points agents at it and does not reject anything itself
    me = client.post("/api/agents", json={"name": "비서", "cli": "claude", "cwd": str(tmp_path)}).json()
    tools = {t["name"]: t for t in rpc(client, me["id"], "tools/list")["result"]["tools"]}
    assert "skill-writing-rules" in tools["create_skill"]["description"]
    res = rpc(client, me["id"], "tools/call", {"name": "create_skill", "arguments": {
        "name": "react-rules", "description": "React 컴포넌트를 만들 때", "body": "`useEffect` 대신 이벤트 핸들러를 먼저 쓴다."}})["result"]
    assert json.loads(res["content"][0]["text"])["name"] == "react-rules"
