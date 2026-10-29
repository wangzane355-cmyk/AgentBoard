"""Explicit live smoke: a bounded, shared DeepSeek -> Codex -> DeepSeek discussion."""
import os
import time
from pathlib import Path

root = Path(__file__).resolve().parent
os.environ["AGENTBOARD_DATA_DIR"] = str(root / "data" / "smoke-group")
os.environ["AGENTBOARD_WORKSPACES_DIR"] = str(Path.home() / "AgentBoardGroupSmokeWork")
import server as board

source = Path.home() / "AgentBoardGroupSmokeSource"
source.mkdir(exist_ok=True)
board.STATE = {"version": 1, "projects": [{"id": "smoke", "name": "Group chat smoke",
    "path": str(source), "protected_paths": [], "context_files": [], "check": "none"}],
    "tasks": [], "runs": [], "chats": [], "budget": {}}
board.save()
chat = board.create_chat({"project_id": "smoke", "agent": "deepseek", "mode": "group"})
board.send_chat(chat["id"], {"agent": "all", "message":
    "/讨论 2 这是群聊连通性测试，不要用工具。共享口令是 ROOM_6821。"
    "DeepSeek第一次发言：带上口令给一句开发建议，末行 AGENTBOARD_TO: codex。"
    "Codex发言：确认看见DeepSeek的建议和口令，补充一句，再以 AGENTBOARD_TO: deepseek 邀请对方总结。"
    "DeepSeek第二次发言：回应Codex的补充，一句总结后以 AGENTBOARD_TO: DONE 结束。不要代写其他成员。"})
last = None
while chat["status"] == "running":
    active = chat.get("batch", {}).get("active_agent")
    if active != last:
        print({"active_agent": active}, flush=True)
        last = active
    time.sleep(1)
replies = [m for m in chat["messages"] if m["role"] == "assistant"]
agents = [m["agent"] for m in replies]
passed = chat["status"] == "idle" and agents == ["deepseek", "codex", "deepseek"] and all("ROOM_6821" in m["text"] for m in replies[:2])
print({"passed": passed, "status": chat["status"], "error": chat["error"], "agents": agents,
       "replies": [{"agent": m["agent"], "text": m["text"][:300]} for m in replies]}, flush=True)
raise SystemExit(0 if passed else 1)
