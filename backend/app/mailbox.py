"""The mailbox itself, over IMAP: folders, search, reading any folder, flags, moving, deleting, drafts.

Everything works on (account, folder, uid), so agents can reach mail the app never imported. Changes to the inbox
are mirrored into the app's own list (mails table): moved or deleted mails leave it, read flags follow."""

import base64
import email.policy
import imaplib
import re
import time
from email.message import EmailMessage

from fastapi import HTTPException

from . import db, mail


# ---- folder names: modified UTF-7 (RFC 3501 5.1.3), '스팸메일함' <-> '&wqTTOLpUx3zVaA-' -----------------------------

def utf7_encode(name: str) -> str:
    out, run = [], ""

    def flush():
        out.append("&" + base64.b64encode(run.encode("utf-16-be")).decode().rstrip("=").replace("/", ",") + "-")

    for ch in name:
        if 0x20 <= ord(ch) <= 0x7E:
            if run:
                flush()
                run = ""
            out.append("&-" if ch == "&" else ch)
        else:
            run += ch
    if run:
        flush()
    return "".join(out)


def utf7_decode(name: str) -> str:
    def part(m):
        b64 = m.group(1).replace(",", "/")
        return "&" if not b64 else base64.b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-16-be")

    return re.sub(r"&([^-]*)-", part, name)


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---- folders -------------------------------------------------------------------------------------

# By what a folder is for: the server's special-use flag (RFC 6154) first, then common names (Naver has no flags).
ROLES = {
    "spam": (r"\Junk", "스팸메일함", "스팸함", "Spam", "Junk"),
    "trash": (r"\Trash", "휴지통", "Trash", "Deleted Messages"),
    "sent": (r"\Sent", "보낸메일함", "보낸편지함", "Sent", "Sent Messages"),
    "drafts": (r"\Drafts", "임시보관함", "Drafts"),
    "archive": (r"\Archive", "보관함", "Archive"),
}
LIST_LINE = re.compile(r'\((?P<flags>[^)]*)\) (?:"[^"]*"|NIL) (?P<name>"(?:[^"\\]|\\.)*"|\S+)')


def _folders(conn) -> list[dict]:
    _, lines = conn.list()
    out = []
    for line in lines:
        m = LIST_LINE.match(line.decode() if isinstance(line, bytes) else str(line))
        if not m:
            continue
        raw = m["name"].strip('"').replace('\\"', '"')
        flags = m["flags"].split()
        role = next((r for r, keys in ROLES.items() if keys[0] in flags), None)
        out.append({"name": utf7_decode(raw), "raw": raw, "role": role, "selectable": r"\Noselect" not in flags})
    taken = {f["role"] for f in out}
    for f in out:  # no flag: match by name
        if not f["role"]:
            f["role"] = next((r for r, keys in ROLES.items() if r not in taken and f["name"].split("/")[-1] in keys[1:]), None)
            taken.add(f["role"])
    return out


