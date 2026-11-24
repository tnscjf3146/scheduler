from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import db

router = APIRouter(prefix="/api/todos", tags=["todos"])


class TodoIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


class TodoPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_at: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
    done: bool | None = None


def _get(conn, todo_id: str) -> dict:
    row = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
    if not row:
        raise HTTPException(404, "할 일이 없습니다")
    return {**dict(row), "done": bool(row["done"])}


@router.get("")
def list_todos() -> list[dict]:
    with db.connect() as conn:
        items = db.rows(conn.execute(
            "SELECT * FROM todos ORDER BY done, due_at IS NULL, due_at, created_at"
        ))
    return [{**t, "done": bool(t["done"])} for t in items]


@router.get("/upcoming")
def upcoming(limit: int = 5) -> list[dict]:
    # Not done, dated, and not yet past.
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    with db.connect() as conn:
        items = db.rows(conn.execute(
            "SELECT * FROM todos WHERE done = 0 AND due_at IS NOT NULL AND due_at >= ? ORDER BY due_at LIMIT ?",
            (now, limit),
        ))
    return [{**t, "done": False} for t in items]


@router.post("", status_code=201)
def create(body: TodoIn) -> dict:
    with db.connect() as conn:
        todo_id = db.new_id()
        conn.execute(
            "INSERT INTO todos (id, title, due_at, created_at) VALUES (?, ?, ?, ?)",
            (todo_id, body.title.strip(), body.due_at, db.now()),
        )
        return _get(conn, todo_id)


@router.patch("/{todo_id}")
def update(todo_id: str, body: TodoPatch) -> dict:
    fields = body.model_dump(exclude_unset=True)
    with db.connect() as conn:
        _get(conn, todo_id)
        for key, value in fields.items():
            conn.execute(f"UPDATE todos SET {key} = ? WHERE id = ?", (value, todo_id))  # keys come from the model
        return _get(conn, todo_id)


@router.delete("/{todo_id}", status_code=204)
def delete(todo_id: str) -> None:
    with db.connect() as conn:
        _get(conn, todo_id)
        conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
