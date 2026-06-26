from __future__ import annotations
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional

class TaskSource(str, Enum):
    QQ = "qq"
    WECHAT = "wechat"
    WECOM = "wecom"
    MANUAL = "manual"
    AI = "ai"

class TaskPriority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"

class Task(BaseModel):
    id: str
    title: str
    description: str = ""
    source: TaskSource = TaskSource.MANUAL
    source_detail: str = ""          # 来源于哪条消息
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.TODO
    deadline: Optional[datetime] = None
    estimated_hours: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    ai_schedule: Optional[str] = None  # AI 建议的执行时间段
    ai_reason: Optional[str] = None    # AI 规划理由

class TaskCreate(BaseModel):
    title: str
    description: str = ""
    source: TaskSource = TaskSource.MANUAL
    priority: TaskPriority = TaskPriority.MEDIUM
    deadline: Optional[datetime] = None
    estimated_hours: float = 0.0

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    deadline: Optional[datetime] = None
    estimated_hours: Optional[float] = None

class ScrapedMessage(BaseModel):
    id: str
    source: TaskSource
    sender: str
    content: str
    group_name: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)

class ExtractResult(BaseModel):
    message_id: str
    extracted_tasks: list[TaskCreate]
    raw_content: str
