"""The chat view of a Claude Code agent. The agent itself runs as always, interactively in its terminal
(sessions.py); this module only shows that terminal as a chat (design: terminal-chat-design.md).

  content   Claude Code's own transcript (~/.claude/projects/.../<session>.jsonl), read as it is written. Its path
            comes from the SessionStart hook, so it is the right file even after --continue or /clear.
  state     app hooks in the agent's plugin: UserPromptSubmit (working), Stop (done), PermissionRequest (asks
            in the chat), PreToolUse on show_card / ask_user (checks a card before it is shown).
  cards     the agent makes them itself, following the chat-card-rules skill, with the show_card and ask_user
            tools; the app checks them (check_card) and draws them in fixed parts or a sandboxed HTML frame.
  fallback  the screen is read only to spot questions the hooks don't cover (trust this folder, choice menus).

Events (chat_events table, one row per id, shown in order of first appearance):
  user {text} · text {text} · tool {name, input, status, result} · note {text} · card {card}
  question {question, options, status, answer} · permission {name, input, status} · done {ms}"""

import asyncio
import json
import re
import threading
import time

from fastapi import HTTPException

from . import db

RESULT_MAX = 20_000  # characters of a tool result kept
HISTORY = 500  # events sent to a newly opened chat
ANSWER_TIMEOUT = 30 * 60  # seconds a question waits for the user
CHOICE_MENU = re.compile(r"❯\s*\S")  # Claude Code's selection cursor: a menu is waiting for an answer
APP_TOOLS = ("mcp__scheduler__show_card", "mcp__scheduler__ask_user")


# ---- storage and fan-out -------------------------------------------------------------------------

def _store(agent_id: str, event: dict) -> bool:
    """Saves the event (insert, or update by id). True if anything changed, so re-reading a transcript is quiet."""
    data = json.dumps(event, ensure_ascii=False)
    with db.connect() as conn:
        row = conn.execute("SELECT data FROM chat_events WHERE id = ?", (event["id"],)).fetchone()
        if row and row["data"] == data:
            return False
        conn.execute(
            "INSERT INTO chat_events (id, agent_id, data, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
            (event["id"], agent_id, data, event["at"]),
        )
    return True


def history(agent_id: str) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT data FROM (SELECT data, rowid FROM chat_events WHERE agent_id = ? ORDER BY rowid DESC LIMIT ?) ORDER BY rowid",
            (agent_id, HISTORY),
        ).fetchall()
    return [json.loads(r["data"]) for r in rows]


def _get_event(event_id: str) -> dict | None:
    with db.connect() as conn:
        row = conn.execute("SELECT data FROM chat_events WHERE id = ?", (event_id,)).fetchone()
    return json.loads(row["data"]) if row else None


_guard = threading.Lock()
_listeners: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}


def broadcast(agent_id: str, msg: dict) -> None:
    with _guard:
        for loop, queue in _listeners.get(agent_id, []):
            loop.call_soon_threadsafe(queue.put_nowait, msg)


def listen(agent_id: str, loop) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    with _guard:
        _listeners.setdefault(agent_id, []).append((loop, queue))
    return queue


def unlisten(agent_id: str, queue) -> None:
    with _guard:
        _listeners[agent_id] = [x for x in _listeners.get(agent_id, []) if x[1] is not queue]


def emit(agent_id: str, event: dict) -> dict:
    event.setdefault("id", db.new_id())
    event.setdefault("at", db.now())
    if _store(agent_id, event):
        broadcast(agent_id, {"op": "event", "event": event})
    return event


def forget(agent_id: str) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM chat_events WHERE agent_id = ?", (agent_id,))
        conn.execute("DELETE FROM chat_aliases WHERE agent_id = ?", (agent_id,))
    _states.pop(agent_id, None)


# ---- per-agent state -----------------------------------------------------------------------------

class State:
    def __init__(self):
        self.working = False
        self.since = 0.0
        self.transcript: str | None = None
        self.terminal_question = False
        self.waiting: dict[str, tuple[threading.Event, list]] = {}  # event id -> (answered, [answer])


