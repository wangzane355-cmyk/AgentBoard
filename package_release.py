"""Build a local source distribution from explicit public directories, never runtime state."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path


PUBLIC_ROOTS = {"AGENTS.md", "README.md", "README.zh-CN.md", "CHANGELOG.md", "CONTRIBUTING.md",
                "DEEPSEEK_HANDOFF.md", "SECURITY.md", "LICENSE", "start.cmd", ".gitignore", ".gitattributes", "browser_probe.mjs", "test_phone_login.mjs", "test_group_chat_ui.mjs"}
PUBLIC_MODULES = set("""agent_registry agent_worker autonomy autonomy_bridge autonomy_store context_sources
demo doctor executor_discovery group_chat launch managed_executors model_settings package_release restart_service
server phone_access phone_firewall test_phone_firewall test_phone_access test_phone_server task_archive test_task_archive test_workspace_ux smoke_chat smoke_group_chat smoke_probe supervised_process usage_probe verification test_agent_registry
test_autonomy test_context_sources test_executor_discovery test_group_chat test_launch test_managed_executors
test_model_settings test_release test_server test_supervised_process test_usage_probe test_verification""".split())
PRIVATE_NAMES = {"data", ".git", ".codex", ".dsh", "node_modules", "__pycache__", ".venv", "venv",
                 "auth.json", "credentials.json", "executors.json", "agents.json", "model-settings.json"}
PRIVATE_SUFFIXES = {".key", ".pem", ".pfx", ".p12", ".sqlite", ".sqlite3", ".db", ".lnk"}


def source_files(root):
    root = Path(root).resolve()
    files = []
    for path in root.iterdir():
        if path.is_file() and not path.is_symlink() and (path.name in PUBLIC_ROOTS or path.suffix == ".py" and path.stem in PUBLIC_MODULES):
            files.append(path)
    for name in ("static", "docs", ".github"):
        directory = root / name
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and not path.is_symlink() and path.suffix.lower() not in PRIVATE_SUFFIXES and path.resolve().is_relative_to(root) and not any(part in PRIVATE_NAMES or part.startswith(".env") for part in path.relative_to(root).parts):
                files.append(path)
    return sorted(files)


def package(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    files = source_files(root)
    if not files:
        raise ValueError("没有找到可发行的源文件")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative = path.relative_to(root).as_posix()
            data = path.read_bytes()
            archive.writestr("AgentBoard/" + relative, data)
            manifest.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest()})
        archive.writestr("AgentBoard/SOURCE_MANIFEST.json", json.dumps({"version": "0.4.0-local", "files": manifest}, indent=2))
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(checksum + "  " + output.name + "\n", encoding="ascii")
    return {"archive": str(output), "files": len(files), "sha256": checksum}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a private-state-free AgentBoard source archive")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "data/releases/AgentBoard-0.4.0-source.zip")
    args = parser.parse_args()
    print(json.dumps(package(Path(__file__).resolve().parent, args.output), ensure_ascii=False, indent=2))
