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
    extensions TEXT NOT NULL DEFAULT '[]'   -- ids of attached skills and harness (extensions table)
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
    created_at TEXT NOT NULL
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
    read_at TEXT,                        -- first opened in the app (local only; the mailbox is opened read-only)
    UNIQUE (account_id, uid)
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
        if "extensions" not in agent_cols:
            conn.execute("ALTER TABLE agents ADD COLUMN extensions TEXT NOT NULL DEFAULT '[]'")
        if not conn.execute("SELECT 1 FROM meta WHERE key = 'seeded_skill_rules'").fetchone():
            # The rule agents follow when they make skills. A skill, not code: the user edits it in the app.
            conn.execute(
                "INSERT INTO extensions (id, kind, name, description, body, created_at) VALUES (?, 'skill', ?, ?, ?, ?)",
                (new_id(), "skill-writing-rules", SKILL_RULES_DESCRIPTION, SKILL_RULES_BODY, now()),
            )
            conn.execute("INSERT INTO meta (key, value) VALUES ('seeded_skill_rules', '1')")
        if not conn.execute("SELECT 1 FROM forms").fetchone():  # starter forms; the user can change or delete them
            for name, kind, labels in DEFAULT_FORMS:
                fields = [{"label": l, "long": True} for l in labels]
                conn.execute("INSERT INTO forms (id, name, kind, fields, created_at) VALUES (?, ?, ?, ?, ?)",
                             (new_id(), name, kind, json.dumps(fields, ensure_ascii=False), now()))


SKILL_RULES_DESCRIPTION = "스킬을 만들거나 고칠 때. create_skill 도구를 쓰기 전에 읽는다"
SKILL_RULES_BODY = """# 스킬 작성 규칙

## 이름

- 영어 소문자, 숫자, 하이픈(-)으로 쓴다. 예: `doc-writing-rules`
- 이유: Claude Code는 스킬 이름에 이 글자만 받는다. 다른 글자가 있으면 앱이 이름을 `skill-<번호>`로 바꾼다.

## 설명과 내용의 언어

- 한국어로 쓴다.
- 영어 단어는 그대로 둔다. 기술 용어, 제품 이름, 명령, 코드, 경로, 식별자가 여기에 해당한다.
- 영어로만 이루어진 문장은 한국어로 바꾼다.

| 원문 | 처리 |
| --- | --- |
| Use this skill when writing docs. | "문서를 쓸 때 이 스킬을 쓴다."로 바꾼다 |
| React 컴포넌트를 만들 때 | 그대로 둔다 |
| `git commit` 전에 테스트를 돌린다. | 그대로 둔다 |

## 설명(언제 쓰는지) 쓰는 법

- 이 스킬을 언제 쓰는지 쓴다. Claude는 본문을 읽기 전에 설명만 보고 스킬을 고른다.
- 사용자가 할 법한 말을 넣는다. 예: "보고서 써 줘", "문서 다듬어 줘"

## 내용 쓰는 법

- 지시를 먼저 쓰고, 이유는 다음 문장에 쓴다.
- 절차는 번호 목록으로 쓴다. 항목 하나에는 동작 하나만 둔다.
"""

DEFAULT_FORMS = [
    ("결재서", "approval", ["배경", "결정 사항"]),
    ("보고서", "report", ["개요", "진행 내용", "결과", "다음 할 일"]),
]


def rows(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]