_states: dict[str, State] = {}


def state(agent_id: str) -> State:
    with _guard:
        return _states.setdefault(agent_id, State())


def state_msg(agent_id: str, alive: bool) -> dict:
    s = state(agent_id)
    return {"op": "state", "working": s.working, "alive": alive, "terminalQuestion": s.terminal_question}


def _push_state(agent_id: str) -> None:
    from . import sessions  # sessions imports this module

    broadcast(agent_id, state_msg(agent_id, sessions.status(agent_id) == "running"))


def _wait_answer(agent_id: str, event: dict) -> object:
    """Shows the event (a question) and blocks this worker thread until the user answers in the chat."""
    s = state(agent_id)
    done, answer_box = threading.Event(), []
    event = emit(agent_id, event)
    s.waiting[event["id"]] = (done, answer_box)
    _push_state(agent_id)
    done.wait(ANSWER_TIMEOUT)
    s.waiting.pop(event["id"], None)
    return answer_box[0] if answer_box else None


def answer(agent_id: str, event_id: str, value) -> None:
    waiting = state(agent_id).waiting.get(event_id)
    if waiting:
        waiting[1].append(value)
        waiting[0].set()


def stopped(agent_id: str) -> None:
    """The terminal ended or was interrupted: open questions are dropped, nothing is working any more."""
    s = state(agent_id)
    for done, _ in list(s.waiting.values()):
        done.set()
    if s.working:
        s.working = False
        emit(agent_id, {"kind": "note", "text": "작업을 멈췄습니다"})
    _push_state(agent_id)


# ---- the transcript ------------------------------------------------------------------------------

COMMAND = re.compile(r"<command-name>(.*?)</command-name>", re.S)
COMMAND_OUT = re.compile(r"<local-command-stdout>(.*?)</local-command-stdout>", re.S)


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(c.get("text", "") if c.get("type") == "text" else "(그림)" if c.get("type") == "image" else ""
                     for c in content or [] if isinstance(c, dict)).strip()


def events_from_entry(entry: dict) -> list[dict]:
    """One transcript line -> chat events with stable ids, so reading the file again changes nothing.
    A tool result comes back as {"id": tool id, "status", "result", "merge": True} to land on its call."""
    kind, at = entry.get("type"), entry.get("timestamp") or db.now()
    if kind not in ("user", "assistant") or entry.get("isSidechain") or entry.get("isMeta"):
        return []
    uuid, content = entry.get("uuid", ""), (entry.get("message") or {}).get("content")
    out = []
    if kind == "user":
        if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    out.append({"id": b["tool_use_id"], "status": "error" if b.get("is_error") else "done",
                                "result": _text_of(b.get("content"))[:RESULT_MAX], "merge": True})
            return out
        text = _text_of(content)
        if COMMAND.search(text):
            return [{"id": uuid, "at": at, "kind": "user", "text": COMMAND.search(text).group(1).strip()}]
        if COMMAND_OUT.search(text):
            note = COMMAND_OUT.search(text).group(1).strip()
            return [{"id": uuid, "at": at, "kind": "note", "text": note}] if note else []
        if text.startswith("<") and text.endswith(">"):  # other wrapped notices (caveats, reminders): not the user's words
            return []
        return [{"id": uuid, "at": at, "kind": "user", "text": text}] if text else []
    for i, b in enumerate(content or []):
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text" and b.get("text", "").strip():
            out.append({"id": f"{uuid}:{i}", "at": at, "kind": "text", "text": b["text"]})
        elif b.get("type") == "tool_use":
            out.append({"id": b["id"], "at": at, "kind": "tool", "name": b["name"], "input": b.get("input", {}), "status": "running"})
    return out


HANDOFF = re.compile(r"메일을 넘깁니다\. inbox/\d{4}-\d{2}-\d{2}-(?P<slug>.+?)-[0-9a-f]{6}\.md 파일을 읽어 주세요\..*?요청: (?P<request>.*)$")


