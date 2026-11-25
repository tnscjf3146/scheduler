"""Skills and harness (hooks) the user keeps in the app and attaches to agents.

Each Claude Code agent gets its attached ones as a plugin built in its own app folder and loaded with --plugin-dir,
so nothing is written into the agent's work folder (which may be the user's own project). The plugin is rebuilt at
every launch: changes apply when the agent restarts. Codex has no such plugin mechanism, so they apply to Claude Code
agents only."""

import json
import os
import re
import shutil
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from . import db, defaults

router = APIRouter(prefix="/api/extensions", tags=["extensions"])

# Claude Code hook events offered in the editor; installed hooks may use others, which are kept as they are.
EVENTS = ("PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop", "SessionStart", "SessionEnd", "Notification",
          "SubagentStop", "PreCompact")
TOOL_EVENTS = ("PreToolUse", "PostToolUse")  # the only events that take a matcher (which tools)


class ExtensionIn(BaseModel):
    kind: str = Field(pattern="^(skill|hook)$")
    name: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=1000)  # skill: when to use it. hook: a note for the user
    body: str = Field(default="", max_length=50_000)  # skill: SKILL.md body
    event: str = Field(default="", pattern="^[A-Za-z]*$")  # hook
    matcher: str = Field(default="", max_length=200)  # hook, tool events only: e.g. "Bash" or "Edit|Write"
    command: str = Field(default="", max_length=2000)  # hook

    @model_validator(mode="after")
    def _check(self):
        if self.kind == "skill" and not (self.description.strip() and self.body.strip()):
            raise ValueError("스킬은 언제 쓰는지(설명)와 내용이 필요합니다")
        if self.kind == "hook" and not (self.event and self.command.strip()):
            raise ValueError("하네스는 실행 시점과 명령이 필요합니다")
        return self


def _with_agents(conn, ext: dict) -> dict:
    agents = conn.execute("SELECT id, extensions FROM agents").fetchall()
    return {**ext, "agent_ids": [a["id"] for a in agents if ext["id"] in json.loads(a["extensions"])]}


def _get(conn, ext_id: str) -> dict:
    row = conn.execute("SELECT * FROM extensions WHERE id = ?", (ext_id,)).fetchone()
    if not row:
        raise HTTPException(404, "스킬이나 하네스가 없습니다")
    return _with_agents(conn, dict(row))


def _values(body: ExtensionIn) -> tuple:
    hook = body.kind == "hook"
    return (
        body.kind, body.name.strip(), body.description.strip(), "" if hook else body.body.strip(),
        body.event if hook else "", body.matcher.strip() if hook and body.event in TOOL_EVENTS else "",
        body.command.strip() if hook else "",
    )


def save(body: ExtensionIn, created_by: str | None = None) -> dict:
    """Also used by the MCP tools; created_by names the agent that made it, so the user can review it."""
    ext_id = db.new_id()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO extensions (id, kind, name, description, body, event, matcher, command, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ext_id, *_values(body), created_by, db.now()),
        )
        return _get(conn, ext_id)


@router.get("")
def list_extensions() -> list[dict]:
    with db.connect() as conn:
        rows = db.rows(conn.execute("SELECT * FROM extensions ORDER BY kind DESC, created_at"))  # skills first
        return [_with_agents(conn, r) for r in rows]


@router.post("", status_code=201)
def create(body: ExtensionIn) -> dict:
    return save(body)


@router.put("/{ext_id}")
def update(ext_id: str, body: ExtensionIn) -> dict:
    with db.connect() as conn:
        _get(conn, ext_id)
        conn.execute(
            "UPDATE extensions SET kind = ?, name = ?, description = ?, body = ?, event = ?, matcher = ?, command = ?, "
            "created_by = NULL WHERE id = ?",  # saved by the user from here on: reviewed
            (*_values(body), ext_id),
        )
        return _get(conn, ext_id)


@router.delete("/{ext_id}", status_code=204)
def delete(ext_id: str) -> None:
    with db.connect() as conn:
        _set_agents(conn, ext_id, [])
        conn.execute("DELETE FROM extensions WHERE id = ?", (ext_id,))


class AgentIds(BaseModel):
    agent_ids: list[str]


def _set_agents(conn, ext_id: str, agent_ids: list[str]) -> None:
    for a in conn.execute("SELECT id, extensions FROM agents").fetchall():
        ids = [i for i in json.loads(a["extensions"]) if i != ext_id] + ([ext_id] if a["id"] in agent_ids else [])
        conn.execute("UPDATE agents SET extensions = ? WHERE id = ?", (json.dumps(ids), a["id"]))


@router.put("/{ext_id}/agents")
def set_agents(ext_id: str, body: AgentIds) -> dict:
    """Which agents get this one. Only the user does this (there is no MCP tool for it): a hook runs commands
    without the CLI asking first, so an agent must not be able to attach one to itself."""
    with db.connect() as conn:
        _get(conn, ext_id)
        _set_agents(conn, ext_id, body.agent_ids)
        return _get(conn, ext_id)


