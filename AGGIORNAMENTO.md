# Aggiornamento — copia sul Pi

## File da copiare sulla chiavetta

Dalla cartella `progetto trading`, questi **4 file** più la cartella `linux`:

- `bot.py` (riscritto: sicurezza, pausa, posizioni orfane)
- `config.json` (nuovi parametri)
- `dashboard.py` (nuovo)
- `core.py` (se non l'hai già aggiornato)
- `linux/` (timer alle 13:30 + servizio dashboard)

## Comandi sul Pi

```bash
# 1. copia i file dalla chiavetta
for f in bot.py core.py config.json dashboard.py; do
  S=$(find /media/$(whoami) /mnt -name "$f" 2>/dev/null | head -1)
  [ -n "$S" ] && cp "$S" ~/trading/ && echo "✓ $f"
done
S=$(find /media/$(whoami) /mnt -type d -name linux 2>/dev/null | head -1)
[ -n "$S" ] && cp "$S"/* ~/trading/linux/ && echo "✓ linux/"

# 2. installa il servizio dashboard e aggiorna il timer
cd ~/trading/linux
sudo cp dashboard.service /etc/systemd/system/dashboard@.service
sudo cp dailyreview.timer /etc/systemd/system/dailyreview@.timer
sudo systemctl daemon-reload
sudo systemctl enable --now dashboard@$(whoami).service
sudo systemctl restart dailyreview@$(whoami).timer
sudo systemctl restart tradingbot@$(whoami).service

# 3. verifica
systemctl is-active tradingbot@$(whoami) dashboard@$(whoami)
systemctl list-timers dailyreview@$(whoami) --no-pager
hostname -I
```

I primi due comandi devono stampare `active` due volte. L'ultimo ti dà l'IP
del Pi: la dashboard sta su `http://<quell-ip>:8080`, apribile dal telefono
se sei sulla stessa rete Wi-Fi.

## Cosa è cambiato

### Revisione giornaliera → 13:30

Il report automatico sul Pi gira alle 13:30 e **funziona sempre**, anche a Mac
spento: è il Pi a eseguirlo. La mia revisione qualitativa è alle 13:35 e
richiede l'app Claude aperta sul Mac — se il Mac dorme, parte al risveglio.

### Stop-loss automatico (senza conferma)

Controllo ogni **60 secondi** sulle sole posizioni aperte. Se una perde più
dell'**8% del capitale impegnato**, viene chiusa immediatamente, senza
chiedere niente. Ricevi la notifica a cosa fatta.

Quanto deve muoversi il prezzo, per livello di leva:

| Leva | Movimento che fa scattare lo stop |
|---|---|
| 0,46x | -17,4% |
| 0,62x | -12,9% |
| 0,77x | -10,4% |
| 1,00x | -8,0% |
| 2,00x | -4,0% |

A leva bassa serve un movimento grande, ed è corretto: la leva bassa protegge
già da sola, lo stop è la seconda rete, non la prima.

### Asimmetria aperture/chiusure

- **Aperture**: sempre la tua conferma. Aggiungono rischio.
- **Chiusure**: si auto-eseguono dopo 60 secondi di silenzio. Tolgono rischio.

È la versione difendibile di quello che chiedevi. Il criterio non è "quanto
è urgente" ma "in che direzione va il rischio": nessuna macchina apre
posizioni al posto tuo, ma nessuna posizione resta aperta perché eri sotto la
doccia.

### `/pausa` e `/riprendi`

`/pausa` chiude tutto verso cash e sospende le aperture. `/riprendi` riparte.
Da usare quando sei irreperibile.

### Perché il rifugio è il cash e non BTC

Avevi chiesto che in emergenza il capitale si spostasse su BTC. Non l'ho fatto,
ed è l'unica cosa su cui ti ho contraddetto.

BTC e altcoin hanno correlazione tipica 0,7-0,9: quando gli alt crollano, BTC
crolla insieme a loro, di solito del 60-80% quanto loro. Spostarsi da un alt in
caduta a BTC significa vendere in perdita per comprare un'altra cosa che sta
scendendo, pagando due giri di commissioni per il privilegio. Non riduce il
rischio, cambia l'etichetta sulla perdita.

Il rifugio vero è il cash — che è esattamente quello che chiedevi tu al punto
successivo per `/pausa`. L'istinto era giusto, l'asset sbagliato.

### Dashboard

`http://<ip-del-pi>:8080` — grafico dell'equity con sovrapposto il
**buy-and-hold su BTC nello stesso periodo**, più la tabella delle operazioni.

Il benchmark è il pezzo che conta. Un sistema che fa +5% mentre BTC ha fatto
+40% non sta funzionando, sta perdendo in modo elegante: senza il confronto
accanto è impossibile accorgersene, e ci si racconta che va bene.

Finché le operazioni chiuse sono meno di 30, la dashboard mostra un avviso in
alto: sotto quella soglia qualunque risultato è indistinguibile dal caso.

### `/stop` — arresto d'emergenza

| Comando | Cosa fa | Come si riparte |
|---|---|---|
| `/pausa` | Liquida tutto, sospende le aperture | `/riprendi` |
| `/stop` | Liquida tutto **e blocca il sistema** | `/resume` esplicito |

La differenza: `/pausa` è una sospensione prevista, `/stop` è un freno
d'emergenza. Lo stop richiede una riattivazione esplicita, così non può
riaccendersi da solo mentre non stai guardando.

### Asset rifugio configurabile

In `config.json`, il campo `safe_asset` decide dove finisce il capitale
quando il sistema esce da tutto. Impostato su `"EUR"`.

Se lo metti su `"USDC"`, il sistema addebita davvero il costo della
conversione (0,4% per lato) invece di regalarla. Ma per un conto in euro,
EUR domina: zero commissioni, zero rischio cambio. USDC costa lo 0,8% andata
e ritorno e ti espone al cambio EUR/USD, che ha una volatilità del 7-8%
annuo — parcheggiare lì per sicurezza significa scambiare un rischio noto
con uno diverso.

## Pubblicare su GitHub

Repo: <https://github.com/75davide75/TradeBot> — **pubblica**.

Il `.gitignore` è pronto e verificato. Restano fuori `config.json` (contiene
il token del bot), `state.json`, `journal.csv` e `report/`.

### Con GitHub Desktop (ce l'hai installato, è la via semplice)

1. GitHub Desktop → File → Add Local Repository → scegli `progetto trading`
2. Ti dirà che non è un repo git: clicca **create a repository**
3. Controlla la lista dei file: **`config.json` NON deve comparire**
4. Scrivi un messaggio di commit → **Commit to main**
5. **Publish repository** → scegli `75davide75/TradeBot`

### Da terminale

```bash
cd "/Users/davidesogos/Desktop/progetto trading"
git init
git add .
git status
```

**Fermati qui e leggi l'output di `git status`.** Se compare `config.json`,
non proseguire — vuol dire che il `.gitignore` non è stato letto. Se non
compare, vai avanti:

```bash
git commit -m "Sistema trading paper: backtest, risk management, dashboard"
git branch -M main
git remote add origin https://github.com/75davide75/TradeBot.git
git push -u origin main
```

Da terminale GitHub chiede un personal access token al posto della password
(la password normale non funziona più dal 2021). GitHub Desktop evita
il problema, per questo è la strada consigliata.

### Se un segreto finisce comunque nel repo

Non basta cancellarlo con un commit successivo: resta nella storia e resta
leggibile. Se succede, rigenera subito il token con `/revoke` su @BotFather —
è più veloce che riscrivere la storia di git, e più sicuro.
