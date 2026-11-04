"""Durable, bounded plan/build/test/review/repair orchestration.

The runtime adapter owns project copies and Codex invocation. This module owns
the state machine. A model cannot change its checks, permissions or retry budget.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from autonomy_store import MissionStore, utc_now
from supervised_process import ProcessRunner, WorkInterrupted, process_stamp, process_exists, same_process, terminate_record
from verification import validate_checks, verification_files, verification_unchanged, run_verification


ACTIVE = {"preparing", "planning", "building", "checking", "reviewing", "repairing"}
FINISHED = {"review", "accepted", "cancelled"}
PHASE_LABELS = {"queued": "等待开始", "preparing": "准备工作区", "planning": "制定计划",
                "building": "实现目标", "checking": "程序验收", "reviewing": "独立审查",
                "repairing": "根据问题返工", "paused": "已暂停", "blocked": "需要处理",
                "review": "交付待查收", "accepted": "已接入", "cancelled": "已停止"}


def validate_policy(body):
    if not isinstance(body, dict):
        raise ValueError("自主执行设置须是对象")
    def integer(key, default):
        raw = body.get(key, default)
        try:
            if isinstance(raw, bool) or isinstance(raw, float) and not raw.is_integer():
                raise ValueError()
            return int(raw)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("执行轮数和时限须是整数") from None
    if not isinstance(body.get("auto_resume", True), bool):
        raise ValueError("自动恢复设置须为布尔值")
    policy = {"max_attempts": integer("max_attempts", 3),
              "total_minutes": integer("total_minutes", 90),
              "attempt_minutes": integer("attempt_minutes", 25),
              "stall_minutes": integer("stall_minutes", 5),
              "auto_resume": body.get("auto_resume", True),
              "checks": validate_checks(body.get("checks")),
              "protected_files": body.get("protected_files", [])}
    if not 1 <= policy["max_attempts"] <= 6 or not 1 <= policy["total_minutes"] <= 720:
        raise ValueError("最多1至6轮，累计时限1至720分钟")
    if not 1 <= policy["attempt_minutes"] <= 25 or not 1 <= policy["stall_minutes"] <= 25:
        raise ValueError("单次执行和无活动时限须为1至25分钟")
    from verification import relative_path
    if not isinstance(policy["protected_files"], list) or len(policy["protected_files"]) > 100:
        raise ValueError("验收保护文件列表无效")
    policy["protected_files"] = [relative_path(path) for path in policy["protected_files"]]
    return policy


def parse_plan(answer):
    data = json.loads(answer)
    steps = data.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 8 or any(not isinstance(s, str) or not s.strip() for s in steps):
        raise ValueError("规划结果缺少可执行步骤")
    if not isinstance(data.get("summary"), str) or not data["summary"].strip() or not isinstance(data.get("risks", []), list):
        raise ValueError("规划摘要或风险格式无效")
    return {"summary": data["summary"][:3000], "steps": [s[:1000] for s in steps],
            "risks": [str(s)[:1000] for s in data.get("risks", [])][:8]}


def parse_review(answer):
    data = json.loads(answer)
    if data.get("verdict") not in ("pass", "changes_requested", "blocked") or not isinstance(data.get("findings"), list):
        raise ValueError("审查结果格式无效")
    if not isinstance(data.get("summary"), str) or not data["summary"].strip():
        raise ValueError("审查缺少可核对的结论")
    findings = []
    for item in data["findings"][:12]:
        if not isinstance(item, dict) or item.get("severity") not in ("high", "medium", "low") or not str(item.get("detail", "")).strip():
            raise ValueError("审查问题缺少有效说明")
        findings.append({"severity": item["severity"], "file": str(item.get("file", ""))[:400],
                         "detail": str(item["detail"])[:3000]})
    verdict = data["verdict"]
    if verdict == "pass" and any(item["severity"] in ("high", "medium") for item in findings):
        verdict = "changes_requested"
    return {"verdict": verdict, "summary": str(data.get("summary", ""))[:5000], "findings": findings}


class AutonomyService:
    def __init__(self, data, runtime, max_workers=1, runner_factory=ProcessRunner):
        self.store = MissionStore(data)
        self.runtime = runtime
        self.runner_factory = runner_factory
        self.max_workers = min(2, max(1, int(max_workers)))
        self.owner = {"token": uuid.uuid4().hex, "pid": os.getpid(), "stamp": process_stamp(os.getpid())}
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.lock = threading.RLock()
        self.futures = {}
        self.heartbeat_times = {}
        self.thread = None
        self.pool = None
        self.error = ""

    def create(self, task, policy, auto_start=False):
        mission_id = uuid.uuid4().hex[:12]
        mission = self.store.create({"id": mission_id, "task_id": task["id"], "project_id": task["project_id"],
            "task_snapshot": task,
            "title": task["title"], "goal": task["description"], "phase": "queued" if auto_start else "paused",
            "control": "run" if auto_start else "pause", "policy": validate_policy(policy),
            "attempt": 0, "spent_seconds": 0, "next_phase": "build", "history": [], "checks": [],
            "active_processes": [], "error": "", "resume_phase": "preparing", "feedback": "",
            "progress": {}, "invocations": [], "plan": None, "review_result": None})
        self.runtime.attach(mission)
        self.wake.set()
        return mission

    def notify(self, mission):
        self.runtime.publish(mission)
        return mission

    def change(self, mission_id, patch, kind, message, detail=None):
        return self.notify(self.store.update(mission_id, patch, kind, message, detail))

    def action(self, mission_id, action):
        with self.lock:
            mission = self.store.get(mission_id)
            if action == "pause":
                if mission["phase"] in FINISHED:
                    raise ValueError("任务已经结束")
                patch = {"control": "pause"}
                if mission["phase"] == "queued":
                    patch["phase"] = "paused"
                message = "已请求暂停，正在保存当前进度"
            elif action == "stop":
                if mission["phase"] in ("accepted", "cancelled"):
                    raise ValueError("任务已经结束")
                patch = {"control": "stop"}
                if mission["phase"] not in ACTIVE:
                    patch["phase"] = "cancelled"
                message = "已请求停止，不再安排下一轮"
            elif action == "recheck":
                if mission["phase"] != "review":
                    raise ValueError("只有待查收的交付可以重新验收")
                previous = mission.get("previous_deliveries", []) + [{"receipt": mission.get("receipt"), "checks": mission["checks"]}]
                patch = {"phase": "queued", "control": "run", "next_phase": "check", "error": "",
                         "receipt": None, "review_result": None, "checks": [], "previous_deliveries": previous[-6:]}
                message = "已安排重新验收和独立审查，不重复已经完成的实现"
            elif action == "resume":
                if mission["phase"] not in ("paused", "blocked"):
                    raise ValueError("只有暂停或阻塞的任务可以继续")
                if mission.get("fatal"):
                    raise ValueError("范围、源文件或验收保护已触发，请基于当前源项目新建任务")
                if mission["attempt"] >= mission["policy"]["max_attempts"] and mission["next_phase"] == "build":
                    raise ValueError("执行次数已用尽，请调整目标后新建任务")
                patch = {"phase": "queued", "control": "run", "error": "", "decision": None}
                message = "已加入队列，将从保存的检查点继续"
            else:
                raise ValueError("无效的自主任务操作")
            result = self.change(mission_id, patch, action, message)
            self.wake.set()
            return result

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.store.claim_owner(self.owner, same_process)
        self._recover()
        self.pool = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="agentboard-mission")
        self.thread = threading.Thread(target=self._loop, daemon=True, name="agentboard-supervisor")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=10)
        if self.pool:
            self.pool.shutdown(wait=True)
        self.store.release_owner(self.owner["token"])

    def _recover(self):
        for mission in self.store.all():
            reconciliation = getattr(self.runtime, "reconcile", lambda m: {})(mission)
            if reconciliation:
                mission = self.store.update(mission["id"], reconciliation, "reconciled", "已核对实际接入状态")
            if mission["phase"] not in ACTIVE:
                self.runtime.publish(mission)
                continue
            unsafe = False
            for record in mission.get("active_processes", []):
                current = process_stamp(record["pid"])
                if not record.get("stamp"):
                    unsafe |= process_exists(record["pid"])
                    continue
                if current is None:
                    unsafe |= process_exists(record["pid"])
                    continue
                if current != record.get("stamp"):
                    # PID was reused. The recorded process is gone; never touch its replacement.
                    continue
                if not record.get("stamp") or not terminate_record(record):
                    unsafe = True
            last = mission.get("heartbeat_at") or mission.get("stage_started_at")
            elapsed = 0
            if last and mission.get("stage_started_at"):
                from datetime import datetime
                elapsed = max(0, (datetime.fromisoformat(last) - datetime.fromisoformat(mission["stage_started_at"])).total_seconds())
            auto = mission["policy"]["auto_resume"] and mission.get("control") == "run" and not unsafe
            self.change(mission["id"], {"phase": "queued" if auto else "paused", "active_processes": [],
                "spent_seconds": mission["spent_seconds"] + elapsed, "stage_started_at": None,
                "error": "无法核对旧执行器身份，请检查后新建任务" if unsafe else "" if auto else "上次执行已保存，请确认后继续",
                "fatal": bool(unsafe or mission.get("fatal")), "recovered": True},
                "recovered", "已核对进程身份并恢复检查点" if auto else "已恢复记录，等待继续")

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                idle = False
                with self.lock:
                    self.futures = {key: future for key, future in self.futures.items() if not future.done()}
                    if len(self.futures) < self.max_workers and self.runtime.can_start():
                        queued = [m for m in self.store.all() if m["phase"] == "queued" and m["control"] == "run"]
                        for mission in sorted(queued, key=lambda m: m["created_at"]):
                            if len(self.futures) >= self.max_workers:
                                break
                            if mission["id"] in self.futures or not getattr(self.runtime, "ready", lambda m: True)(mission):
                                continue
                            claimed = self.store.update(mission["id"], {"phase": "preparing"}, "claimed", "任务监督器已领取", revision=mission["revision"])
                            try:
                                self.runtime.publish(claimed)
                                self.futures[mission["id"]] = self.pool.submit(self.execute, mission["id"])
                            except Exception as exc:
                                self.store.update(mission["id"], {"phase": "blocked", "error": str(exc)}, "blocked", "无法启动执行，请检查本机记录")
                                raise
                    idle = not self.futures
                if idle:
                    getattr(self.runtime, "idle", lambda: None)()
            except Exception as exc:
                self.error = str(exc)[:500]
            self.wake.wait(1)
            self.wake.clear()

    def _control(self, mission_id):
        if self.stop_event.is_set():
            return "shutdown"
        mission = self.store.get(mission_id)
        if mission["control"] != "run":
            return mission["control"]
        elapsed = 0
        if mission.get("stage_started_at"):
            from datetime import datetime, timezone
            elapsed = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(mission["stage_started_at"])).total_seconds())
        if mission["spent_seconds"] + elapsed >= mission["policy"]["total_minutes"] * 60:
            return "budget"
        if time.monotonic() - self.heartbeat_times.get(mission_id, 0) > 3:
            self.store.update(mission_id, {"heartbeat_at": utc_now()})
            self.heartbeat_times[mission_id] = time.monotonic()
        return None

    def _phase(self, mission_id, phase, message):
        reason = self._control(mission_id)
        if reason:
            raise WorkInterrupted(reason)
        return self.change(mission_id, {"phase": phase, "stage_started_at": utc_now(), "heartbeat_at": utc_now(),
                                      "progress": {}, "error": ""}, phase, message)

    def _finish_stage(self, mission_id):
        mission = self.store.get(mission_id)
        elapsed = 0
        if mission.get("stage_started_at"):
            from datetime import datetime, timezone
            elapsed = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(mission["stage_started_at"])).total_seconds())
        self.store.update(mission_id, {"spent_seconds": mission["spent_seconds"] + elapsed, "stage_started_at": None})

    def _integrity(self, mission):
        report = self.runtime.integrity(mission)
        if not report["safe"]:
            self.change(mission["id"], {"fatal": True}, "guard", "文件范围或原项目保护已触发", report)
            raise RuntimeError(report["error"])
        if not verification_unchanged(mission["workspace"], mission.get("verification_manifest", {})):
            self.change(mission["id"], {"fatal": True}, "guard", "验收文件被修改，拒绝判定成功")
            raise RuntimeError("固定验收文件已变化，请保留证据并新建任务")
        return report

    def _invoke(self, mission_id, stage, runner):
        mission = self.store.get(mission_id)
        self.runtime.preflight(mission)
        number = len(mission.get("invocations", [])) + 1
        folder = self.runtime.folder(mission) / f"{number:02d}-{stage}-{uuid.uuid4().hex[:6]}"
        folder.mkdir(parents=True, exist_ok=True)
        self.store.update(mission_id, {"current_invocation": {"stage": stage, "folder": str(folder)}})
        invocation = self.runtime.invoke(mission, stage, folder, runner)
        latest = self.store.get(mission_id)
        self.store.update(mission_id, {"invocations": latest["invocations"] + [{"stage": stage, "folder": str(folder), **invocation.get("metadata", {})}]})
        if invocation.get("exit_code") != 0:
            raise RuntimeError("Codex执行未成功；诊断已保留，请查看本轮记录")
        return invocation["answer"]

    def _retry(self, mission_id, reason, detail):
        mission = self.store.get(mission_id)
        digest = self.runtime.workspace_digest(mission)
        stable_detail = re.sub(r"(in |elapsed[^\d]*)(\d+(?:\.\d+)?)(s| seconds)", r"\1<duration>\3",
                               json.dumps(detail, sort_keys=True, ensure_ascii=False))
        signature = hashlib.sha256((reason + stable_detail).encode()).hexdigest()
        history = mission["history"] + [{"attempt": mission["attempt"], "reason": reason,
                                         "digest": digest, "signature": signature, "at": utc_now()}]
        no_progress = len(history) >= 2 and history[-1]["digest"] == history[-2]["digest"] and history[-1]["signature"] == history[-2]["signature"]
        limit = mission["attempt"] >= mission["policy"]["max_attempts"]
        feedback = json.dumps({"reason": reason, "evidence": detail}, ensure_ascii=False)[-20000:]
        self.change(mission_id, {"history": history, "feedback": feedback, "next_phase": "build", "review_result": None},
                    "finding", "本轮未通过，问题已整理成返工要求", {"reason": reason, "attempt": mission["attempt"]})
        if no_progress:
            raise RuntimeError("连续两轮没有有效进展，已停止重复尝试")
        if limit:
            raise RuntimeError("已达到最大返工轮数；保留结果等待调整目标")
        self._phase(mission_id, "repairing", "正在携带失败证据安排下一轮修复")
        for _ in range(min(mission["attempt"], 3)):
            if self._control(mission_id):
                raise WorkInterrupted(self._control(mission_id))
            time.sleep(1)
        self._finish_stage(mission_id)

    def execute(self, mission_id):
        runner = self.runner_factory(lambda: self._control(mission_id),
            lambda records: self.store.update(mission_id, {"active_processes": records}),
            lambda event: self.store.update(mission_id, {"progress": event, "heartbeat_at": utc_now()}),
            stall_seconds=self.store.get(mission_id)["policy"]["stall_minutes"] * 60)
        try:
            mission = self.store.get(mission_id)
            if not mission.get("workspace"):
                self._phase(mission_id, "preparing", "正在复制项目并固定验收标准")
                prepared = self.runtime.prepare(mission)
                manifest = verification_files(prepared["workspace"], mission["policy"]["checks"], mission["policy"]["protected_files"])
                if any(c["kind"] == "python_unittest" for c in mission["policy"]["checks"]) and not manifest:
                    raise ValueError("没有找到固定的Python验收文件；请先补充测试或选择网页验收")
                self.store.update(mission_id, {**prepared, "verification_manifest": manifest})
                self._finish_stage(mission_id)
            mission = self.store.get(mission_id)
            self._integrity(mission)
            if not mission["plan"]:
                self._phase(mission_id, "planning", "Codex正在阅读项目并制定实施计划")
                before = self.runtime.workspace_digest(self.store.get(mission_id))
                plan = parse_plan(self._invoke(mission_id, "plan", runner))
                current = self.store.get(mission_id)
                if self.runtime.workspace_digest(current) != before:
                    self.change(mission_id, {"fatal": True}, "guard", "只读规划阶段修改了文件")
                    raise RuntimeError("规划阶段发生文件改动，已停止")
                self.store.update(mission_id, {"plan": plan})
                self._finish_stage(mission_id)
            while True:
                runner.checkpoint()
                mission = self.store.get(mission_id)
                self._integrity(mission)
                if mission["next_phase"] == "build":
                    if mission["attempt"] >= mission["policy"]["max_attempts"]:
                        raise RuntimeError("执行次数已用尽")
                    self.store.update(mission_id, {"attempt": mission["attempt"] + 1})
                    self._phase(mission_id, "building", f"Codex开始第{mission['attempt'] + 1}轮实现")
                    answer = self._invoke(mission_id, "build", runner)
                    self.store.update(mission_id, {"last_answer": answer[:50000], "next_phase": "check"})
                    self._finish_stage(mission_id)
                    question = self.runtime.decision(answer)
                    if question:
                        self.change(mission_id, {"decision": question, "next_phase": "build"}, "decision", question["question"])
                        raise RuntimeError("需要你决定一个具体问题，已保存进度")
                    if not answer.strip() or answer.strip().splitlines()[-1].strip() != "AGENTBOARD_STATUS: DONE":
                        self._retry(mission_id, "执行者未确认完成", {"answer": answer[-4000:]})
                        continue
                mission = self.store.get(mission_id)
                if mission["next_phase"] == "check":
                    self._phase(mission_id, "checking", "Python正在独立运行固定验收")
                    self._integrity(self.store.get(mission_id))
                    checks = run_verification(mission["policy"]["checks"], mission["workspace"],
                                              self.runtime.folder(mission) / f"checks-{mission['attempt']:02d}-{uuid.uuid4().hex[:6]}", runner)
                    self._integrity(self.store.get(mission_id))
                    self.store.update(mission_id, {"checks": checks, "next_phase": "review",
                                                   "checked_digest": self.runtime.workspace_digest(mission)})
                    self._finish_stage(mission_id)
                    failures = [{"name": c["name"], "detail": c["detail"]} for c in checks if not c["passed"]]
                    if failures:
                        self._retry(mission_id, "固定验收未通过", failures)
                        continue
                mission = self.store.get(mission_id)
                if mission.get("checked_digest") != self.runtime.workspace_digest(mission):
                    self.change(mission_id, {"next_phase": "check"}, "changed", "工作区有新变化，重新执行验收")
                    continue
                self._phase(mission_id, "reviewing", "另一Codex会话正在独立审查改动与证据")
                before = self.runtime.workspace_digest(mission)
                review = parse_review(self._invoke(mission_id, "review", runner))
                self._integrity(self.store.get(mission_id))
                if self.runtime.workspace_digest(mission) != before:
                    self.change(mission_id, {"fatal": True}, "guard", "审查期间工作区发生变化")
                    raise RuntimeError("审查阶段文件发生变化，拒绝接入")
                self.store.update(mission_id, {"review_result": review})
                self._finish_stage(mission_id)
                if review["verdict"] == "blocked":
                    raise RuntimeError("独立审查需要人工处理：" + review["summary"][:1000])
                if review["verdict"] != "pass":
                    self._retry(mission_id, "独立审查要求修复", review)
                    continue
                runner.checkpoint()
                final = self.store.get(mission_id)
                report = self._integrity(final)
                receipt = self.runtime.receipt(final, report)
                snapshot = getattr(self.runtime, "workspace_snapshot", lambda m: None)(final)
                self.change(mission_id, {"phase": "review", "error": "", "finished_at": utc_now(),
                    "receipt": receipt, "workspace_after": snapshot, "active_processes": [], "progress": {}, "stage_started_at": None},
                    "delivered", "固定验收与独立审查均通过，成果等待查收")
                break
        except WorkInterrupted as exc:
            self._finish_stage(mission_id)
            mission = self.store.get(mission_id)
            reason = str(exc)
            if reason == "shutdown":
                phase = "queued" if mission["policy"]["auto_resume"] and mission["control"] == "run" else "paused"
                message = "服务关闭前已保存进度"
            elif reason == "stop":
                phase, message = "cancelled", "任务已停止，没有安排后续尝试"
            elif reason == "budget":
                phase, message = "blocked", "已达到任务累计时限，进度已保存"
            else:
                phase, message = "paused", "已暂停并保存当前进度"
            self.change(mission_id, {"phase": phase, "error": "" if phase == "paused" else message,
                "active_processes": [], "stage_started_at": None}, "checkpoint", message)
        except Exception as exc:
            self._finish_stage(mission_id)
            self.change(mission_id, {"phase": "blocked", "error": str(exc)[:3000], "active_processes": [],
                                     "stage_started_at": None}, "blocked", str(exc)[:2000])
        finally:
            runner.close()
            self.wake.set()

    def status(self):
        with self.lock:
            active = len([f for f in list(self.futures.values()) if not f.done()])
        return {"running": bool(self.thread and self.thread.is_alive()), "error": self.error,
                "max_workers": self.max_workers, "active": active,
                "missions": [public_mission(mission, summary=True) for mission in self.store.all()[:100]]}


def public_mission(mission, summary=False):
    hidden = {"source_before", "protected_before", "baseline", "verification_manifest", "active_processes",
              "context_text", "project_snapshot", "task_snapshot", "workspace_after"}
    data = {key: value for key, value in mission.items() if key not in hidden}
    if summary:
        data.pop("last_answer", None)
        data.pop("feedback", None)
        data["checks"] = [{key: check.get(key) for key in ("id", "name", "kind", "passed", "tests")} for check in mission["checks"]]
    return data
