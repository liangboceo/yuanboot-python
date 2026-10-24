from uuid import UUID

from .models import Task, TaskCreate, TaskPage, TaskStats, TaskStatus, TaskUpdate
from .repository import TaskRepository


class TaskNotFoundError(Exception):
    pass


class TaskService:
    def __init__(self, repository: TaskRepository):
        self.repository = repository

    def get(self, task_id: UUID) -> Task:
        task = self.repository.get(task_id)
        if task is None:
            raise TaskNotFoundError
        return task

    def create(self, body: TaskCreate) -> Task:
        return self.repository.create(body)

    def list(self, page: int, page_size: int, status: TaskStatus | None, q: str) -> TaskPage:
        return self.repository.list(page=page, page_size=page_size, status=status, q=q.strip())

    def update(self, task_id: UUID, body: TaskUpdate) -> Task:
        task = self.repository.update(task_id, body)
        if task is None:
            raise TaskNotFoundError
        return task

    def delete(self, task_id: UUID):
        if not self.repository.delete(task_id):
            raise TaskNotFoundError

    def stats(self) -> TaskStats:
        return self.repository.stats()
