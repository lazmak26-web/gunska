#!/usr/bin/env python3
"""GUNSKA smoke tests — real HTTP against a real server process.

    python3 test_smoke.py -v
"""
import base64
import http.client
import json
import os
import socket
import subprocess
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
AUTH = "testauth"
TOK = "testtoken"
PROC = None


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


PORT = free_port()


def req(method, path, body=None, headers=None, auth=True, timeout=15):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=timeout)
    h = dict(headers or {})
    if auth:
        h["X-Auth"] = AUTH
    if isinstance(body, str):
        body = body.encode()
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    data = r.read()
    hdrs = dict(r.getheaders())
    c.close()
    return r.status, data, hdrs


def agent_post(sid, obj, tok=TOK):
    return req("POST", "/r/%s?t=%s" % (sid, tok), json.dumps(obj), auth=False)


class Smoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global PROC
        env = dict(os.environ, PORT=str(PORT), AUTH=AUTH, AGENT_TOKEN=TOK)
        PROC = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for _ in range(100):
            try:
                if req("GET", "/healthz", auth=False)[0] == 200:
                    return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    @classmethod
    def tearDownClass(cls):
        PROC.terminate()
        PROC.wait(timeout=10)

    def test_health(self):
        st, body, _ = req("GET", "/healthz", auth=False)
        self.assertEqual(st, 200)
        self.assertEqual(body, b"ok")

    def test_panel_brand(self):
        st, body, hdrs = req("GET", "/", auth=False)
        self.assertEqual(st, 200)
        self.assertIn("GUNSKA", body.decode())
        self.assertIn("text/html", hdrs["Content-Type"])

    def test_bootstrap_replaces_base(self):
        st, body, _ = req("GET", "/i", auth=False)
        self.assertEqual(st, 200)
        text = body.decode()
        self.assertNotIn("__B__", text)
        self.assertIn("127.0.0.1:%d" % PORT, text)

    def test_agent_source_has_token(self):
        st, body, _ = req("GET", "/a", auth=False)
        self.assertEqual(st, 200)
        text = body.decode()
        self.assertIn(TOK, text)
        self.assertNotIn("__TOKEN__", text)

    def test_api_requires_auth(self):
        st, _, _ = req("GET", "/api/sessions", auth=False)
        self.assertEqual(st, 401)

    def test_query_key_auth(self):
        st, _, _ = req("GET", "/api/sessions?k=" + AUTH, auth=False)
        self.assertEqual(st, 200)

    def test_link(self):
        st, body, _ = req("GET", "/link")
        self.assertEqual(st, 200)
        self.assertIn("curl -fsSL", body.decode())

    def test_agent_token_enforced(self):
        st, _, _ = req("GET", "/p/zzz", auth=False)
        self.assertEqual(st, 403)
        st, _, _ = req("GET", "/p/zzz?t=wrong", auth=False)
        self.assertEqual(st, 403)

    def test_hello_and_sessions(self):
        agent_post("s1", {"t": "hello", "info": {"user": "u", "host": "h", "ip": "1.2.3.4", "os": "Linux"}})
        st, body, _ = req("GET", "/api/sessions")
        self.assertEqual(st, 200)
        rows = json.loads(body)
        me = [r for r in rows if r["id"] == "s1"]
        self.assertTrue(me and me[0]["on"] and me[0]["host"] == "h")

    def test_cmd_roundtrip(self):
        agent_post("s1", {"t": "hello", "info": {"user": "u", "host": "h", "ip": "1.2.3.4", "os": "Linux"}})
        st, _, _ = req("POST", "/api/cmd", json.dumps({"sid": "s1", "cmd": "id"}))
        self.assertEqual(st, 200)
        st, body, _ = req("GET", "/p/s1?t=" + TOK, auth=False)
        self.assertEqual(st, 200)
        cmd = json.loads(body)["c"][0]
        self.assertEqual(cmd["t"], "shell")
        self.assertEqual(cmd["a"], "id")

        agent_post("s1", {"t": "out", "id": cmd["id"], "d": "uid=0\n"})
        st, body, _ = req("GET", "/api/out?sid=s1&after=0")
        self.assertEqual(st, 200)
        self.assertIn("uid=0", json.loads(body)["lines"])

    def test_leave_is_noop(self):
        agent_post("s1", {"t": "hello", "info": {}})
        req("POST", "/api/cmd", json.dumps({"sid": "s1", "cmd": ".leave"}))
        _, body, _ = req("GET", "/p/s1?t=" + TOK, auth=False)
        self.assertEqual(json.loads(body)["c"][0]["t"], "noop")

    def test_bad_after_value(self):
        st, _, _ = req("GET", "/api/out?sid=s1&after=abc")
        self.assertEqual(st, 200)

    def test_loot_upload_and_download(self):
        agent_post("s1", {"t": "hello", "info": {}})
        payload = b"hello loot"
        agent_post("s1", {"t": "file", "fid": "f1", "name": "a.txt", "i": 0,
                          "d": base64.b64encode(payload).decode(), "last": True})
        st, body, _ = req("GET", "/api/loot")
        self.assertEqual(st, 200)
        self.assertTrue(any(f["id"] == "f1" for f in json.loads(body)))
        st, body, hdrs = req("GET", "/api/loot/f1")
        self.assertEqual(st, 200)
        self.assertEqual(body, payload)
        self.assertIn("a.txt", hdrs["Content-Disposition"])

    def test_put_queue(self):
        agent_post("s1", {"t": "hello", "info": {}})
        st, _, _ = req("POST", "/api/put", b"abcdef",
                       {"X-Sid": "s1", "X-Name": "x.bin"})
        self.assertEqual(st, 200)
        _, body, _ = req("GET", "/p/s1?t=" + TOK, auth=False)
        kinds = [c["t"] for c in json.loads(body)["c"]]
        self.assertEqual(kinds, ["put_begin", "put_chunk", "put_end"])

    def test_unknown_route(self):
        st, _, _ = req("GET", "/nope", auth=False)
        self.assertEqual(st, 404)


class Static(unittest.TestCase):
    def test_compiles(self):
        import py_compile
        for f in ("app.py", "agent.py", "console.py"):
            py_compile.compile(os.path.join(ROOT, f), doraise=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
