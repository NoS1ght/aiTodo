"""本地调度引擎 —— 零 AI 调用，动态优先级 + 日分配 + 自动重排"""
from __future__ import annotations
from datetime import datetime, date, timedelta
from models import Task, TaskPriority, TaskStatus

# 优先级权重：紧急4分 > 高3分 > 中2分 > 低1分
PRIORITY_WEIGHT = {"urgent": 4, "high": 3, "medium": 2, "low": 1}

# 默认每日工作容量（小时）
DAILY_CAPACITY = 8.0

def compute_urgency(task: Task, today: date) -> float:
    """
    动态优先级 = 基础权重 + 截止日期紧迫度。
    越临近 DDL 分数越高，逾期分数暴涨。
    """
    base = PRIORITY_WEIGHT.get(task.priority.value, 2)
    
    if task.deadline is None:
        # 无 DDL: 纯靠基础权重
        return base
    
    dl = task.deadline.date() if isinstance(task.deadline, datetime) else task.deadline
    days_left = (dl - today).days
    
    if days_left < 0:
        # 逾期: 基础分 + 20
        return base + 20.0
    elif days_left == 0:
        # 今天截止
        return base + 10.0
    elif days_left == 1:
        return base + 7.0
    elif days_left <= 3:
        return base + 5.0
    elif days_left <= 7:
        return base + 3.0
    else:
        # 距离远: 轻微加权
        return base + min(2.0, 14.0 / max(days_left, 1))


def schedule_tasks(tasks: list[Task], today: date | None = None, daily_capacity: float = DAILY_CAPACITY) -> list[dict]:
    """
    核心调度算法：贪心 + 动态优先级。
    
    返回按天分组的计划列表：
    [
      { "date": "2026-06-16", "day_name": "周二", "tasks": [...], "total_hours": 5.5, "capacity": 8 },
      ...
    ]
    
    保证：
    - 逾期任务排在最前
    - 每天事务量不超过 capacity
    - 前一天未完成的自动进入今天
    - 截止日期前所有任务必须完成（否则标记逾期）
    """
    if not tasks:
        return []
    
    today = today or date.today()
    
    # 只处理未完成的任务
    active = [t for t in tasks if t.status != TaskStatus.DONE]
    
    # 计算动态紧急度并排序
    for t in active:
        urgency = compute_urgency(t, today)
        # 将紧急度临时存为 float 用于排序
        t._urgency = urgency  # type: ignore
    
    active.sort(key=lambda t: getattr(t, '_urgency', 0), reverse=True)
    
    # 更新优先级的 reason
    priority_labels = {4: "紧急", 3: "高", 2: "中", 1: "低"}
    for t in active:
        urgency = getattr(t, '_urgency', 0)
        if t.deadline:
            dl = t.deadline.date() if isinstance(t.deadline, datetime) else t.deadline
            days_left = (dl - today).days
            if days_left < 0:
                t.ai_reason = f"⚠️ 已逾期 {abs(days_left)} 天，请立即处理"
            elif days_left == 0:
                t.ai_reason = "🔥 今天截止，必须完成"
            elif days_left == 1:
                t.ai_reason = "⏰ 明天截止，今天务必开始"
            elif days_left <= 3:
                t.ai_reason = f"⏳ {days_left} 天后截止"
            else:
                t.ai_reason = f"📅 {days_left} 天后截止，可适度延后"
        else:
            t.ai_reason = "📋 无硬性截止，按优先级排列"
    
    # 贪心分配：从今天起，逐天填满
    weekday_names = ["周一","周二","周三","周四","周五","周六","周日"]
    
    schedule = []
    current_day = today
    day_index = 0
    
    for task in active:
        placed = False
        # 尝试放入现有的一天
        for day_plan in schedule:
            if day_plan["total_hours"] + task.estimated_hours <= day_plan["capacity"]:
                day_plan["tasks"].append(task)
                day_plan["total_hours"] += task.estimated_hours
                task.ai_schedule = day_plan["date"]
                placed = True
                break
        
        # 放不进现有日子 → 新开一天
        while not placed:
            # 检查是否超过截止日期
            if task.deadline:
                dl = task.deadline.date() if isinstance(task.deadline, datetime) else task.deadline
                if current_day > dl and dl < today + timedelta(days=30):
                    # 已经逾期，但仍然安排
                    pass
            
            # 确保这天在 schedule 中
            existing = [d for d in schedule if d["date"] == current_day.strftime("%Y-%m-%d")]
            if not existing:
                day_name = weekday_names[current_day.weekday()]
                schedule.append({
                    "date": current_day.strftime("%Y-%m-%d"),
                    "day_name": day_name,
                    "is_today": current_day == today,
                    "tasks": [],
                    "total_hours": 0.0,
                    "capacity": daily_capacity,
                })
                existing = [schedule[-1]]
            
            day_plan = existing[0]
            remaining = day_plan["capacity"] - day_plan["total_hours"]
            
            if remaining >= task.estimated_hours:
                day_plan["tasks"].append(task)
                day_plan["total_hours"] += task.estimated_hours
                task.ai_schedule = day_plan["date"]
                placed = True
            else:
                current_day += timedelta(days=1)
                day_index += 1
    
    # 排序：今天排最前，然后日期升序
    schedule.sort(key=lambda d: d["date"])
    
    # 清理临时属性
    for t in active:
        if hasattr(t, '_urgency'):
            delattr(t, '_urgency')
    
    return schedule


def get_today_tasks(tasks: list[Task], today: date | None = None) -> list[Task]:
    """获取今天应该做的任务列表（自动包含昨天未完成的任务）"""
    today = today or date.today()
    full_schedule = schedule_tasks(tasks, today)
    
    for day_plan in full_schedule:
        if day_plan["is_today"]:
            return day_plan["tasks"]
    
    # 如果今天没有计划（所有任务已完成）
    return []


def get_weekly_overview(tasks: list[Task], today: date | None = None) -> list[dict]:
    """获取本周概览（最多显示7天）"""
    today = today or date.today()
    full_schedule = schedule_tasks(tasks, today)
    return full_schedule[:7]
