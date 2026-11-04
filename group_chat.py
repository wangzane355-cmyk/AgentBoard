"""Explicit routing and bounded handoffs for shared local AgentBoard rooms."""
import re

AGENTS = ("deepseek", "codex")


def route_message(text: str, mode: str, selected: str, members: list[str], rounds=0, agents=None) -> dict:
    agents = tuple(agents or AGENTS)
    try:
        rounds = int(rounds)
    except (TypeError, ValueError):
        raise ValueError("讨论轮数须是0至3的整数")
    if not 0 <= rounds <= 3:
        raise ValueError("最多讨论3轮")
    directed = selected in agents
    recipients = [selected] if directed else list(members)
    if text.startswith("/"):
        command, _, content = text.partition(" ")
        # Accept tabs and newlines after slash commands too.
        pieces = text.split(maxsplit=1)
        command = pieces[0].lower()
        content = pieces[1].strip() if len(pieces) == 2 else ""
        if command[1:] in agents or command == "/ds":
            recipient = "deepseek" if command == "/ds" else command[1:]
            recipients, directed, rounds = [recipient], True, 0
        elif command in ("/all", "/讨论", "/discuss"):
            if mode != "group":
                raise ValueError("请先新建Agent群聊，再使用全体或讨论命令")
            recipients, directed = list(members), False
            if command == "/all":
                rounds = 0  # Explicit broadcast is one reply per member.
            else:
                parts = content.split(maxsplit=1)
                if parts and parts[0].isdigit():
                    rounds = int(parts[0])
                    content = parts[1] if len(parts) == 2 else ""
                else:
                    rounds = rounds or 2
                if not 1 <= rounds <= 3:
                    raise ValueError("讨论轮数须是1至3，例如 /讨论 2 检查这个方案")
                content = content or "请围绕当前方案互相讨论，指出分歧和可执行的下一步。"
        else:
            raise ValueError("未知命令；支持 /codex、/deepseek、/all、/讨论 2")
        if not content:
            raise ValueError("请在命令后填写消息内容")
    if mode != "group" and selected not in agents:
        raise ValueError("单聊请选择一个Agent")
    if not recipients or any(agent not in members or agent not in agents for agent in recipients):
        raise ValueError("指定Agent不在这个房间中")
    recipients = list(dict.fromkeys(recipients))
    if directed or len(recipients) == 1:
        # A directed message or a one-member room gets one response, never
        # repeated self-discussion under a multi-round selection.
        rounds = 0
    return {"recipients": recipients, "directed": directed, "rounds": rounds,
            "max_replies": min(6, len(recipients) * max(1, rounds))}


def parse_reply_directive(answer: str, sender: str, members: list[str]) -> tuple[str, str | None, bool]:
    """Parse an optional final directive; missing/inline markers never mean DONE."""
    lines = answer.rstrip().splitlines()
    recipient, done = None, False
    if lines:
        match = re.fullmatch(r"AGENTBOARD_TO:\s*([a-z][a-z0-9_-]{1,31}|DONE)", lines[-1].strip())
        if match:
            target = match.group(1)
            done = target == "DONE"
            if target in members and target != sender:
                recipient = target
            lines.pop()
    cleaned = "\n".join(lines).strip()
    # Preserve old rendering without treating an inline marker as a round vote.
    cleaned = re.sub(r"\s*AGENTBOARD_TO:\s*DONE\s*$", "", cleaned).rstrip()
    return cleaned, recipient, done


def strip_handoff(answer: str, sender: str, members: list[str]) -> tuple[str, str | None]:
    cleaned, recipient, _ = parse_reply_directive(answer, sender, members)
    return cleaned, recipient
