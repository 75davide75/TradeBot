# Sistema di trading — paper trading con conferma manuale

### 📊 [**Dashboard in diretta**](https://75davide75.github.io/TradeBot/) · 📄 [**Report tecnico**](https://75davide75.github.io/TradeBot/ricerca.html)

La dashboard mostra portafoglio, posizioni aperte e grafici a candela in tempo
reale. Il report tecnico raccoglie le evidenze pubblicate su day trading e IA
nei mercati, confrontate con quanto misurato da questo sistema.

---

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

Dalla cartella del progetto:

```bash
python3 bot.py
```

Dovresti ricevere su Telegram il messaggio di avvio. Scrivi `/status` per
vedere lo stato del conto, `/check` per forzare un controllo del mercato.
Ferma con `Ctrl+C`.

### 6. Fallo partire da solo

Il sistema è pensato per girare su una macchina sempre accesa — un Raspberry
Pi va benissimo. Istruzioni complete in **[`linux/INSTALLA.md`](linux/INSTALLA.md)**:
servizi systemd per il bot, la pubblicazione della dashboard ogni 30 minuti e
il controllo di salute del mattino.

Un portatile non è adatto: chiudere il coperchio lo addormenta, e i buchi nel
controllo diventano buchi nello storico.

## Frequenza dei controlli

Due orologi distinti, ed è deliberato:

- **stop-loss ogni 60 secondi** — il rischio va tolto in fretta
- **segnale ogni 15 minuti**, ma calcolato sull'ultima candela **giornaliera
  chiusa** — le decisioni vanno prese al ritmo dell'informazione che le genera

Il segnale è il momentum a 60 giorni: cambia in media una volta ogni 18 giorni
per mercato. Controllarlo più spesso non trova occasioni prima, e usare la
candela ancora aperta genera 1,8 falsi cambi per ogni cambio vero — misurato.

## Verifiche

```bash
python3 -m unittest test_stato -v      # persistenza, versamenti, ombra
python3 -m unittest test_segnale -v    # segnale (richiede pandas, sennò si salta)
```

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

- **Portafoglio ombra** — gira in parallelo con leva fissa 1x, rispecchiando
  ogni decisione. Serve a rispondere a "il volatility targeting aiuta o fa
  danni?", che con un solo portafoglio resterebbe un'opinione.

## Cosa aspettarsi

Nessuna delle strategie testate ha mostrato un vantaggio che sopravviva ai
costi reali: né le quattro classiche sullo spot (`RISULTATI.md`), né le sei
provate sui perpetui con spread e commissioni veri (`RICERCA_AGOSTO_2026.md`).
Il candidato migliore aveva Sharpe 3,75 e si è rivelato dieci giorni di
funding anomalo su un mercato illiquido.

Questo sistema non è un generatore di profitti: è uno **strumento di misura**.
Serve a osservare come si comporta una strategia con costi reali, e a produrre
dati onesti su cui decidere.

Se dopo qualche settimana di paper il conto simulato è sotto, quella è
l'informazione, ed è costata zero.

## File

| File | Cosa fa |
|---|---|
| `stato.py` | Persistenza: dove vivono i dati, blocco all'avvio, versamenti |
| `core.py` | Dati, segnale, layer di rischio, portafoglio, ombra |
| `bot.py` | Bot Telegram, processo sempre attivo |
| `perp.py` | Adattatore per i futures perpetui Kraken |
| `publish.py` | Genera e pubblica `docs/data.json` per la dashboard |
| `healthcheck.py` | Controllo di salute delle 9:00 |
| `daily_review.py` | Report giornaliero |
| `backtest.py` / `run_backtest.py` | Motore di backtest sullo spot |
| `perp_test/ricerca.py` | Ricerca sui segnali, con costi e spread reali |
| `docs/` | Dashboard e report tecnico pubblicati su GitHub Pages |
| `linux/` | Servizi systemd e istruzioni d'installazione |

### Dove vivono i dati

`state.json`, `journal.csv` e `report/` **non** stanno nella cartella del
codice: stanno in `~/trading-dati/`. La cartella del codice è sacrificabile,
lo storico no. Il motivo è in `linux/INSTALLA.md`.

## Documenti

| Documento | Contenuto |
|---|---|
| `RISULTATI.md` | Backtest sullo spot a margine: nessun edge, a nessuna leva |
| `TEST_PERPETUI.md` | 57 mercati perpetui con funding reale |
| `RICERCA_AGOSTO_2026.md` | Sei segnali con costi veri: nessuno supera le prove |
| `specs/` | Progetto e piano della persistenza dello stato |
