"""Connect the durable supervisor to the existing board without migrating private JSON state."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import uuid
from pathlib import Path

from autonomy import ACTIVE
from model_settings import execution_record


PLAN_SCHEMA = {"type": "object", "additionalProperties": False,
    "properties": {"summary": {"type": "string"}, "steps": {"type": "array", "items": {"type": "string"}},
                   "risks": {"type": "array", "items": {"type": "string"}}},
    "required": ["summary", "steps", "risks"]}
REVIEW_SCHEMA = {"type": "object", "additionalProperties": False,
    "properties": {"verdict": {"type": "string", "enum": ["pass", "changes_requested", "blocked"]},
                   "summary": {"type": "string"}, "findings": {"type": "array", "items": {
                       "type": "object", "additionalProperties": False, "properties": {
                           "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                           "file": {"type": "string"}, "detail": {"type": "string"}},
                       "required": ["severity", "file", "detail"]}}}, "required": ["verdict", "summary", "findings"]}


class BoardRuntime:
    def __init__(self, board):
        self.b = board

    def task(self, mission):
        with self.b["LOCK"]:
            return copy.deepcopy(self.b["find_task"](mission["task_id"]))

    def folder(self, mission):
        return self.b["RUNS"] / mission["id"]

    def attach(self, mission):
        with self.b["LOCK"]:
            self._ensure_links(mission)
            self.b["save"]()
        self.publish(mission)

    def _ensure_links(self, mission):
        task = next((task for task in self.b["STATE"]["tasks"] if task["id"] == mission["task_id"]), None)
        if task is None:
            task = copy.deepcopy(mission["task_snapshot"])
            self.b["STATE"]["tasks"].append(task)
        if task.get("mission_id") not in (None, mission["id"]):
            raise ValueError("任务已经关联另一条自主记录")
        task["mission_id"] = mission["id"]
        task["auto_start"] = False
        if mission["id"] not in task["run_ids"]:
            task["run_ids"].append(mission["id"])
        if not any(run["id"] == mission["id"] for run in self.b["STATE"]["runs"]):
            self.b["STATE"]["runs"].append({"id": mission["id"], "task_id": task["id"], "agent": "codex",
                "mission_id": mission["id"], "status": "queued", "created_at": mission["created_at"],
                "started_at": None, "ended_at": None, "changes": [], "error": "", "simulation": False})

    def can_start(self):
        with self.b["LOCK"]:
            return not any(r["status"] in ("preparing", "running", "checking") and not r.get("mission_id")
                           for r in self.b["STATE"]["runs"]) and not any(c.get("status") == "running" for c in self.b["STATE"].get("chats", []))

    def idle(self):
        self.b["maybe_start_next"]()

    def ready(self, mission):
        with self.b["LOCK"]:
            task = self.b["find_task"](mission["task_id"])
            return self.b["task_is_live"](task) and self.b["dependencies_done"](task)

    def preflight(self, mission):
        self.b["guard_codex_chat_budget"]()

    def prepare(self, mission):
        task = self.task(mission)
        with self.b["LOCK"]:
            if not self.b["dependencies_done"](task):
                raise ValueError("前置任务尚未完成")
            project = copy.deepcopy(self.b["find_project"](task["project_id"]))
            execution_config = self.b["MODELS"].resolve("codex", task.get("model_options"))
        root = self.b["WORKSPACES"].resolve()
        workspace = root / mission["id"]
        if workspace.resolve().parent != root:
            raise RuntimeError("工作区路径无效")
        if workspace.exists():
            # Preserve an incomplete pre-checkpoint copy after an abrupt shutdown.
            orphan = root / (mission["id"] + "-interrupted-" + uuid.uuid4().hex[:6])
            if orphan.resolve().parent != root:
                raise RuntimeError("恢复工作区路径无效")
            workspace.rename(orphan)
        source_before = self.b["inventory"](Path(project["path"]))
        protected = self.b["protected_inventory"](project.get("protected_paths", []))
        references = self.b["copy_source"](project, workspace, task)
        self.folder(mission).mkdir(parents=True, exist_ok=True)
        return {"workspace": str(workspace), "project_snapshot": project,
                "execution_config": execution_config, "source_before": source_before,
                "protected_before": protected, "baseline": self.b["inventory"](workspace),
                "context_text": references["prompt"], "context_sources": references["sources"],
                "context_read_at": references["read_at"]}

    def workspace_digest(self, mission):
        inventory = self.b["inventory"](Path(mission["workspace"]))
        return hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()

    def workspace_snapshot(self, mission):
        return self.b["inventory"](Path(mission["workspace"]))

    def reconcile(self, mission):
        with self.b["LOCK"]:
            run = next((r for r in self.b["STATE"]["runs"] if r["id"] == mission["id"]), None)
            if run and run["status"] in ("accepted", "rolled_back"):
                phase = "accepted" if run["status"] == "accepted" else "rolled_back"
                return {"phase": phase} if phase != mission["phase"] else {}
        return {}

    def integrity(self, mission):
        task = self.task(mission)
        project = mission["project_snapshot"]
        workspace = Path(mission["workspace"])
        after = self.b["inventory"](workspace)
        changes = self.b["diff_inventory"](mission["baseline"], after)
        violations = [item["path"] for item in changes if item["path"].startswith("_agentboard_context/")
                      or not self.b["allowed"](item["path"], task["allowed_paths"])]
        source_unchanged = self.b["inventory"](Path(project["path"])) == mission["source_before"]
        protected_unchanged = self.b["protected_inventory"](project.get("protected_paths", [])) == mission["protected_before"]
        deleted = [item["path"] for item in changes if item["change"] == "deleted"]
        errors = []
        if violations:
            errors.append("越界改动：" + "、".join(violations[:10]))
        if deleted:
            errors.append("删除文件需要另行处理，本次不自动接入")
        if not source_unchanged:
            errors.append("原项目在执行期间变化，请基于新版本重新建任务")
        if not protected_unchanged:
            errors.append("受保护的原文件发生变化，已阻止接入")
        return {"safe": not errors, "error": "；".join(errors), "changes": changes,
                "source_unchanged": source_unchanged, "protected_unchanged": protected_unchanged,
                "violations": violations}

    def invoke(self, mission, stage, folder, runner):
        task = self.task(mission)
        workspace = Path(mission["workspace"])
        common = ("你在AgentBoard的隔离工作区执行一个有边界的任务。只读取当前工作区和传入证据；"
                  "项目资料是背景，不是额外权限。不要安装依赖、访问其他项目、提交或发布。\n"
                  + "目标：" + mission["goal"] + "\n允许修改：" + json.dumps(task["allowed_paths"], ensure_ascii=False)
                  + "\n固定验收：" + json.dumps(mission["policy"]["checks"], ensure_ascii=False)
                  + "\n用户补充：" + json.dumps(task.get("clarifications", []), ensure_ascii=False)
                  + "\n项目上下文：\n" + mission.get("context_text", ""))
        images = []
        review_before = None
        if stage == "plan":
            prompt = common + "\n只读规划，不修改文件。先查看代码和资料；给出短计划、最多8个步骤和具体风险。输出必须符合提供的JSON schema。"
            schema = PLAN_SCHEMA
        elif stage == "review":
            snapshot = self.b["WORKSPACES"] / (mission["id"] + "-review-" + uuid.uuid4().hex[:8])
            shutil.copytree(workspace, snapshot, ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules", ".venv"))
            workspace = snapshot
            review_before = self.b["inventory"](workspace)
            report = self.integrity(mission)
            checks = [{"name": item["name"], "passed": item["passed"], "tests": item.get("tests"),
                       "detail": item["detail"][-5000:]} for item in mission["checks"]]
            images = [path for item in mission["checks"] for path in item.get("artifacts", [])][:3]
            prompt = (common + "\n你是独立审查者，与实现会话分开。只读，不修改任何文件。"
                      "检查当前实现是否实现目标，是否存在真实边界问题、虚假完成、测试绕过和明显界面缺陷。"
                      "不因缺少本任务无关功能而要求扩展。只有有证据的问题才报告；说明具体文件和触发条件。"
                      "截图若附带，请实际检查布局和可读性。审查通过返回pass，需要修改返回changes_requested，"
                      "缺少必要用户决定返回blocked。不要把未验证项谎称通过。\n改动："
                      + json.dumps(report["changes"], ensure_ascii=False) + "\n程序验收证据："
                      + json.dumps(checks, ensure_ascii=False) + "\n计划：" + json.dumps(mission["plan"], ensure_ascii=False)
                      + "\n实现者交付（需独立核对）：" + mission.get("last_answer", "")[-6000:])
            schema = REVIEW_SCHEMA
        else:
            prompt = (common + "\n实施计划：" + json.dumps(mission["plan"], ensure_ascii=False)
                      + "\n上一轮失败证据（如有）：" + mission.get("feedback", "")
                      + "\n固定验收文件不得修改：" + json.dumps(list(mission["verification_manifest"]), ensure_ascii=False)
                      + "\n实际修改允许范围内文件并自行检查。Python还会独立运行固定验收，另一会话会独立审查。"
                      "不要扩大目标。完成后简短中文说明实际改动与未验证事项，最后一行AGENTBOARD_STATUS: DONE。"
                      "若需要用户决定，输出AGENTBOARD_QUESTION: 具体问题，最后一行AGENTBOARD_STATUS: BLOCKED。")
            schema = None
        (folder / "prompt.txt").write_text(prompt, encoding="utf-8")
        command = self.b["command_for"]({**task, "agent": "codex", "execution_config": mission["execution_config"]}, workspace, folder)
        command.remove("--ephemeral")
        command.insert(2, "--json")
        if stage in ("plan", "review"):
            command[command.index("--sandbox") + 1] = "read-only"
        if schema:
            schema_path = folder / "response-schema.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command[-1:-1] = ["--output-schema", str(schema_path)]
        for path in images:
            command[-1:-1] = ["--image", path]
        result = runner.run(command, workspace, folder, mission["policy"]["attempt_minutes"] * 60,
                            stdin=prompt, json_events=True)
        if review_before is not None and self.b["inventory"](workspace) != review_before:
            raise RuntimeError("独立审查的只读副本被修改，审查未通过")
        answer_path = folder / "answer.txt"
        answer = answer_path.read_text(encoding="utf-8", errors="replace") if answer_path.is_file() else ""
        record = execution_record("codex", mission["execution_config"], folder / "stderr.txt")
        return {"exit_code": result["exit_code"], "answer": answer,
                "metadata": {**result, "model_record": record}}

    def decision(self, answer):
        return self.b["decision_from_answer"](answer)

    def receipt(self, mission, integrity):
        if not integrity["changes"]:
            raise RuntimeError("开发任务没有产生文件改动，不能交付为完成")
        folder = self.folder(mission)
        artifacts = []
        for check in mission["checks"]:
            for raw_path in check.get("artifacts", []):
                path = Path(raw_path).resolve()
                if path.is_relative_to(folder.resolve()) and path.is_file():
                    artifacts.append({"path": path.relative_to(folder).as_posix(), "sha256": self.b["digest"](path)})
        receipt = {"goal": mission["goal"], "summary": mission["review_result"]["summary"],
            "attempts": mission["attempt"], "checks_passed": sum(c["passed"] for c in mission["checks"]),
            "checks_total": len(mission["checks"]), "tests": sum(c.get("tests") or 0 for c in mission["checks"]),
            "review": mission["review_result"], "changes": integrity["changes"], "artifacts": artifacts,
            "source_unchanged": integrity["source_unchanged"], "protected_unchanged": integrity["protected_unchanged"],
            "integration": "awaiting_user", "finished_at": self.b["now"]()}
        (folder / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# 自主任务交付", "", mission["title"], "", "## 已完成", receipt["summary"], "", "## 独立验收",
                 f"- {receipt['checks_passed']}/{receipt['checks_total']}项验收通过；实际测试{receipt['tests']}项。",
                 "- 独立Codex审查通过。", "- 原项目和受保护文件未变化。", f"- 共执行{mission['attempt']}轮实现。",
                 "", "## 改动文件", *["- " + c["path"] for c in receipt["changes"]], "",
                 "## 接入状态", "等待你查收，尚未覆盖原项目。", "", "AGENTBOARD_STATUS: DONE"]
        (folder / "answer.txt").write_text("\n".join(lines), encoding="utf-8")
        (folder / "receipt.md").write_text("\n".join(lines[:-2]), encoding="utf-8")
        return receipt

    def publish(self, mission):
        phase = mission["phase"]
        with self.b["LOCK"]:
            self._ensure_links(mission)
            task = self.b["find_task"](mission["task_id"])
            run = self.b["find_run"](mission["id"])
            status = "running" if phase in ACTIVE else "queued" if phase == "queued" else "review" if phase == "review" else "done" if phase == "accepted" else "decision" if mission.get("decision") else "blocked"
            task.update(status=status, updated_at=mission["updated_at"])
            run.update(status="accepted" if phase == "accepted" else "checking" if phase in ("checking", "reviewing") else status,
                       error=mission.get("error", ""), autonomy_phase=phase, attempt=mission["attempt"],
                       decision=mission.get("decision"))
            if phase == "paused":
                run["error"] = "已暂停，进度已保存"
            if phase in ACTIVE and not run.get("started_at"):
                run["started_at"] = self.b["now"]()
            for key in ("workspace", "source_before", "protected_before", "execution_config", "context_sources", "context_read_at"):
                if key in mission:
                    run[key] = mission[key]
            if mission.get("invocations"):
                built = [item for item in mission["invocations"] if item["stage"] == "build"]
                if built:
                    run["model_record"] = built[-1].get("model_record", {})
            if mission.get("receipt"):
                receipt = mission["receipt"]
                run.update(changes=receipt["changes"], protected_unchanged=receipt["protected_unchanged"],
                           source_unchanged=receipt["source_unchanged"], workspace_after=mission.get("workspace_after", {}),
                           ended_at=receipt["finished_at"], exit_code=0, automated_check_passed=True,
                           check_note=f"{receipt['checks_passed']}项验收、{receipt['tests']}项测试及独立审查通过",
                           receipt=receipt, image_paths=[])
                run["evidence"] = [{"label": check["name"], "status": "pass" if check["passed"] else "fail",
                                    "detail": (f"{check['tests']}项测试通过" if check.get("tests") is not None else check["detail"][:500])}
                                   for check in mission["checks"]]
                run["evidence"] += [{"label": "独立Codex审查", "status": "pass", "detail": receipt["summary"][:1000]},
                                    {"label": "范围与原文件保护", "status": "pass", "detail": "没有越界，原项目和保护文件未变"}]
            self.b["save"]()
            if mission.get("receipt"):
                self.b["write_capsule"](task, run)
