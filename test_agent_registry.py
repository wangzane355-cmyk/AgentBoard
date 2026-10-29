"""Offline adapter contract checks; only a loopback fake provider is contacted."""
import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from agent_registry import AgentRegistry
from group_chat import route_message, strip_handoff


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.registry = AgentRegistry(Path(self.tmp.name))

    def test_configuration_never_persists_key_values(self):
        body = {"id": "api-test", "name": "API", "kind": "api", "endpoint": "https://provider.example/v1/chat/completions", "model": "test", "key_env": "AGENTBOARD_FAKE_KEY", "api_key": "do-not-store"}
        with patch.dict(os.environ, {"AGENTBOARD_FAKE_KEY": "secret-fixture"}):
            public = self.registry.save(body)
            self.assertTrue(public["configured"])
            self.assertNotIn("secret-fixture", json.dumps(public))
        self.assertNotIn("secret-fixture", self.registry.path.read_text())
        self.assertNotIn("do-not-store", self.registry.path.read_text())
        self.assertFalse(self.registry.get("api-test")["can_implement"])

    def test_reserved_ids_and_unsafe_endpoint_are_rejected(self):
        for agent in ("codex", "all", "ds", "discuss", "../escape"):
            with self.assertRaises(ValueError):
                self.registry.save({"id": agent, "name": "Invalid", "kind": "mock"})
        for endpoint in ("http://provider.example/v1/chat/completions", "https://user:secret@provider.example/v1/chat/completions", "https://provider.example/v1/chat/completions?key=secret"):
            with self.assertRaises(ValueError):
                self.registry.save({"id": "api-test", "name": "Invalid", "kind": "api", "endpoint": endpoint, "model": "test", "key_env": "KEY"})

    def test_custom_routing_is_direct_and_handoffs_are_bounded(self):
        members = ["one", "two", "three"]
        direct = route_message("/two Hello", "group", "all", members, 3, agents=members)
        self.assertEqual(direct["recipients"], ["two"])
        self.assertEqual(direct["max_replies"], 1)
        broadcast = route_message("/discuss 3 Hello", "group", "all", members, agents=members)
        self.assertEqual(broadcast["max_replies"], 6)
        self.assertEqual(strip_handoff("Reply\nAGENTBOARD_TO: two", "one", members), ("Reply", "two"))
        self.assertIsNone(strip_handoff("Reply\nAGENTBOARD_TO: outside", "one", members)[1])
        with self.assertRaises(ValueError):
            route_message("Hello", "group", "all", members, agents=["one", "two"])

    def test_api_worker_against_local_fake_provider_and_error_redaction(self):
        seen = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append((self.path, self.headers.get("Authorization"), body))
                if body['model'] == 'redirect':
                    self.send_response(302)
                    self.send_header('Location', '/must-not-follow')
                    self.end_headers()
                    return
                if body['model'] == 'error':
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b'secret-fixture must not reach diagnostics')
                    return
                response = json.dumps({"choices": [{"message": {"content": "LOCAL_FAKE_OK"}}]}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(response)
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for model, expected_code in [('fixture', 0), ('error', 1), ('redirect', 1)]:
                self.registry.save({"id": "api-test", "name": "Fake", "kind": "api", "endpoint": f"http://127.0.0.1:{server.server_port}/v1/chat/completions", "model": model, "key_env": "AGENTBOARD_FAKE_KEY"})
                cmd = self.registry.command('api-test', Path(self.tmp.name), Path(self.tmp.name)/'answer.txt')
                result = subprocess.run(cmd, input=b'local fixture prompt', capture_output=True, env={**os.environ, 'AGENTBOARD_FAKE_KEY':'secret-fixture'}, timeout=15)
                self.assertEqual(result.returncode, expected_code)
                self.assertNotIn(b'secret-fixture', result.stdout + result.stderr)
                if expected_code == 0:
                    self.assertEqual(result.stdout, b'LOCAL_FAKE_OK')
            self.assertEqual(seen[0][1], 'Bearer secret-fixture')
            self.assertEqual(seen[0][2]['messages'][0]['content'], 'local fixture prompt')
            self.assertEqual(len(seen), 3)  # The redirect did not trigger a second request.
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
