"""Bounded subprocesses, fresh process identity, cancellation and real JSONL progress."""
from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path


class WorkInterrupted(RuntimeError):
    pass


def process_stamp(pid):
    try:
        if os.name == "nt":
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return None
            try:
                code = wintypes.DWORD()
                if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
                    return None
                times = [wintypes.FILETIME() for _ in range(4)]
                if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                    return None
                return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
            finally:
                kernel.CloseHandle(handle)
        text = Path(f"/proc/{int(pid)}/stat").read_text()
        fields = text[text.rfind(")") + 2:].split()
        return fields[19] if fields[0] != "Z" else None
    except (OSError, ValueError, IndexError):
        return None


def same_process(record):
    return bool(record.get("stamp") and process_stamp(record["pid"]) == record["stamp"])


def process_exists(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def terminate_record(record):
    """Only touch a process created by this runner and still matching its identity."""
    if not same_process(record):
        return False
    if os.name == "nt":
        result = subprocess.run(["taskkill", "/PID", str(record["pid"]), "/T", "/F"],
                       capture_output=True, timeout=15, check=False,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode != 0:
            return not same_process(record)
    else:
        try:
            os.killpg(record["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 5
    while same_process(record) and time.monotonic() < deadline:
        time.sleep(0.1)
    return not same_process(record)


def clean_environment():
    # CLI authentication remains in its normal home. Do not inherit unrelated API secrets.
    return {k: v for k, v in os.environ.items()
            if not any(marker in k.upper() for marker in ("API_KEY", "PASSWORD", "ACCESS_TOKEN", "SECRET"))}


class ProcessRunner:
    def __init__(self, control, processes, progress=lambda event: None, stall_seconds=300):
        self.control = control
        self.processes = processes
        self.progress = progress
        self.stall_seconds = stall_seconds
        self.active = {}

    def start(self, argv, cwd, folder, stdin=None, extra_env=None):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        out = (folder / "stdout.txt").open("wb")
        err = (folder / "stderr.txt").open("wb")
        try:
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                       stdout=out, stderr=err, env={**clean_environment(), "PYTHONUTF8": "1", **(extra_env or {})},
                                       creationflags=flags, start_new_session=os.name != "nt")
        finally:
            out.close()
            err.close()
        record = {"pid": process.pid, "stamp": process_stamp(process.pid), "cwd": str(cwd)}
        self.active[process.pid] = (process, record)
        self.processes([record for _, record in self.active.values()])
        if stdin is not None:
            def write_input():
                try:
                    process.stdin.write(stdin.encode("utf-8"))
                    process.stdin.close()
                except (OSError, BrokenPipeError):
                    pass
            threading.Thread(target=write_input, daemon=True).start()
        return process

    def checkpoint(self):
        reason = self.control()
        if reason:
            raise WorkInterrupted(reason)

    def wait(self, process, folder, timeout, json_events=False):
        folder = Path(folder)
        started = last_activity = time.monotonic()
        last_size = position = 0
        last_report = 0.0
        partial = b""
        usage, session = {}, None
        try:
            while process.poll() is None:
                self.checkpoint()
                elapsed = time.monotonic() - started
                if elapsed >= timeout:
                    raise TimeoutError("本次执行已达到时限")
                size = sum((folder / name).stat().st_size for name in ("stdout.txt", "stderr.txt"))
                if size > 64 * 1024 * 1024:
                    raise RuntimeError("本次诊断输出超过64MB，已停止以保护本机空间")
                if size != last_size:
                    last_size, last_activity = size, time.monotonic()
                if json_events:
                    with (folder / "stdout.txt").open("rb") as stream:
                        stream.seek(position)
                        raw = stream.read(256_000)
                        position = stream.tell()
                    parts = (partial + raw).split(b"\n")
                    partial = parts.pop()
                    for line in parts:
                        try:
                            event = json.loads(line)
                        except (ValueError, UnicodeDecodeError):
                            continue
                        if event.get("type") == "thread.started":
                            session = event.get("thread_id")
                        if event.get("type") == "turn.completed":
                            usage = event.get("usage", {})
                        if time.monotonic() - last_report > 2:
                            self.progress({"kind": event.get("type"), "item_type": event.get("item", {}).get("type"),
                                           "elapsed_seconds": int(elapsed), "session_id": session})
                            last_report = time.monotonic()
                if self.stall_seconds and time.monotonic() - last_activity >= self.stall_seconds:
                    raise TimeoutError("执行器长时间没有活动，已停止并保留进度")
                time.sleep(0.2)
            self.checkpoint()
        except BaseException:
            self.stop(process)
            raise
        finally:
            if process.poll() is not None:
                self.active.pop(process.pid, None)
                self.processes([record for _, record in self.active.values()])
        # Small, completed streams can exit before the first poll. Parse final metadata too.
        if json_events:
            with (folder / "stdout.txt").open("r", encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("type") == "thread.started":
                        session = event.get("thread_id")
                    elif event.get("type") == "turn.completed":
                        usage = event.get("usage", {})
        return {"exit_code": process.returncode, "elapsed_seconds": round(time.monotonic() - started, 2),
                "usage": usage, "session_id": session,
                "stdout": str(folder / "stdout.txt"), "stderr": str(folder / "stderr.txt")}

    def run(self, argv, cwd, folder, timeout, stdin=None, json_events=False, extra_env=None):
        self.checkpoint()
        return self.wait(self.start(argv, cwd, folder, stdin, extra_env), folder, timeout, json_events)

    def stop(self, process):
        pair = self.active.get(process.pid)
        if pair and process.poll() is None:
            terminate_record(pair[1])
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # The Popen object retains its own process handle, even when a
                # creation timestamp could not be queried on the host.
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
        self.active.pop(process.pid, None)
        self.processes([record for _, record in self.active.values()])

    def close(self):
        for process, _ in list(self.active.values()):
            self.stop(process)
