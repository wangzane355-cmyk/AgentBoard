"""Firewall authorization checks. Every OS command/UAC action is mocked."""
import base64
import json
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import phone_firewall as firewall


class FirewallTests(unittest.TestCase):
    def setUp(self):
        self.manager = firewall.PhoneFirewall()
        self.shell = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

    def output(self, data=None, code=0):
        return SimpleNamespace(returncode=code, stdout=json.dumps(data or {"exists": False}).encode(), stderr=b"")

    def ready_rule(self, port=8767):
        return {"exists": True, "name": self.manager._payload(port)["name"], "group": "AgentBoard",
                "enabled": "True", "direction": "Inbound", "action": "Allow", "profiles": 6,
                "edge": "Block", "program": self.manager.program, "protocol": "TCP",
                "local_ports": [str(port)], "remote_ports": ["Any"], "local_addresses": ["Any"],
                "remote_addresses": ["LocalSubnet"], "service": "Any", "interface_types": ["Any"]}

    @contextmanager
    def windows(self, side_effect):
        with patch("phone_firewall.os.name", "nt"), patch("phone_firewall._powershell_path", return_value=self.shell), patch("phone_firewall.subprocess.run", side_effect=side_effect) as run:
            yield run

    def finish(self):
        self.manager._worker.join(timeout=4)
        self.assertFalse(self.manager._worker.is_alive())
        return self.manager.status()

    @staticmethod
    def script(call):
        args = call.args[0]
        return base64.b64decode(args[args.index("-EncodedCommand") + 1]).decode("utf-16le")

    @staticmethod
    def payload(script):
        match = re.search(r"FromBase64String\('([A-Za-z0-9+/=]+)'\)", script)
        return json.loads(base64.b64decode(match.group(1)).decode("utf-8"))

    def test_non_windows_never_spawns_commands_or_claims_windows_permission(self):
        with patch("phone_firewall.os.name", "posix"), patch("phone_firewall.subprocess.run") as run:
            for operation in [self.manager.status, self.manager.inspect, self.manager.request]:
                result = operation(8777)
                self.assertEqual(result["state"], "not_required")
                self.assertEqual(result["port"], 8777)
                self.assertIn("本地网络", result["message"])
            run.assert_not_called()

    def test_status_is_cached_and_never_launches_powershell(self):
        with self.windows([self.output(self.ready_rule())]) as run:
            self.assertEqual(self.manager.status()["state"], "unknown")
            run.assert_not_called()
            inspected = self.manager.inspect()
            self.assertEqual(inspected["state"], "ready")
            for _ in range(5):
                self.assertEqual(self.manager.status()["state"], "ready")
            self.assertEqual(run.call_count, 1)
            inspected["state"] = "changed externally"
            self.assertEqual(self.manager.status()["state"], "ready")

    def test_inspection_is_read_only_and_checks_only_owned_rule(self):
        with self.windows([self.output(self.ready_rule())]) as run:
            self.assertEqual(self.manager.inspect()["state"], "ready")
        call = run.call_args
        script = self.script(call)
        self.assertEqual(call.args[0][0], self.shell)
        self.assertEqual(call.kwargs["timeout"], firewall.INSPECT_TIMEOUT)
        self.assertEqual(self.payload(script), self.manager._payload(8767))
        for command in ["Get-NetFirewallRule", "Get-NetFirewallPortFilter", "Get-NetFirewallAddressFilter", "Get-NetFirewallApplicationFilter"]:
            self.assertIn(command, script)
        self.assertIn("-Name $p.name -PolicyStore ActiveStore", script)
        for command in ["Start-Process", "Set-Net", "New-Net", "Remove-Net", "ExecutionPolicy"]:
            self.assertNotIn(command, script)

    def test_missing_rule_requires_explicit_permission(self):
        with self.windows([self.output()]):
            state = self.manager.inspect()
        self.assertEqual(state["state"], "needs_permission")
        self.assertIn("Windows授权", state["message"])

    def test_broad_wrong_disabled_or_unrelated_rule_never_passes_inspection(self):
        changes = [
            {"exists": False}, {"name": "Another-Rule"}, {"group": "Other"}, {"enabled": "False"},
            {"direction": "Outbound"}, {"action": "Block"}, {"profiles": 7}, {"profiles": 2},
            {"edge": "Allow"}, {"program": self.manager.program + ".other"}, {"protocol": "UDP"},
            {"local_ports": ["Any"]}, {"local_ports": ["8767", "8768"]}, {"local_ports": ["8000-9000"]},
            {"remote_addresses": ["Any"]}, {"remote_addresses": ["LocalSubnet", "8.8.8.8"]},
            {"remote_ports": ["443"]}, {"local_addresses": ["192.168.9.9"]},
            {"service": "WinRM"}, {"interface_types": ["RemoteAccess"]},
        ]
        for changed in changes:
            with self.subTest(changed=changed):
                rule = {**self.ready_rule(), **changed}
                with self.windows([self.output(rule)]):
                    self.assertEqual(self.manager.inspect()["state"], "needs_permission")

    def test_protocol_number_and_case_insensitive_program_path_are_supported(self):
        rule = {**self.ready_rule(), "protocol": "6", "program": self.manager.program.upper()}
        with self.windows([self.output(rule)]):
            self.assertEqual(self.manager.inspect()["state"], "ready")

    def test_command_failure_bad_json_or_timeout_is_an_error(self):
        results = [self.output(code=1), SimpleNamespace(returncode=0, stdout=b"not-json"),
                   OSError("fixture"), subprocess.TimeoutExpired("fixture", 1)]
        for result in results:
            with self.subTest(result=result), self.windows([result]):
                state = self.manager.inspect()
                self.assertEqual(state["state"], "error")
                self.assertNotIn("fixture", state["message"])

    def test_request_returns_immediately_and_ready_requires_post_uac_inspection(self):
        with self.windows([self.output(), self.output(code=0), self.output(self.ready_rule())]) as run:
            initial = self.manager.request()
            self.assertEqual(initial["state"], "requesting")
            self.assertTrue(self.manager._worker.daemon)
            self.assertEqual(self.finish()["state"], "ready")
            self.assertEqual(run.call_count, 3)
            before, elevated, after = [self.script(call) for call in run.call_args_list]
            self.assertIn("Get-NetFirewallRule", before)
            self.assertIn("Start-Process", elevated)
            self.assertIn("Get-NetFirewallRule", after)

    def test_existing_verified_rule_does_not_prompt_uac_again(self):
        with self.windows([self.output(self.ready_rule())]) as run:
            self.assertEqual(self.manager.request()["state"], "requesting")
            self.assertEqual(self.finish()["state"], "ready")
            self.assertEqual(run.call_count, 1)
            self.assertNotIn("Start-Process", self.script(run.call_args))

    def test_elevated_script_is_fixed_scoped_and_has_no_policy_bypass(self):
        with self.windows([self.output(), self.output(), self.output(self.ready_rule())]) as run:
            self.manager.request()
            self.assertEqual(self.finish()["state"], "ready")
        wrapper = self.script(run.call_args_list[1])
        outer = self.payload(wrapper)
        self.assertEqual(outer["shell"], self.shell)
        inner = base64.b64decode(outer["command"]).decode("utf-16le")
        params = self.payload(inner)
        self.assertEqual(params, self.manager._payload(8767))
        self.assertRegex(params["name"], r"^AgentBoard-Phone-8767-[0-9a-f]{16}$")
        for required in ["-Verb RunAs", "-WindowStyle Hidden", "-Wait", "-PassThru"]:
            self.assertIn(required, wrapper)
        for required in ["New-NetFirewallRule -Name $p.name", "Remove-NetFirewallRule -Name $p.name",
                         "-Group 'AgentBoard'", "-Direction Inbound", "-Action Allow", "-Enabled True",
                         "-Profile Private,Public", "-Protocol TCP", "-LocalPort ([string]$p.port)",
                         "-Program $p.program", "-RemoteAddress LocalSubnet", "-EdgeTraversalPolicy Block"]:
            self.assertIn(required, inner)
        for forbidden in ["Set-NetFirewallProfile", "Set-NetConnectionProfile", "Set-ExecutionPolicy", "-ExecutionPolicy", "Bypass", "netsh", "SendKeys", "Remove-NetFirewallRule -Group"]:
            self.assertNotIn(forbidden, wrapper + inner)
        self.assertEqual(run.call_args_list[1].kwargs["timeout"], firewall.UAC_TIMEOUT)

    def test_program_text_is_data_even_with_quotes_or_shell_metacharacters(self):
        program = str(Path(tempfile.gettempdir()) / "AgentBoard ' ; $(not-a-command)" / "python.exe")
        manager = firewall.PhoneFirewall(program)
        payload = manager._payload(8767)
        script = firewall._rule_script(payload)
        self.assertEqual(self.payload(script)["program"], manager.program)
        self.assertNotIn("$(not-a-command)", script)
        self.assertNotIn(manager.program, script)
        other = firewall.PhoneFirewall(sys.executable)
        self.assertNotEqual(payload["name"], other._payload(8767)["name"])

    def test_cancelling_uac_is_reported_and_never_claims_ready(self):
        with self.windows([self.output(), self.output(code=1223)]) as run:
            self.manager.request()
            result = self.finish()
        self.assertEqual(result["state"], "error")
        self.assertIn("取消", result["message"])
        self.assertEqual(run.call_count, 2)

    def test_failed_elevation_is_reported_without_automatic_retry(self):
        for failure in [self.output(code=1), OSError("fixture"), subprocess.TimeoutExpired("fixture", 1)]:
            with self.subTest(failure=failure), self.windows([self.output(), failure]) as run:
                self.manager.request()
                result = self.finish()
                self.assertEqual(result["state"], "error")
                self.assertEqual(run.call_count, 2)
                self.assertNotIn("fixture", result["message"])

    def test_successful_process_exit_cannot_fake_an_unverified_rule(self):
        with self.windows([self.output(), self.output(code=0), self.output()]) as run:
            self.manager.request()
            result = self.finish()
        self.assertEqual(result["state"], "error")
        self.assertIn("未通过检查", result["message"])
        self.assertEqual(run.call_count, 3)

    def test_inspection_error_does_not_launch_uac_blindly(self):
        with self.windows([self.output(code=1)]) as run:
            self.manager.request()
            self.assertEqual(self.finish()["state"], "error")
            self.assertEqual(run.call_count, 1)

    def test_only_one_concurrent_request_and_status_polling_never_relaunches(self):
        entered, release = threading.Event(), threading.Event()
        counter = []
        def commands(*args, **kwargs):
            counter.append(args)
            if len(counter) == 1:
                return self.output()
            if len(counter) == 2:
                entered.set()
                if not release.wait(timeout=3):
                    raise AssertionError("fixture authorization barrier timed out")
                return self.output()
            return self.output(self.ready_rule())
        with self.windows(commands) as run:
            self.manager.request()
            try:
                self.assertTrue(entered.wait(timeout=2))
                worker = self.manager._worker
                self.assertEqual(self.manager.request()["state"], "requesting")
                self.assertEqual(self.manager.request(8777)["port"], 8767)
                self.assertEqual(self.manager.inspect()["state"], "requesting")
                self.assertEqual(self.manager.status()["state"], "requesting")
                self.assertIs(self.manager._worker, worker)
                self.assertEqual(run.call_count, 2)
            finally:
                release.set()
            self.assertEqual(self.finish()["state"], "ready")
            self.assertEqual(run.call_count, 3)

    def test_port_validation_and_program_are_not_request_controlled(self):
        with patch("phone_firewall.subprocess.run") as run:
            for operation in [self.manager.status, self.manager.inspect, self.manager.request]:
                for port in [True, 0, 1, -1, 65536, "8767; calc.exe"]:
                    with self.subTest(operation=operation.__name__, port=port), self.assertRaises(ValueError):
                        operation(port)
            with self.assertRaises(TypeError):
                self.manager.request(8767, program="evil.exe")
            run.assert_not_called()
        with self.assertRaises(ValueError):
            firewall.PhoneFirewall("relative-python.exe")


if __name__ == "__main__":
    unittest.main()
