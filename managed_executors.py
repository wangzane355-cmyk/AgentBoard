"""Versioned local DeepSeek installations. No model calls or automatic activation."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import uuid
import traceback
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?")


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ManagedExecutors:
    def __init__(self, data):
        self.data = Path(data)
        self.file = self.data / "executors.json"
        default = Path(os.environ.get("LOCALAPPDATA", str(Path.home()/".local/share"))) / "AgentBoard/executors"
        self.default_root = Path(os.environ.get("AGENTBOARD_EXECUTORS_DIR", str(default))).resolve()
        self.lock = threading.RLock()
        self.operation = {"status":"idle"}

    def read(self):
        if not self.file.exists():
            return {"current":None,"previous":None,"versions":{},"root":str(self.default_root)}
        state=json.loads(self.file.read_text(encoding="utf-8"))
        if not isinstance(state,dict) or not isinstance(state.get("versions"),dict) or not isinstance(state.get("root"),str) or not Path(state["root"]).is_absolute():
            raise ValueError("Invalid executor configuration")
        if any(state.get(key) is not None and state[key] not in state["versions"] for key in ("current","previous")):
            raise ValueError("Unknown selected executor")
        return state

    def write(self, state):
        self.data.mkdir(parents=True, exist_ok=True)
        temp = self.file.with_suffix(".tmp")
        temp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
        temp.replace(self.file)

    def slot_path(self, state, slot):
        root = Path(state["root"]).resolve()
        path = (root / "deepseek" / slot).resolve()
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}",slot) or not path.is_relative_to(root/"deepseek"):
            raise ValueError("Invalid executor slot")
        return path

    def command(self, state, slot):
        record = state["versions"][slot]
        folder = self.slot_path(state,slot)
        node = folder/"runtime"/("node.exe" if os.name=="nt" else "node")
        entry = (folder/record["entry"]).resolve()
        if not entry.is_relative_to(folder) or not node.is_file() or not entry.is_file():
            raise ValueError("固定执行器文件缺失；请在Agent管理中检查或回退 / Managed executor files missing")
        return [str(node),str(entry)]

    def current_command(self):
        state=self.read()
        if not state.get("current"):
            return None
        record=state["versions"][state["current"]]
        if record.get("health",{}).get("status")=="failed":
            raise RuntimeError("固定执行器检查失败，请手动检查或回退 / Managed executor check failed")
        return self.command(state,state["current"])

    def probe(self, command, version, profile, full=True):
        flags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0
        env={**os.environ,"NO_COLOR":"1"}
        with tempfile.TemporaryDirectory(prefix="agentboard-check-") as cwd:
            for args in ([["--version"],["--profile",profile,"--help"]] if full else [["--version"]]):
                result=subprocess.run([*command,*args],input=b"",capture_output=True,timeout=60 if len(args)>1 else 15,env=env,cwd=cwd,creationflags=flags)
                if result.returncode or not result.stdout.strip() or (args==["--version"] and result.stdout.decode("utf-8","replace").strip().removeprefix("v")!=version):
                    raise ValueError("版本或headless参数检查失败；未调用模型 / Version or headless help check failed")
        return {"status":"passed","checked_at":timestamp(),"profile":profile,"full_check":full,"account_verified":False}

    def check(self, slot=None, full=True):
        with self.lock:
            state=self.read();slot=slot or state.get("current")
            if not slot:raise ValueError("尚未固定执行器 / No managed executor selected")
            if slot not in state["versions"]:raise ValueError("Unknown executor version")
            record=state["versions"][slot]
            try:
                profile=os.environ.get("AGENTBOARD_DEEPSEEK_PROFILE","headless")
                health=self.probe(self.command(state,slot),record["version"],profile,full=full or profile!=record.get("health",{}).get("profile"))
            except (OSError,ValueError,subprocess.SubprocessError):
                record["health"]={"status":"failed","checked_at":timestamp(),"account_verified":False}
                self.write(state)
                raise ValueError("本机启动检查失败，入口未切换；请查看配置或回退 / Startup check failed; selection unchanged") from None
            record["health"]=health;self.write(state)
            return health

    def startup_check(self):
        try:
            if self.read().get("current"):self.check(full=False)
        except (OSError,ValueError,KeyError):
            pass  # Keep the board available so the user can inspect or roll back.

    def activate(self, slot):
        with self.lock:
            if self.operation["status"]=="running":raise ValueError("正在准备版本，请稍后切换 / Preparation is running")
            self.check(slot)  # Recheck immediately before changing the pointer.
            state=self.read()
            if state.get("current")!=slot:
                state["previous"]=state.get("current");state["current"]=slot;self.write(state)
            return self.status()

    def rollback(self):
        state=self.read()
        if not state.get("previous"):raise ValueError("没有可回退的旧版本 / No previous version")
        return self.activate(state["previous"])

    def status(self):
        with self.lock:
            try:
                state=self.read()
                return {**state,"operation":dict(self.operation),"account_verified":False}
            except (OSError,ValueError):
                return {"error":"执行器配置无法读取 / Executor configuration unreadable","operation":dict(self.operation),"versions":{}}

    def latest(self):
        with urlopen("https://registry.npmjs.org/@deepseek-ai%2fdsh/latest",timeout=15) as response:
            raw=response.read(1_000_001)
        if len(raw)>1_000_000:raise ValueError("Registry response too large")
        version=json.loads(raw)["version"]
        if not VERSION.fullmatch(version):raise ValueError("Invalid registry version")
        return {"version":version,"source":"https://registry.npmjs.org","installed":False}

    def start_prepare(self, version=""):
        if version and not VERSION.fullmatch(version):raise ValueError("请输入完整指定版本 / Exact version required")
        with self.lock:
            if self.operation["status"]=="running":raise ValueError("正在准备另一个版本 / Preparation already running")
            self.operation={"status":"running","phase":"preparing","started_at":timestamp(),"version":version or "installed"}
            threading.Thread(target=self._prepare,args=(version,),daemon=True).start()
            return dict(self.operation)

    def _copy_modules(self, source, target, log):
        if os.name=="nt":
            result=subprocess.run(["robocopy",str(source),str(target),"/E","/COPY:DAT","/DCOPY:DAT","/R:1","/W:1","/XJ","/MT:8","/NFL","/NDL","/NJH","/NJS"],stdout=log,stderr=log,timeout=600,creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode>=8:raise ValueError("Copy failed")
        else:
            shutil.copytree(source,target,symlinks=True)

    def _prepare(self, requested):
        # Only this worker writes versions while preparation is running. Activation is blocked.
        slot=None
        log_path=self.data/"executor-installer.log"
        try:
            from executor_discovery import deepseek_command
            self.data.mkdir(parents=True,exist_ok=True)
            state=self.read()
            current=None
            if state.get("current"):
                candidate=self.slot_path(state,state["current"])/"runtime"/("node.exe" if os.name=="nt" else "node")
                if candidate.is_file():current=[str(candidate)]
            if requested:
                source_command=current or [shutil.which("node.exe") or shutil.which("node") or ""]
                if not source_command[0]:raise ValueError("Node is required")
                version=requested
            else:
                source_command=self.command(state,state["current"]) if state.get("current") else deepseek_command()
                if len(source_command)==1:
                    executable=Path(source_command[0]).resolve()
                    entry=executable if executable.suffix in (".js",".mjs") else executable.parent/"node_modules/@deepseek-ai/dsh/lib/bin.js"
                    source_command=[shutil.which("node.exe") or shutil.which("node") or "",str(entry)]
                if len(source_command)!=2 or not source_command[0]:raise ValueError("A Node CLI entry is required")
                package=Path(source_command[1]).resolve().parent
                while package.parent!=package:
                    metadata=package/"package.json"
                    if metadata.is_file() and json.loads(metadata.read_text(encoding="utf-8")).get("name")=="@deepseek-ai/dsh":break
                    package=package.parent
                metadata=json.loads((package/"package.json").read_text(encoding="utf-8"))
                version=metadata["version"]
            if not VERSION.fullmatch(version):raise ValueError("Invalid installed version")
            slot=version+"-"+uuid.uuid4().hex[:8]
            folder=self.slot_path(state,slot);folder.mkdir(parents=True,exist_ok=False)
            runtime=folder/"runtime";runtime.mkdir()
            node=runtime/("node.exe" if os.name=="nt" else "node")
            shutil.copy2(source_command[0],node)
            self.data.mkdir(parents=True,exist_ok=True)
            with log_path.open("ab") as log:
                npm_source=(Path(source_command[0]).parent/"npm") if current else (Path(source_command[0]).parent/"node_modules/npm")
                if not npm_source.is_dir():
                    npm=shutil.which("npm.cmd") or shutil.which("npm")
                    npm_source=Path(npm).resolve().parent/"node_modules/npm" if npm else Path("__missing_npm__")
                if npm_source.is_dir():self._copy_modules(npm_source,runtime/"npm",log)
                if not requested:
                    modules=package.parent.parent
                    if modules.name!="node_modules":raise ValueError("Installed dependency tree not found")
                    with self.lock:self.operation["phase"]="copying_installed_version"
                    self._copy_modules(modules,folder/"node_modules",log)
                    lock=modules.parent/"package-lock.json"
                    if lock.is_file():shutil.copy2(lock,folder/"package-lock.json")
                else:
                    npm_cli=runtime/"npm/bin/npm-cli.js"
                    if not npm_cli.is_file():raise ValueError("npm required for explicit updates")
                    with self.lock:self.operation["phase"]="installing_requested_version"
                    result=subprocess.run([str(node),str(npm_cli),"install","--prefix",str(folder),"--registry=https://registry.npmjs.org","--save-exact","--ignore-scripts","--no-audit","--no-fund","--engine-strict","--prefer-offline","@deepseek-ai/dsh@"+version],stdout=log,stderr=log,timeout=600,creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
                    if result.returncode:raise ValueError("npm preparation failed")
            entry=folder/"node_modules/@deepseek-ai/dsh/lib/bin.js"
            installed=json.loads((entry.parent.parent/"package.json").read_text(encoding="utf-8"))
            if installed.get("name")!="@deepseek-ai/dsh" or installed.get("version")!=version:raise ValueError("Package identity mismatch")
            with self.lock:self.operation["phase"]="checking_version_and_profile"
            health=self.probe([str(node),str(entry)],version,os.environ.get("AGENTBOARD_DEEPSEEK_PROFILE","headless"))
            with self.lock:
                state=self.read()
                state["versions"][slot]={"version":version,"entry":entry.relative_to(folder).as_posix(),"health":health,"prepared_at":timestamp(),"source":"official_npm" if requested else "installed_snapshot","entry_sha256":hashlib.sha256(entry.read_bytes()).hexdigest()}
                self.write(state)
                self.operation={"status":"ready","slot":slot,"version":version,"activated":False}
        except Exception:
            self.data.mkdir(parents=True,exist_ok=True)
            with log_path.open("a",encoding="utf-8") as log:traceback.print_exc(file=log)
            with self.lock:
                self.operation={"status":"failed","slot":slot,"error":"准备失败，当前版本保持不变；请查看data/executor-installer.log / Preparation failed; current version unchanged. See local installer log."}


def managed_command(data):
    try:return ManagedExecutors(data).current_command()
    except (OSError,ValueError,KeyError) as error:raise RuntimeError("固定执行器不可用；请检查或回退 / Managed executor unavailable; check or roll back") from error
