# Sistema di trading — paper trading con conferma manuale

Bot Telegram che propone operazioni, tu confermi con un tap, il sistema esegue
**in simulazione**. Nessuna credenziale Kraken, nessun soldo reale.

## Cosa devi fare tu (10 minuti)

### 1. Crea il bot Telegram

Apri Telegram, cerca **@BotFather**, scrivi `/newbot` e segui le istruzioni.
Alla fine ti dà un token del tipo `8123456789:AAH...`. Copialo.

### 2. Trova il tuo chat ID

Sempre su Telegram, cerca **@userinfobot** e scrivi `/start`. Ti risponde con
il tuo ID numerico.

### 3. Compila `config.json`

Sostituisci i due segnaposto:

```json
"telegram_token": "8123456789:AAH...",
"telegram_chat_id": "123456789",
```

### 4. Installa le dipendenze

```bash
pip3 install pandas numpy
```

### 5. Prova che funzioni

```bash
cd "/Users/davidesogos/Desktop/progetto trading"
python3 bot.py
```

Dovresti ricevere su Telegram il messaggio di avvio. Scrivi `/status` per
vedere lo stato del conto, `/check` per forzare un controllo del mercato.
Ferma con `Ctrl+C`.

### 6. Fallo partire da solo

```bash
cp com.davide.tradingbot.plist ~/Library/LaunchAgents/
cp com.davide.dailyreview.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.davide.tradingbot.plist
launchctl load ~/Library/LaunchAgents/com.davide.dailyreview.plist
```

Da qui in poi il bot parte da solo all'accensione del Mac e si riavvia se
crasha. `caffeinate -i` nel plist impedisce lo sleep da inattività.

Per fermarlo: `launchctl unload ~/Library/LaunchAgents/com.davide.tradingbot.plist`

## Sul Mac in standby

`caffeinate -i` impedisce lo sleep da inattività, ma **chiudere il coperchio
del MacBook lo addormenta comunque**. Se ti serve continuità:

- lascia il coperchio aperto, oppure
- clamshell: alimentazione + monitor esterno collegati, oppure
- accetta i buchi

L'ultima opzione è quella giusta. Il sistema lavora su candele daily e
controlla ogni 4 ore: saltare un controllo non rompe niente, il segnale viene
ricalcolato al risveglio. Se ti servisse una macchina sempre viva vorrebbe
dire che stai usando un timeframe sbagliato per questo capitale.

## Comandi Telegram

| Comando | Cosa fa |
|---|---|
| `/status` | Equity, posizioni aperte, P&L |
| `/check` | Forza subito un controllo del mercato |
| `/halt` | Ferma il sistema |
| `/resume` | Riprende dopo uno stop |

## Come sono state prese le decisioni di rischio

Non a naso. Vengono dal backtest in `RISULTATI.md`:

- **Leva massima 2x** — a 3x il 44% dei conti simulati veniva liquidato, a 5x
  l'89%, a 10x il 100%. Alzare `max_leverage` significa scegliere di ignorare
  i dati che abbiamo prodotto.
- **Volatility targeting** — l'esposizione si muove inversamente alla
  volatilità realizzata, mai in risposta ai profitti recenti. Reagire ai propri
  profitti è performance chasing, e fa danni misurabili.
- **Kill switch a -25%** dal picco — il sistema si ferma e richiede `/resume`
  manuale. Un sistema automatico senza kill switch non è un sistema
  automatico, è una perdita che non hai ancora notato.
- **Nessuna credenziale Kraken** — il bot legge solo dati pubblici. Non può
  muovere soldi neanche se avesse un bug.

## Cosa aspettarsi

Il backtest non ha trovato edge in nessuna delle strategie testate, a nessun
livello di leva. Questo sistema non è un generatore di profitti: è uno
strumento di misura. Serve a osservare come si comporta una strategia con
costi reali, e a produrre dati onesti su cui decidere.

Se dopo qualche settimana di paper il conto simulato è sotto, quella è
l'informazione, ed è costata zero.

## File

| File | Cosa fa |
|---|---|
| `core.py` | Dati, segnale, layer di rischio, portafoglio |
| `bot.py` | Bot Telegram, processo sempre attivo |
| `daily_review.py` | Report giornaliero delle 9:00 |
| `backtest.py` / `run_backtest.py` | Motore di backtest |
| `RISULTATI.md` | Risultati e metodo del backtest |
| `state.json` | Stato del portafoglio (generato) |
| `journal.csv` | Log di ogni decisione (generato) |
| `report/` | Report giornalieri in JSON (generato) |
