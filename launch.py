"""Open the existing local board, or start it when needed."""
import socket
import os
import sys
import webbrowser
from pathlib import Path
from urllib.request import urlopen


def prepare_windowless_logging() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    data = Path(os.environ.get("AGENTBOARD_DATA_DIR", str(Path(__file__).resolve().parent / "data")))
    data.mkdir(parents=True, exist_ok=True)
    log = (data / "launcher.log").open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log


def page_ready(port: int = 8765) -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
            return response.status == 200 and b"AgentBoard" in response.read(4096)
    except (OSError, ValueError):
        return False

def already_running(port: int = 8765) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


if __name__ == "__main__":
    prepare_windowless_logging()
    if page_ready():
        webbrowser.open("http://127.0.0.1:8765/")
        print("看板已在运行，已打开页面。")
    elif already_running():
        print("8765端口已占用但网页未正常响应。请结束旧AgentBoard后台后重新启动；诊断记录在data/launcher.log。", file=sys.stderr)
    else:
        import server
        server.main()
