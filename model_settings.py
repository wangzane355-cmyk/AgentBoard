"""Per-invocation Codex preferences; no credentials, network or model calls."""
import json
import os
import re
from functools import lru_cache
from pathlib import Path

EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z")


@lru_cache(maxsize=4)
def _catalog_file(path, stamp):
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return [{"id": m["slug"], "name": m.get("display_name", m["slug"]),
                 "efforts": [e["effort"] for e in m.get("supported_reasoning_levels", [])
                             if e.get("effort") in EFFORTS]}
                for m in raw.get("models", []) if m.get("visibility") == "list"
                and isinstance(m.get("slug"), str) and MODEL_ID.fullmatch(m["slug"])]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return []


def local_catalog(home):
    path = home / "models_cache.json"
    try:
        return _catalog_file(str(path), path.stat().st_mtime_ns)
    except OSError:
        return []


def local_defaults(home):
    # Read only simple, root-level string keys, including on Python 3.10.
    # Profiles, project config and managed defaults may override these references.
    try:
        root = re.split(r"^\s*\[", (home / "config.toml").read_text(encoding="utf-8"), maxsplit=1, flags=re.M)[0]
    except OSError:
        return {}
    result = {}
    for key, out in (("model", "model"), ("model_reasoning_effort", "reasoning_effort")):
        match = re.search(r"^\s*" + key + r"\s*=\s*([\"'])([^\r\n]*?)\1\s*(?:#.*)?$", root, re.M)
        if match:
            value = match[2]
            if (out == "model" and MODEL_ID.fullmatch(value)) or (out == "reasoning_effort" and value in EFFORTS):
                result[out] = value
    return result


class ModelSettings:
    def __init__(self, data, home=None):
        self.path = data / "model-settings.json"
        self.home = home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))

    def saved(self):
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def status(self):
        defaults = local_defaults(self.home)
        models = local_catalog(self.home)
        if defaults.get("model") and not any(m["id"] == defaults["model"] for m in models):
            models = [*models, {"id": defaults["model"], "name": defaults["model"], "efforts": []}]
        return {"codex": {"preferences": self.saved(), "local_defaults": defaults, "models": models,
                          "source": "local_cache", "availability_verified": False}}

    def validate(self, options):
        if not isinstance(options, dict) or options.keys() - {"model", "reasoning_effort"}:
            raise ValueError("模型设置格式无效 / Invalid model settings")
        model, effort = options.get("model", ""), options.get("reasoning_effort", "")
        if not isinstance(model, str) or not isinstance(effort, str):
            raise ValueError("模型设置必须是文字 / Model settings must be strings")
        current = self.status()["codex"]
        selected = model or current["local_defaults"].get("model", "")
        entry = next((m for m in current["models"] if m["id"] == selected), None)
        if model and not entry:
            raise ValueError("型号不在本机模型目录中，请先刷新Codex模型目录 / Model is absent from the local Codex catalog")
        if effort and (not entry or effort not in entry["efforts"]):
            raise ValueError("本机目录未声明此型号支持该推理档位 / Reasoning level is not advertised for this model")
        return {"model": model, "reasoning_effort": effort}

    def save(self, options):
        options = self.validate(options)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(options, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        return self.status()

    def resolve(self, agent, overrides=None):
        if agent != "codex":
            return {}
        if overrides is not None and (not isinstance(overrides, dict) or overrides.keys() - {"model", "reasoning_effort"} or any(not isinstance(v, str) for v in overrides.values())):
            raise ValueError("模型设置格式无效 / Invalid model settings")
        options = {**self.saved(), **{k: v for k, v in (overrides or {}).items() if v}}
        options = self.validate(options)
        # Pin the referenced model when effort alone was chosen, so project
        # defaults cannot silently pair that effort with a different model.
        if options["reasoning_effort"] and not options["model"]:
            options["model"] = local_defaults(self.home).get("model", "")
        return options


def codex_arguments(options):
    args = []
    if options.get("model"):
        args += ["--model", options["model"]]
    if options.get("reasoning_effort"):
        args += ["-c", "model_reasoning_effort=" + json.dumps(options["reasoning_effort"])]
    return args


def execution_record(agent, options, stderr):
    record = {"requested": dict(options), "confirmed": {}, "source": "unconfirmed"}
    if agent != "codex":
        return record
    # Only parse the CLI startup header, before the prompt or diagnostics.
    header = ""
    if stderr.is_file():
        with stderr.open(encoding="utf-8", errors="replace") as stream:
            header = stream.read(4096)
    header = re.split(r"(?:^|\n)(?:user|prompt)\s*\n", header, maxsplit=1)[0]
    for label, key in (("model", "model"), ("reasoning effort", "reasoning_effort")):
        match = re.search(r"^" + label + r": ([A-Za-z0-9._:/-]+)\s*$", header, re.M)
        if match:
            record["confirmed"][key] = match[1]
    if record["confirmed"]:
        record["source"] = "executor_log"
    return record
