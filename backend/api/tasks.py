"""任务管理 API —— 持久化 Key + 本地调度 + AI 提取"""
from __future__ import annotations
import uuid
import base64
from datetime import datetime
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from models import Task, TaskCreate, TaskUpdate, TaskStatus, TaskSource
from scraper.task_extractor import llm_extract_and_create
from planner.scheduler import schedule_tasks, get_today_tasks
from llm_client import llm
from storage import store as _tasks

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

# ====== LLM 配置（持久化）======

@router.get("/llm-config")
async def get_llm_config():
    return {
        "has_api_key": llm.available,
        "api_base": llm.api_base,
        "model": llm.model,
    }

@router.post("/llm-config")
async def set_llm_config(api_key: str = Form(""), api_base: str = Form("https://api.openai.com/v1"), model: str = Form("gpt-4o-mini")):
    ok = llm.save_config(api_key, api_base, model)
    return {"ok": ok, "has_api_key": llm.available}

# ====== 文本提取 + 自动规划 ======

@router.post("/extract")
async def extract_from_text(text: str = Form(...)):
    if not text.strip():
        raise HTTPException(400, "文本不能为空")
    task_creates = await llm_extract_and_create(text, llm_client=llm)
    new_tasks = []
    for tc in task_creates:
        exists = any(t.title == tc.title for t in _tasks.values())
        if not exists:
            task = Task(
                id=str(uuid.uuid4())[:8], title=tc.title, description=tc.description,
                source=TaskSource.AI if llm.available else TaskSource.MANUAL,
                priority=tc.priority, status=TaskStatus.TODO,
                deadline=tc.deadline, estimated_hours=tc.estimated_hours,
                created_at=datetime.now(), updated_at=datetime.now(),
            )
            _tasks[task.id] = task
            new_tasks.append(task)
    return {"extracted": len(task_creates), "new_tasks": len(new_tasks), "tasks": new_tasks, "used_llm": llm.available}

# ====== 截图提取 ======

@router.post("/extract-image")
async def extract_from_image(file: UploadFile = File(...)):
    contents = await file.read()
    b64 = base64.b64encode(contents).decode()
    if llm.available:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    f"{llm.api_base}/chat/completions",
                    headers={"Authorization": f"Bearer {llm.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": [
                            {"type": "text", "text": "我是一名学生。查看这张截图，列出所有需要我做的事情：任务标题、截止时间。"},
                            {"type": "image_url", "image_url": {"url": f"data:{file.content_type};base64,{b64}"}}
                        ]}],
                        "max_tokens": 1500,
                    }
                )
                resp.raise_for_status()
                data = resp.json()
                description = data["choices"][0]["message"]["content"]
        except Exception as e:
            description = f"[视觉识别失败: {e}] 请手动粘贴文本"
    else:
        description = "（未配置 AI Key，请粘贴截图中的文本）"
    
    task_creates = await llm_extract_and_create(description, llm_client=llm)
    new_tasks = []
    for tc in task_creates:
        exists = any(t.title == tc.title for t in _tasks.values())
        if not exists:
            task = Task(
                id=str(uuid.uuid4())[:8], title=tc.title,
                description=f"[截图] {tc.description}", source=TaskSource.AI,
                priority=tc.priority, status=TaskStatus.TODO,
                deadline=tc.deadline, estimated_hours=tc.estimated_hours,
                created_at=datetime.now(), updated_at=datetime.now(),
            )
            _tasks[task.id] = task
            new_tasks.append(task)
    return {"extracted": len(task_creates), "new_tasks": len(new_tasks), "tasks": new_tasks, "used_llm": llm.available}

# ====== 本地调度引擎（零 AI）======

@router.post("/schedule")
async def run_scheduler():
    """本地贪心调度：动态优先级 + 逐天分配 + 自动重排昨天未完成"""
    todo = [t for t in _tasks.values() if t.status == TaskStatus.TODO]
    plan = schedule_tasks(todo)
    # 更新任务的 ai_schedule / ai_reason
    for day in plan:
        for t in day["tasks"]:
            if t.id in _tasks:
                _tasks[t.id] = t
    return {
        "schedule": plan,
        "total_tasks": len(todo),
        "total_days": len(plan),
    }

@router.get("/today")
async def get_today_plan():
    """获取今日计划（含自动重排昨天未完成）"""
    todo = [t for t in _tasks.values() if t.status == TaskStatus.TODO]
    today_tasks = get_today_tasks(todo)
    # 同步状态
    for t in today_tasks:
        if t.id in _tasks:
            _tasks[t.id] = t
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tasks": today_tasks,
        "total_hours": sum(t.estimated_hours for t in today_tasks),
    }

# ====== 规划（保留向后兼容）======

@router.post("/plan")
async def run_planner():
    return await run_scheduler()

# ====== 重置 ======

@router.post("/reset")
async def reset_all():
    _tasks.clear()
    return {"ok": True}

# ====== CRUD ======

@router.get("", response_model=list[Task])
async def list_tasks(status: TaskStatus | None = None):
    result = list(_tasks.values())
    if status:
        result = [t for t in result if t.status == status]
    return sorted(result, key=lambda t: (t.status != "todo", t.deadline if t.deadline else datetime(2099, 1, 1)))

@router.post("", response_model=Task)
async def create_task(body: TaskCreate):
    task = Task(id=str(uuid.uuid4())[:8], title=body.title, description=body.description,
                source=body.source, priority=body.priority, status=TaskStatus.TODO,
                deadline=body.deadline, estimated_hours=body.estimated_hours,
                created_at=datetime.now(), updated_at=datetime.now())
    _tasks[task.id] = task
    return task

@router.get("/stats")
async def get_stats():
    all_tasks = list(_tasks.values())
    return {"total": len(all_tasks), "todo": sum(1 for t in all_tasks if t.status == TaskStatus.TODO),
            "in_progress": sum(1 for t in all_tasks if t.status == TaskStatus.IN_PROGRESS),
            "done": sum(1 for t in all_tasks if t.status == TaskStatus.DONE),
            "urgent": sum(1 for t in all_tasks if t.priority.value == "urgent" and t.status != TaskStatus.DONE)}

@router.get("/{task_id}", response_model=Task)
async def get_task(task_id: str):
    if task_id not in _tasks: raise HTTPException(404, "任务不存在")
    return _tasks[task_id]

@router.put("/{task_id}", response_model=Task)
async def update_task(task_id: str, body: TaskUpdate):
    if task_id not in _tasks: raise HTTPException(404, "任务不存在")
    task = _tasks[task_id]
    for key, val in body.model_dump(exclude_unset=True).items(): setattr(task, key, val)
    task.updated_at = datetime.now()
    _tasks[task.id] = task
    return task

@router.delete("/{task_id}")
async def delete_task(task_id: str):
    if task_id not in _tasks: raise HTTPException(404, "任务不存在")
    del _tasks[task_id]
    return {"ok": True}
