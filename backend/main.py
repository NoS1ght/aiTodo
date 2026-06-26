"""TaskTodo 后端主入口"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
import traceback

from api.tasks import router as tasks_router
from storage import store

app = FastAPI(
    title="TaskTodo",
    description="学生智能任务管理",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)


# ====== 全局异常处理 ======

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"服务器内部错误: {str(exc)}",
            "type": type(exc).__name__,
        },
    )


# ====== 健康检查 ======

@app.get("/health")
async def health():
    db_ok = False
    try:
        db_ok = len(store) >= 0  # SQLite 正常
    except Exception:
        pass
    return {
        "status": "ok",
        "service": "TaskTodo",
        "version": "0.1.0",
        "time": datetime.now().isoformat(),
        "db": "connected" if db_ok else "error",
        "tasks_count": len(store),
    }
