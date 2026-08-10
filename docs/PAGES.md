# Dashboard pubblica su GitHub Pages

Indirizzo finale: **https://75davide75.github.io/TradeBot/**

## Come funziona

GitHub Pages serve solo contenuto statico, e il Pi sta dietro NAT: una pagina
su internet non può interrogarlo. Quindi il flusso è invertito — è il Pi a
spingere fuori i dati.

```
Pi  →  publish.py ogni 30 min  →  docs/data.json  →  git push
                                                        ↓
                              GitHub Pages  →  docs/index.html legge data.json
```

La stessa `index.html` viene servita anche in locale da `dashboard.py` sulla
rete di casa. Una sola pagina da mantenere: se la versione locale e quella
pubblica divergessero, prima o poi guarderesti quella sbagliata senza
accorgertene.

## Cosa viene pubblicato

Solo questi campi, scelti uno per uno (whitelist, non blacklist — con una
blacklist basta aggiungere un campo domani per pubblicarlo per sbaglio):

`ts`, `action`, `pair`, `price`, `notional`, `leverage`, `reason`

Più la curva di equity, il benchmark BTC e i contatori. **Non** escono
`config.json`, il token, né lo stato grezzo.

Il repo è pubblico, quindi questi dati sono leggibili da chiunque. Sono 20 €
simulati, ma è una scelta consapevole: se preferisci, rendi il repo privato
(Settings → General → Danger Zone) — Pages continua a funzionare sui piani
a pagamento, altrimenti resta la dashboard locale.

## Attivazione — una volta sola

### 1. Primo push dal Mac

Segui `AGGIORNAMENTO.md`. Verifica che `git status` **non** mostri
`config.json` prima di committare.

### 2. Abilita Pages

Su GitHub: **Settings → Pages → Source: Deploy from a branch →
Branch: `main`, cartella `/docs` → Save**

Dopo un paio di minuti la pagina è online.

### 3. Dai al Pi il permesso di pubblicare

Sul Pi, genera una chiave dedicata:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/tradebot_deploy -N "" -C "pi-tradebot"
cat ~/.ssh/tradebot_deploy.pub
```

Copia l'output. Su GitHub: **Settings → Deploy keys → Add deploy key**,
incolla la chiave, **spunta "Allow write access"**, salva.

Una deploy key vale solo per questo repo. Un personal access token invece
darebbe accesso a tutti i tuoi repo: se il Pi venisse compromesso, la deploy
key limita il danno a questo progetto.

Poi configura git sul Pi:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github-tradebot
  HostName github.com
  User git
  IdentityFile ~/.ssh/tradebot_deploy
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config

cd ~/trading
git init 2>/dev/null
git remote remove origin 2>/dev/null
git remote add origin github-tradebot:75davide75/TradeBot.git
git config user.email "pi@tradebot.local"
git config user.name "TradeBot Pi"
git fetch origin && git checkout -B main --track origin/main
```

Prova:

```bash
cd ~/trading && python3 publish.py
```

Deve stampare `push OK`. Ricarica la pagina: i dati sono lì.

### 4. Pubblicazione automatica ogni 30 minuti

```bash
cd ~/trading/linux
sudo cp publish.service /etc/systemd/system/publish@.service
sudo cp publish.timer /etc/systemd/system/publish@.timer
sudo systemctl daemon-reload
sudo systemctl enable --now publish@$(whoami).timer
systemctl list-timers publish@$(whoami) --no-pager
```

## Se qualcosa non va

| Sintomo | Causa |
|---|---|
| "Impossibile caricare data.json" | Il Pi non ha ancora fatto il primo push |
| `push fallito` con `Permission denied` | Deploy key senza "Allow write access" |
| Pagina 404 | Pages non abilitato, o cartella diversa da `/docs` |
| Dati fermi | `journalctl -u publish@$(whoami) -n 30` |

`publish.py` ha un controllo di sicurezza finale: se `config.json` risultasse
tracciato da git per qualsiasi motivo, si ferma e rifiuta di pubblicare
invece di mandare un token su un repo pubblico.