def _plain(text: str) -> str:
    return " ".join(text.split())


def alias(agent_id: str, typed: str, shown: dict) -> None:
    """A line the app types for the user (a handed-over mail, a document request) is shown in the chat as `shown`
    ({label, title, request}) rather than as the whole instruction the agent reads."""
    with db.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO chat_aliases (agent_id, text, shown) VALUES (?, ?, ?)",
                     (agent_id, _plain(typed), json.dumps(shown, ensure_ascii=False)))


def apply(agent_id: str, event: dict) -> None:
    if event.get("kind") == "user":
        with db.connect() as conn:
            row = conn.execute("SELECT shown FROM chat_aliases WHERE agent_id = ? AND text = ?",
                               (agent_id, _plain(event["text"]))).fetchone()
        if row:
            event["shown"] = json.loads(row["shown"])
        elif m := HANDOFF.match(_plain(event["text"])):  # typed before aliases were kept: known by its wording
            event["shown"] = {"label": "메일 전달", "title": m["slug"].replace("-", " "), "request": m["request"]}
    if event.pop("merge", False):
        call = _get_event(event["id"])
        if call:
            emit(agent_id, {**call, **event})
        return
    old = _get_event(event["id"])
    if old and old.get("kind") == "tool" and old.get("status") != "running":
        return  # a call read again after its result: keep the result
    emit(agent_id, event)


class Watcher:
    """Follows one terminal session: tails the transcript the SessionStart hook named, and looks at the screen
    for questions no hook covers. Ends with the session."""

    def __init__(self, agent_id: str, session):
        self.agent_id, self.session = agent_id, session
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        s = state(self.agent_id)
        path, offset, pending, trust = None, 0, b"", None
        while self.session.alive:
            if s.transcript and s.transcript != path:
                path, offset, pending = s.transcript, 0, b""  # a new session (start, resume, /clear): read it whole
            if path:
                try:
                    with open(path, "rb") as f:
                        f.seek(offset)
                        chunk = f.read()
                    offset += len(chunk)
                    lines = (pending + chunk).split(b"\n")
                    pending = lines.pop()  # a line still being written
                    for raw in lines:
                        try:
                            entry = json.loads(raw)
                        except ValueError:
                            continue
                        for event in events_from_entry(entry):
                            apply(self.agent_id, event)
                except OSError:
                    pass
            trust = self._look_at_screen(s, trust)
            time.sleep(0.4)
        stopped(self.agent_id)

    def _look_at_screen(self, s: State, trust):
        from .sessions import TRUST_PROMPT

        screen = self.session.screen_tail(1200)
        if TRUST_PROMPT.search(screen):
            if trust is None:  # asked once, in its own thread: the answer waits for the user
                trust = {"kind": "permission", "name": "TrustFolder", "input": {"path": self.session.cwd}, "status": "pending"}
                threading.Thread(target=self._ask_trust, args=(trust,), daemon=True).start()
            return trust
        menu = bool(CHOICE_MENU.search(screen[-600:])) and not s.waiting
        if menu != s.terminal_question:
            s.terminal_question = menu
            _push_state(self.agent_id)
        return None

    def _ask_trust(self, event: dict) -> None:
        value = _wait_answer(self.agent_id, event)
        emit(self.agent_id, {**event, "status": "allowed" if value else "denied"})
        if value:  # the menu starts on "No, exit": one down, then Enter
            self.session.write("\x1b[B")
            time.sleep(0.3)
            self.session.write("\r")


# ---- hooks (POST /api/agents/{id}/hook/{event}, from the agent's hook.ps1) -------------------------

