"""SQLite 持久化存储层 —— 零依赖，进程重启数据不丢失"""
from __future__ import annotations
import sqlite3
import json
import os
from datetime import datetime
from models import Task, TaskPriority, TaskStatus, TaskSource

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "tasktodo.db")


class TaskStore:
    """SQLite-backed task store with dict-like interface."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = os.path.abspath(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_table()

    def _create_table(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                source TEXT DEFAULT 'manual',
                source_detail TEXT DEFAULT '',
                priority TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'todo',
                deadline TEXT,
                estimated_hours REAL DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                ai_schedule TEXT,
                ai_reason TEXT
            )
        """)
        self._conn.commit()

    # ---- dict-like interface used by api/tasks.py ----

    def __getitem__(self, task_id: str) -> Task:
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._row_to_task(row)

    def __setitem__(self, task_id: str, task: Task):
        self._conn.execute("""
            INSERT OR REPLACE INTO tasks
            (id, title, description, source, source_detail, priority, status,
             deadline, estimated_hours, created_at, updated_at, ai_schedule, ai_reason)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            task.id, task.title, task.description or "",
            task.source.value if hasattr(task.source, 'value') else task.source,
            task.source_detail or "",
            task.priority.value if hasattr(task.priority, 'value') else task.priority,
            task.status.value if hasattr(task.status, 'value') else task.status,
            task.deadline.isoformat() if task.deadline else None,
            task.estimated_hours or 0,
            task.created_at.isoformat() if task.created_at else datetime.now().isoformat(),
            task.updated_at.isoformat() if task.updated_at else datetime.now().isoformat(),
            task.ai_schedule,
            task.ai_reason,
        ))
        self._conn.commit()

    def __delitem__(self, task_id: str):
        if task_id not in self:
            raise KeyError(task_id)
        self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()

    def __contains__(self, task_id: str) -> bool:
        row = self._conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return row is not None

    def __iter__(self):
        return iter(self.keys())

    def __len__(self):
        row = self._conn.execute("SELECT COUNT(*) FROM tasks").fetchone()
        return row[0]

    def keys(self):
        rows = self._conn.execute("SELECT id FROM tasks").fetchall()
        return [r["id"] for r in rows]

    def values(self):
        rows = self._conn.execute("SELECT * FROM tasks").fetchall()
        return [self._row_to_task(r) for r in rows]

    def items(self):
        rows = self._conn.execute("SELECT * FROM tasks").fetchall()
        return [(r["id"], self._row_to_task(r)) for r in rows]

    def get(self, task_id: str, default=None) -> Task | None:
        try:
            return self[task_id]
        except KeyError:
            return default

    def clear(self):
        self._conn.execute("DELETE FROM tasks")
        self._conn.commit()

    # ---- helpers ----

    def _row_to_task(self, row) -> Task:
        def parse_dt(val):
            if not val:
                return None
            return datetime.fromisoformat(val)

        return Task(
            id=row["id"],
            title=row["title"],
            description=row["description"] or "",
            source=TaskSource(row["source"]),
            source_detail=row["source_detail"] or "",
            priority=TaskPriority(row["priority"]),
            status=TaskStatus(row["status"]),
            deadline=parse_dt(row["deadline"]),
            estimated_hours=row["estimated_hours"] or 0,
            created_at=parse_dt(row["created_at"]) or datetime.now(),
            updated_at=parse_dt(row["updated_at"]) or datetime.now(),
            ai_schedule=row["ai_schedule"],
            ai_reason=row["ai_reason"],
        )


# Singleton
store = TaskStore()
