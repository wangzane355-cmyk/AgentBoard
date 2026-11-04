"""One opt-in Windows firewall rule for AgentBoard's paired LAN gateway.

Inspect is read-only. Request only opens the OS UAC prompt: the user must grant
permission. Never changes firewall profiles, global policy or execution policy.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path


INSPECT_TIMEOUT = 15
UAC_TIMEOUT = 150


def _powershell_path():
    # Use the OS system directory, never PATH or a request-supplied executable.
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise OSError("Windows system directory unavailable")
    return str(Path(buffer.value) / "WindowsPowerShell" / "v1.0" / "powershell.exe")


def _encoded(script):
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def _parameters(payload):
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    return "$p = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded + "')) | ConvertFrom-Json\n"


def _inspection_script(payload):
    return r'''$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
''' + _parameters(payload) + r'''
$rules = @(Get-NetFirewallRule -Name $p.name -PolicyStore ActiveStore -ErrorAction SilentlyContinue)
if ($rules.Count -ne 1) {
 [pscustomobject]@{exists=$false} | ConvertTo-Json -Compress
 exit 0
}
$rule = $rules[0]
$port = $rule | Get-NetFirewallPortFilter
$address = $rule | Get-NetFirewallAddressFilter
$app = $rule | Get-NetFirewallApplicationFilter
$service = $rule | Get-NetFirewallServiceFilter
$interface = $rule | Get-NetFirewallInterfaceTypeFilter
[pscustomobject]@{
 exists=$true
 name=[string]$rule.Name
 group=[string]$rule.Group
 enabled=[string]$rule.Enabled
 direction=[string]$rule.Direction
 action=[string]$rule.Action
 profiles=[int]$rule.Profile
 edge=[string]$rule.EdgeTraversalPolicy
 program=[string]$app.Program
 protocol=[string]$port.Protocol
 local_ports=@($port.LocalPort)
 remote_ports=@($port.RemotePort)
 local_addresses=@($address.LocalAddress)
 remote_addresses=@($address.RemoteAddress)
 service=[string]$service.Service
 interface_types=@([string]$interface.InterfaceType)
} | ConvertTo-Json -Compress -Depth 4
'''


def _rule_script(payload):
    # Only this exact name is modified; every scope is a fixed constant except
    # the validated gateway port and the constructor-pinned interpreter path.
    return r'''$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
''' + _parameters(payload) + r'''
try {
 $existing = @(Get-NetFirewallRule -Name $p.name -PolicyStore PersistentStore -ErrorAction SilentlyContinue)
 if ($existing.Count -gt 0) {
  Remove-NetFirewallRule -Name $p.name -PolicyStore PersistentStore -ErrorAction Stop
 }
 New-NetFirewallRule -Name $p.name -DisplayName ('AgentBoard phone access (' + $p.port + ')') -Group 'AgentBoard' -Description 'Paired AgentBoard gateway on a trusted local network only.' -PolicyStore PersistentStore -Direction Inbound -Action Allow -Enabled True -Profile Private,Public -Protocol TCP -LocalPort ([string]$p.port) -RemotePort Any -Program $p.program -RemoteAddress LocalSubnet -LocalAddress Any -Service Any -InterfaceType Any -EdgeTraversalPolicy Block -ErrorAction Stop | Out-Null
 exit 0
} catch {
 exit 1
}
'''


def _elevation_script(shell, command):
    return r'''$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
''' + _parameters({"shell": shell, "command": command}) + r'''
try {
 $child = Start-Process -FilePath $p.shell -ArgumentList @('-NoProfile','-NonInteractive','-EncodedCommand',$p.command) -Verb RunAs -WindowStyle Hidden -Wait -PassThru
 $child.Refresh()
 if ($null -eq $child.ExitCode) { exit 1 }
 exit $child.ExitCode
} catch {
 $code = $_.Exception.NativeErrorCode
 if ($code -ne 1223 -and $null -ne $_.Exception.InnerException) {
  $code = $_.Exception.InnerException.NativeErrorCode
 }
 if ($code -eq 1223) { exit 1223 }
 exit 1
}
'''


def _port(value):
    if not isinstance(value, int) or isinstance(value, bool) or not 1024 <= value <= 65535:
        raise ValueError("手机访问端口须为1024至65535")
    return value


def _only(value, expected):
    values = value if isinstance(value, list) else [value]
    return len(values) == 1 and str(values[0]).casefold() == str(expected).casefold()


class PhoneFirewall:
    def __init__(self, program: str = sys.executable):
        path = Path(program).expanduser()
        if not path.is_absolute() or any(character in str(program) for character in "\r\n\x00"):
            raise ValueError("防火墙程序必须是固定的绝对路径")
        self.program = str(path.resolve())
        self._program_hash = hashlib.sha256(self.program.casefold().encode("utf-8")).hexdigest()[:16]
        self._lock = threading.Lock()
        self._states = {}
        self._worker = None
        self._active_port = None

    def _payload(self, port):
        return {"name": f"AgentBoard-Phone-{port}-{self._program_hash}", "program": self.program, "port": port}

    @staticmethod
    def _result(state, message, port):
        return {"state": state, "message": message, "port": port}

    def status(self, port=8767):
        port = _port(port)
        if os.name != "nt":
            return self._result("not_required", "此系统不使用Windows授权按钮；如系统询问，请允许AgentBoard访问本地网络。", port)
        with self._lock:
            return dict(self._states.get(port, self._result("unknown", "尚未检查此端口的Windows防火墙许可。", port)))

    def _matches(self, rule, payload):
        if not isinstance(rule, dict):
            return False
        program = str(rule.get("program", "")).replace("/", "\\").casefold()
        expected_program = self.program.replace("/", "\\").casefold()
        return (rule.get("exists") is True and rule.get("name") == payload["name"]
                and rule.get("group") == "AgentBoard" and str(rule.get("enabled")).casefold() == "true"
                and rule.get("direction") == "Inbound" and rule.get("action") == "Allow"
                and rule.get("profiles") == 6 and rule.get("edge") == "Block"
                and program == expected_program and str(rule.get("protocol")).casefold() in ("tcp", "6")
                and _only(rule.get("local_ports"), payload["port"]) and _only(rule.get("remote_ports"), "Any")
                and _only(rule.get("local_addresses"), "Any") and _only(rule.get("remote_addresses"), "LocalSubnet")
                and _only(rule.get("service"), "Any") and _only(rule.get("interface_types"), "Any"))

    @staticmethod
    def _run(shell, script, timeout):
        return subprocess.run([shell, "-NoProfile", "-NonInteractive", "-EncodedCommand", _encoded(script)],
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def _inspect_result(self, port):
        try:
            payload = self._payload(port)
            result = self._run(_powershell_path(), _inspection_script(payload), INSPECT_TIMEOUT)
            if result.returncode != 0:
                return self._result("error", "无法读取Windows防火墙规则，请在电脑上重试检查。", port)
            raw = result.stdout.decode("utf-8-sig") if isinstance(result.stdout, bytes) else result.stdout
            rule = json.loads(raw)
            if self._matches(rule, payload):
                return self._result("ready", "AgentBoard专用局域网规则已配置，请用手机验证连接。", port)
            return self._result("needs_permission", "需要一次Windows授权，才能允许同一Wi-Fi的手机连接。", port)
        except subprocess.TimeoutExpired:
            return self._result("error", "Windows防火墙检查超时，请稍后重试。", port)
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
            return self._result("error", "暂时无法检查Windows防火墙，请在电脑上重试。", port)

    def inspect(self, port=8767):
        port = _port(port)
        if os.name != "nt":
            return self.status(port)
        with self._lock:
            if self._worker is not None and self._worker.is_alive() and self._active_port == port:
                return dict(self._states[port])
        result = self._inspect_result(port)
        with self._lock:
            # An authorization request may have started during the read-only check.
            if self._worker is None or not self._worker.is_alive() or self._active_port != port:
                self._states[port] = result
            return dict(self._states.get(port, result))

    def request(self, port=8767):
        port = _port(port)
        if os.name != "nt":
            return self.status(port)
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return dict(self._states[self._active_port])
            requesting = self._result("requesting", "请在电脑弹出的Windows权限提示中选择“是”；不授权时不会修改防火墙。", port)
            self._states[port] = requesting
            self._active_port = port
            self._worker = threading.Thread(target=self._request_worker, args=(port,), daemon=True,
                                            name="AgentBoard firewall permission")
            self._worker.start()
            return dict(requesting)

    def _request_worker(self, port):
        try:
            before = self._inspect_result(port)
            if before["state"] != "needs_permission":
                result = before
            else:
                shell = _powershell_path()
                command = _encoded(_rule_script(self._payload(port)))
                elevated = self._run(shell, _elevation_script(shell, command), UAC_TIMEOUT)
                if elevated.returncode == 1223:
                    result = self._result("error", "你取消了Windows授权，手机访问许可尚未开启。可准备好后再次点击授权。", port)
                elif elevated.returncode != 0:
                    result = self._result("error", "Windows授权未能完成，手机访问许可尚未确认。请重试或检查系统策略。", port)
                else:
                    result = self._inspect_result(port)
                    if result["state"] == "needs_permission":
                        result = self._result("error", "授权已结束，但专用规则未通过检查。请在电脑上检查系统防火墙策略后重试。", port)
        except subprocess.TimeoutExpired:
            result = self._result("error", "Windows权限请求超时，许可尚未确认。请查看电脑上的提示后重试。", port)
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
            result = self._result("error", "无法完成Windows权限请求，请在电脑上重试。", port)
        with self._lock:
            self._states[port] = result
