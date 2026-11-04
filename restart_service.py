"""Restart only the explicitly identified, idle local AgentBoard process."""
import os
import subprocess
import sys
import time
from pathlib import Path

from supervised_process import process_stamp


def main():
    parent, stamp, port = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
    deadline = time.monotonic() + 40
    while process_stamp(parent) == stamp and time.monotonic() < deadline:
        time.sleep(0.2)
    if process_stamp(parent) == stamp:
        raise RuntimeError("原服务尚未退出，未启动第二个实例")
    root = Path(__file__).resolve().parent
    data = Path(os.environ.get("AGENTBOARD_DATA_DIR", root / "data"))
    data.mkdir(parents=True, exist_ok=True)
    with (data / "launcher.log").open("ab") as log:
        subprocess.Popen([sys.executable, "-B", "-X", "utf8", str(root / "server.py"), "--no-browser", "--port", str(port)],
            cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt")


if __name__ == "__main__":
    main()
