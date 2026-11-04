"""Open the local board after bounded, single-instance background startup."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.request import ProxyHandler, build_opener


BASE = Path(__file__).resolve().parent
STARTUP_SECONDS = 120
# Loopback checks must not depend on a user's system or environment HTTP proxy.
urlopen = build_opener(ProxyHandler({})).open


class StartupError(RuntimeError):
    pass


class LaunchCancelled(Exception):
    pass


def data_directory() -> Path:
    return Path(os.environ.get("AGENTBOARD_DATA_DIR", BASE / "data")).expanduser().resolve()


def prepare_windowless_logging() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    data = data_directory()
    data.mkdir(parents=True, exist_ok=True)
    log = (data / "launcher.log").open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log


def page_ready(port: int = 8765) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.5) as response:
            health = json.loads(response.read(4096))
            if response.status != 200 or health.get("app") != "AgentBoard" or health.get("ready") is not True:
                return False
        with urlopen(f"http://127.0.0.1:{port}/", timeout=0.5) as response:
            return response.status == 200 and b"AgentBoard" in response.read(4096)
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def already_running(port: int = 8765) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


class StartupLock:
    """An OS-owned byte lock; crashed launchers cannot leave a stale PID lock."""
    def __init__(self, path):
        self.path = Path(path)
        self.stream = None
        self.acquired = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.stream.write(b"0")
            self.stream.flush()
        return self

    def acquire(self):
        if self.acquired:
            return True
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, PermissionError):
            return False
        self.acquired = True
        return True

    def __exit__(self, *args):
        try:
            if self.acquired:
                self.stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        finally:
            self.stream.close()


def start_background(port, data):
    data.mkdir(parents=True, exist_ok=True)
    with (data / "launcher.log").open("ab") as log:
        return subprocess.Popen(
            [sys.executable, "-B", "-X", "utf8", str(BASE / "server.py"), "--no-browser", "--port", str(port)],
            cwd=BASE, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            env={**os.environ, "AGENTBOARD_DATA_DIR": str(data)},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt")


def ensure_running(port=8765, data=None, timeout=STARTUP_SECONDS, progress=lambda message, elapsed: None):
    data = Path(data) if data else data_directory()
    started = time.monotonic()
    deadline = started + timeout
    if page_ready(port):
        return
    progress("正在准备 AgentBoard…", 0)
    with StartupLock(data / f"launcher-{port}.lock") as lock:
        while not lock.acquire():
            if page_ready(port):
                return
            if time.monotonic() >= deadline:
                raise StartupError("另一次启动还没有完成。请稍后重试，或查看启动日志。")
            progress("已有启动正在进行，正在等待它就绪…", time.monotonic() - started)
            time.sleep(0.3)
        if page_ready(port):
            return
        child = None if already_running(port) else start_background(port, data)
        while time.monotonic() < deadline:
            if page_ready(port):
                return
            if child is not None and child.poll() is not None:
                # Another entry point may have won the bind; reuse its ready board.
                if page_ready(port):
                    return
                raise StartupError("后台没有成功启动。详细原因已保存在启动日志中。")
            progress("正在启动后台并检查本机环境，请稍候…", time.monotonic() - started)
            time.sleep(0.5)
    raise StartupError(f"等待启动超过{timeout}秒。端口可能被其他程序占用，或后台仍未就绪；请查看启动日志。")


class StartupProgress:
    """Small native feedback for a desktop shortcut whose console is hidden."""
    def __init__(self):
        self.root = None
        self.label = None
        self.cancelled = False
        self.unavailable = False

    def update(self, message, elapsed):
        if self.cancelled:
            raise LaunchCancelled()
        if self.unavailable:
            return
        if self.root is None:
            try:
                import tkinter as tk
                from tkinter import ttk
                self.root = tk.Tk()
                self.root.title("AgentBoard · 正在启动")
                self.root.resizable(False, False)
                width, height = 440, 175
                self.root.geometry(f"{width}x{height}+{(self.root.winfo_screenwidth()-width)//2}+{(self.root.winfo_screenheight()-height)//2}")
                frame = ttk.Frame(self.root, padding=22)
                frame.pack(fill="both", expand=True)
                ttk.Label(frame, text="AgentBoard", font=("Segoe UI", 17, "bold")).pack(anchor="w")
                self.label = ttk.Label(frame, wraplength=390)
                self.label.pack(anchor="w", pady=(10, 10))
                bar = ttk.Progressbar(frame, mode="indeterminate")
                bar.pack(fill="x")
                bar.start(15)
                ttk.Label(frame, text="关闭此提示只取消本次打开，不停止已有任务。", font=("Segoe UI", 9)).pack(anchor="w", pady=(9, 0))
                self.root.protocol("WM_DELETE_WINDOW", self.cancel)
                self.root.lift()
            except Exception:
                self.close()
                self.unavailable = True
                return
        self.label.configure(text=f"{message}  {int(elapsed)}秒")
        self.root.update()
        if self.cancelled:
            raise LaunchCancelled()

    def cancel(self):
        self.cancelled = True
        self.close()

    def close(self):
        if self.root is not None:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None


def show_error(message):
    text = f"{message}\n\n网页入口：http://127.0.0.1:8765/\n启动日志：{data_directory() / 'launcher.log'}"
    print(text, file=sys.stderr, flush=True)
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "AgentBoard · 启动提示", 0x10)


def main():
    progress = StartupProgress()
    try:
        prepare_windowless_logging()
        print(f"\n[{datetime.now().astimezone().isoformat(timespec='seconds')}] 正在打开 AgentBoard", flush=True)
        ensure_running(progress=progress.update)
        progress.close()
        url = "http://127.0.0.1:8765/"
        if not webbrowser.open(url):
            raise StartupError("后台已经就绪，但系统未能打开浏览器。请手动打开下面的网页入口。")
        print("AgentBoard 已就绪，已打开页面。", flush=True)
        return 0
    except LaunchCancelled:
        print("已取消本次打开；已有后台和任务继续运行。", flush=True)
        return 0
    except Exception as exc:
        progress.close()
        if not isinstance(exc, StartupError):
            traceback.print_exc()
        show_error(str(exc))
        return 1
    finally:
        progress.close()


if __name__ == "__main__":
    raise SystemExit(main())