def _connect(account_id: str):
    with db.connect() as c:
        row = c.execute("SELECT * FROM mail_accounts WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "메일 계정이 없습니다")
    password = mail.keyring.get_password(mail.KEYRING_SERVICE, account_id)
    if not password:
        raise HTTPException(400, "메일 계정 비밀번호가 없습니다. 계정을 다시 연결하세요")
    return mail._imap(dict(row), password)


class _Session:
    """with _Session(account_id) as (conn, folders): one login per tool call."""

    def __init__(self, account_id: str):
        self.account_id = account_id

    def __enter__(self):
        self.conn = _connect(self.account_id)
        return self.conn, _folders(self.conn)

    def __exit__(self, *exc):
        try:
            self.conn.logout()
        except Exception:  # noqa: BLE001 - the work is done or already failed
            pass


def _find(folders: list[dict], name: str) -> dict:
    """A folder by name or by role ('spam', 'trash', 'sent', 'drafts', 'archive', 'inbox')."""
    if name.lower() == "inbox":
        name = "INBOX"
    hit = next((f for f in folders if f["name"] == name or f["role"] == name), None)
    if not hit:
        raise HTTPException(400, f"폴더가 없습니다: {name}. 있는 폴더: {', '.join(f['name'] for f in folders)}")
    return hit


def _ok(result, what: str):
    typ, data = result
    if typ != "OK":
        raise HTTPException(502, f"{what}하지 못했습니다: {data[0].decode(errors='replace') if data and isinstance(data[0], bytes) else data}")
    return data


def _select(conn, folders, name: str, readonly: bool = False) -> dict:
    folder = _find(folders, name)
    _ok(conn.select(_quote(folder["raw"]), readonly=readonly), "폴더를 열지")
    return folder


def list_folders(account_id: str) -> list[dict]:
    """Every folder with its role and message counts."""
    with _Session(account_id) as (conn, folders):
        out = []
        for f in folders:
            item = {"name": f["name"], "role": f["role"] or ("inbox" if f["name"].upper() == "INBOX" else None)}
            if f["selectable"]:
                typ, data = conn.status(_quote(f["raw"]), "(MESSAGES UNSEEN)")
                if typ == "OK":
                    m = re.search(rb"MESSAGES (\d+).*?UNSEEN (\d+)", data[0])
                    if m:
                        item.update(total=int(m[1]), unread=int(m[2]))
            out.append(item)
        return out


def create_folder(account_id: str, name: str) -> dict:
    with _Session(account_id) as (conn, _):
        _ok(conn.create(_quote(utf7_encode(name))), "폴더를 만들지")
    return {"created": name}


def rename_folder(account_id: str, name: str, new_name: str) -> dict:
    with _Session(account_id) as (conn, folders):
        _ok(conn.rename(_quote(_find(folders, name)["raw"]), _quote(utf7_encode(new_name))), "이름을 바꾸지")
    return {"renamed": name, "to": new_name}


def delete_folder(account_id: str, name: str) -> dict:
    with _Session(account_id) as (conn, folders):
        folder = _find(folders, name)
        if folder["role"] or folder["name"].upper() == "INBOX":
            raise HTTPException(400, "받은편지함, 스팸함, 휴지통 같은 기본 폴더는 지울 수 없습니다")
        _ok(conn.delete(_quote(folder["raw"])), "폴더를 지우지")
    return {"deleted": name}


def subscribe_folder(account_id: str, name: str, subscribed: bool) -> dict:
    with _Session(account_id) as (conn, folders):
        raw = _quote(_find(folders, name)["raw"])
        _ok(conn.subscribe(raw) if subscribed else conn.unsubscribe(raw), "구독을 바꾸지")
    return {"folder": name, "subscribed": subscribed}


def quota(account_id: str) -> dict:
    with _Session(account_id) as (conn, _):
        if "QUOTA" not in conn.capabilities:
            return {"supported": False}
        typ, data = conn.getquotaroot("INBOX")
        m = re.search(rb"STORAGE (\d+) (\d+)", b" ".join(x for part in data for x in (part if isinstance(part, list) else [part]) if isinstance(x, bytes)))
        return {"supported": True, "used_kb": int(m[1]), "limit_kb": int(m[2])} if m else {"supported": True}


# ---- search & read -------------------------------------------------------------------------------

FLAG_NAMES = {"read": r"\Seen", "flagged": r"\Flagged", "answered": r"\Answered", "deleted": r"\Deleted", "draft": r"\Draft"}
HEADER_FIELDS = "BODY.PEEK[HEADER.FIELDS (FROM TO CC SUBJECT DATE MESSAGE-ID)]"
FETCH_META = re.compile(rb"UID (\d+)|FLAGS \(([^)]*)\)")


def _meta(head: bytes) -> tuple[int | None, list[str]]:
    uid, flags = None, []
    for m in FETCH_META.finditer(head):
        if m[1]:
            uid = int(m[1])
        else:
            flags = m[2].decode().split()
    return uid, flags


def _named(flags: list[str]) -> list[str]:
    back = {v: k for k, v in FLAG_NAMES.items()}
    return [back.get(f, f) for f in flags if f != r"\Recent"]


def _imap_date(value: str) -> str:
    return time.strftime("%d-%b-%Y", time.strptime(value[:10], "%Y-%m-%d"))  # IMAP wants 01-Nov-2026


def search(account_id: str, folder: str = "INBOX", sender: str | None = None, to: str | None = None,
           subject: str | None = None, text: str | None = None, since: str | None = None, before: str | None = None,
           unread: bool | None = None, flagged: bool | None = None, limit: int = 30) -> list[dict]:
    """Newest first. Words may be Korean: the server gets one of them (as a UTF-8 literal, imaplib can send one per
    command), the rest are matched here on the fetched headers."""
    crit, words = [], [(k, v) for k, v in (("FROM", sender), ("TO", to), ("SUBJECT", subject), ("TEXT", text)) if v]
    if since:
        crit += ["SINCE", _imap_date(since)]
    if before:
        crit += ["BEFORE", _imap_date(before)]
    if unread is not None:
        crit.append("UNSEEN" if unread else "SEEN")
    if flagged is not None:
        crit.append("FLAGGED" if flagged else "UNFLAGGED")
    literal, local = None, []
    for key, value in words:
        if value.isascii():
            crit += [key, _quote(value)]
        elif literal is None:
            literal = (key, value)
        else:
            local.append((key, value))  # ponytail: only From/To/Subject can be matched here, a second Korean TEXT word is dropped
    with _Session(account_id) as (conn, folders):
        _select(conn, folders, folder, readonly=True)
        if literal:
            conn.literal = literal[1].encode()
            data = _ok(conn.uid("SEARCH", "CHARSET", "UTF-8", *crit, literal[0]), "검색")
        else:
            data = _ok(conn.uid("SEARCH", *(crit or ["ALL"])), "검색")
        uids = [int(u) for u in data[0].split()]
        found = []
        for chunk in range(len(uids), 0, -50):  # newest first, 50 per FETCH
            batch = uids[max(0, chunk - 50):chunk]
            data = _ok(conn.uid("FETCH", ",".join(map(str, batch)), f"(UID FLAGS {HEADER_FIELDS})"), "메일을 가져오")
            for part in data:
                if not isinstance(part, tuple):
                    continue
                uid, flags = _meta(part[0])
                h = email.message_from_bytes(part[1], policy=email.policy.default)
                item = {"uid": uid, "from": str(h["From"] or ""), "to": str(h["To"] or ""), "subject": str(h["Subject"] or ""),
                        "date": str(h["Date"] or ""), "flags": _named(flags)}
                if all(v.lower() in item[{"FROM": "from", "TO": "to", "SUBJECT": "subject"}[k]].lower() for k, v in local if k != "TEXT"):
                    found.append(item)
            found.sort(key=lambda x: -x["uid"])
            if len(found) >= limit:
                break
        return found[:limit]


def read(account_id: str, folder: str, uid: int) -> dict:
    """The whole mail, without marking it read (BODY.PEEK)."""
    with _Session(account_id) as (conn, folders):
        _select(conn, folders, folder, readonly=True)
        data = _ok(conn.uid("FETCH", str(uid), "(UID FLAGS BODY.PEEK[])"), "메일을 가져오")
    part = next((p for p in data if isinstance(p, tuple)), None)
    if not part:
        raise HTTPException(404, "메일이 없습니다")
    _, flags = _meta(part[0])
    msg = email.message_from_bytes(part[1], policy=email.policy.default)
    doc = mail.parse_message(part[1])
    return {"uid": uid, "folder": folder, "from": doc["sender"], "to": str(msg["To"] or ""), "cc": str(msg["Cc"] or ""),
            "subject": doc["subject"], "date": doc["received_at"], "flags": _named(flags), "body": doc["body"],
            "attachments": [p.get_filename() for p in msg.iter_attachments() if p.get_filename()]}


# ---- change: flags, copy, move, delete -----------------------------------------------------------

def _uid_set(uids: list[int]) -> str:
    if not uids:
        raise HTTPException(400, "uid가 없습니다")
    return ",".join(str(int(u)) for u in uids)


def _mirror_inbox(account_id: str, folder: dict, uids: list[int], gone: bool = False, read: bool | None = None) -> None:
    """Keeps the app's list (inbox mails only) the same as the mailbox."""
    if folder["name"].upper() != "INBOX":
        return
    marks = ",".join("?" * len(uids))
    with db.connect() as c:
        if gone:
            c.execute(f"DELETE FROM mails WHERE account_id = ? AND uid IN ({marks})", (account_id, *uids))
        elif read is not None:
            c.execute(f"UPDATE mails SET read_at = {'COALESCE(read_at, ?)' if read else '?'} WHERE account_id = ? AND uid IN ({marks})",
                      (db.now() if read else None, account_id, *uids))


def set_flags(account_id: str, folder: str, uids: list[int], add: list[str] = (), remove: list[str] = ()) -> dict:
    """Flags by name (read, flagged, answered, deleted, draft) or any keyword the server takes (letters, digits, $_-)."""
    def imap_flags(names):
        out = []
        for n in names:
            f = FLAG_NAMES.get(n, n)
            if f not in FLAG_NAMES.values() and not re.fullmatch(r"[$A-Za-z0-9_-]{1,40}", f):
                raise HTTPException(400, f"표시 이름을 확인하세요: {n}")
            out.append(f)
        return "(" + " ".join(out) + ")"

    with _Session(account_id) as (conn, folders):
        f = _select(conn, folders, folder)
        if add:
            _ok(conn.uid("STORE", _uid_set(uids), "+FLAGS.SILENT", imap_flags(add)), "표시를 붙이")
        if remove:
            _ok(conn.uid("STORE", _uid_set(uids), "-FLAGS.SILENT", imap_flags(remove)), "표시를 떼")
    if "read" in add or "read" in remove:
        _mirror_inbox(account_id, f, uids, read="read" in add)
    return {"uids": uids, "added": list(add), "removed": list(remove)}


def _expunge(conn, uid_set: str) -> None:
    """Removes only these mails if the server can (UIDPLUS), else everything flagged deleted in the folder."""
    if "UIDPLUS" in conn.capabilities:
        conn.uid("EXPUNGE", uid_set)
    else:  # ponytail: plain EXPUNGE also clears other mails already flagged deleted in this folder
        conn.expunge()


def transfer(account_id: str, folder: str, uids: list[int], to: str, copy: bool = False) -> dict:
    """Moves (or copies) mails to a folder by name or role: 'spam', 'trash', 'archive', 'inbox'."""
    with _Session(account_id) as (conn, folders):
        src = _select(conn, folders, folder)
        dest = _find(folders, to)
        uid_set, quoted = _uid_set(uids), _quote(dest["raw"])
        if copy:
            _ok(conn.uid("COPY", uid_set, quoted), "복사")
        elif "MOVE" in conn.capabilities:
            _ok(conn.uid("MOVE", uid_set, quoted), "옮기")
        else:
            _ok(conn.uid("COPY", uid_set, quoted), "옮기")
            _ok(conn.uid("STORE", uid_set, "+FLAGS.SILENT", r"(\Deleted)"), "옮기")
            _expunge(conn, uid_set)
    if not copy:
        _mirror_inbox(account_id, src, uids, gone=True)
    return {"uids": uids, "to": dest["name"], "copied" if copy else "moved": True}


def delete(account_id: str, folder: str, uids: list[int], permanent: bool = False) -> dict:
    """To the trash; for good if permanent, or if the mails are already in the trash, or there is no trash."""
    with _Session(account_id) as (conn, folders):
        trash = next((f for f in folders if f["role"] == "trash"), None)
        src = _find(folders, folder)
    if trash and not permanent and src["name"] != trash["name"]:
        return {**transfer(account_id, folder, uids, "trash"), "deleted": "trash"}
    with _Session(account_id) as (conn, folders):
        src = _select(conn, folders, folder)
        _ok(conn.uid("STORE", _uid_set(uids), "+FLAGS.SILENT", r"(\Deleted)"), "지우")
        _expunge(conn, _uid_set(uids))
    _mirror_inbox(account_id, src, uids, gone=True)
    return {"uids": uids, "deleted": "permanent"}


def save_draft(account_id: str, to: str, subject: str, body: str) -> dict:
    """Puts a draft in the drafts folder; it shows in the mail service's drafts, ready to send from there."""
    with db.connect() as c:
        row = c.execute("SELECT email FROM mail_accounts WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "메일 계정이 없습니다")
    msg = EmailMessage()
    msg["From"] = row["email"]
    if to:
        msg["To"] = ", ".join(mail.forward_recipients(to))
    msg["Subject"] = mail._one_line(subject)
    msg.set_content(body)
    with _Session(account_id) as (conn, folders):
        drafts = next((f for f in folders if f["role"] == "drafts"), None)
        if not drafts:
            raise HTTPException(400, "임시보관함을 찾지 못했습니다")
        _ok(conn.append(_quote(drafts["raw"]), r"(\Draft \Seen)", imaplib.Time2Internaldate(time.time()), msg.as_bytes()), "초안을 저장")
    return {"saved": drafts["name"], "subject": subject}


# ---- the app's own list, by mail id --------------------------------------------------------------

def app_mail(mail_id: str) -> tuple[str, int]:
    with db.connect() as c:
        row = c.execute("SELECT account_id, uid FROM mails WHERE id = ?", (mail_id,)).fetchone()
    if not row:
        raise HTTPException(404, "메일이 없습니다")
    return row["account_id"], row["uid"]
