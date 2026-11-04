"""Offline LAN-access security checks. Only disposable loopback listeners are used."""
import hashlib
import http.client
import io
import json
import socket
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import phone_access as phone


class Clock:
    def __init__(self):
        self.value = 1_800_000_000.0

    def __call__(self):
        return self.value


class PhoneAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.static = self.root / "static"
        self.static.mkdir()
        for name, content in [("phone-login.html", "<h1>Pair this phone</h1>"),
                              ("phone-login.js", "/* login fixture */"), ("phone-login.css", "/* style fixture */"),
                              ("app.js", "PRIVATE APP FIXTURE")]:
            (self.static / name).write_text(content, encoding="utf-8")
        self.calls = []
        calls = self.calls

        class BoardHandler(BaseHTTPRequestHandler):
            def result(self, body):
                encoded = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_GET(self):
                calls.append(("GET", self.path))
                self.result({"board": "shared state", "remote": self.server.phone_remote})

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                calls.append(("POST", self.path, body))
                self.result({"board": "shared state"})

        self.handler = BoardHandler
        self.clock = Clock()
        self.interfaces = [{"address": "127.0.0.1", "label": "Offline loopback fixture", "prefix": 8}]
        self.access = self.manager()

    def manager(self, interfaces=None):
        value = phone.PhoneAccess(self.handler, self.root / "data", self.static,
                                  interfaces=self.interfaces if interfaces is None else interfaces, clock=self.clock)
        self.addCleanup(value.shutdown)
        return value

    def start(self):
        result = self.access.enable(port=0)
        self.port = result["port"]
        self.origin = result["origin"]
        return result

    def request(self, path, method="GET", body=None, cookie=None, headers=None, manager=None):
        access = manager or self.access
        state = access.status()
        connection = http.client.HTTPConnection("127.0.0.1", state["port"], timeout=3)
        actual = {}
        if method not in ("GET", "HEAD"):
            actual["Origin"] = state["origin"]
        if cookie:
            actual["Cookie"] = cookie
        if body is not None and not isinstance(body, bytes):
            body = json.dumps(body).encode()
            actual["Content-Type"] = "application/json"
        actual.update(headers or {})
        if actual.get("Origin") is None:
            actual.pop("Origin", None)
        try:
            connection.request(method, path, body=body, headers=actual)
            response = connection.getresponse()
            data, response_headers = response.read(), dict(response.getheaders())
            try:
                data = json.loads(data)
            except ValueError:
                data = data.decode("utf-8")
            return response.status, data, response_headers
        finally:
            connection.close()

    def pair(self, name="Android fixture", manager=None):
        access = manager or self.access
        result = self.request("/phone/pair", "POST", {"code": access.status()["pairing_code"], "name": name}, manager=access)
        self.assertEqual(result[0], 200, result[1])
        return result[2]["Set-Cookie"].split(";", 1)[0], result[1]["data"]["device_id"]

    def test_default_closed_has_no_code_device_file_or_listener(self):
        state = self.access.status()
        self.assertFalse(state["enabled"])
        self.assertFalse(state["running"])
        self.assertEqual(state["origin"], "")
        self.assertIsNone(state["pairing_code"])
        self.assertEqual(state["devices"], [])
        self.assertFalse(self.access.path.exists())
        with self.assertRaises(ValueError):
            self.access.new_code()

    def test_enable_only_allows_an_explicit_current_private_interface(self):
        with patch("phone_access.private_ipv4_interfaces", return_value=[{"address": "192.168.7.10", "label": "Wi-Fi", "prefix": 24}]):
            production = phone.PhoneAccess(self.handler, self.root / "other", self.static)
        self.addCleanup(production.shutdown)
        for address in ["0.0.0.0", "127.0.0.1", "8.8.8.8", "192.168.7.11", "localhost", "::1"]:
            with self.subTest(address=address), self.assertRaises(ValueError):
                production.enable(address)
        self.assertFalse(production.status()["running"])
        self.assertFalse(production.path.exists())

    def test_bind_applies_platform_socket_ownership_before_parent_bind(self):
        for platform in ("posix", "nt"):
            with self.subTest(platform=platform):
                server = object.__new__(phone._LANServer)
                server.socket = Mock()
                observed = []

                def parent_bind():
                    observed.append((server.allow_reuse_address, list(server.socket.mock_calls)))

                with patch("phone_access.os.name", platform), \
                        patch.object(phone.socket, "SO_EXCLUSIVEADDRUSE", 12345, create=True), \
                        patch.object(phone.ThreadingHTTPServer, "server_bind", side_effect=parent_bind):
                    server.server_bind()

                self.assertEqual(len(observed), 1)
                reuse, socket_calls = observed[0]
                self.assertEqual(reuse, platform == "posix")
                if platform == "nt":
                    server.socket.setsockopt.assert_called_once_with(socket.SOL_SOCKET, 12345, 1)
                    self.assertEqual(len(socket_calls), 1)
                else:
                    server.socket.setsockopt.assert_not_called()
                    self.assertEqual(socket_calls, [])

    def test_second_gateway_cannot_take_an_active_listener_port(self):
        self.start()
        cookie, _ = self.pair()
        contender = self.manager()
        with self.assertRaises(ValueError):
            contender.enable("127.0.0.1", self.port)
        self.assertFalse(contender.status()["running"])
        self.assertEqual(self.request("/api/state", cookie=cookie)[0], 200)

    def test_enable_uses_one_listener_and_rejects_invalid_ports(self):
        for port in [True, -1, 1, 65536, "8767"]:
            with self.subTest(port=port), self.assertRaises(ValueError):
                self.access.enable(port=port)
        state = self.start()
        server = self.access._server
        self.assertEqual(server.server_address[0], "127.0.0.1")
        self.assertTrue(server.phone_remote)
        self.assertEqual(server.phone_origin, self.origin)
        self.assertEqual(len(state["pairing_code"]), 8)
        self.access.enable("127.0.0.1", state["port"])
        self.assertIs(self.access._server, server)

    def test_unpaired_only_sees_login_and_its_two_assets(self):
        self.start()
        for path in ["/", "/phone/login", "/index.html", "/other.html"]:
            status, body, headers = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn("Pair this phone", body)
            self.assertIn("no-store", headers["Cache-Control"])
        for path in ["/static/phone-login.js", "/static/phone-login.css"]:
            self.assertEqual(self.request(path)[0], 200)
        for path in ["/api/state", "/phone/client", "/static/app.js", "/static/../app.js"]:
            self.assertEqual(self.request(path)[0], 401)
        self.assertEqual(self.calls, [])

    def test_pair_creates_hash_only_cookie_and_single_use_code(self):
        state = self.start()
        code = state["pairing_code"]
        status, body, headers = self.request("/phone/pair", "POST", {"code": code, "name": "我的安卓"})
        self.assertEqual(status, 200)
        self.assertTrue(body["data"]["remote"])
        cookie = headers["Set-Cookie"]
        for attribute in ["HttpOnly", "SameSite=Strict", "Path=/", "Max-Age=2592000"]:
            self.assertIn(attribute, cookie)
        token = cookie.split(";", 1)[0].split("=", 1)[1]
        self.assertGreaterEqual(len(token), 32)
        saved = self.access.path.read_text(encoding="utf-8")
        self.assertNotIn(token, saved)
        self.assertNotIn(code, saved)
        self.assertNotIn("pairing_code", saved)
        self.assertIn(hashlib.sha256(token.encode()).hexdigest(), saved)
        self.assertIsNone(self.access.status()["pairing_code"])
        self.assertNotIn("token_hash", json.dumps(self.access.status()))
        self.assertEqual(self.request("/phone/pair", "POST", {"code": code})[0], 401)
        self.assertEqual(self.request("/api/state", cookie=cookie)[0], 200)
        self.assertEqual(self.calls[-1], ("GET", "/api/state"))
        client = self.request("/phone/client", cookie=cookie)
        self.assertEqual(client[1], {"remote": True, "device_id": body["data"]["device_id"], "name": "我的安卓"})

    def test_host_and_origin_are_strict_even_for_paired_devices(self):
        self.start()
        for bad in ["localhost:" + str(self.port), "evil.example:" + str(self.port), "127.0.0.1"]:
            self.assertEqual(self.request("/phone/login", headers={"Host": bad})[0], 403)
        for origin in [None, "null", "http://evil.example", self.origin + "/"]:
            self.assertEqual(self.request("/phone/pair", "POST", {"code": self.access.status()["pairing_code"]}, headers={"Origin": origin})[0], 403)
        cookie, _ = self.pair()
        self.assertEqual(self.request("/api/state", cookie=cookie, headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("/api/state", cookie=cookie, headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.request("/api/tasks", "POST", {}, cookie=cookie, headers={"Origin": None})[0], 403)
        self.assertEqual(self.request("/api/tasks", "POST", {}, cookie=cookie)[0], 200)

    def test_pair_body_is_bounded_and_validated(self):
        self.start()
        self.assertEqual(self.request("/phone/pair", "POST", b"x" * 4097)[0], 413)
        for payload in [b"not-json", [], {"code": "１２３４５６７８"}, {"code": self.access.status()["pairing_code"], "name": "bad\nname"}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.request("/phone/pair", "POST", payload)[0], 400)
        self.assertEqual(self.access.status()["devices"], [])

    def test_pair_rejects_codes_in_query_and_transfer_encoding(self):
        self.start()
        code = self.access.status()["pairing_code"]
        self.assertEqual(self.request("/phone/pair?code=" + code, "POST", {"code": code})[0], 400)
        self.assertEqual(self.request("/phone/pair", "POST", {}, headers={"Transfer-Encoding": "identity"})[0], 400)
        self.assertEqual(self.access.status()["pairing_code"], code)

    def test_pair_attempts_are_limited_by_ip_and_window_recovers(self):
        self.start()
        wrong = "00000000" if self.access.status()["pairing_code"] != "00000000" else "11111111"
        for _ in range(phone.PAIR_IP_LIMIT):
            self.assertEqual(self.request("/phone/pair", "POST", {"code": wrong})[0], 401)
        self.assertEqual(self.request("/phone/pair", "POST", {"code": self.access.status()["pairing_code"]})[0], 429)
        self.clock.value += 61
        self.pair()

    def test_pair_global_limit_prevents_rotating_ip_bypass(self):
        self.start()
        with self.access._lock:
            for number in range(phone.PAIR_GLOBAL_LIMIT):
                self.assertTrue(self.access._allow_pair_attempt("10.0.0." + str(number + 1)))
        self.assertEqual(self.request("/phone/pair", "POST", {"code": self.access.status()["pairing_code"]})[0], 429)
        self.clock.value += 61
        self.pair()

    def test_pair_code_expires_and_manual_new_code_reopens_pairing(self):
        state = self.start()
        old = state["pairing_code"]
        self.clock.value += phone.PAIR_SECONDS
        self.assertIsNone(self.access.status()["pairing_code"])
        self.assertEqual(self.request("/phone/pair", "POST", {"code": old})[0], 401)
        refreshed = self.access.new_code()
        self.assertIsNotNone(refreshed["pairing_code"])
        self.assertGreater(refreshed["pairing_expires_at"], state["pairing_expires_at"])
        self.pair()

    def test_session_expires_after_thirty_days(self):
        self.start()
        cookie, _ = self.pair()
        self.clock.value += phone.SESSION_SECONDS
        self.assertEqual(self.request("/api/state", cookie=cookie)[0], 401)
        self.assertEqual(self.access.status()["devices"], [])

    def test_logout_revokes_only_own_cookie(self):
        self.start()
        first, _ = self.pair("First phone")
        self.access.new_code()
        second, second_id = self.pair("Second phone")
        status, _, headers = self.request("/phone/logout", "POST", {}, cookie=first)
        self.assertEqual(status, 200)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        self.assertEqual(self.request("/api/state", cookie=first)[0], 401)
        self.assertEqual(self.request("/api/state", cookie=second)[0], 200)
        self.assertEqual([device["id"] for device in self.access.status()["devices"]], [second_id])

    def test_desktop_revoke_invalidates_cookie_immediately(self):
        self.start()
        cookie, device_id = self.pair()
        self.assertEqual(self.access.revoke(device_id)["devices"], [])
        self.assertEqual(self.request("/api/state", cookie=cookie)[0], 401)
        self.assertEqual(json.loads(self.access.path.read_text())["devices"], [])

    def test_disable_closes_listener_and_erases_all_sessions(self):
        self.start()
        cookie, _ = self.pair()
        state = self.access.disable()
        self.assertFalse(state["enabled"])
        self.assertFalse(state["running"])
        self.assertEqual(state["devices"], [])
        self.assertIsNone(state["pairing_code"])
        saved = json.loads(self.access.path.read_text())
        self.assertFalse(saved["enabled"])
        self.assertEqual(saved["devices"], [])
        self.start()
        self.assertEqual(self.request("/api/state", cookie=cookie)[0], 401)

    def test_restart_restores_valid_devices_without_generating_pair_code(self):
        self.start()
        cookie, device_id = self.pair()
        port = self.port
        self.access.shutdown()
        self.assertTrue(json.loads(self.access.path.read_text())["enabled"])
        restored = self.manager()
        with patch("phone_access.secrets.randbelow") as random_code:
            state = restored.restore()
        random_code.assert_not_called()
        self.assertTrue(state["running"], state)
        self.assertEqual(state["port"], port)
        self.assertIsNone(state["pairing_code"])
        self.assertEqual(state["devices"][0]["id"], device_id)
        self.assertEqual(self.request("/api/state", cookie=cookie, manager=restored)[0], 200)

    def test_restore_never_binds_a_missing_interface_or_wildcard(self):
        self.start()
        self.pair()
        self.access.shutdown()
        restored = self.manager(interfaces=[])
        state = restored.restore()
        self.assertTrue(state["enabled"])
        self.assertFalse(state["running"])
        self.assertEqual(state["origin"], "")
        self.assertTrue(state["error"])
        self.assertIsNone(state["pairing_code"])

    def test_corrupt_saved_state_is_closed_and_does_not_leak_details(self):
        self.access.path.parent.mkdir()
        for contents in ["not-json", "[]", json.dumps({"version": 1, "enabled": True, "devices": [{"token_hash": "a" * 64, "id": "fixture", "name": "fixture", "last_seen": None, "expires_at": None}]})]:
            with self.subTest(contents=contents):
                self.access.path.write_text(contents, encoding="utf-8")
                state = self.manager().restore()
                self.assertFalse(state["running"])
                self.assertTrue(state["error"])
                self.assertNotIn(str(self.root), state["error"])

    def test_remote_management_and_desktop_mutations_are_blocked(self):
        self.start()
        cookie, _ = self.pair()
        for path in ["/api/phone-access", "/api/phone-access/status", "/api/system/doctor", "/api/system/restart", "/api/pick-path"]:
            for method in ["GET", "POST"]:
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.request(path, method, {} if method == "POST" else None, cookie=cookie)[0], 403)
        for path in ["/api/agents", "/api/agents/test", "/api/model-settings", "/api/executors/activate", "/api/settings"]:
            self.assertEqual(self.request(path, "POST", {}, cookie=cookie)[0], 403)
        for path in ["/api/agents", "/api/projects", "/api/tasks", "/api/chats", "/api/missions"]:
            self.assertEqual(self.request(path, cookie=cookie)[0], 200)
        for path in ["/api/projects", "/api/tasks", "/api/chats/fixture/send", "/api/missions/fixture/resume"]:
            self.assertEqual(self.request(path, "POST", {}, cookie=cookie)[0], 200)

    def test_remote_requests_never_log_code_cookie_or_query_strings(self):
        self.start()
        code = self.access.status()["pairing_code"]
        with patch.object(BaseHTTPRequestHandler, "log_message") as logged:
            self.request("/phone/login?code=" + code)
            cookie, _ = self.pair()
            self.request("/api/state", cookie=cookie)
        logged.assert_not_called()

    def test_unsupported_methods_require_authentication_and_do_not_forward(self):
        self.start()
        self.assertEqual(self.request("/api/state", "HEAD")[0], 401)
        cookie, _ = self.pair()
        self.assertEqual(self.request("/api/tasks", "DELETE", cookie=cookie)[0], 405)
        self.assertEqual(self.calls, [])

    def test_foreign_subnet_is_denied_before_any_board_handler(self):
        self.start()
        handler = object.__new__(self.access._server.RequestHandlerClass)
        handler.client_address = ("10.55.0.10", 34567)
        handler._json = Mock()
        self.assertFalse(handler._basic())
        self.assertEqual(handler._json.call_args.args[0], 403)
        self.assertEqual(self.calls, [])

    def test_handshake_diagnostics_are_sanitized_desktop_only_and_not_persisted(self):
        initial = self.start()
        code = initial["pairing_code"]
        self.request("/private-request-fixture?code=QUERY_SECRET_FIXTURE")
        cookie, _ = self.pair("PRIVATE_DEVICE_NAME_FIXTURE")
        self.request("/phone/client?token=QUERY_SECRET_FIXTURE", cookie=cookie,
                     headers={"User-Agent": "PRIVATE_USER_AGENT_FIXTURE"})
        self.request("/api/state", cookie=cookie)
        status, body, _ = self.request("/api/phone-access", cookie=cookie)
        self.assertEqual(status, 403)
        self.assertNotIn("handshake_checks", json.dumps(body))
        checks = self.access.status()["handshake_checks"]
        self.assertTrue(checks)
        for record in checks:
            self.assertEqual(set(record), {"at", "path", "cookie_present", "authenticated", "reason"})
            self.assertIn(record["path"], ("/", "/phone/client", "/api/state", "/phone/pair", "other"))
            self.assertIsInstance(record["cookie_present"], bool)
            self.assertIsInstance(record["authenticated"], bool)
        encoded = json.dumps(checks)
        token = cookie.split("=", 1)[1]
        for secret in [code, token, hashlib.sha256(token.encode()).hexdigest(), "QUERY_SECRET_FIXTURE",
                       "PRIVATE_USER_AGENT_FIXTURE", "PRIVATE_DEVICE_NAME_FIXTURE", "/private-request-fixture", "127.0.0.1"]:
            self.assertNotIn(secret, encoded)
        self.assertNotIn("handshake_checks", self.access.path.read_text(encoding="utf-8"))
        checks[0]["reason"] = "external mutation"
        self.assertNotEqual(self.access.status()["handshake_checks"][0]["reason"], "external mutation")
        self.assertEqual(self.manager().status()["handshake_checks"], [])

    def test_handshake_distinguishes_cookie_and_session_failure_reasons(self):
        self.start()
        self.assertEqual(self.request("/api/state")[0], 401)
        self.assertEqual(self.request("/api/state", cookie=phone.COOKIE_NAME + "=bad")[0], 401)
        self.assertEqual(self.request("/api/state", cookie=phone.COOKIE_NAME + "=" + "unknown_fixture_" * 3)[0], 401)
        cookie, _ = self.pair()
        self.assertEqual(self.request("/phone/client", cookie=cookie)[0], 200)
        self.clock.value += phone.SESSION_SECONDS
        self.assertEqual(self.request("/api/state", cookie=cookie)[0], 401)
        # Simulate an already accepted request reaching its auth check after
        # disable() has invalidated the in-memory session set.
        with self.access._lock:
            self.access._enabled = False
        self.assertEqual(self.request("/api/state", cookie=cookie)[0], 401)
        checks = self.access.status()["handshake_checks"]
        self.assertEqual([record["reason"] for record in checks],
                         ["missing_cookie", "invalid_cookie", "unknown_session", "pair_issued", "ok", "expired", "disabled"])
        self.assertFalse(checks[0]["cookie_present"])
        self.assertTrue(checks[1]["cookie_present"])
        self.assertFalse(checks[3]["authenticated"])
        self.assertTrue(checks[4]["authenticated"])

    def test_handshake_memory_is_bounded_and_static_assets_do_not_bury_the_chain(self):
        self.start()
        for _ in range(30):
            self.request("/api/state?code=DO_NOT_SAVE_QUERY")
            self.clock.value += 1
        checks = self.access.status()["handshake_checks"]
        self.assertEqual(len(checks), 20)
        self.assertTrue(all(record["path"] == "/api/state" for record in checks))
        before = [dict(record) for record in checks]
        self.request("/static/app.js")
        self.assertEqual(self.access.status()["handshake_checks"], before)

    def test_failed_rebind_keeps_existing_listener_and_paired_session(self):
        self.start()
        cookie, _ = self.pair()
        original = self.access._server
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen(1)
            with self.assertRaises(ValueError):
                self.access.enable("127.0.0.1", occupied.getsockname()[1])
        self.assertIs(self.access._server, original)
        self.assertTrue(self.access.status()["running"])
        self.assertEqual(self.request("/api/state", cookie=cookie)[0], 200)


class InterfaceDiscoveryTests(unittest.TestCase):
    def test_windows_discovery_prefers_real_default_lan_and_filters_virtual_public(self):
        rows = [
            {"address": "10.2.3.4", "label": "Ethernet", "prefix": 24, "hardware": True},
            {"address": "192.168.4.8", "label": "家庭 Wi-Fi", "prefix": 24, "hardware": True, "default": True},
            {"address": "172.18.0.1", "label": "vEthernet (WSL)", "prefix": 16, "virtual": True},
            {"address": "100.100.1.8", "label": "Carrier", "prefix": 24},
            {"address": "8.8.8.8", "label": "Public", "prefix": 24},
            {"address": "169.254.1.2", "label": "Unconfigured", "prefix": 16},
            {"address": "192.168.1.1", "label": "Invalid prefix", "prefix": 0},
        ]
        result = SimpleNamespace(stdout=json.dumps(rows, ensure_ascii=False).encode("utf-8"))
        with patch("phone_access.os.name", "nt"), patch("phone_access.subprocess.run", return_value=result) as run:
            actual = phone.private_ipv4_interfaces()
        self.assertEqual([row["address"] for row in actual], ["192.168.4.8", "10.2.3.4"])
        self.assertEqual(actual[0]["label"], "家庭 Wi-Fi")
        self.assertEqual(run.call_args.args[0][:3], ["powershell.exe", "-NoProfile", "-NonInteractive"])

    def test_discovery_failure_returns_no_guess_instead_of_wildcard(self):
        with patch("phone_access.subprocess.run", side_effect=OSError("fixture")):
            self.assertEqual(phone.private_ipv4_interfaces(), [])


if __name__ == "__main__":
    unittest.main()
