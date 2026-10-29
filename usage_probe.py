"""Read the signed-in Codex account's 5-hour quota through app-server JSON-RPC.

This makes no model turn. It never reads or prints auth secrets.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone


def read_five_hour_limit(timeout_seconds: float = 15.0) -> dict:
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
        bucket = (result.get("rateLimitsByLimitId") or {}).get("codex") or result.get("rateLimits") or {}
        windows = [bucket.get("primary"), bucket.get("secondary")]
        five_hour = next((w for w in windows if isinstance(w, dict) and w.get("windowDurationMins") == 300), None)
        if five_hour is None or five_hour.get("usedPercent") is None:
            raise RuntimeError("当前账号没有可读取的 5 小时窗口")
        used = max(0, min(100, int(five_hour["usedPercent"])))
        return {
            "codex_5h_remaining": 100 - used,
            "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "resets_at": five_hour.get("resetsAt"),
            "ordinary_usage_allowed": result.get("ordinaryUsageAllowed"),
            "source": "app-server",
        }
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


if __name__ == "__main__":
    try:
        print(json.dumps(read_five_hour_limit(), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
