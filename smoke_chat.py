"""Explicit live chat smoke: DeepSeek then Codex, using isolated sample data."""
import os
import argparse
import time
from pathlib import Path

root = Path(__file__).resolve().parent
os.environ["AGENTBOARD_DATA_DIR"] = str(root / "data" / "smoke-chat")
os.environ["AGENTBOARD_WORKSPACES_DIR"] = str(Path.home() / "AgentBoardChatSmokeWork")
import server as board
parser = argparse.ArgumentParser()
parser.add_argument("--continue-codex", action="store_true")
args = parser.parse_args()

source = Path.home() / "AgentBoardChatSmokeSource"
source.mkdir(exist_ok=True)
if args.continue_codex:
    chat = board.STATE["chats"][-1]
else:
    board.STATE = {"version": 1, "projects": [{"id": "smoke", "name": "Chat smoke",
        "path": str(source), "protected_paths": [], "context_files": [], "check": "none"}],
        "tasks": [], "runs": [], "chats": [], "budget": {}}
    board.save()
    chat = board.create_chat({"project_id": "smoke", "agent": "deepseek"})
turns = [
    ("deepseek", "记住暗号 ORBIT_4729，只回复这个暗号，不要运行工具。", "ORBIT_4729"),
    ("codex", "上一条用户消息里让你记住的暗号是什么？只回复暗号，不要运行工具。", "ORBIT_4729"),
]
for agent, question, marker in (turns[1:] if args.continue_codex else turns):
    board.send_chat(chat["id"], {"agent": agent, "message": question})
    while chat["status"] == "running":
        time.sleep(1)
    answer = chat["messages"][-1]
    passed = chat["status"] == "idle" and answer["role"] == "assistant" and marker in answer["text"]
    print({"agent": agent, "passed": passed, "status": chat["status"], "error": chat["error"],
           "reply": answer["text"][:200] if answer["role"] == "assistant" else ""}, flush=True)
    if not passed:
        raise SystemExit(1)
