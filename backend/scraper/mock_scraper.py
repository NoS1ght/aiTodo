"""模拟消息抓取器 —— 生产环境中替换为真实的 QQ/微信/企业微信 hook 方案"""
from __future__ import annotations
import uuid
from datetime import datetime, timedelta
from models import ScrapedMessage, TaskSource

# 模拟消息库：包含隐含任务和 DDL 的中文对话
MOCK_MESSAGES: list[dict] = [
    # --- QQ 群聊 ---
    {"source":"qq","sender":"张三","group":"项目A讨论组",
     "content":"@所有人 周五之前记得把需求文档发出来，客户端那边催了"},
    {"source":"qq","sender":"李四","group":"项目A讨论组",
     "content":"数据库迁移脚本写好了，今晚12点之前部署到测试环境"},
    {"source":"qq","sender":"王五","group":"技术交流群",
     "content":"下周三有个技术分享，谁要报名？主题不限"},
    {"source":"qq","sender":"赵六","group":"项目A讨论组",
     "content":"收到，我明天下午3点前把接口文档补完"},
    {"source":"qq","sender":"张三","group":"项目A讨论组",
     "content":"紧急！线上出了个bug，登录接口报500，@李四 赶紧看一下"},
    {"source":"qq","sender":"小刘","group":"摸鱼群",
     "content":"周末团建去爬山，周六早上8点集合，别忘了带水"},

    # --- 微信群聊 ---
    {"source":"wechat","sender":"老板","group":"核心团队",
     "content":"下周一早会每个人准备5分钟的周报，重点说进度和风险"},
    {"source":"wechat","sender":"产品经理","group":"核心团队",
     "content":"新版本的PRD已经更新了，大家6月20号之前给反馈"},
    {"source":"wechat","sender":"设计师","group":"核心团队",
     "content":"首页改版的设计稿已经上传蓝湖了，@前端 明天之前确认一下可行性"},
    {"source":"wechat","sender":"测试","group":"核心团队",
     "content":"回归测试发现3个问题，已经提单了，开发尽快修，下周二发版"},
    {"source":"wechat","sender":"HR","group":"全员群",
     "content":"请大家在6月25号之前完成年度绩效自评，系统里直接填"},
    {"source":"wechat","sender":"同事A","group":"午饭群",
     "content":"明天中午12点老地方聚餐，庆祝项目上线！"},

    # --- 企业微信 ---
    {"source":"wecom","sender":"CTO","group":"技术委员会",
     "content":"这个季度的技术方案评审安排在6月30号，各团队提前准备好PPT"},
    {"source":"wecom","sender":"项目经理","group":"交付项目",
     "content":"客户要求月底前交付第一版，@全体 排一下剩下的任务"},
    {"source":"wecom","sender":"运维","group":"SRE",
     "content":"今晚凌晨2点到4点服务器维护，大家提前备份数据"},
    {"source":"wecom","sender":"安全","group":"安全通知",
     "content":"安全扫描发现高危漏洞CVE-2024-xxxx，所有服务需在48小时内升级"},
    {"source":"wecom","sender":"部门主管","group":"部门群",
     "content":"7月1号之前提交Q2的OKR总结，模板已经发邮件了"},

    # --- 私聊 ---
    {"source":"qq","sender":"好友","group":"",
     "content":"周末有空吗？帮我看一下简历，我周一要投出去"},
    {"source":"wechat","sender":"朋友","group":"",
     "content":"别忘了明天下午3点约了牙医"},
    {"source":"wecom","sender":"同事","group":"",
     "content":"代码review已经提了，有空帮我看下，周五之前合进去"},
]

class MockScraper:
    """模拟消息抓取器"""
    
    def __init__(self):
        self._fetched_ids: set[str] = set()
    
    def fetch_new_messages(self) -> list[ScrapedMessage]:
        """抓取新消息（demo中每次返回全部未读）"""
        results = []
        now = datetime.now()
        for i, msg in enumerate(MOCK_MESSAGES):
            msg_id = f"msg_{i}"
            if msg_id not in self._fetched_ids:
                self._fetched_ids.add(msg_id)
                results.append(ScrapedMessage(
                    id=msg_id,
                    source=TaskSource(msg["source"]),
                    sender=msg["sender"],
                    content=msg["content"],
                    group_name=msg.get("group", ""),
                    timestamp=now - timedelta(minutes=len(MOCK_MESSAGES) - i)
                ))
        return results
    
    def reset(self):
        """重置抓取状态"""
        self._fetched_ids.clear()

# 全局实例
scraper = MockScraper()
