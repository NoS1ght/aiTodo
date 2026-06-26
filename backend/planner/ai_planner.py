"""AI 智能规划器 —— 基于 LLM 的任务调度 + 规则引擎回退"""
from __future__ import annotations
from datetime import datetime, timedelta
from models import Task, TaskPriority, TaskStatus

async def ai_plan(tasks: list[Task], llm_client=None, api_key: str = "", api_base: str = "") -> list[Task]:
    """
    智能规划：LLM 优先，规则引擎回退。
    返回排序后的任务列表，每个任务带有 ai_schedule 和 ai_reason。
    """
    if not tasks:
        return tasks
    
    # 尝试 LLM 规划
    if llm_client is None:
        from llm_client import LLMClient
        llm_client = LLMClient(api_key=api_key, api_base=api_base)
    
    if llm_client.available:
        task_json = []
        for t in tasks:
            task_json.append({
                "id": t.id,
                "title": t.title,
                "priority": t.priority.value,
                "deadline": t.deadline.isoformat() if t.deadline else None,
                "estimated_hours": t.estimated_hours,
            })
        result = await llm_client.plan_tasks(task_json)
        if result:
            id_map = {t.id: t for t in tasks}
            planned = []
            seen = set()
            for item in result:
                tid = item.get("id")
                if tid and tid in id_map and tid not in seen:
                    seen.add(tid)
                    t = id_map[tid]
                    t.ai_schedule = item.get("ai_schedule")
                    t.ai_reason = item.get("ai_reason")
                    planned.append(t)
            # 补充未被 LLM 返回的任务
            for t in tasks:
                if t.id not in seen:
                    planned.append(t)
            if planned:
                return planned
    
    # 回退：规则引擎
    return _rule_based_plan(tasks)

def _rule_based_plan(tasks: list[Task]) -> list[Task]:
    """基于规则的规划"""
    priority_order = {
        TaskPriority.URGENT: 0,
        TaskPriority.HIGH: 1,
        TaskPriority.MEDIUM: 2,
        TaskPriority.LOW: 3,
    }
    
    now = datetime.now()
    for task in tasks:
        reasons = []
        
        if task.deadline:
            hours_left = (task.deadline - now).total_seconds() / 3600
            if hours_left < 0:
                task.ai_reason = "⚠️ 已逾期，请立即处理"
                task.priority = TaskPriority.URGENT
                continue
            elif hours_left < 4:
                reasons.append(f"仅剩 {int(hours_left)} 小时到期")
            elif hours_left < 24:
                reasons.append("24小时内到期")
            elif hours_left < 72:
                reasons.append("3天内到期")
            
            if task.estimated_hours > 0 and hours_left > 0:
                start = task.deadline - timedelta(hours=task.estimated_hours * 1.5)
                if start > now:
                    task.ai_schedule = f"{start.strftime('%m/%d %H:%M')} → {task.deadline.strftime('%m/%d %H:%M')}"
                    reasons.append("按DDL倒推安排")
                else:
                    task.ai_schedule = f"立即开始 → {task.deadline.strftime('%m/%d %H:%M')}"
                    reasons.append("时间紧张，尽快开始")
        else:
            task.ai_schedule = "无硬性截止，可灵活安排"
        
        if reasons:
            task.ai_reason = "；".join(reasons)
        elif not task.ai_reason:
            task.ai_reason = "按优先级排列"
    
    return sorted(tasks, key=lambda t: (
        priority_order.get(t.priority, 2),
        t.deadline if t.deadline else datetime(2099, 1, 1)
    ))
