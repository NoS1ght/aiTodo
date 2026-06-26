"""任务提取器 —— 从非结构化文本中提取任务（规则引擎 + LLM 双路径）"""
from __future__ import annotations
import re
import uuid
from datetime import datetime, timedelta, date
from models import TaskCreate, TaskPriority, TaskSource

# ====== 时间解析 ======
WEEKDAY_CN = {"周一":0,"周二":1,"周三":2,"周四":3,"周五":4,"周六":5,"周日":6,"星期天":6}

def _next_weekday(target: int, from_date=None):
    d = from_date or date.today()
    days = target - d.weekday()
    if days <= 0: days += 7
    return d + timedelta(days=days)

def parse_time_in_text(text: str, base: datetime = None) -> datetime | None:
    base = base or datetime.now()
    today = base.date()
    
    # 明天下午3点
    m = re.search(r"明天[上下]午?(\d{1,2})[点时](\d{1,2})?[分]?", text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if "下" in text[max(0,m.start()-5):m.start()]: h += 12
        return datetime.combine(today + timedelta(days=1), datetime.min.time().replace(hour=h, minute=mi))
    
    # 今晚X点
    m = re.search(r"今晚(\d{1,2})[点时](\d{1,2})?[分半]?", text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if "半" in text: mi = 30
        return datetime.combine(today, datetime.min.time().replace(hour=h, minute=mi))
    
    # 明天之前 / 明天
    if "明天" in text and re.search(r"之前|前$", text):
        return datetime.combine(today + timedelta(days=1), datetime.min.time().replace(hour=23, minute=59))
    if "明天" in text:
        return datetime.combine(today + timedelta(days=1), datetime.min.time().replace(hour=18, minute=0))
    
    # 今天X点 / 今晚 / 今天之前
    m = re.search(r"今天(\d{1,2})[点时]", text)
    if m: return datetime.combine(today, datetime.min.time().replace(hour=int(m.group(1)), minute=0))
    if "今晚" in text: return datetime.combine(today, datetime.min.time().replace(hour=20, minute=0))
    if "今天" in text and re.search(r"之前|前$", text):
        return datetime.combine(today, datetime.min.time().replace(hour=23, minute=59))
    
    # ⚠️ 关键：先匹配"下周X"/"下X"，再匹配"周X"/"X"
    # "下周三" = "下"+"周三" (3字)  "下周周三"也需要覆盖
    for cn, wd in WEEKDAY_CN.items():
        if re.search(rf"下周\s*{cn}", text) or re.search(rf"下\s*{cn}", text):
            d = today + timedelta(days=7)
            result = _next_weekday(wd, d)
            h = 23 if re.search(r"之前|前$", text) else 18
            return datetime.combine(result, datetime.min.time().replace(hour=h, minute=59 if h==23 else 0))
    
    for cn, wd in WEEKDAY_CN.items():
        if re.search(rf"周\s*{cn}", text) or cn in text:
            result = _next_weekday(wd, today)
            h = 23 if re.search(r"之前|前$", text) else 18
            return datetime.combine(result, datetime.min.time().replace(hour=h, minute=59 if h==23 else 0))
    
    # X月X号
    m = re.search(r"(\d{1,2})月(\d{1,2})[号日]", text)
    if m: return datetime.combine(date(today.year, int(m.group(1)), int(m.group(2))), datetime.min.time().replace(hour=23, minute=59))
    
    # X天后
    m = re.search(r"(\d+)\s*天[后内]", text)
    if m: return datetime.combine(today + timedelta(days=int(m.group(1))), datetime.min.time().replace(hour=23, minute=59))
    
    # X小时内
    m = re.search(r"(\d+)\s*(小)?时[之内]", text)
    if m: return base + timedelta(hours=int(m.group(1)))
    
    # 周末
    if "周末" in text:
        return datetime.combine(_next_weekday(5, today), datetime.min.time().replace(hour=23, minute=59))
    
    # 月底
    if "月底" in text:
        import calendar
        last = calendar.monthrange(today.year, today.month)[1]
        return datetime.combine(date(today.year, today.month, last), datetime.min.time().replace(hour=23, minute=59))
    
    return None

# ====== 任务提取 ======
URGENT_KW = ["紧急","立刻","马上","报错","挂了","500","crash","bug","故障","漏洞","高危","严重","尽快","逾期","今晚","今天截止","明天考试"]
HIGH_KW = ["抓紧","赶紧","催","deadline","ddl","必须","务必"]

TASK_VERBS = re.compile(
    r"(记得|别忘了|不要忘|务必|需|需要|必须|一定[要得]|"
    r"安排|准备|完成|提交|发[布出送]?|上传|填写|升级|修复|"
    r"部署|备份|检查|确认|反馈|review|合[并入]?|报名|通知|"
    r"做[好完]?|处理|交[付出上]?|写[好完]?|改[好完]?|"
    r"考试|复习|预习|背书|做题|实验|论文|答辩|填表|"
    r"报告|编程|数据处理|设计)"
)

def _make_title(sent: str) -> str:
    cleaned = re.sub(r"^(另外|对了|还有|同时|此外|以及|并且|而且)\s*", "", sent.strip())
    cleaned = re.sub(r"^[（(]?\s*\d+[\.\、\)）]\s*", "", cleaned)
    cleaned = re.sub(r"[！!，,；;、\s]+$", "", cleaned)
    if len(cleaned) > 45: cleaned = cleaned[:45] + "..."
    return cleaned.strip()

def extract_tasks_rule(text: str) -> list[TaskCreate]:
    tasks = []
    sentences = re.split(r"[。\n；;！!？?\r]+", text)
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 3: continue
        if re.search(r"\d[\.\、]", sent) and len(sent) > 10:
            subs = re.split(r"(?=\d[\.\、])", sent)
            if len(subs) > 1:
                for sub in subs:
                    sub = sub.strip().rstrip(",，")
                    if sub and len(sub) >= 3: tasks.extend(_try_extract_sentence(sub))
                continue
        tasks.extend(_try_extract_sentence(sent))
    return tasks

def _try_extract_sentence(sent: str) -> list[TaskCreate]:
    has_task = TASK_VERBS.search(sent) is not None
    if not has_task and re.search(r"^[（(]?\s*(请|帮我|帮忙|麻烦)", sent): has_task = True
    if not has_task and re.search(r"(之前|前$|之内|之内|前提交|前交|前完成|日截止)", sent): has_task = True
    if not has_task: return []
    deadline = parse_time_in_text(sent)
    priority = TaskPriority.MEDIUM
    for kw in URGENT_KW:
        if kw in sent: priority = TaskPriority.URGENT; break
    if priority != TaskPriority.URGENT:
        for kw in HIGH_KW:
            if kw in sent: priority = TaskPriority.HIGH; break
    est = 2.0
    if any(kw in sent for kw in ["考试","复习","预习","背书"]): est = 3.0
    elif any(kw in sent for kw in ["实验","报告","编程"]): est = 4.0
    elif any(kw in sent for kw in ["论文","答辩"]): est = 10.0
    elif any(kw in sent for kw in ["习题","作业","做题"]): est = 2.0
    title = _make_title(sent)
    if not title: return []
    return [TaskCreate(title=title, description=sent[:200], source=TaskSource.MANUAL, priority=priority, deadline=deadline, estimated_hours=est)]

async def llm_extract_and_create(text: str, llm_client=None, api_key="", api_base="") -> list[TaskCreate]:
    if llm_client is None:
        from llm_client import LLMClient
        llm_client = LLMClient()
    if llm_client.available:
        result = await llm_client.extract_tasks(text)
        if result:
            tasks = []
            for item in result:
                dl = None
                if item.get("deadline"):
                    try: dl = datetime.fromisoformat(item["deadline"])
                    except (ValueError, TypeError):
                        try: dl = datetime.strptime(item["deadline"], "%Y-%m-%d %H:%M")
                        except ValueError: pass
                tasks.append(TaskCreate(title=item.get("title","未命名")[:40], description=item.get("description",""), source=TaskSource.AI, priority=TaskPriority(item.get("priority","medium")), deadline=dl, estimated_hours=float(item.get("estimated_hours",2))))
            if tasks: return tasks
    return extract_tasks_rule(text)