def on_hook(agent_id: str, event: str, payload: dict) -> dict | None:
    """Returns what the hook prints for Claude Code (None: nothing, and Claude Code goes on as usual)."""
    s = state(agent_id)
    if event == "SessionStart":
        if payload.get("transcript_path"):
            s.transcript = payload["transcript_path"]
        return None
    if event == "UserPromptSubmit":
        s.working, s.since = True, time.monotonic()
        _push_state(agent_id)
        return None
    if event == "Stop":
        if s.working:
            emit(agent_id, {"kind": "done", "ms": round((time.monotonic() - s.since) * 1000)})
        s.working = False
        _push_state(agent_id)
        return None
    if event == "PermissionRequest":
        ev = {"kind": "permission", "name": str(payload.get("tool_name", "")), "input": payload.get("tool_input") or {},
              "status": "pending"}
        value = _wait_answer(agent_id, ev)
        if value is None:  # no answer in time: Claude Code shows its own question in the terminal
            emit(agent_id, {**ev, "status": "terminal"})
            return None
        emit(agent_id, {**ev, "status": "allowed" if value else "denied"})
        decision = {"behavior": "allow"} if value else {"behavior": "deny", "message": "사용자가 허락하지 않았습니다."}
        return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}
    if event == "PreToolUse" and payload.get("tool_name") in APP_TOOLS:
        tool_input = payload.get("tool_input") or {}
        problems = check_card(tool_input) if payload["tool_name"].endswith("show_card") else check_question(tool_input)
        if problems:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": "고쳐서 다시 올리세요: " + "; ".join(problems)}}
    return None


# ---- cards and questions (MCP tools show_card / ask_user) -----------------------------------------

PART_TYPES = {"text", "fields", "list", "date", "todo", "mail", "buttons", "html"}
ACTIONS = {"send", "open_todo", "open_mail", "link"}
HTML_MAX = 200_000
HTML_BANNED = re.compile(
    r"<\s*(form|iframe|frame|object|embed|base|link|meta)\b|<input[^>]*type\s*=\s*[\"']?password"
    r"|\b(src|href|action|srcset|poster)\s*=\s*[\"']?\s*(https?:|//|javascript:)|url\(\s*[\"']?\s*(https?:|//)|@import",
    re.I)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$")


def _exists(table: str, row_id) -> bool:
    with db.connect() as conn:
        return bool(conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (str(row_id),)).fetchone())


def _check_action(action, where: str) -> list[str]:
    if not isinstance(action, dict) or action.get("kind") not in ACTIONS:
        return [f"{where}: action.kind는 {sorted(ACTIONS)} 중 하나"]
    kind = action["kind"]
    if kind == "send" and not str(action.get("text", "")).strip():
        return [f"{where}: send에는 text가 필요"]
    if kind == "link" and not re.match(r"https?://", str(action.get("url", ""))):
        return [f"{where}: link의 url은 http(s)로 시작"]
    if kind in ("open_todo", "open_mail") and not _exists("todos" if kind == "open_todo" else "mails", action.get("id")):
        return [f"{where}: {kind}의 id가 없습니다 ({action.get('id')})"]
    return []


