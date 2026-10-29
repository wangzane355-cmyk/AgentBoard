"""Find installed executors without installing packages or contacting a registry."""
import json
import os
import shutil
from pathlib import Path


def _entry_command(path: Path) -> list[str] | None:
    if not path.is_file():
        return None
    if path.suffix.lower() in (".js", ".mjs", ".cjs"):
        node = shutil.which("node.exe") or shutil.which("node")
        return [node, str(path)] if node else None
    return [str(path)]


def deepseek_command() -> list[str]:
    explicit = os.environ.get("AGENTBOARD_DEEPSEEK_ENTRY", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        command = _entry_command(path) if path.is_absolute() else None
        if command:
            return command
        raise RuntimeError("DeepSeek入口不可用；请检查AGENTBOARD_DEEPSEEK_ENTRY和Node / Invalid DeepSeek entry or missing Node")
    executable = shutil.which("dsh.cmd") or shutil.which("dsh")
    if executable:
        return [executable]
    # Desktop shortcuts may inherit an older PATH. Check standard user installs too.
    roaming = os.environ.get("APPDATA")
    if roaming:
        command = _entry_command(Path(roaming) / "npm" / "dsh.cmd")
        if command:
            return command
    roots = [Path.home() / ".npm"]
    for value in (os.environ.get("npm_config_cache"), os.environ.get("NPM_CONFIG_CACHE")):
        if value:
            roots.insert(0, Path(value))
    if os.environ.get("LOCALAPPDATA"):
        roots.append(Path(os.environ["LOCALAPPDATA"]) / "npm-cache")
    candidates = []
    for root in dict.fromkeys(roots):
        for metadata in (root / "_npx").glob("*/node_modules/@deepseek-ai/dsh/package.json"):
            try:
                package = json.loads(metadata.read_text(encoding="utf-8"))
                if package.get("name") != "@deepseek-ai/dsh":
                    continue
                entry = package.get("bin", {})
                entry = entry.get("dsh") if isinstance(entry, dict) else entry
                if not isinstance(entry, str):
                    continue
                path = (metadata.parent / entry).resolve()
                if not path.is_relative_to(metadata.parent.resolve()):
                    continue
                command = _entry_command(path)
                if command:
                    candidates.append((metadata.stat().st_mtime, command))
            except (OSError, ValueError, TypeError):
                continue
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    raise RuntimeError("未找到已安装的DeepSeek CLI；请先安装，或设置AGENTBOARD_DEEPSEEK_ENTRY。聊天不会自动下载程序 / DeepSeek CLI is not installed; automatic downloads are disabled")


def deepseek_available() -> bool:
    try:
        deepseek_command()
        return True
    except RuntimeError:
        return False