# ---- What the user already has in Claude Code (~/.claude) ------------------------------------------------------

def _claude_home() -> Path:
    return Path(os.environ.get("SCHEDULER_CLAUDE_HOME") or Path.home() / ".claude")  # override for tests


def _read_skill(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"---\s*\n(.*?)\n---\s*\n?(.*)", text, re.S)
    if not m:
        return None
    try:
        front = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(front, dict):
        return None
    return {
        "kind": "skill", "name": str(front.get("name") or path.parent.name)[:40],
        "description": str(front.get("description") or "")[:1000], "body": m.group(2).strip()[:50_000],
        "event": "", "matcher": "", "command": "", "source": str(path),
    }


@router.get("/installed")
def installed() -> list[dict]:
    """Skills in ~/.claude/skills and hooks in ~/.claude/settings.json, for importing into the app.
    These already apply to every Claude Code session of this user, agents included; importing makes a copy that
    can be edited and attached to chosen agents."""
    home = _claude_home()
    found = []
    for root, dirs, files in os.walk(home / "skills", followlinks=True):
        if len(Path(root).relative_to(home / "skills").parts) >= 4:
            dirs.clear()  # skills sit a level or two down; don't wander into whole repos
        if "SKILL.md" in files and (skill := _read_skill(Path(root) / "SKILL.md")):
            found.append(skill)
    try:
        hooks = json.loads((home / "settings.json").read_text(encoding="utf-8")).get("hooks") or {}
    except (OSError, ValueError):
        hooks = {}
    for event, entries in hooks.items():
        for entry in entries if isinstance(entries, list) else []:
            for h in entry.get("hooks") or []:
                if h.get("type") == "command" and h.get("command"):
                    cmd = h["command"]
                    found.append({
                        "kind": "hook", "name": f"{event} · {Path(cmd.split()[0]).name}"[:40], "description": "",
                        "body": "", "event": event, "matcher": entry.get("matcher") or "", "command": cmd,
                        "source": str(home / "settings.json"),
                    })
    return found


# ---- The plugin an agent is launched with -------------------------------------------------------------------------

def _skill_name(ext: dict) -> str:
    """Claude Code skill names are lowercase letters, digits and hyphens; Korean names fall back to the id."""
    slug = re.sub(r"[^a-z0-9]+", "-", ext["name"].lower()).strip("-")[:40]
    return slug or f"skill-{ext['id'][:8]}"


def build_plugin(agent: dict) -> Path:
    """Writes the Claude Code plugin the agent starts with: its identity, given by a SessionStart hook (what a
    SessionStart hook prints goes into the conversation), plus the skills and hooks attached to it."""
    folder = db.data_dir() / "agents" / agent["id"] / "plugin"
    shutil.rmtree(folder, ignore_errors=True)  # rebuilt from scratch so removed ones disappear
    ids = json.loads(agent.get("extensions") or "[]")
    with db.connect() as conn:
        marks = ",".join("?" * len(ids))
        exts = db.rows(conn.execute(f"SELECT * FROM extensions WHERE id IN ({marks}) ORDER BY created_at", ids)) if ids else []

    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps({
        "name": "scheduler-agent",
        "version": "0.1.0",
        "description": f"Scheduler 에이전트 '{agent['name']}'의 정체성, 스킬, 하네스",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    identity = folder / "identity.md"
    identity.write_text(defaults.identity(agent), encoding="utf-8")
    # PowerShell is on every Windows machine; UTF-8 output keeps the Korean text intact.
    show = (f"powershell -NoProfile -Command \"[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
            f"Get-Content -Raw -Encoding UTF8 -LiteralPath '{identity}'\"")

    hooks: dict[str, list] = {"SessionStart": [{"hooks": [{"type": "command", "command": show}]}]}
    used: set[str] = set()
    for ext in exts:
        if ext["kind"] == "skill":
            name = _skill_name(ext)
            if name in used:
                name = f"{name}-{ext['id'][:6]}"
            used.add(name)
            (folder / "skills" / name).mkdir(parents=True)
            front = json.dumps(f"{ext['name']}: {ext['description']}", ensure_ascii=False)  # a JSON string is valid YAML
            (folder / "skills" / name / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: {front}\n---\n\n{ext['body']}\n", encoding="utf-8"
            )
        else:
            entry = {"hooks": [{"type": "command", "command": ext["command"]}]}
            if ext["matcher"]:
                entry["matcher"] = ext["matcher"]
            hooks.setdefault(ext["event"], []).append(entry)
    (folder / "hooks").mkdir()
    (folder / "hooks" / "hooks.json").write_text(json.dumps({"hooks": hooks}, ensure_ascii=False, indent=2), encoding="utf-8")
    return folder


def builtin_ids() -> list[str]:
    """The app's default skills, attached to a new agent unless the user picks otherwise."""
    with db.connect() as conn:
        return [r["id"] for r in conn.execute("SELECT id FROM extensions WHERE builtin = 1 ORDER BY created_at")]
