"""Offline integration of paired phone access with the real board handler."""
import contextlib
import http.client
import json
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

import test_server as fixtures
from phone_access import PhoneAccess


class PhoneServerTests(unittest.TestCase):
    def setUp(self):
        fixtures.BoardTests.setUp(self)
        self.board.MANAGED_PROJECTS = Path(self.tmp.name) / "managed-projects"
        self.manager = PhoneAccess(self.board.Handler, self.board.DATA, self.board.STATIC,
            interfaces=lambda: [{"address": "127.0.0.1", "label": "Offline loopback fixture", "prefix": 8}])
        self.board._PHONE_ACCESS = self.manager
        self.firewall = Mock()
        self.firewall.status.side_effect = lambda port=8767: {"state": "unknown", "message": "Offline fixture", "port": port}
        self.board._PHONE_FIREWALL = self.firewall
        self.addCleanup(self.manager.shutdown)

    tearDown = fixtures.BoardTests.tearDown

    @staticmethod
    def request(port, method, path, body=None, cookie=None, origin=None, host=None):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if cookie:
            headers["Cookie"] = cookie
        if origin is not None:
            headers["Origin"] = origin
        if host is not None:
            headers["Host"] = host
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        try:
            connection.request(method, path, payload, headers)
            response = connection.getresponse()
            content = response.read()
            metadata = dict(response.getheaders())
            try:
                content = json.loads(content)
            except (ValueError, UnicodeDecodeError):
                content = content.decode("utf-8", errors="replace")
            return response.status, content, metadata
        finally:
            connection.close()

    @contextlib.contextmanager
    def desktop(self):
        server = self.board.ThreadingHTTPServer(("127.0.0.1", 0), self.board.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)

    def pair(self, status):
        port = status["port"]
        code, result, headers = self.request(port, "POST", "/phone/pair",
            {"code": status["pairing_code"], "device_name": "Offline phone"}, origin=status["origin"])
        self.assertEqual(code, 200, result)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        return cookie, result["data"]["device_id"]

    def test_default_status_and_pairing_secrets_stay_desktop_only(self):
        with self.desktop() as port:
            code, status, _ = self.request(port, "GET", "/api/phone-access")
            self.assertEqual(code, 200)
            self.assertFalse(status["running"])
            self.assertFalse(status["enabled"])
            code, client, _ = self.request(port, "GET", "/phone/client")
            self.assertEqual((code, client), (200, {"remote": False}))
            code, enabled, _ = self.request(port, "POST", "/api/phone-access/enable", {"address": "127.0.0.1", "port": 0})
            self.assertEqual(code, 200, enabled)
            status = enabled["data"]
            self.assertTrue(status["running"])
            code, public, _ = self.request(port, "GET", "/api/state")
            self.assertEqual(code, 200)
            self.assertNotIn("pairing_code", json.dumps(public))
            self.assertNotIn("agentboard_phone_session", json.dumps(public))
            code, page, _ = self.request(status["port"], "GET", "/")
            self.assertEqual(code, 200)
            self.assertIn("phone-login.js", page)
            code, data, _ = self.request(status["port"], "GET", "/api/state")
            self.assertEqual(code, 401, data)
            cookie, _ = self.pair(status)
            code, _, _ = self.request(status["port"], "GET", "/api/phone-access", cookie=cookie)
            self.assertEqual(code, 403)

    def test_paired_phone_creates_project_and_chat_in_the_same_board_and_can_be_revoked(self):
        status = self.manager.enable(address="127.0.0.1", port=0)
        cookie, device_id = self.pair(status)
        code, response, _ = self.request(status["port"], "POST", "/api/projects",
            {"name": "Phone idea", "managed_directory": True}, cookie, status["origin"])
        self.assertEqual(code, 200, response)
        project = response["data"]
        self.assertIn(project, self.board.STATE["projects"])
        self.assertTrue(Path(project["path"]).is_dir())
        # Windows runners may spell the temporary root with an 8.3 alias.
        self.assertTrue(Path(project["path"]).resolve().is_relative_to(self.board.MANAGED_PROJECTS.resolve()))
        code, response, _ = self.request(status["port"], "POST", "/api/chats",
            {"project_id": project["id"], "agent": "codex"}, cookie, status["origin"])
        self.assertEqual(code, 200, response)
        self.assertEqual(self.board.STATE["chats"][-1]["id"], response["data"]["id"])
        for path in ("/api/system/shutdown", "/api/system/restart", "/api/pick-path", "/api/agents", "/api/agents/model-settings", "/api/executors/activate", "/api/phone-access/disable"):
            with self.subTest(path=path):
                code, _, _ = self.request(status["port"], "POST", path, {}, cookie, status["origin"])
                self.assertEqual(code, 403)
        code, _, _ = self.request(status["port"], "POST", "/api/projects", {"name": "No origin", "managed_directory": True}, cookie)
        self.assertEqual(code, 403)
        code, _, _ = self.request(status["port"], "POST", "/api/projects", {"name": "Wrong origin", "managed_directory": True}, cookie, "http://attacker.invalid")
        self.assertEqual(code, 403)
        self.assertEqual(len(self.board.STATE["projects"]), 2)
        with self.desktop() as port:
            code, _, _ = self.request(port, "POST", "/api/phone-access/revoke", {"device_id": device_id})
            self.assertEqual(code, 200)
        code, _, _ = self.request(status["port"], "GET", "/api/state", cookie=cookie)
        self.assertEqual(code, 401)

    def test_firewall_permission_uses_only_active_port_and_cannot_be_requested_by_phone(self):
        with self.desktop() as port:
            code, _, _ = self.request(port, "POST", "/api/phone-access/firewall", {})
            self.assertEqual(code, 400)
            self.firewall.request.assert_not_called()
            status = self.manager.enable(address="127.0.0.1", port=0)
            code, result, _ = self.request(port, "POST", "/api/phone-access/firewall", {"port": 9999, "program": "untrusted.exe"})
            self.assertEqual(code, 200, result)
            self.firewall.request.assert_called_once_with(port=status["port"])
            code, _, _ = self.request(port, "POST", "/api/phone-access/firewall-check", {})
            self.assertEqual(code, 200)
            self.firewall.inspect.assert_called_once_with(port=status["port"])
            cookie, _ = self.pair(status)
            code, _, _ = self.request(status["port"], "POST", "/api/phone-access/firewall", {}, cookie, status["origin"])
            self.assertEqual(code, 403)
            self.assertEqual(self.firewall.request.call_count, 1)

    def test_invalid_host_and_origin_cannot_read_pairing_code_or_enable_access(self):
        with self.desktop() as port:
            code, _, _ = self.request(port, "GET", "/api/phone-access", host="attacker.invalid")
            self.assertEqual(code, 403)
            code, _, _ = self.request(port, "POST", "/api/phone-access/enable", {}, origin="http://attacker.invalid")
            self.assertEqual(code, 403)
            self.assertFalse(self.manager.status()["enabled"])

    def test_managed_project_folders_are_unique_contained_and_keep_original_titles(self):
        name = "../First\\idea: draft?"
        first = self.board.create_project({"name": name, "managed_directory": True})
        second = self.board.create_project({"name": name, "managed_directory": True})
        self.assertEqual(first["name"], name)
        self.assertNotEqual(first["path"], second["path"])
        for project in (first, second):
            root = Path(project["path"])
            self.assertTrue(root.is_dir())
            self.assertEqual(root.parent, self.board.MANAGED_PROJECTS.resolve())
            self.assertFalse(any(char in root.name for char in '<>:"/\\|?*'))
        reserved = self.board.create_project({"name": "CON", "managed_directory": True})
        self.assertTrue(Path(reserved["path"]).is_dir())

    def test_invalid_managed_metadata_has_no_folder_or_state_side_effect(self):
        count = len(self.board.STATE["projects"])
        for changes in ({"name": ""}, {"managed_directory": "yes"}, {"check": "invalid"}, {"create_directory": False}, {"path": str(self.source)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.board.create_project({"name": "Phone project", "managed_directory": True, **changes})
            self.assertFalse(self.board.MANAGED_PROJECTS.exists())
            self.assertEqual(len(self.board.STATE["projects"]), count)


if __name__ == "__main__":
    unittest.main()
