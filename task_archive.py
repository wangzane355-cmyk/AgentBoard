"""Recoverable metadata deletion. Never delete source files, runs or mission records.

Call these functions under the board lock (and the mission-service lock when used).
Schedulers and live-action APIs must exclude deleted tasks and projects. Restoring
metadata does not re-enable automatic execution or reconnect a detached discussion.
"""
from __future__ import annotations

from pathlib import Path


ACTIVE_TASKS = {"queued", "preparing", "running", "checking"}
ACTIVE_RUNS = {"queued", "preparing", "running", "checking"}
ACTIVE_MISSIONS = {"queued", "preparing", "planning", "building", "checking", "reviewing", "repairing"}
KNOWN_MISSIONS = ACTIVE_MISSIONS | {"paused", "blocked", "review", "accepted", "cancelled", "rolled_back"}
ACTIVE_CHATS = {"queued", "preparing", "running"}


def _find(state, collection, record_id, label):
    record = next((record for record in state.get(collection, []) if record.get("id") == record_id), None)
    if record is None:
        raise ValueError(f"{label}不存在")
    return record


def _stamp(now):
    value = now() if callable(now) else now
    if not isinstance(value, str) or not value.strip():
        raise ValueError("删除和恢复记录缺少时间")
    return value


def _chat_running(chat):
    return chat.get("status") in ACTIVE_CHATS or (chat.get("batch") or {}).get("status") in ACTIVE_CHATS


def _task_running(state, task, mission):
    if task.get("status") in ACTIVE_TASKS:
        return True
    if any(run.get("task_id") == task["id"] and run.get("status") in ACTIVE_RUNS for run in state.get("runs", [])):
        return True
    if task.get("mission_id"):
        if not isinstance(mission, dict) or mission.get("phase") not in KNOWN_MISSIONS:
            raise ValueError("无法确认自主任务状态，请刷新后重试")
        if mission.get("id", task["mission_id"]) != task["mission_id"] or mission.get("task_id", task["id"]) != task["id"]:
            raise ValueError("自主任务记录不匹配")
    return bool(mission and mission.get("phase") in ACTIVE_MISSIONS)


def _dependency_error(blockers, subject):
    titles = [str(task.get("title") or task["id"])[:120] for task in blockers]
    shown = "、".join(titles[:10])
    if len(titles) > 10:
        shown += f"等{len(titles)}项任务"
    return ValueError(f"{subject}仍被这些任务依赖，先处理依赖后再删除：{shown}")


def archive_task(state, task_id, now, mission=None):
    """Hide one inactive card, preserving its records and all file changes."""
    task = _find(state, "tasks", task_id, "任务")
    if task.get("deleted_at"):
        return task
    if _task_running(state, task, mission):
        raise ValueError("任务正在运行或排队，请先停止或暂停后再删除")
    blockers = [other for other in state.get("tasks", [])
                if other.get("id") != task_id and not other.get("deleted_at") and task_id in other.get("depends_on", [])]
    if blockers:
        raise _dependency_error(blockers, "这张任务")
    chats = [chat for chat in state.get("chats", [])
             if chat.get("task_id") == task_id or task.get("discussion_id") and chat.get("id") == task["discussion_id"]]
    if any(_chat_running(chat) for chat in chats):
        raise ValueError("关联对话仍在回复，请等回复结束后再删除任务")
    stamp = _stamp(now)
    task.update(deleted_at=stamp, deleted_from_status=task.get("status", "ready"),
                deleted_auto_start=bool(task.get("auto_start")), auto_start=False, updated_at=stamp)
    for chat in chats:
        if chat.get("task_id") == task_id:
            chat.update(task_id="", detached_task_id=task_id,
                        consensus_needs_review=bool(chat.get("consensus")), updated_at=stamp)
    return task


def restore_task(state, task_id, now):
    """Restore a card without scheduling work or silently relinking a chat."""
    task = _find(state, "tasks", task_id, "任务")
    if not task.get("deleted_at"):
        return task
    project = _find(state, "projects", task.get("project_id"), "所属项目")
    if project.get("deleted_at"):
        raise ValueError("请先恢复这张任务所属的项目")
    stamp = _stamp(now)
    task.update(deleted_at=None, restored_at=stamp, auto_start=False, updated_at=stamp)
    return task


def archive_project(state, project_id, now, missions=()):
    """Hide a project and its views while retaining cards, conversations and files."""
    project = _find(state, "projects", project_id, "项目")
    if project.get("deleted_at"):
        return project
    missions = list(missions)
    if any(not isinstance(mission, dict) for mission in missions):
        raise ValueError("自主任务记录无效")
    tasks = [task for task in state.get("tasks", []) if task.get("project_id") == project_id]
    task_ids = {task["id"] for task in tasks}
    by_mission = {mission.get("id"): mission for mission in missions}
    if any(_task_running(state, task, by_mission.get(task.get("mission_id"))) for task in tasks):
        raise ValueError("项目还有运行中或排队的任务，请先停止或暂停后再删除")
    if any(mission.get("phase") in ACTIVE_MISSIONS and
           (mission.get("project_id") == project_id or mission.get("task_id") in task_ids)
           for mission in missions):
        raise ValueError("项目还有运行中或排队的自主任务，请先停止或暂停后再删除")
    if any(chat.get("project_id") == project_id and _chat_running(chat) for chat in state.get("chats", [])):
        raise ValueError("项目中的对话仍在回复，请等回复结束后再删除项目")
    blockers = [task for task in state.get("tasks", [])
                if task.get("project_id") != project_id and not task.get("deleted_at")
                and task_ids.intersection(task.get("depends_on", []))]
    if blockers:
        raise _dependency_error(blockers, "这个项目中的任务")
    stamp = _stamp(now)
    project.update(deleted_at=stamp, updated_at=stamp,
                   deleted_auto_start_tasks=[task["id"] for task in tasks if task.get("auto_start")])
    for task in tasks:
        task["auto_start"] = False
    return project


def restore_project(state, project_id, now):
    """Restore the project without reviving individually deleted cards or jobs."""
    project = _find(state, "projects", project_id, "项目")
    if not project.get("deleted_at"):
        return project
    path = Path(project["path"]).resolve()
    conflict = next((other for other in state.get("projects", [])
                     if other.get("id") != project_id and not other.get("deleted_at") and other.get("path")
                     and Path(other["path"]).resolve() == path), None)
    if conflict:
        raise ValueError(f"这个文件夹已由项目“{conflict.get('name') or conflict['id']}”使用，请先处理已有项目再恢复")
    stamp = _stamp(now)
    project.update(deleted_at=None, restored_at=stamp, updated_at=stamp)
    for task in state.get("tasks", []):
        if task.get("project_id") == project_id:
            task["auto_start"] = False
    return project
