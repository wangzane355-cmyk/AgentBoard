"""Read actual signed-in Codex quota windows through app-server JSON-RPC.

This makes no model turn. It never reads or prints auth secrets.
"""
from __future__ import annotations

import json
import math
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def summarize_rate_limits(result: dict) -> dict:
    """A weekly reading is never a five-hour estimate."""
    buckets = result.get("rateLimitsByLimitId") or {}
    bucket = buckets.get("codex") or result.get("rateLimits") or {}
    windows = []
    for name in ("primary", "secondary"):
        window = bucket.get(name)
        if window is None:
            continue
        if not isinstance(window, dict):
            raise ValueError("Codex额度窗口格式无效")
        minutes, used = window.get("windowDurationMins"), window.get("usedPercent")
        if not _number(minutes) or minutes <= 0 or not _number(used) or not 0 <= used <= 100:
            raise ValueError("Codex额度窗口缺失或读数无效")
        windows.append({"name": name, "window_minutes": minutes, "remaining_percent": 100 - used,
                        "resets_at": window.get("resetsAt")})
    if not windows:
        raise RuntimeError("当前账号没有可验证的Codex额度窗口")
    limiting = min(windows, key=lambda window: window["remaining_percent"])
    five_hour = next((window for window in windows if window["window_minutes"] == 300), None)
    return {"codex_5h_remaining": five_hour["remaining_percent"] if five_hour else None,
            "codex_remaining": limiting["remaining_percent"], "quota_windows": windows,
            "limiting_window_minutes": limiting["window_minutes"],
            "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "resets_at": limiting["resets_at"],
            "ordinary_usage_allowed": result.get("ordinaryUsageAllowed"), "source": "app-server"}


def codex_budget_block_reason(budget: dict, current_time: float | None = None) -> str | None:
    """Apply one fresh, real-window guard to tasks and conversations."""
    if budget.get("probe_error"):
        return "Codex用量读取失败"
    if budget.get("ordinary_usage_allowed") is False:
        return "Codex账号当前不允许使用"
    current_time = time.time() if current_time is None else current_time
    try:
        age = current_time - datetime.fromisoformat(budget["observed_at"]).timestamp()
    except (KeyError, TypeError, ValueError, OverflowError):
        return "Codex用量读数缺失或无效"
    if not 0 <= age <= 1800:
        return "Codex用量读数已过期或时间无效"
    windows = budget.get("quota_windows")
    if windows is not None:
        if not isinstance(windows, list) or not windows:
            return "Codex没有可验证的额度窗口"
        readings = []
        for window in windows:
            if not isinstance(window, dict) or not _number(window.get("window_minutes")) or window["window_minutes"] <= 0:
                return "Codex额度窗口格式无效"
            readings.append(window.get("remaining_percent"))
    else:
        readings = [budget.get("codex_5h_remaining")]  # Old local records.
    if any(not _number(value) or not 0 <= value <= 100 for value in readings):
        return "Codex没有有效额度读数"
    if min(readings) <= 15:
        return "Codex可读额度窗口剩余不高于15%"
    return None


def read_account_limits(timeout_seconds: float = 15.0) -> dict:
    exe = shutil.which("codex.cmd") or shutil.which("codex")
    if not exe:
        raise RuntimeError("找不到 Codex CLI")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen([exe, "app-server", "--listen", "stdio://"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                            errors="replace", bufsize=1, creationflags=flags)
    messages: queue.Queue = queue.Queue()

    def read_lines() -> None:
        try:
            for line in proc.stdout:
                try:
                    messages.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
        finally:
            messages.put(None)

    threading.Thread(target=read_lines, daemon=True).start()
    deadline = time.monotonic() + timeout_seconds

    def send(message: dict) -> None:
        proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    def reply(request_id: int) -> dict:
        while time.monotonic() < deadline:
            try:
                message = messages.get(timeout=min(0.5, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if message is None:
                raise RuntimeError("Codex app-server 提前退出")
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError("Codex 用量接口返回错误")
                return message.get("result") or {}
        raise TimeoutError("读取 Codex 用量超时")

    try:
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {
            "name": "agentboard", "title": "AgentBoard", "version": "0.2.0"}}})
        reply(1)
        send({"method": "initialized", "params": {}})
        send({"id": 2, "method": "account/rateLimits/read"})
        result = reply(2)
        return summarize_rate_limits(result)
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()


read_five_hour_limit = read_account_limits  # Compatibility for local callers.


if __name__ == "__main__":
    try:
        print(json.dumps(read_account_limits(), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
