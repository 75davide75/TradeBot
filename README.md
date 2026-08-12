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
python3 -m unittest discover -p "test_*.py" -v
```

| File | Cosa copre |
|---|---|
| `test_stato.py` | Persistenza, versamenti, blocco all'avvio, ombra |
| `test_mercati.py` | Filtro di negoziabilità: spread, volume, contratti sospesi |
| `test_ia.py` | Livello IA e terzo portafoglio (nessuna chiamata di rete) |
| `test_segnale.py` | Segnale (richiede pandas, sennò si salta da solo) |

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
- **Filtro di negoziabilità** — prima di operare, ogni mercato deve avere
  spread sotto lo 0,15% e volume sopra i 250.000 USD nelle 24 ore. Sono soglie
  misurate sui 57 perpetui Kraken, non prudenza generica: su un mercato
  all'1,3% di spread nessun segnale sopravvive al costo di entrarci e uscirne.
  Se i dati di liquidità non arrivano, o se il filtro scarterebbe l'universo
  intero, non esclude niente: in dubbio è un guardiano, non un decisore.

## I tre portafogli

Girano insieme, sugli stessi dati, e differiscono per **una variabile
ciascuno**. È l'unico modo di attribuire una differenza a una causa.

| Portafoglio | Segnale | Leva | Universo |
|---|---|---|---|
| **Reale** | momentum 60g | volatility targeting | lista in `config.json`, filtrata |
| **Ombra** | *identico* | fissa 1x | *identico* |
| **Sperimentale** | *identico* | *identica* | scelto da un modello linguistico |

Il terzo portafoglio risponde a "conviene far scegliere i mercati a un'IA?".
Non si può backtestare: un modello linguistico è addestrato su testo storico e
lo ricorda, quindi ogni prova sul passato è contaminata — su rendimenti annuali
dell'S&P 500 sono documentate correlazioni fino al 100%. L'unico modo di
saperlo è misurare in avanti, con soldi finti, per mesi.

Tre difese, perché un modello che non sa risponde lo stesso:

1. **Sceglie solo fra mercati già filtrati** dal filtro di negoziabilità.
2. **I simboli tornati vengono validati** contro i candidati: uno inventato
   non può far aprire una posizione.
3. **Cambia universo al massimo una volta al giorno.** Ogni rimescolamento
   costa un giro di commissioni: due mercati al giorno su 200 € fanno circa il
   5,6% annuo di costi contro l'1,06% attuale — l'IA dovrebbe aggiungere oltre
   4,5 punti di rendimento solo per pagarsi il proprio rimescolamento.

Ha lo stesso stop-loss degli altri due. Senza, la differenza fra le curve
misurerebbe la mancanza dello stop invece della selezione dei mercati.

**L'IA non tocca il portafoglio reale né l'ombra**, e non decide mai una
direzione: sceglie *dove* guardare, non *cosa fare*. Senza chiave API il
sistema funziona identico, con due portafogli invece di tre.

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
| `core.py` | Dati, segnale, layer di rischio, i tre portafogli |
| `mercati.py` | Filtro di negoziabilità: spread, volume, contratti sospesi |
| `analisi.py` | Livello IA: riassunto delle 9:00 e scelta dell'universo |
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
