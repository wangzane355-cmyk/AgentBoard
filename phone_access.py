"""Opt-in, paired-device access to one private IPv4 interface on a trusted LAN.

This is an HTTP listener for a trusted home network, not an Internet server.
It reuses the board handler and state; it never starts another supervisor.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.cookies import CookieError, SimpleCookie
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


COOKIE_NAME = "agentboard_phone_session"
PAIR_SECONDS = 5 * 60
SESSION_SECONDS = 30 * 24 * 60 * 60
PAIR_IP_LIMIT = 5
PAIR_GLOBAL_LIMIT = 30
RFC1918 = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def _private(address):
    try:
        value = ipaddress.ip_address(address)
        return isinstance(value, ipaddress.IPv4Address) and any(value in network for network in RFC1918)
    except ValueError:
        return False


def _iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds")


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Invalid timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp needs a time zone")
    return parsed.timestamp()


def private_ipv4_interfaces():
    """Read real private LAN adapters; never guess a subnet or use a wildcard."""
    try:
        if os.name == "nt":
            script = r'''
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$routes = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue)
$adapters = @(Get-NetAdapter -IncludeHidden -ErrorAction SilentlyContinue)
$rows = @(Get-NetIPAddress -AddressFamily IPv4 -AddressState Preferred -ErrorAction Stop | ForEach-Object {
 $ip = $_
 $nic = $adapters | Where-Object { $_.ifIndex -eq $ip.InterfaceIndex } | Select-Object -First 1
 $route = $routes | Where-Object { $_.InterfaceIndex -eq $ip.InterfaceIndex } | Sort-Object RouteMetric | Select-Object -First 1
 [pscustomobject]@{address=$ip.IPAddress;label=$ip.InterfaceAlias;prefix=$ip.PrefixLength;virtual=($nic.Virtual -eq $true);hardware=($nic.HardwareInterface -eq $true);default=($null -ne $route);metric=$route.RouteMetric}
})
ConvertTo-Json -InputObject $rows -Compress
'''
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                    capture_output=True, timeout=8, check=True,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            rows = json.loads(result.stdout.decode("utf-8-sig"))
            if isinstance(rows, dict):
                rows = [rows]
        else:
            result = subprocess.run(["ip", "-j", "-4", "address", "show", "up"],
                                    capture_output=True, timeout=5, check=True)
            addresses = json.loads(result.stdout)
            try:
                result = subprocess.run(["ip", "-j", "-4", "route", "show", "default"],
                                        capture_output=True, timeout=5, check=True)
                defaults = {item["dev"] for item in json.loads(result.stdout) if "dev" in item}
            except (OSError, ValueError, subprocess.SubprocessError):
                defaults = set()
            rows = [{"address": item.get("local"), "label": row.get("ifname", ""),
                     "prefix": item.get("prefixlen"), "default": row.get("ifname") in defaults}
                    for row in addresses for item in row.get("addr_info", []) if item.get("family") == "inet"]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    if not isinstance(rows, list):
        return []
    valid = []
    virtual_names = ("vethernet", "hyper-v", "virtual", "vmware", "docker", "wsl", "tailscale", "wireguard", "zerotier", "vpn")
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label", ""))
        lower = label.lower()
        if (row.get("virtual") or any(name in lower for name in virtual_names)
                or lower.startswith(("veth", "virbr", "br-", "tun", "tap", "wg", "zt", "vmnet"))):
            continue
        prefix = row.get("prefix")
        if not _private(row.get("address", "")) or not isinstance(prefix, int) or isinstance(prefix, bool) or not 8 <= prefix <= 32:
            continue
        valid.append(row)
    valid.sort(key=lambda row: (not bool(row.get("default")), not bool(row.get("hardware")), row.get("metric") or 0, str(row["address"])))
    seen, interfaces = set(), []
    for row in valid:
        if row["address"] not in seen:
            seen.add(row["address"])
            interfaces.append({"address": row["address"], "label": str(row.get("label", "")), "prefix": row["prefix"]})
    return interfaces


class _LANServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class PhoneAccess:
    def __init__(self, handler_class, data: Path, static_dir: Path, interfaces=None, *, clock=time.time):
        self.handler_class = handler_class
        self.path = Path(data) / "phone-access.json"
        self.static_dir = Path(static_dir).resolve()
        self._interface_source = interfaces if interfaces is not None else private_ipv4_interfaces
        self._test_interfaces = interfaces is not None
        self._clock = clock
        self._lock = threading.RLock()
        self._control = threading.Lock()
        self._server = self._thread = None
        self._enabled = False
        self._address = ""
        self._port = 8767
        self._error = None
        self._sessions = {}
        self._code = None
        self._code_expires = 0
        self._handshake_checks = deque(maxlen=20)
        self._attempts = {}
        self._global_attempts = deque()
        self._interfaces_cache = []
        self._interfaces_at = float("-inf")

    def _interfaces(self, force=False):
        with self._lock:
            if not force and self._clock() - self._interfaces_at < 10:
                return [dict(row) for row in self._interfaces_cache]
        source = self._interface_source
        try:
            rows = source() if callable(source) else source
            result = []
            for row in rows:
                address = str(row.get("address", ""))
                value = ipaddress.ip_address(address)
                prefix = row.get("prefix")
                allowed = _private(address) or self._test_interfaces and value.is_loopback
                if (isinstance(value, ipaddress.IPv4Address) and allowed and isinstance(prefix, int)
                        and not isinstance(prefix, bool) and 8 <= prefix <= 32):
                    result.append({"address": address, "label": str(row.get("label", "")), "prefix": prefix})
        except (OSError, ValueError, TypeError, AttributeError):
            result = []
        with self._lock:
            self._interfaces_cache = result
            self._interfaces_at = self._clock()
        return [dict(row) for row in result]

    def status(self):
        interfaces = self._interfaces()
        with self._lock:
            now = self._clock()
            running = self._server is not None and self._thread is not None and self._thread.is_alive()
            code_active = running and self._code is not None and now < self._code_expires
            devices = [{key: record[key] for key in ("id", "name", "last_seen", "expires_at")}
                       for record in self._sessions.values() if _timestamp(record["expires_at"]) > now]
            return {"enabled": self._enabled, "running": running,
                    "origin": self._server.phone_origin if running else "", "bound_address": self._address,
                    "port": self._port, "interfaces": interfaces,
                    "pairing_code": self._code if code_active else None,
                    "pairing_expires_at": _iso(self._code_expires) if code_active else None,
                    "devices": sorted(devices, key=lambda item: item["id"]), "error": self._error,
                    "handshake_checks": [dict(item) for item in self._handshake_checks]}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + "." + secrets.token_hex(8) + ".tmp")
        state = {"version": 1, "enabled": self._enabled, "address": self._address,
                 "port": self._port, "devices": list(self._sessions.values())}
        try:
            descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(state, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _new_code(self):
        self._code = f"{secrets.randbelow(100_000_000):08d}"
        self._code_expires = self._clock() + PAIR_SECONDS

    def _bind(self, interface, port):
        manager = self
        parent = self.handler_class

        class PairedHandler(parent):
            def setup(self):
                super().setup()
                self.connection.settimeout(10)

            def log_message(self, *args):
                # Request lines can contain user-supplied codes or tokens. LAN
                # requests are intentionally never written to diagnostic logs.
                pass

            def _json(self, status, body, cookie=None):
                encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                if cookie:
                    self.send_header("Set-Cookie", cookie)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(encoded)

            def _basic(self):
                try:
                    client = ipaddress.ip_address(self.client_address[0])
                    network = ipaddress.ip_network(f"{interface['address']}/{interface['prefix']}", strict=False)
                    local = client in network and (_private(str(client)) or manager._test_interfaces and client.is_loopback)
                except ValueError:
                    local = False
                if not local:
                    self._json(403, {"error": "仅允许同一局域网设备访问"})
                    return False
                hosts = self.headers.get_all("Host", [])
                expected = self.server.phone_origin.removeprefix("http://")
                if hosts != [expected]:
                    self._json(403, {"error": "访问地址不匹配"})
                    return False
                origins = self.headers.get_all("Origin", [])
                if (origins and origins != [self.server.phone_origin]) or (self.command not in ("GET", "HEAD") and origins != [self.server.phone_origin]):
                    self._json(403, {"error": "请求必须来自本页"})
                    return False
                target = urlsplit(self.path)
                if target.scheme or target.netloc or not self.path.startswith("/"):
                    self._json(400, {"error": "请求地址无效"})
                    return False
                if self.headers.get("Transfer-Encoding"):
                    self.close_connection = True
                    self._json(400, {"error": "不支持此请求编码"})
                    return False
                return True

            def _token_hash(self):
                try:
                    cookie = SimpleCookie()
                    cookie.load(self.headers.get("Cookie", ""))
                    token = cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else ""
                    return hashlib.sha256(token.encode("ascii")).hexdigest() if 20 <= len(token) <= 256 else None
                except (CookieError, UnicodeError):
                    return None

            def _handshake(self, authenticated, reason):
                # A small desktop-only diagnostic contains outcomes, never request
                # values. Ignore static assets so they cannot bury the handshake.
                path = urlsplit(self.path).path
                if path.startswith("/static/"):
                    return
                known = ("/", "/phone/client", "/api/state", "/phone/pair")
                cookie_present = any(part.partition("=")[0].strip() == COOKIE_NAME
                                     for header in self.headers.get_all("Cookie", []) for part in header.split(";"))
                with manager._lock:
                    manager._handshake_checks.append({"at": _iso(manager._clock()),
                        "path": path if path in known else "other", "cookie_present": cookie_present,
                        "authenticated": bool(authenticated), "reason": reason})

            def _device(self):
                digest = self._token_hash()
                with manager._lock:
                    if not manager._enabled or manager._server is not self.server:
                        self._handshake(False, "disabled")
                        return None
                    if digest is None:
                        present = any(part.partition("=")[0].strip() == COOKIE_NAME
                                      for header in self.headers.get_all("Cookie", []) for part in header.split(";"))
                        self._handshake(False, "invalid_cookie" if present else "missing_cookie")
                        return None
                    record = manager._sessions.get(digest)
                    if not record:
                        self._handshake(False, "unknown_session")
                        return None
                    if _timestamp(record["expires_at"]) <= manager._clock():
                        self._handshake(False, "expired")
                        return None
                    now = manager._clock()
                    if now - _timestamp(record["last_seen"]) >= 60:
                        record["last_seen"] = _iso(now)
                        try:
                            manager._save()
                        except OSError:
                            manager._error = "设备活动记录未能保存，请检查电脑存储空间"
                    self._handshake(True, "ok")
                    return dict(record)

            def _blocked(self, path):
                if path.startswith(("/api/phone-access", "/api/system")) or path == "/api/pick-path":
                    return True
                return self.command != "GET" and path.startswith(("/api/agents", "/api/model-settings", "/api/executors", "/api/settings"))

            def _file(self, filename):
                target = (manager.static_dir / filename).resolve()
                if not target.is_relative_to(manager.static_dir) or not target.is_file():
                    self._json(503, {"error": "手机配对页面尚未安装"})
                    return
                body = target.read_bytes()
                content_type = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[target.suffix]
                self.send_response(200)
                self.send_header("Content-Type", content_type + "; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def do_GET(self):
                if not self._basic():
                    return
                path = urlsplit(self.path).path
                if path == "/phone/login":
                    self._file("phone-login.html")
                    return
                if path in ("/static/phone-login.js", "/static/phone-login.css"):
                    self._file(path.rsplit("/", 1)[-1])
                    return
                device = self._device()
                if not device:
                    if path == "/" or path.endswith(".html"):
                        self._file("phone-login.html")
                    else:
                        self._json(401, {"error": "请先在手机配对页面输入电脑显示的一次码"})
                    return
                if self._blocked(path):
                    self._json(403, {"error": "此设置只能在电脑上修改"})
                elif path == "/phone/client":
                    self._json(200, {"remote": True, "device_id": device["id"], "name": device["name"]})
                else:
                    super().do_GET()

            def do_POST(self):
                if not self._basic():
                    return
                parsed = urlsplit(self.path)
                if parsed.path == "/phone/pair":
                    self._pair(parsed.query)
                    return
                device = self._device()
                if not device:
                    self._json(401, {"error": "设备未配对或已过期，请重新配对"})
                    return
                if self._blocked(parsed.path):
                    self._json(403, {"error": "此设置只能在电脑上修改"})
                elif parsed.path == "/phone/logout":
                    manager.revoke(device["id"])
                    self._json(200, {"ok": True}, COOKIE_NAME + "=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
                else:
                    super().do_POST()

            def _pair(self, query):
                if query:
                    self._json(400, {"error": "配对信息必须放在请求正文"})
                    return
                with manager._lock:
                    if not manager._allow_pair_attempt(self.client_address[0]):
                        self._json(429, {"error": "尝试过于频繁，请一分钟后重试"})
                        return
                lengths = self.headers.get_all("Content-Length", [])
                if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
                    self._json(400, {"error": "请求正文长度无效"})
                    return
                length = int(lengths[0])
                if length > 4096:
                    self.close_connection = True
                    self._json(413, {"error": "配对请求不能超过4KB"})
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError()
                    code, name = payload.get("code"), payload.get("name", payload.get("device_name", "手机"))
                    if not isinstance(code, str) or len(code) != 8 or not code.isascii() or not code.isdecimal():
                        raise ValueError()
                    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(char) < 32 for char in name):
                        raise ValueError()
                except (ValueError, UnicodeError, OSError):
                    self._json(400, {"error": "请输入8位一次码和不超过80字的设备名称"})
                    return
                with manager._lock:
                    now = manager._clock()
                    if (not manager._enabled or manager._server is not self.server or not manager._code
                            or now >= manager._code_expires or not secrets.compare_digest(code, manager._code)):
                        self._json(401, {"error": "一次码无效或已过期，请查看电脑上的新码"})
                        return
                    token = secrets.token_urlsafe(32)
                    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
                    record = {"id": secrets.token_hex(16), "name": name.strip(), "token_hash": digest,
                              "created_at": _iso(now), "last_seen": _iso(now), "expires_at": _iso(now + SESSION_SECONDS)}
                    old_digest = self._token_hash()
                    old_record = manager._sessions.pop(old_digest, None)
                    manager._sessions[digest] = record
                    try:
                        manager._save()
                    except OSError:
                        manager._sessions.pop(digest, None)
                        if old_record:
                            manager._sessions[old_digest] = old_record
                        self._json(503, {"error": "配对记录无法保存，请在电脑上检查存储空间"})
                        return
                    manager._code = None
                    manager._code_expires = 0
                    self._handshake(False, "pair_issued")
                cookie = COOKIE_NAME + "=" + token + "; Path=/; HttpOnly; SameSite=Strict; Max-Age=" + str(SESSION_SECONDS)
                self._json(200, {"ok": True, "data": {"remote": True, "device_id": record["id"], "name": record["name"]}}, cookie)

            def _unsupported(self):
                if not self._basic():
                    return
                if not self._device():
                    self._json(401, {"error": "请先配对设备"})
                else:
                    self._json(405, {"error": "不支持此请求方法"})

            do_HEAD = do_OPTIONS = do_PUT = do_DELETE = do_PATCH = _unsupported

        server = _LANServer((interface["address"], port), PairedHandler)
        server.phone_remote = True
        server.phone_origin = f"http://{interface['address']}:{server.server_port}"
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True, name="AgentBoard phone access")
        return server, thread

    @staticmethod
    def _stop(server, thread):
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)

    def enable(self, address=None, port=8767, *, _pairing=True):
        with self._control:
            interfaces = self._interfaces(force=True)
            if address is None:
                address = interfaces[0]["address"] if interfaces else ""
            interface = next((row for row in interfaces if row["address"] == address), None)
            if interface is None:
                raise ValueError("请选择本机真实的家庭局域网IPv4地址")
            if (not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535) and not (port == 0 and self._test_interfaces and ipaddress.ip_address(address).is_loopback):
                raise ValueError("手机访问端口须为1024至65535")
            with self._lock:
                same = self._server is not None and self._address == address and self._port == port
                if same:
                    if _pairing:
                        self._new_code()
                    else:
                        self._code, self._code_expires = None, 0
                    return self.status()
            try:
                server, thread = self._bind(interface, port)
            except OSError as exc:
                with self._lock:
                    self._error = "无法开启手机访问，请检查所选网络和端口是否可用"
                raise ValueError(self._error) from exc
            with self._lock:
                old_server, old_thread = self._server, self._thread
                old_state = (self._enabled, self._address, self._port, self._error)
                self._enabled, self._address, self._port, self._error = True, address, server.server_port, None
                try:
                    self._save()
                except OSError:
                    self._enabled, self._address, self._port, self._error = old_state
                    server.server_close()
                    raise
                self._server, self._thread = server, thread
                if _pairing:
                    self._new_code()
                else:
                    self._code, self._code_expires = None, 0
                thread.start()
            self._stop(old_server, old_thread)
            return self.status()

    def disable(self):
        with self._control:
            server = thread = None
            try:
                with self._lock:
                    server, thread = self._server, self._thread
                    self._server = self._thread = None
                    self._enabled = False
                    self._sessions.clear()
                    self._code = None
                    self._code_expires = 0
                    self._error = None
                    self._save()
            finally:
                self._stop(server, thread)
        return self.status()

    def new_code(self):
        with self._lock:
            if not self._enabled or self._server is None:
                raise ValueError("请先开启手机访问")
            self._new_code()
        return self.status()

    def revoke(self, device_id):
        if not isinstance(device_id, str):
            raise ValueError("设备标识无效")
        with self._lock:
            self._sessions = {digest: record for digest, record in self._sessions.items() if record["id"] != device_id}
            self._save()
        return self.status()

    def _allow_pair_attempt(self, address):
        now = self._clock()
        self._global_attempts = deque(at for at in self._global_attempts if now - at < 60)
        self._attempts = {ip: deque(at for at in attempts if now - at < 60) for ip, attempts in self._attempts.items()}
        self._attempts = {ip: attempts for ip, attempts in self._attempts.items() if attempts}
        attempts = self._attempts.get(address, deque())
        if len(attempts) >= PAIR_IP_LIMIT or len(self._global_attempts) >= PAIR_GLOBAL_LIMIT:
            return False
        attempts.append(now)
        self._attempts[address] = attempts
        self._global_attempts.append(now)
        return True

    def restore(self):
        if not self.path.exists():
            return self.status()
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict) or saved.get("version") != 1 or not isinstance(saved.get("enabled"), bool):
                raise ValueError()
            devices = saved.get("devices", [])
            if not isinstance(devices, list):
                raise ValueError()
            sessions = {}
            for device in devices:
                if (not isinstance(device, dict) or not isinstance(device.get("token_hash"), str)
                        or len(device["token_hash"]) != 64 or any(char not in "0123456789abcdef" for char in device["token_hash"])
                        or not isinstance(device.get("id"), str) or not isinstance(device.get("name"), str)):
                    raise ValueError()
                if _timestamp(device["expires_at"]) > self._clock():
                    _timestamp(device["last_seen"])
                    sessions[device["token_hash"]] = dict(device)
            with self._lock:
                self._address = saved.get("address", "")
                self._port = saved.get("port", 8767)
                self._enabled = saved["enabled"]
                self._sessions = sessions if saved["enabled"] else {}
                self._code = None
                self._code_expires = 0
            if saved["enabled"]:
                self.enable(self._address, self._port, _pairing=False)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            with self._lock:
                self._error = "手机访问未能恢复，请在电脑上重新选择家庭网络并开启"
        return self.status()

    def shutdown(self):
        # Application shutdown preserves the opt-in preference and device hashes.
        # Explicit disable(), in contrast, revokes all paired devices immediately.
        with self._control:
            with self._lock:
                server, thread = self._server, self._thread
                self._server = self._thread = None
                self._code = None
                self._code_expires = 0
            self._stop(server, thread)
        return self.status()
