"""MySQL repository and Redis cache for remote infrastructure in any deployment environment."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from redis import RedisError
from sqlalchemy import Column, MetaData, String, Table, Text, func, select
from sqlalchemy.orm import Session

from yuanboot import HostedService
from yuanboot.components.mysql import MySqlDataSource
from yuanboot.components.redis import RedisCache
from yuanboot.logging import get_logger

from .models import Task, TaskCreate, TaskPage, TaskStats, TaskStatus, TaskUpdate
from .repository import TaskRepository
from .services import TaskService

metadata = MetaData()
tasks = Table(
    "taskboard_tasks",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("title", String(200), nullable=False),
    Column("description", Text, nullable=False),
    Column("status", String(16), nullable=False, index=True),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)
logger = get_logger("taskboard")


class MySqlSchemaInitializer(HostedService):
    def __init__(self, source: MySqlDataSource):
        self.source = source

    def start(self):
        metadata.create_all(self.source.engine)


class MySqlTaskRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, task_id: UUID) -> Task | None:
        row = (
            self.session.execute(select(tasks).where(tasks.c.id == str(task_id))).mappings().first()
        )
        return Task.model_validate(dict(row)) if row else None

    def create(self, body: TaskCreate) -> Task:
        task_id = uuid4()
        now = datetime.now(UTC).isoformat()
        self.session.execute(
            tasks.insert().values(
                id=str(task_id),
                title=body.title,
                description=body.description,
                status=body.status.value,
                created_at=now,
                updated_at=now,
            )
        )
        self.session.commit()
        task = self.get(task_id)
        assert task is not None
        return task

    def list(self, *, page: int, page_size: int, status: TaskStatus | None, q: str) -> TaskPage:
        conditions = []
        if status is not None:
            conditions.append(tasks.c.status == status.value)
        if q:
            literal = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{literal}%"
            conditions.append(
                tasks.c.title.like(pattern, escape="\\")
                | tasks.c.description.like(pattern, escape="\\")
            )
        total = self.session.execute(
            select(func.count()).select_from(tasks).where(*conditions)
        ).scalar_one()
        rows = (
            self.session.execute(
                select(tasks)
                .where(*conditions)
                .order_by(tasks.c.created_at.desc(), tasks.c.id.desc())
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
            .mappings()
            .all()
        )
        return TaskPage(
            items=[Task.model_validate(dict(row)) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def update(self, task_id: UUID, body: TaskUpdate) -> Task | None:
        fields = body.model_dump(exclude_unset=True, mode="json")
        result = self.session.execute(
            tasks.update()
            .where(tasks.c.id == str(task_id))
            .values(**fields, updated_at=datetime.now(UTC).isoformat())
        )
        self.session.commit()
        return self.get(task_id) if result.rowcount else None

    def delete(self, task_id: UUID) -> bool:
        result = self.session.execute(tasks.delete().where(tasks.c.id == str(task_id)))
        self.session.commit()
        return result.rowcount > 0

    def stats(self) -> TaskStats:
        rows = self.session.execute(select(tasks.c.status, func.count()).group_by(tasks.c.status))
        counts = dict(rows.all())
        return TaskStats(
            total=sum(counts.values()),
            todo=counts.get("todo", 0),
            in_progress=counts.get("in_progress", 0),
            done=counts.get("done", 0),
        )


class CachedTaskService(TaskService):
    """Cache aggregate statistics for at most 10 seconds; task reads use the database."""

    def __init__(self, repository: TaskRepository, cache: RedisCache):
        super().__init__(repository)
        self.cache = cache

    def _invalidate(self):
        try:
            self.cache.delete("tasks:stats")
        except RedisError:
            logger.warning("Statistics cache invalidation failed; cached values expire within 10s")

    def create(self, body: TaskCreate) -> Task:
        task = super().create(body)
        self._invalidate()
        return task

    def update(self, task_id: UUID, body: TaskUpdate) -> Task:
        task = super().update(task_id, body)
        self._invalidate()
        return task

    def delete(self, task_id: UUID):
        super().delete(task_id)
        self._invalidate()

    def stats(self) -> TaskStats:
        try:
            cached = self.cache.get_json("tasks:stats")
            if cached is not None:
                return TaskStats.model_validate(cached)
        except RedisError:
            logger.warning("Statistics cache unavailable; querying database")
        result = super().stats()
        try:
            self.cache.set_json("tasks:stats", result.model_dump(), ttl=10)
        except RedisError:
            pass
        return result
