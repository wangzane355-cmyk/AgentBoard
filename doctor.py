"""Local, read-only startup diagnostics. Version/login/quota checks never call a model."""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from usage_probe import read_account_limits
from verification import browser_executable


def check_environment(data=None, live=True):
    data = Path(data or os.environ.get("AGENTBOARD_DATA_DIR", Path(__file__).resolve().parent / "data"))
    checks = [{"id": "python", "name": "Python运行环境", "passed": sys.version_info >= (3, 10),
               "detail": sys.version.split()[0]}]
    executable = shutil.which("codex.cmd") or shutil.which("codex")
    checks.append({"id": "codex", "name": "Codex执行器", "passed": bool(executable),
                   "detail": "已发现本机CLI" if executable else "请安装并登录Codex CLI"})
    if executable and live:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        for key, name, args in (("version", "Codex版本", ["--version"]), ("login", "Codex登录", ["login", "status"])):
            try:
                result = subprocess.run([executable, *args], capture_output=True, text=True, encoding="utf-8",
                                        errors="replace", timeout=20, creationflags=flags)
                text = (result.stdout + result.stderr).strip()
                detail = text[:200] if key == "version" else "本机CLI已登录" if result.returncode == 0 else "请在Codex中完成登录"
                checks.append({"id": key, "name": name, "passed": result.returncode == 0, "detail": detail})
            except (OSError, subprocess.SubprocessError):
                checks.append({"id": key, "name": name, "passed": False, "detail": "检查超时或无法启动；未调用模型"})
        try:
            reading = read_account_limits()
            windows = reading["quota_windows"]
            checks.append({"id": "quota", "name": "真实额度窗口", "passed": reading.get("ordinary_usage_allowed") is not False and bool(windows) and all(w["remaining_percent"] > 15 for w in windows),
                "detail": "；".join(f"{w['window_minutes']}分钟窗口剩余{w['remaining_percent']}%" for w in windows)})
        except Exception:
            checks.append({"id": "quota", "name": "真实额度窗口", "passed": False, "detail": "当前无法读取有效窗口，请刷新或检查CLI登录"})
    database = data / "autonomy.sqlite3"
    if database.is_file():
        try:
            connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True, timeout=5)
            try:
                good = connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            finally:
                connection.close()
            checks.append({"id": "checkpoints", "name": "进度数据库", "passed": good,
                           "detail": "检查点与事件记录完整" if good else "完整性检查未通过"})
        except sqlite3.Error:
            checks.append({"id": "checkpoints", "name": "进度数据库", "passed": False, "detail": "无法读取进度数据库"})
    checks.append({"id": "browser", "name": "网页截图能力", "passed": bool(browser_executable()),
                   "detail": "可使用本机Edge或Chrome；精确尺寸验收另需Node 22+" if browser_executable() else "未发现浏览器；Python/Node测试仍可使用"})
    return {"checks": checks, "model_called": False,
            "ready": all(item["passed"] for item in checks if item["id"] != "browser")}


if __name__ == "__main__":
    print(json.dumps(check_environment(), ensure_ascii=False, indent=2))