def check_card(card: dict) -> list[str]:
    """What is wrong with a card, in words the agent can fix. Used by the PreToolUse hook (checked before it is
    shown) and again by show_card itself: a hook can be detached, the safety checks must hold either way."""
    parts = card.get("parts")
    if not isinstance(parts, list) or not parts:
        return ["parts는 비어 있지 않은 목록이어야 합니다"]
    problems = []
    if len(parts) > 20:
        problems.append("parts는 20개까지")
    if len(str(card.get("title", ""))) > 80:
        problems.append("title은 80자까지")
    for n, p in enumerate(parts, 1):
        where = f"parts[{n}]"
        t = p.get("type") if isinstance(p, dict) else None
        if t not in PART_TYPES:
            problems.append(f"{where}: type은 {sorted(PART_TYPES)} 중 하나")
            continue
        if t == "text" and not str(p.get("text", "")).strip():
            problems.append(f"{where}: text가 비어 있음")
        elif t == "date" and not DATE.match(str(p.get("date", ""))):
            problems.append(f"{where}: date는 YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM")
        elif t in ("todo", "mail") and not _exists("todos" if t == "todo" else "mails", p.get("id")):
            problems.append(f"{where}: {t} id가 없습니다 ({p.get('id')}). 도구 결과의 id를 그대로 쓰세요")
        elif t == "fields" and not (isinstance(p.get("rows"), list) and p["rows"]):
            problems.append(f"{where}: rows는 [{{label, value}}] 목록")
        elif t == "list":
            items = p.get("items")
            if not isinstance(items, list) or not items:
                problems.append(f"{where}: items는 비어 있지 않은 목록")
            else:
                for i, item in enumerate(items[:50], 1):
                    if isinstance(item, dict) and item.get("action") is not None:
                        problems += _check_action(item["action"], f"{where}.items[{i}]")
        elif t == "buttons":
            buttons = p.get("buttons")
            if not isinstance(buttons, list) or not 1 <= len(buttons) <= 4:
                problems.append(f"{where}: buttons는 1~4개")
            else:
                for i, b in enumerate(buttons, 1):
                    b = b if isinstance(b, dict) else {}
                    if not str(b.get("label", "")).strip():
                        problems.append(f"{where}.buttons[{i}]: label이 비어 있음")
                    problems += _check_action(b.get("action"), f"{where}.buttons[{i}]")
        elif t == "html":
            doc = str(p.get("html", ""))
            if not doc.strip() or len(doc) > HTML_MAX:
                problems.append(f"{where}: html은 1~{HTML_MAX}자")
            elif HTML_BANNED.search(doc):
                problems.append(f"{where}: html에 쓸 수 없는 것: {HTML_BANNED.search(doc).group(0)[:40]} "
                                "(바깥 주소, form·iframe 등). 그림은 data: 주소로, 링크는 Scheduler.link(url)로")
    return problems


def check_question(q: dict) -> list[str]:
    problems = []
    if not str(q.get("question", "")).strip():
        problems.append("question이 비어 있음")
    options = q.get("options")
    if not isinstance(options, list) or not 2 <= len(options) <= 4 or not all(str(o).strip() for o in options):
        problems.append("options는 비어 있지 않은 2~4개")
    return problems


def _snapshot(card: dict) -> dict:
    """Todo and mail parts carry only an id; the app fills in the real values, so a card can't misstate them."""
    out = []
    for p in card["parts"]:
        if p["type"] in ("todo", "mail"):
            with db.connect() as conn:
                if p["type"] == "todo":
                    row = conn.execute("SELECT id, title, due_at, done FROM todos WHERE id = ?", (p["id"],)).fetchone()
                else:
                    row = conn.execute("SELECT m.id, m.subject, m.sender, m.received_at, a.label AS account FROM mails m "
                                       "JOIN mail_accounts a ON a.id = m.account_id WHERE m.id = ?", (p["id"],)).fetchone()
            p = {**p, "data": dict(row) if row else None}
        out.append(p)
    return {**card, "parts": out}


def show_card(agent_id: str, card: dict) -> dict:
    problems = check_card(card)
    if problems:
        raise HTTPException(400, "카드를 고쳐서 다시 올리세요: " + "; ".join(problems))
    event = emit(agent_id, {"kind": "card", "card": _snapshot(card)})
    return {"shown": event["id"]}


def ask_user(agent_id: str, q: dict) -> dict:
    problems = check_question(q)
    if problems:
        raise HTTPException(400, "질문을 고쳐서 다시 올리세요: " + "; ".join(problems))
    event = {"kind": "question", "question": str(q["question"]), "detail": str(q.get("detail") or ""),
             "options": [str(o) for o in q["options"]], "status": "pending"}
    value = _wait_answer(agent_id, event)
    event = {**event, "status": "answered" if value is not None else "unanswered", "answer": value}
    emit(agent_id, event)
    if value is None:
        return {"answer": None, "note": "사용자가 답하지 않았습니다. 진행하지 말고 기다리세요."}
    return {"answer": value}
