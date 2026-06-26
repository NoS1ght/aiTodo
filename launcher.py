"""
TaskTodo 启动器
- 自动启动后端 + 前端
- 自动打开浏览器
- 关闭窗口时自动释放资源
"""
import subprocess
import os
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent
PYTHON = r"D:\develop\AgentProjects\goals\.venv\Scripts\python.exe"

backend_proc = None
frontend_proc = None


def kill_port(port):
    """杀掉占用指定端口的进程"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(("127.0.0.1", port))
        s.close()
        if sys.platform == "win32":
            os.system(f'for /f "tokens=5" %a in (\'netstat -ano ^| findstr ":{port}"\') do taskkill /PID %a /F >nul 2>&1')
        else:
            os.system(f"lsof -ti:{port} | xargs kill -9 2>/dev/null")
    except Exception:
        pass


def start_backend():
    global backend_proc
    kill_port(8765)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")

    backend_proc = subprocess.Popen(
        [PYTHON, "-c",
         "import uvicorn; uvicorn.run('main:app', host='0.0.0.0', port=8765)"],
        cwd=str(ROOT / "backend"),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 等后端就绪
    for _ in range(30):
        time.sleep(0.3)
        try:
            import urllib.request
            urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=2)
            return True
        except Exception:
            pass
    return False


def start_frontend():
    global frontend_proc
    kill_port(8766)

    frontend_proc = subprocess.Popen(
        [PYTHON, "-m", "http.server", "8766", "-d", str(ROOT / "frontend")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True


def cleanup():
    print("\n正在释放资源...")
    for proc in [backend_proc, frontend_proc]:
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
    kill_port(8765)
    kill_port(8766)
    print("已清理所有进程。")


def main():
    print("=" * 40)
    print("  TaskTodo 启动器")
    print("=" * 40)
    print()

    print("[1/3] 启动后端 (8765)...")
    if start_backend():
        print("       后端已就绪")
    else:
        print("       后端启动失败！")
        return

    print("[2/3] 启动前端 (8766)...")
    start_frontend()
    print("       前端已就绪")

    print("[3/3] 打开浏览器...")
    webbrowser.open("http://localhost:8766")

    print()
    print("=" * 40)
    print("  按 Enter 关闭所有服务")
    print("=" * 40)

    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()