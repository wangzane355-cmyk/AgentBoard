"""Immutable, bounded verification recipes. The worker cannot edit its own acceptance plan."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from pathlib import Path


KINDS = {"python_unittest", "python_compile", "node_test", "command", "web"}


def relative_path(value, allow_dot=False):
    if not isinstance(value, str) or not value.strip() or len(value) > 400:
        raise ValueError("检查路径无效")
    path = Path(value)
    if path.is_absolute() or path.drive or value.startswith("/") or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError("检查路径必须位于项目内部")
    if not allow_dot and value == ".":
        raise ValueError("请指定文件路径")
    return value


def command_argv(argv):
    if not isinstance(argv, list) or not 1 <= len(argv) <= 40 or any(not isinstance(v, str) or not v or len(v) > 1000 for v in argv):
        raise ValueError("检查命令须是非空参数数组")
    name = Path(argv[0]).name.lower().removesuffix(".exe").removesuffix(".cmd")
    args = argv[1:]
    if name in ("python", "python3", "py") or Path(argv[0]).resolve() == Path(sys.executable).resolve():
        stripped = [arg for arg in args if arg not in ("-B", "-X", "utf8")]
        if len(stripped) < 2 or stripped[0] != "-m" or stripped[1] not in ("unittest", "pytest", "compileall"):
            raise ValueError("Python自定义检查仅支持 unittest、pytest 或 compileall 模块")
        executable = sys.executable
    elif name == "node" and args and args[0] in ("--test", "--check"):
        executable = shutil.which("node") or shutil.which("node.exe")
    elif name == "npm" and args and (args == ["test"] or args[0] == "run" and len(args) == 2 and re.fullmatch(r"[\w:-]+", args[1])):
        executable = shutil.which("npm.cmd") or shutil.which("npm")
    else:
        raise ValueError("检查命令仅支持Python测试、node --test/--check、npm test/run；不使用shell")
    if not executable:
        raise ValueError("检查工具尚未安装")
    if any("\x00" in arg or "\n" in arg for arg in args):
        raise ValueError("检查命令参数无效")
    for arg in args:
        value = arg.split("=", 1)[-1] if arg.startswith("-") and "=" in arg else arg
        value = value.split("::", 1)[0]
        if value.startswith(("/", "\\")) or re.match(r"^[a-zA-Z]:", value) or ".." in value.replace("\\", "/").split("/"):
            raise ValueError("检查命令路径必须位于项目内部")
    return [str(executable), *args]


def command_test_kind(argv):
    """Recognize test runners whose zero-test success must be rejected."""
    if "unittest" in argv:
        return "python_unittest"
    if "pytest" in argv:
        return "pytest"
    if "--test" in argv:
        return "node_test"
    return None


def validate_checks(checks):
    if not isinstance(checks, list) or not 1 <= len(checks) <= 10:
        raise ValueError("请配置1至10项验收，至少包含一项实际测试")
    result = []
    for index, raw in enumerate(checks):
        if not isinstance(raw, dict) or raw.get("kind") not in KINDS:
            raise ValueError("验收类型无效")
        kind = raw["kind"]
        item = {"id": f"check-{index+1}", "kind": kind, "name": str(raw.get("name") or kind)[:100],
                "timeout_seconds": int(raw.get("timeout_seconds", 120))}
        if not 1 <= item["timeout_seconds"] <= 600:
            raise ValueError("单项检查时限须为1至600秒")
        if kind == "python_unittest":
            modules = raw.get("modules", [])
            if not isinstance(modules, list) or len(modules) > 30 or any(not isinstance(m, str) or not re.fullmatch(r"[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*", m) for m in modules):
                raise ValueError("测试模块格式无效")
            pattern = raw.get("pattern", "test*.py")
            if not isinstance(pattern, str) or len(pattern) > 100 or "/" in pattern or "\\" in pattern:
                raise ValueError("测试文件匹配格式无效")
            item.update(modules=modules, start_dir=relative_path(raw.get("start_dir", "."), True), pattern=pattern)
        elif kind == "node_test":
            paths = raw.get("paths", [])
            if not isinstance(paths, list) or len(paths) > 30:
                raise ValueError("Node测试路径格式无效")
            item["paths"] = [relative_path(p) for p in paths]
        elif kind == "command":
            command_argv(raw.get("argv"))
            item["argv"] = raw["argv"]
        elif kind == "web":
            item["path"] = relative_path(raw.get("path", "index.html"))
            if not item["path"].endswith(".html"):
                raise ValueError("网页验收入口须是本地HTML文件")
            texts = raw.get("expected_text", [])
            if not isinstance(texts, list) or not texts or len(texts) > 12 or any(not isinstance(t, str) or not t.strip() or len(t) > 200 for t in texts):
                raise ValueError("网页验收需要至少一条预期页面文字")
            sizes = raw.get("viewports", [[1440, 900], [390, 844]])
            if not isinstance(sizes, list) or not 1 <= len(sizes) <= 3:
                raise ValueError("网页尺寸配置无效")
            for size in sizes:
                if not isinstance(size, list) or len(size) != 2 or any(not isinstance(n, int) or not 320 <= n <= 2560 for n in size):
                    raise ValueError("网页宽高须为320至2560像素")
            item.update(expected_text=texts, viewports=sizes)
        result.append(item)
    def behavioral(item):
        if item["kind"] == "python_compile":
            return False
        if item["kind"] == "command":
            return not ("compileall" in item["argv"] or "--check" in item["argv"])
        return True
    if not any(behavioral(item) for item in result):
        raise ValueError("语法检查不能单独作为自主任务的验收，请添加测试或网页检查")
    return result


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verification_files(workspace, checks, extra=()):
    root = Path(workspace).resolve()
    selected = set()
    for check in checks:
        if check["kind"] == "python_unittest":
            if check["modules"]:
                for module in check["modules"]:
                    parts = module.split(".")
                    for length in range(len(parts), 0, -1):
                        base = root / ("/".join(parts[:length]) + ".py")
                        if base.is_file():
                            selected.add(base)
                            break
                    package = root / module.replace(".", "/")
                    if package.is_dir():
                        selected.update(package.rglob("*.py"))
            else:
                start = (root / check["start_dir"]).resolve()
                if not start.is_relative_to(root):
                    raise ValueError("测试目录逃逸工作区")
                if start.is_dir():
                    selected.update(p for p in start.rglob("*.py") if fnmatch.fnmatch(p.name, check["pattern"]))
        elif check["kind"] == "node_test":
            if check["paths"]:
                for name in check["paths"]:
                    path = root / name
                    if path.is_dir():
                        selected.update(p for p in path.rglob("*") if p.is_file() and p.suffix in (".js", ".cjs", ".mjs"))
                    else:
                        selected.add(path)
            else:
                selected.update(fixed_test_candidates(root, javascript_only=True))
        elif check["kind"] == "command":
            selected.update(fixed_test_candidates(root))
            if Path(check["argv"][0]).name.lower() in ("npm", "npm.cmd") and (root / "package.json").is_file():
                selected.add(root / "package.json")
            for arg in check["argv"][1:]:
                path = root / arg
                if path.is_file() and path.resolve().is_relative_to(root):
                    selected.add(path)
    selected.update(root / relative_path(p) for p in extra)
    result = {}
    for path in selected:
        if not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError("保护的验收文件不存在或逃逸工作区")
        result[path.relative_to(root).as_posix()] = file_hash(path)
    return result


def fixed_test_candidates(root, javascript_only=False):
    result = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if not path.is_file() or any(part in ("node_modules", ".git", ".venv", "venv", "__pycache__") for part in rel.parts):
            continue
        js = path.suffix in (".js", ".cjs", ".mjs") and ("test" in rel.parts or "tests" in rel.parts or re.search(r"(?:^test[_.-]|[_.-](?:test|spec)\.)", path.name))
        py = not javascript_only and path.suffix == ".py" and (path.name.startswith("test") or "tests" in rel.parts)
        if js or py:
            result.append(path)
    return result


def verification_unchanged(workspace, manifest):
    root = Path(workspace).resolve()
    return all((root / rel).resolve().is_relative_to(root) and (root / rel).is_file()
               and file_hash(root / rel) == expected for rel, expected in manifest.items())


def browser_executable():
    explicit = os.environ.get("AGENTBOARD_BROWSER_EXECUTABLE")
    candidates = [explicit] if explicit else []
    candidates += [shutil.which(name) for name in ("msedge", "chrome", "chromium", "chromium-browser")]
    if os.name == "nt":
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                for name in ("msedge.exe", "chrome.exe"):
                    try:
                        key_path = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\" + name
                        with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | view) as key:
                            candidates.append(str(winreg.QueryValueEx(key, "")[0]).strip('"'))
                    except OSError:
                        pass
    for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates.extend(str(Path(base) / rel) for rel in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"))
    return next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()), None)


class RenderedText(HTMLParser):
    """Inspect rendered DOM text, not matching strings inside scripts or hidden attributes."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    def __init__(self):
        super().__init__()
        self.stack, self.text = [], []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = bool(self.stack and self.stack[-1][1]) or tag in ("script", "style", "head", "template") or "hidden" in attrs or attrs.get("aria-hidden") == "true" or bool(re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", attrs.get("style", ""), re.I))
        if tag not in self.VOID:
            self.stack.append((tag, hidden))
    def handle_endtag(self, tag):
        for index in range(len(self.stack)-1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
    def handle_data(self, text):
        if not self.stack or not self.stack[-1][1]:
            self.text.append(text)


def run_web_check(check, workspace, folder, runner):
    root, folder = Path(workspace).resolve(), Path(folder)
    entry = (root / check["path"]).resolve()
    browser = browser_executable()
    node = shutil.which("node") or shutil.which("node.exe")
    if not entry.is_relative_to(root) or not entry.is_file():
        return {"passed": False, "detail": "网页入口不存在", "artifacts": []}
    if not browser:
        return {"passed": False, "detail": "未找到可用的Edge/Chrome；网页检查未执行", "artifacts": []}
    if not node:
        return {"passed": False, "detail": "精确网页尺寸验收需要Node 22+；检查未执行", "artifacts": []}
    class QuietHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    artifacts, details = [], []
    passed = True
    try:
        from urllib.parse import quote
        url = f"http://127.0.0.1:{server.server_port}/" + quote(check["path"])
        for width, height in check["viewports"]:
            runner.checkpoint()
            screen = folder / f"page-{width}x{height}.png"
            profile_root = folder / f"browser-profile-{width}"
            args = [node, str(Path(__file__).resolve().with_name("browser_probe.mjs")), browser, url,
                    str(width), str(height), str(screen), str(profile_root)]
            try:
                result = runner.run(args, root, folder / f"viewport-{width}", check["timeout_seconds"])
            except TimeoutError as exc:
                passed = False
                details.append(f"{width}×{height}：{exc}")
                continue
            measurement_path = Path(str(screen) + ".json")
            try:
                measurement = json.loads(measurement_path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                measurement = {}
            text_content = measurement.get("text", "")
            missing = [text for text in check["expected_text"] if text not in text_content]
            image_ok = screen.is_file() and screen.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
            size_ok = measurement.get("width") == width and measurement.get("height") == height
            overflow = measurement.get("scrollWidth", width + 1) > width + 1
            ok = result["exit_code"] == 0 and image_ok and not missing and size_ok and not overflow
            passed &= ok
            reasons = []
            if missing:
                reasons.append("缺失文字：" + "、".join(missing))
            if not size_ok:
                reasons.append("真实页面尺寸未确认；需要可用的Node 22+和浏览器")
            if overflow:
                reasons.append("页面存在横向溢出")
            if result["exit_code"]:
                reasons.append(Path(result["stderr"]).read_text(encoding="utf-8", errors="replace")[-1000:])
            details.append(f"{width}×{height}：" + ("真实尺寸、页面文字与截图通过；无横向溢出" if ok else "失败；" + "；".join(reasons)))
            if image_ok:
                artifacts.append(str(screen))
            # Only this empty, task-owned browser profile can be removed. Evidence remains.
            if profile_root.exists() and not profile_root.is_symlink() and profile_root.resolve().parent == folder.resolve():
                try:
                    shutil.rmtree(profile_root)
                except OSError:
                    pass  # A still-locked diagnostic profile is safe to retain locally.
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    return {"passed": passed, "detail": "；".join(details), "artifacts": artifacts}


def run_verification(checks, workspace, folder, runner):
    root, folder = Path(workspace), Path(folder)
    results = []
    for check in checks:
        runner.checkpoint()
        destination = folder / check["id"]
        destination.mkdir(parents=True, exist_ok=True)
        if check["kind"] == "python_compile":
            count = 0
            try:
                for path in root.rglob("*.py"):
                    if any(part in (".git", ".venv", "venv", "node_modules", "__pycache__") for part in path.relative_to(root).parts):
                        continue
                    compile(path.read_bytes(), str(path), "exec")
                    count += 1
                    runner.checkpoint()
                item = {"passed": count > 0, "detail": f"{count}个Python文件语法通过", "tests": None}
            except (SyntaxError, OSError) as exc:
                item = {"passed": False, "detail": str(exc)[:2000], "tests": None}
        elif check["kind"] == "web":
            item = run_web_check(check, root, destination, runner)
        else:
            if check["kind"] == "python_unittest":
                tail = check["modules"] or ["discover", "-s", check["start_dir"], "-p", check["pattern"]]
                argv = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "-v", *tail]
            elif check["kind"] == "node_test":
                node = shutil.which("node") or shutil.which("node.exe")
                if not node:
                    results.append({**check, "passed": False, "detail": "Node未安装，检查未执行"})
                    continue
                argv = [node, "--test", *check["paths"]]
            else:
                argv = command_argv(check["argv"])
            try:
                execution = runner.run(argv, root, destination, check["timeout_seconds"],
                                       extra_env={"AGENTBOARD_VERIFICATION": "1"})
            except TimeoutError as exc:
                results.append({**check, "passed": False, "tests": None, "detail": str(exc), "exit_code": None})
                continue
            output = "\n".join(Path(execution[name]).read_text(encoding="utf-8", errors="replace")[-12000:] for name in ("stdout", "stderr"))
            tests = None
            test_kind = command_test_kind(check["argv"]) if check["kind"] == "command" else check["kind"]
            if test_kind == "python_unittest":
                match = re.search(r"Ran\s+(\d+)\s+tests?\b", output)
                tests = int(match.group(1)) if match else 0
            elif test_kind == "node_test":
                match = re.search(r"(?:#|ℹ)\s*tests\s+(\d+)", output)
                tests = int(match.group(1)) if match else 0
            elif test_kind == "pytest":
                tests = sum(int(n) for n in re.findall(r"(\d+)\s+(?:passed|failed|skipped|xfailed|xpassed|errors?)\b", output.splitlines()[-1] if output.splitlines() else ""))
            item = {**execution, "passed": execution["exit_code"] == 0 and tests != 0,
                    "tests": tests, "detail": output[-6000:] or "检查未返回输出"}
            if tests == 0:
                item["detail"] = "未发现实际运行的测试，不能视为验收通过。\n" + item["detail"]
        results.append({**check, **item})
    (folder / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results
