"""Explicit paid live smoke test. Run manually only when desired."""
import importlib.util
import argparse
import os
import time
from pathlib import Path


root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--agent", choices=["codex", "deepseek"], default="deepseek")
parser.add_argument("--mode", choices=["explore", "implement"], default="explore")
args = parser.parse_args()
source = Path.home() / f"AgentBoardSmokeSource-{args.mode}"
source.mkdir(exist_ok=True)
(source / "README.txt").write_text("AGENTBOARD_SMOKE_OK\n", encoding="utf-8")
if args.mode == "implement":
    (source / "sample.txt").write_text("TODO\n", encoding="utf-8")
os.environ["AGENTBOARD_DATA_DIR"] = str(root / "data" / f"smoke-{args.agent}-{args.mode}")
os.environ["AGENTBOARD_WORKSPACES_DIR"] = str(Path.home() / f"AgentBoardSmokeWork-{args.agent}-{args.mode}")
spec = importlib.util.spec_from_file_location("live_board", root / "server.py")
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)
board.STATE = {"version": 1, "projects": [{"id": "smoke", "name": "Smoke",
    "path": str(source), "protected_paths": [], "context_files": [], "check": "none"}],
    "tasks": [], "runs": [], "budget": {}}
board.save()
description = ("Read README.txt and reply with its exact marker. Do not edit any file."
               if args.mode == "explore" else
               "Set sample.txt to exactly AGENTBOARD_EDIT_OK and a final newline. Do not change README.txt.")
task = board.create_task({"title": f"{args.agent} {args.mode} smoke", "description": description,
    "project_id": "smoke", "agent": args.agent, "mode": args.mode,
    "allowed_paths": ["sample.txt"] if args.mode == "implement" else [], "limit_minutes": 3,
    "fallback_to_deepseek": False})
run = board.start_task(task["id"])["run"]
while board.find_run(run["id"])["status"] in ("preparing", "running", "checking"):
    time.sleep(1)
record = board.find_run(run["id"])
if args.mode == "implement" and record["status"] == "review":
    board.accept_task(task["id"])
result_path = board.RUNS / run["id"] / "answer.txt"
print({"run_id": run["id"], "agent": record["agent"], "status": record["status"], "error": record["error"],
       "result": result_path.read_text(encoding="utf-8", errors="replace")[-500:] if result_path.exists() else "",
       "sample": (source / "sample.txt").read_text(encoding="utf-8") if (source / "sample.txt").exists() else None}, flush=True)
