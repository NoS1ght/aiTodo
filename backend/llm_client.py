"""LLM 统一调用客户端 —— 持久化 API Key + 学生场景系统提示词"""
from __future__ import annotations
import json
import os
import re
import calendar
import httpx
from datetime import datetime, date, timedelta

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "llm_config.json")

class LLMClient:
    """封装 LLM API 调用"""
    
    def __init__(self):
        self.api_key = ""
        self.api_base = "https://api.openai.com/v1"
        self.model = "gpt-4o-mini"
        self._load_config()
    
    # ====== 持久化 ======
    
    def _load_config(self):
        """从文件加载 API 配置（持久化）"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.api_key = cfg.get("api_key", "")
                self.api_base = cfg.get("api_base", "https://api.openai.com/v1")
                self.model = cfg.get("model", "gpt-4o-mini")
                return True
        except Exception:
            pass
        return False
    
    def save_config(self, api_key: str, api_base: str, model: str):
        """保存 API 配置到文件"""
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")
        self.model = model
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "api_key": api_key,
                    "api_base": self.api_base,
                    "model": model,
                }, f, indent=2)
            return True
        except Exception:
            return False
    
    @property
    def available(self) -> bool:
        return bool(self.api_key)
    
    # ====== 时间上下文 ======
    
    @staticmethod
    def _build_time_context() -> str:
        now = datetime.now()
        today = now.date()
        weekday_names = ["周一","周二","周三","周四","周五","周六","周日"]
        today_name = weekday_names[today.weekday()]
        
        monday = today - timedelta(days=today.weekday())
        this_week = []
        for i in range(7):
            d = monday + timedelta(days=i)
            marker = " ← 今天" if d == today else ""
            this_week.append(f"  {weekday_names[i]} = {d.strftime('%Y-%m-%d')}{marker}")
        
        next_monday = monday + timedelta(days=7)
        next_week = []
        for i in range(7):
            d = next_monday + timedelta(days=i)
            next_week.append(f"  下周{weekday_names[i]} = {d.strftime('%Y-%m-%d')}")
        
        last_day = calendar.monthrange(today.year, today.month)[1]
        end_of_month = date(today.year, today.month, last_day)
        
        next_month = today.month + 1
        next_year = today.year
        if next_month > 12:
            next_month = 1
            next_year += 1
        
        lines = [
            f"⏰ 当前精确时间: {now.strftime('%Y-%m-%d %H:%M')} ({today_name})",
            f"   时区: Asia/Shanghai (UTC+8)",
            f"",
            f"📅 本周日期对照:",
            *this_week,
            f"",
            f"📅 下周日期对照:",
            *next_week,
            f"",
            f"📅 特殊日期:",
            f"  本月月底 = {end_of_month.strftime('%Y-%m-%d')}",
            f"  下月月初 = {date(next_year, next_month, 1).strftime('%Y-%m-%d')}",
            f"",
            f"📌 时间 → ISO 映射:",
            f'  "今天"       → {now.strftime("%Y-%m-%d")}',
            f'  "今晚"       → {now.strftime("%Y-%m-%d")}T23:59:59',
            f'  "明天"       → {(today + timedelta(days=1)).strftime("%Y-%m-%d")}',
            f'  "明天下午3点" → {(today + timedelta(days=1)).strftime("%Y-%m-%d")}T15:00:00',
            f'  "后天"       → {(today + timedelta(days=2)).strftime("%Y-%m-%d")}',
            f'  "下周"       → 从 {next_monday.strftime("%Y-%m-%d")} 起',
            f'  "月底"       → {end_of_month.strftime("%Y-%m-%d")}',
            f"  \"X天后\"     → 从今天 + X 天",
            f"  \"X小时后\"   → 从当前时间 + X 小时",
            f'  "X月X号\"      → 当前年份 ({today.year}) + 该月日',
            f"",
            f"⚠️  deadline 统一输出: YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS",
        ]
        return "\n".join(lines)
    
    # ====== LLM 调用 ======
    
    async def _chat(self, system: str, user: str, temperature: float = 0.2, max_tokens: int = 2000) -> str | None:
        if not self.api_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                resp = await client.post(
                    f"{self.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[LLM] API error: {e}")
            return None
    
    async def extract_tasks(self, text: str) -> list[dict]:
        """从非结构化文本中提取任务 —— 使用学生场景系统提示词"""
        time_ctx = self._build_time_context()
        
        system = (
            "我是一名学生。"
            "帮我分析以下信息，总结出我需要做什么。"
            "提取所有任务，对每个任务输出：\n"
            "- title: 任务标题（15字内，简洁明了地说要干什么）\n"
            "- description: 任务描述（补充说明，如涉及的人、地点、细节，50字内）\n"
            "- deadline: 截止时间（ISO格式 YYYY-MM-DDTHH:MM:SS，无法确定则为 null）\n"
            "- estimated_hours: 预计完成所需小时数（数字）\n\n"
            "=== 时间解析规则 ===\n"
            "使用下方时间对照表精确计算日期：\n"
            "- \"明天下午3点前\" → 查表 + T15:00:00\n"
            "- \"下周三\" → 查表得具体日期\n"
            "- \"月底前\" → 查表得本月最后一天\n"
            "- \"48小时内\" → 当前时间 + 48小时\n"
            "- \"X月X号\" → 当前年份 + 该月日\n"
            "- 无明确时间的默认当天 23:59:59\n\n"
            "=== 任务识别 ===\n"
            "以下算任务: 有明确要做的事（作业/考试/提交/复习/预习/上课/组会/实验/论文/答辩/报名/填表）\n"
            "以下不算: 通知（\"大家注意\"）、问候、已完成事项、无动作陈述\n\n"
            '只返回 JSON 数组: [{"title":"...","description":"...","deadline":"...","estimated_hours":数字}]'
        )
        
        user = f"""{time_ctx}

---
需要分析的文本：
{text}

只返回 JSON 数组:"""
        
        result = await self._chat(system, user, temperature=0.1, max_tokens=1500)
        if result:
            return self._parse_json_array(result)
        return []
    
    def _parse_json_array(self, text: str) -> list[dict]:
        if not text:
            return []
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        start = text.find('[')
        end = text.rfind(']')
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass
        return []

# 全局实例（自动加载持久化配置）
llm = LLMClient()
