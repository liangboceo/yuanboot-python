from datetime import UTC, datetime
from uuid import UUID, uuid4

from .database import DatabaseSession
from .models import Task, TaskCreate, TaskPage, TaskStats, TaskStatus, TaskUpdate


class TaskRepository:
    def __init__(self, session: DatabaseSession):
        self.connection = session.connection

    def get(self, task_id: UUID) -> Task | None:
        row = self.connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (str(task_id),)
        ).fetchone()
        return Task.model_validate(dict(row)) if row else None

    def create(self, body: TaskCreate) -> Task:
        task_id = uuid4()
        now = datetime.now(UTC).isoformat()
        with self.connection:
            self.connection.execute(
                "INSERT INTO tasks (id, title, description, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(task_id), body.title, body.description, body.status.value, now, now),
            )
        task = self.get(task_id)
        assert task is not None
        return task

    def list(self, *, page: int, page_size: int, status: TaskStatus | None, q: str) -> TaskPage:
        clauses = []
        parameters = []
        if status is not None:
            clauses.append("status = ?")
            parameters.append(status.value)
        if q:
            literal = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("(title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')")
            parameters.extend([f"%{literal}%", f"%{literal}%"])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        total = self.connection.execute(
            "SELECT count(*) FROM tasks" + where, parameters
        ).fetchone()[0]
        rows = self.connection.execute(
            "SELECT * FROM tasks" + where + " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            [*parameters, page_size, (page - 1) * page_size],
        ).fetchall()
        return TaskPage(
            items=[Task.model_validate(dict(row)) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def update(self, task_id: UUID, body: TaskUpdate) -> Task | None:
        fields = body.model_dump(exclude_unset=True, mode="json")
        # Field names come from the validated model, never from raw request keys.
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self.connection:
            cursor = self.connection.execute(
                f"UPDATE tasks SET {assignments}, updated_at = ? WHERE id = ?",
                [*fields.values(), datetime.now(UTC).isoformat(), str(task_id)],
            )
        return self.get(task_id) if cursor.rowcount else None

    def delete(self, task_id: UUID) -> bool:
        with self.connection:
            cursor = self.connection.execute("DELETE FROM tasks WHERE id = ?", (str(task_id),))
        return cursor.rowcount > 0

    def stats(self) -> TaskStats:
        counts = {
            row["status"]: row["amount"]
            for row in self.connection.execute(
                "SELECT status, count(*) AS amount FROM tasks GROUP BY status"
            )
        }
        return TaskStats(
            total=sum(counts.values()),
            todo=counts.get("todo", 0),
            in_progress=counts.get("in_progress", 0),
            done=counts.get("done", 0),
        )
