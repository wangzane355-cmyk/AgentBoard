"""Local executor configuration. Secrets are referenced by environment variable name."""
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

BUILTINS = {
    "codex": {"id": "codex", "name": "Codex", "kind": "builtin", "enabled": True, "can_implement": True},
    "deepseek": {"id": "deepseek", "name": "DeepSeek", "kind": "builtin", "enabled": True, "can_implement": True},
}


class AgentRegistry:
    def __init__(self, data: Path):
        self.path = data / "agents.json"

    def custom(self):
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []

    def all(self):
        return [BUILTINS["deepseek"], BUILTINS["codex"], *self.custom()]

    def ids(self):
        return [p["id"] for p in self.all() if p["enabled"]]

    def get(self, agent, enabled=True):
        profile = next((p for p in self.all() if p["id"] == agent), None)
        if not profile or enabled and not profile["enabled"]:
            raise ValueError("Agent不存在或已停用 / Agent missing or disabled")
        return profile

    def save(self, body):
        agent = str(body.get("id", "")).strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{1,31}", agent) or agent in {*BUILTINS, "all", "ds", "discuss", "done", "system"}:
            raise ValueError("Agent ID须为2至32位英文标识，且不能占用内置名称 / Invalid or reserved agent ID")
        name = str(body.get("name", "")).strip()
        kind = body.get("kind")
        if not name or len(name) > 60 or kind not in ("cli", "api", "mock"):
            raise ValueError("请填写名称及有效接入类型 / Name and valid adapter type required")
        profile = {"id": agent, "name": name, "kind": kind, "enabled": bool(body.get("enabled", True)),
                   "can_implement": kind == "cli" and bool(body.get("can_implement", False))}
        if kind == "cli":
            executable = str(body.get("executable", "")).strip()
            args = body.get("args", [])
            if not executable or len(executable) > 1000 or not isinstance(args, list) or len(args) > 40 or any(not isinstance(a, str) or len(a) > 2000 for a in args):
                raise ValueError("命令和参数须分开填写 / Provide an executable and an argument array")
            if Path(executable).stem.lower() in ("codex", "codex.cmd"):
                raise ValueError("请使用内置Codex，以保留额度保护 / Use built-in Codex for quota protection")
            if ("/" in executable or "\\" in executable) and not Path(executable).is_absolute():
                raise ValueError("请使用绝对路径或PATH中的程序名 / Use an absolute executable path or a PATH command")
            profile.update(executable=executable, args=args)
        elif kind == "api":
            endpoint = str(body.get("endpoint", "")).strip().rstrip("/")
            try:
                url = urlsplit(endpoint)
                valid = (url.scheme == "https" or url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1")) and url.hostname and not url.username and not url.password and not url.query and not url.fragment
                url.port
            except ValueError:
                valid = False
            env = str(body.get("key_env", "")).strip()
            model = str(body.get("model", "")).strip()
            if not valid or not endpoint.endswith("/chat/completions") or not model or len(model) > 200 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", env):
                raise ValueError("请填写完整chat/completions地址、模型和密钥环境变量名 / Invalid endpoint, model or key environment variable")
            profile.update(endpoint=endpoint, model=model, key_env=env)
        profiles = self.custom()
        if len(profiles) >= 20 and not any(p["id"] == agent for p in profiles):
            raise ValueError("最多20个自定义Agent / Up to 20 custom agents")
        profiles = [p for p in profiles if p["id"] != agent] + [profile]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        return self.describe(profile)

    def describe(self, profile):
        kind = profile["kind"]
        if kind == "builtin":
            executables = ("codex.cmd", "codex") if profile["id"] == "codex" else ("dsh.cmd", "dsh", "npx.cmd", "npx")
            ready = any(shutil.which(exe) for exe in executables)
        elif kind == "cli":
            ready = bool(shutil.which(profile["executable"]) or Path(profile["executable"]).is_file())
        elif kind == "api":
            ready = bool(os.environ.get(profile["key_env"]))
        else:
            ready = True
        return {**profile, "configured": ready, "check_note": "Configuration check only; authentication and live provider behavior are not verified.",
                "simulation": kind == "mock"}

    def command(self, agent, workspace, answer_file):
        p = self.get(agent)
        if p["kind"] == "cli":
            if not self.describe(p)["configured"]:
                raise ValueError("找不到自定义命令 / Custom executable not found")
            replacements = {"{workspace}": str(workspace), "{answer_file}": str(answer_file)}
            args = []
            for arg in p["args"]:
                for source, target in replacements.items():
                    arg = arg.replace(source, target)
                args.append(arg)
            return [p["executable"], *args]
        return [sys.executable, str(Path(__file__).with_name("agent_worker.py")), str(self.path), agent]
