"""Read-only sample workspace. No credentials or model calls. Defaults to port 8766."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
os.environ["AGENTBOARD_DATA_DIR"] = str(root / "data" / "demo")
os.environ["AGENTBOARD_WORKSPACES_DIR"] = str(root / "data" / "demo" / "workspaces")
os.environ["AGENTBOARD_TEST_MODE"] = "1"
os.environ["AGENTBOARD_DEMO_MODE"] = "1"
import server as board


def seed_demo():
    source = board.DATA / "sample-project"
    source.mkdir(parents=True, exist_ok=True)
    (source / "README.md").write_text("# Atlas Notebook\nIllustrative demo data. No real project or agent execution.\n", encoding="utf-8")
    timestamp = board.now()
    project = {"id": "atlas-demo", "name": "Atlas Notebook · DEMO", "path": str(source),
               "protected_paths": [], "context_files": [], "context_urls": [], "check": "none"}
    tasks = []
    for key, title, description, status, agent in [
        ("plan", "Define the import workflow", "Clarify input formats, validation rules and user feedback before implementation.", "ready", "codex"),
        ("search", "Build the local search panel", "Implement keyboard navigation and an empty state in an isolated workspace.", "running", "deepseek"),
        ("decision", "Choose the sync strategy", "Compare manual export with scheduled sync. The user chooses the scope.", "decision", "codex"),
        ("review", "Review keyboard shortcuts", "Inspect the proposed changes and the sample delivery notes before integration.", "review", "deepseek"),
        ("done", "Document the project boundaries", "Keep scope, acceptance rules and handoff notes in one shared reference.", "done", "codex"),
    ]:
        tasks.append({"id": "demo-" + key, "project_id": project["id"], "title": title,
                      "description": description + "\n[Illustrative sample — not a real run]", "agent": agent,
                      "mode": "explore", "status": status, "allowed_paths": [], "depends_on": [],
                      "auto_start": False, "assertions": [], "limit_minutes": 25, "run_ids": [],
                      "created_at": timestamp, "updated_at": timestamp})
    chat = {"id": "demo-room", "project_id": project["id"], "title": "Plan → build → review",
            "mode": "group", "members": ["deepseek", "codex"], "agent": "codex", "status": "idle",
            "include_source": False, "task_id": "", "consensus": "Start with local search. Keep sync as a separate decision.",
            "created_at": timestamp, "updated_at": timestamp, "error": "",
            "messages": [
                {"role": "user", "text": "Help me split the next milestone into clear, reviewable tasks.", "audience": ["deepseek", "codex"], "created_at": timestamp},
                {"role": "assistant", "agent": "codex", "text": "Start with the local search workflow.\n\n1. Define keyboard navigation and acceptance criteria.\n2. Implement in an isolated copy.\n3. Collect checks and review the changes before integration.\n\nDeepSeek, can you identify the smallest useful implementation?", "handoff_to": "deepseek", "created_at": timestamp},
                {"role": "assistant", "agent": "deepseek", "text": "A focused first task can cover the search field, results list and empty state.\n\nAllowed scope: the search UI folder.\nChecks: syntax validation, keyboard navigation and no changes to user notes.\n\nI would keep synchronization out of this task so its boundaries stay clear.", "created_at": timestamp},
                {"role": "assistant", "agent": "codex", "text": "Agreed. Keep synchronization as a decision card.\n\nSave this scope as the current consensus, then create the implementation card with explicit checks.\n\nThis is an illustrative conversation; no model was called to produce this demo.", "created_at": timestamp},
            ]}
    board.STATE = {"version": 1, "projects": [project], "tasks": tasks, "runs": [], "chats": [chat],
                   "budget": {"codex_5h_remaining": None, "observed_at": None}}
    policy = {"max_attempts": 3, "total_minutes": 90, "attempt_minutes": 25, "auto_resume": True,
              "checks": [{"kind": "python_unittest", "name": "Fixed acceptance tests"}]}
    missions = []
    for key, title, goal, phase, attempt in [
        ("search", "Build a calmer search experience", "Support fast local search, clear empty states and reliable keyboard navigation.", "building", 1),
        ("import", "Make note imports dependable", "Validate imported notes, preserve original files and explain unsupported formats.", "review", 2),
        ("export", "Export a clean reading copy", "Create a readable export with stable headings and useful error messages.", "paused", 0),
    ]:
        mission = {"id": "demo-delivery-" + key, "task_id": "demo-review", "project_id": project["id"],
            "title": title, "goal": goal + " [SAMPLE — no model or tests were run]", "phase": phase,
            "attempt": attempt, "policy": policy, "spent_seconds": 276 if phase == "review" else 95 if phase == "building" else 0,
            "next_phase": "review" if phase == "review" else "build", "created_at": timestamp, "updated_at": timestamp,
            "stage_started_at": None, "error": "", "history": [], "invocations": [],
            "plan": {"summary": "An illustrative plan with a focused scope and fixed checks.",
                     "steps": ["Read the project context and acceptance tests", "Implement the smallest complete change", "Run fixed tests and independently review the result"], "risks": []} if attempt else None,
            "checks": [{"id": "check-1", "kind": "python_unittest", "name": "Fixed acceptance tests", "passed": True,
                        "tests": 12, "detail": "ILLUSTRATIVE SAMPLE: twelve passing tests. No real test process was run."}] if phase == "review" else [],
            "review_result": {"verdict": "pass", "summary": "Sample review: input validation and original-file protection are covered.", "findings": []} if phase == "review" else None,
            "receipt": {"summary": "Illustrative delivery: note imports now validate inputs and preserve original files. This is sample data, not a real execution.",
                        "tests": 12, "attempts": 2, "changes": [{"path": "src/importer.py", "change": "modified"}],
                        "artifacts": [], "checks_passed": 1, "checks_total": 1} if phase == "review" else None,
            "demo": True}
        missions.append(mission)
    board.STATE["autonomy_demo"] = missions
    board.save()


if __name__ == "__main__":
    seed_demo()
    if "--port" not in sys.argv:
        sys.argv.extend(["--port", "8766"])
    board.main()
