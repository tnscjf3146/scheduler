import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path


def data_dir() -> Path:
    # %APPDATA%\Scheduler. SCHEDULER_DATA_DIR overrides it (tests, portable use).
    base = os.environ.get("SCHEDULER_DATA_DIR") or Path(os.environ.get("APPDATA", Path.home())) / "Scheduler"
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(data_dir() / "scheduler.db", timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # UI, mail watcher and agents write at the same time
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS todos (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    due_at TEXT,                         -- local time 'YYYY-MM-DDTHH:MM', NULL = no date
    done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    memo TEXT NOT NULL DEFAULT '',
    subtasks TEXT NOT NULL DEFAULT '[]'  -- JSON [{"title", "done"}], always saved as a whole list
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    cli TEXT NOT NULL,                   -- 'claude' | 'codex' | 'shell'
    cwd TEXT NOT NULL,
    created_at TEXT NOT NULL,
    extensions TEXT NOT NULL DEFAULT '[]',  -- ids of attached skills and harness (extensions table)
    persona TEXT NOT NULL DEFAULT ''        -- part of the identity the agent is started with
);

-- Skills and harness (Claude Code hooks) the user keeps in the app and attaches to agents.
CREATE TABLE IF NOT EXISTS extensions (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,                  -- 'skill' | 'hook'
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',       -- skill: SKILL.md body
    event TEXT NOT NULL DEFAULT '',      -- hook: e.g. PreToolUse
    matcher TEXT NOT NULL DEFAULT '',    -- hook: which tools, for tool events
    command TEXT NOT NULL DEFAULT '',    -- hook: command to run
    created_by TEXT,                     -- agent name when an agent made it through MCP, until the user saves it
    created_at TEXT NOT NULL,
    builtin INTEGER NOT NULL DEFAULT 0   -- one of the app's default skills: attached to new agents by default
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    agent_id TEXT REFERENCES agents(id) ON DELETE SET NULL,
    agent_name TEXT NOT NULL,            -- kept even if the agent is deleted later
    title TEXT NOT NULL,
    background TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL,
    attachments TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected
    reason TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    kind TEXT NOT NULL DEFAULT 'approval',    -- approval (결재) | report (보고)
    form_name TEXT NOT NULL DEFAULT '결재서',
    fields TEXT NOT NULL DEFAULT '[]'         -- [{"label", "value", "long"}], filled from the form
);

-- Document forms (결재서, 보고서, ...) the user edits; agents fill them in through submit_approval.
CREATE TABLE IF NOT EXISTS forms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'approval',   -- approval | report
    fields TEXT NOT NULL DEFAULT '[]',       -- [{"label", "long"}]; long = a tall box
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mail_accounts (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    email TEXT NOT NULL,
    imap_host TEXT NOT NULL,
    imap_port INTEGER NOT NULL,
    smtp_host TEXT NOT NULL,
    smtp_port INTEGER NOT NULL,
    last_uid INTEGER,                    -- password lives in Windows Credential Manager, not here
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mails (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES mail_accounts(id) ON DELETE CASCADE,
    uid INTEGER NOT NULL,
    message_id TEXT,
    sender TEXT NOT NULL,
    subject TEXT NOT NULL,
    received_at TEXT NOT NULL,
    body TEXT NOT NULL,                  -- plain text: what the summary reads
    body_html TEXT,                      -- original HTML for display; '' = plain-text mail, NULL = not fetched yet
    summary_title TEXT,
    summary TEXT,
    reply_draft TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | ready | failed
    sent_at TEXT,
    read_at TEXT,                        -- read: follows the mailbox's Seen flag (mail.py _refresh_known)
    UNIQUE (account_id, uid)
);

CREATE TABLE IF NOT EXISTS chat_events (  -- a Claude Code agent's chat, one row per event (chat.py)
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_events_agent ON chat_events (agent_id);

CREATE TABLE IF NOT EXISTS sets (  -- skills and harness bundled, to attach to agents together (extensions.py)
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    builtin INTEGER NOT NULL DEFAULT 0,  -- the app's "Scheduler 기본": all default skills, kept by the app
    created_by TEXT,                     -- the agent that made it, until the user saves it
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS set_items (set_id TEXT NOT NULL, ext_id TEXT NOT NULL, PRIMARY KEY (set_id, ext_id));
CREATE TABLE IF NOT EXISTS agent_sets (agent_id TEXT NOT NULL, set_id TEXT NOT NULL, PRIMARY KEY (agent_id, set_id));

CREATE TABLE IF NOT EXISTS chat_aliases (  -- a line the app typed for the user, and the short form the chat shows
    agent_id TEXT NOT NULL,
    text TEXT NOT NULL,                  -- the typed line, whitespace collapsed
    shown TEXT NOT NULL,                 -- JSON {label, title, request}
    PRIMARY KEY (agent_id, text)
);
"""


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1')")
        # Columns added after the first release; CREATE TABLE IF NOT EXISTS leaves older databases without them.
        todo_cols = {r["name"] for r in conn.execute("PRAGMA table_info(todos)")}
        for col, ddl in (("memo", "TEXT NOT NULL DEFAULT ''"), ("subtasks", "TEXT NOT NULL DEFAULT '[]'")):
            if col not in todo_cols:
                conn.execute(f"ALTER TABLE todos ADD COLUMN {col} {ddl}")
        mail_cols = {r["name"] for r in conn.execute("PRAGMA table_info(mails)")}
        for col in ("body_html", "read_at"):
            if col not in mail_cols:
                conn.execute(f"ALTER TABLE mails ADD COLUMN {col} TEXT")
        approval_cols = {r["name"] for r in conn.execute("PRAGMA table_info(approvals)")}
        for col, ddl in (("kind", "TEXT NOT NULL DEFAULT 'approval'"), ("form_name", "TEXT NOT NULL DEFAULT '결재서'"),
                         ("fields", "TEXT NOT NULL DEFAULT '[]'")):
            if col not in approval_cols:
                conn.execute(f"ALTER TABLE approvals ADD COLUMN {col} {ddl}")
        agent_cols = {r["name"] for r in conn.execute("PRAGMA table_info(agents)")}
        for col, ddl in (("extensions", "TEXT NOT NULL DEFAULT '[]'"), ("persona", "TEXT NOT NULL DEFAULT ''")):
            if col not in agent_cols:
                conn.execute(f"ALTER TABLE agents ADD COLUMN {col} {ddl}")
        if "builtin" not in {r["name"] for r in conn.execute("PRAGMA table_info(extensions)")}:
            conn.execute("ALTER TABLE extensions ADD COLUMN builtin INTEGER NOT NULL DEFAULT 0")
        if not conn.execute("SELECT 1 FROM meta WHERE key = 'html_refetch_1'").fetchone():
            # Mails with large inline images were kept without their HTML (''); NULL makes them refetch once on open.
            conn.execute("UPDATE mails SET body_html = NULL WHERE body_html = ''")
            conn.execute("INSERT INTO meta (key, value) VALUES ('html_refetch_1', '1')")
        _seed_default_skills(conn)
        _sync_default_set(conn)
        if not conn.execute("SELECT 1 FROM forms").fetchone():  # starter forms; the user can change or delete them
            for name, kind, labels in DEFAULT_FORMS:
                fields = [{"label": l, "long": True} for l in labels]
                conn.execute("INSERT INTO forms (id, name, kind, fields, created_at) VALUES (?, ?, ?, ?, ?)",
                             (new_id(), name, kind, json.dumps(fields, ensure_ascii=False), now()))


DEFAULT_SET = "Scheduler 기본"


def _sync_default_set(conn) -> None:
    """The app's own set holds every default skill there is. Made once, and then given to the Claude Code agents
    that existed before sets did (their individually attached skills stay; duplicates go in once)."""
    row = conn.execute("SELECT id FROM sets WHERE builtin = 1").fetchone()
    if row:
        set_id = row["id"]
    else:
        set_id = new_id()
        conn.execute("INSERT INTO sets (id, name, description, builtin, created_at) VALUES (?, ?, ?, 1, ?)",
                     (set_id, DEFAULT_SET, "앱을 쓰는 데 필요한 기본 스킬. 앱이 관리합니다.", now()))
        for a in conn.execute("SELECT id FROM agents WHERE cli = 'claude'").fetchall():
            conn.execute("INSERT OR IGNORE INTO agent_sets (agent_id, set_id) VALUES (?, ?)", (a["id"], set_id))
    conn.execute("DELETE FROM set_items WHERE set_id = ?", (set_id,))
    conn.execute("INSERT INTO set_items (set_id, ext_id) SELECT ?, id FROM extensions WHERE builtin = 1", (set_id,))


def _seed_default_skills(conn) -> None:
    """Puts each of the app's default skills in once (agents get them through the default set).
    A skill the user deleted stays deleted (remembered in meta)."""
    from .defaults import DEFAULT_SKILLS

    for name, description, body in DEFAULT_SKILLS:
        key = f"seeded_skill:{name}"
        seeded = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        if seeded:
            _refresh_default_skill(conn, key, seeded["value"], name, description, body)
            continue
        row = conn.execute("SELECT id FROM extensions WHERE kind = 'skill' AND name = ?", (name,)).fetchone()
        old = name == "skill-writing-rules" and conn.execute("SELECT 1 FROM meta WHERE key = 'seeded_skill_rules'").fetchone()
        if row:
            ext_id = row["id"]
            conn.execute("UPDATE extensions SET builtin = 1 WHERE id = ?", (ext_id,))
        elif old:  # put in by an earlier version and deleted by the user since
            ext_id = None
        else:
            ext_id = new_id()
            conn.execute(
                "INSERT INTO extensions (id, kind, name, description, body, created_at, builtin) VALUES (?, 'skill', ?, ?, ?, ?, 1)",
                (ext_id, name, description, body, now()),
            )
        # Agents get it through the default set (_sync_default_set), not one by one.
        conn.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (key, _text_hash(description, body)))


# Default skill texts from before the hash was stored in meta (value '1'), so those copies can be told apart from edits.
_LEGACY_SKILL_HASHES = {"307481081766", "c574e59127ac", "e75960a85b81", "3011e98efb92"}


def _text_hash(description: str, body: str) -> str:
    return hashlib.sha1((description + body).encode()).hexdigest()[:12]


def _refresh_default_skill(conn, key: str, seeded: str, name: str, description: str, body: str) -> None:
    """Brings a default skill up to the app's current text, unless the user edited it since it was put in."""
    new = _text_hash(description, body)
    if seeded == new:
        return
    row = conn.execute("SELECT id, description, body FROM extensions WHERE kind = 'skill' AND builtin = 1 AND name = ?", (name,)).fetchone()
    if row and _text_hash(row["description"], row["body"]) in {seeded, *(_LEGACY_SKILL_HASHES if seeded == "1" else ())}:
        conn.execute("UPDATE extensions SET description = ?, body = ? WHERE id = ?", (description, body, row["id"]))
        conn.execute("UPDATE meta SET value = ? WHERE key = ?", (new, key))


DEFAULT_FORMS = [
    ("결재서", "approval", ["배경", "결정 사항"]),
    ("보고서", "report", ["개요", "진행 내용", "결과", "다음 할 일"]),
]


def rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]
