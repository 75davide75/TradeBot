# Persistenza dello stato: i dati escono dalla cartella del codice

Data: 2026-08-11
Stato: approvato, da implementare

## Il problema

Lo stato del sistema (`state.json`) si azzera durante i deploy. Accertato due volte
sul Pi in produzione, ricostruendo la cronologia dai commit di `docs/data.json`
pubblicati dal Pi ogni 30 minuti.

| Quando (UTC) | Storico equity | Posizioni | Equity |
|---|---|---|---|
| 2026-08-10 19:39 | 32 punti → **1** | 3 → **0** | 19,84 → **100,00** |
| 2026-08-11 11:18 | 74 punti → **1** | 8 → **0** | 100,40 → **100,00** |

Il secondo azzeramento è a **25 secondi** dal salvataggio di `bot.py`, `core.py` e
`perp.py` sul Mac (13:13:24 Roma; nuovo stato creato alle 13:13:49 Roma). La
correlazione con il momento del deploy è il fatto centrale.

Il primo azzeramento coincide con il passaggio del capitale da 20 a 100 €, quindi
potrebbe essere stato voluto. Il secondo no: ha distrutto 74 misure e 8 posizioni
aperte.

### Conseguenze

1. Ogni misura di rendimento riparte da zero senza dichiararlo. La dashboard mostra
   un numero che si autoresetta.
2. Le posizioni aperte spariscono dal registro ma restano concettualmente aperte:
   il journal pubblicato conta **20 aperture e 1 sola chiusura**, con BTC aperto tre
   volte (56148 → 55412 → 64297) senza chiusure intermedie. `execute()` chiude sempre
   prima di riaprire (`bot.py:276`), quindi l'unica spiegazione è che
   `state["positions"]` fosse vuoto a ogni apertura.
3. Il guasto è invisibile: vedi sotto.

## Causa

Il meccanismo esatto non è dimostrabile senza accesso al Pi (non raggiungibile dalla
rete del Mac al momento della diagnosi). I candidati sono due, entrambi legati al
deploy:

- `linux/INSTALLA.md` documenta come procedura di copia
  `scp -r "progetto trading" pi@raspberrypi.local:~/trading`, che copia l'intera
  cartella **compreso `state.json`**. `.gitignore` non protegge da `scp`. Sul Mac è
  presente un `state.json` da 176 byte con `cash 100.0`, `positions {}`, `history []`:
  esattamente la forma in cui il Pi è ripartito.
- Oppure `state.json` cancellato a mano sul Pi.

**La causa a monte che rende possibili entrambi è una sola:** `sync.sh` — il percorso
sicuro, che copia una lista esplicita di file — è incompleto. Non copia `perp.py`,
`publish.py`, `healthcheck.py` né `linux/`, cioè i file su cui si regge il sistema
attuale. Chi deve fare un deploy completo non può usarlo, e ricade sull'`scp -r`.

Una lista di file da copiare invecchia in silenzio ogni volta che nasce un file nuovo.

### Perché nessuno se n'è accorto

Dopo un azzeramento `healthcheck.py` riporta tutto verde:

```
✅ ultimo controllo del mercato: 5 minuti fa
💰 equity 100.00 € (+0.00% dal via)
```

Il controllo verifica che lo stato sia **recente**, non che sia **continuo**. Uno
stato appena azzerato è recentissimo. Il controllo che esiste apposta per distinguere
il silenzio corretto dal guasto non vede il guasto peggiore.

## Il disegno

Sei pezzi indipendenti, ognuno verificabile da solo.

Nota trasversale sugli allarmi: `core.py` non parla con Telegram e non deve iniziare
a farlo — è il livello dei dati. Dove qui sotto si legge "manda l'allarme", il
meccanismo è: `core.py` solleva un'eccezione dedicata (`StatoPerduto`), e
`bot.py` la intercetta all'avvio e invia il messaggio con la `send()` che già ha.

### 1. `DATA_DIR`: i dati escono dalla cartella del codice

`core.py` calcola la cartella dati in quest'ordine:

1. variabile d'ambiente `TRADEBOT_DATI`
2. chiave `data_dir` in `config.json`
3. default `~/trading-dati`

Dentro ci vanno `state.json`, `journal.csv` e `report/`. La cartella del codice
diventa sacrificabile: nessun `scp`, `rsync` o `rm -rf` del codice può più toccare
lo storico.

`BASE` resta com'è (serve per `docs/`, che è codice pubblicato, non dato).

`daily_review.py:33` calcola `REPORT_DIR` da `BASE`: va spostato su `DATA_DIR`,
altrimenti i report restano nella cartella sacrificabile.

### 2. Migrazione automatica, una volta sola

All'avvio, dentro la risoluzione di `DATA_DIR`:

- se `DATA_DIR/state.json` **non** esiste e ne esiste uno accanto al codice → sposta
  `state.json` e `journal.csv` in `DATA_DIR`, scrivi a log cosa è stato spostato, e
  segnalalo su Telegram.
- se `DATA_DIR/state.json` **esiste già** → i file accanto al codice vengono
  **ignorati** e viene emesso un avviso a log. Questo è il caso dell'`scp -r`
  distratto: diventa innocuo.

Nessun passaggio manuale sul Pi.

### 3. Blocco all'avvio

In `load_state`, quando il file di stato manca:

- se `DATA_DIR/journal.csv` esiste **e contiene almeno una riga `open` o `close`** →
  **non creare uno stato vuoto**. Solleva un errore esplicito e manda l'allarme
  Telegram. Un bot che riparte in silenzio da 100 € distrugge l'unica cosa di valore
  prodotta finora, che è il registro delle misure.
- altrimenti (journal assente o vuoto) → installazione nuova, crea lo stato vuoto.

Via d'uscita esplicita per azzerare di proposito: `TRADEBOT_NUOVO_CONTO=1`.

### 4. Default per lo stato

`load_state` riempie le chiavi mancanti da un `DEFAULTS_STATE`, come già fa
`load_config` con `DEFAULTS` (`core.py:64`). Lo `state.json` attuale non ha
`shadow_cash`, `shadow_positions` né `created`: chiavi che `blank_state()` crea ma
che uno stato scritto da una versione precedente non possiede. Alla prima lettura
diretta sono un `KeyError`. È la stessa classe di bug già pagata una volta con 37
riavvii in loop, documentata a `core.py:56`.

Lo stato nuovo include anche `created` (timestamp ISO), che serve al punto 5.

### 5. `sync.sh`: da lista di file a esclusioni

Passa a `rsync` con lista di esclusioni:

```
.git  __pycache__  *.pyc  *.log  .venv  venv  .DS_Store
state.json  state.json.tmp  journal.csv  report/
```

Copia tutto il resto, `linux/` compreso. Un file nuovo viene sincronizzato per
default: è l'inversione che impedisce il ripetersi della causa a monte.

Niente `--delete`: file vecchi che restano non fanno danno, una cancellazione
sbagliata sì.

Se `rsync` non è disponibile sul Pi, lo script si ferma con un messaggio chiaro
invece di degradare a `scp` parziale.

`config.json` continua a essere copiato, come oggi.

### 6. `healthcheck.py`: rilevare la discontinuità

A ogni giro salva in `DATA_DIR/ultimo_controllo.json` il `created` dello stato e la
lunghezza dello storico. Al giro successivo confronta:

- `created` cambiato → 🔴 **"lo stato è stato azzerato"**, con le due date
- storico più corto del giro prima → 🔴 stesso allarme

Difesa in profondità: il punto 3 rende quasi impossibile un azzeramento silenzioso,
questo lo rende visibile se accade lo stesso.

## Verifica

Test con `unittest` (nessuna dipendenza nuova, nessuna rete), su cartelle temporanee:

1. installazione pulita, senza journal → crea lo stato vuoto
2. stato esistente → viene caricato invariato
3. **stato mancante + journal con operazioni → deve rifiutarsi di partire**
4. stato mancante + journal con operazioni + `TRADEBOT_NUOVO_CONTO=1` → riparte
5. migrazione: stato accanto al codice, `DATA_DIR` vuota → viene spostato
6. precedenza: stato in entrambi i posti → vince `DATA_DIR`, l'altro è ignorato
7. default: stato privo di `shadow_cash`/`created` → le chiavi vengono riempite

Verifica manuale su `sync.sh`: `rsync --dry-run` deve mostrare che `state.json` e
`journal.csv` non sono nell'elenco, e che `linux/` e `perp.py` ci sono.

## Fuori perimetro

Restano in coda, non toccati da questo lavoro:

- **Portafoglio ombra.** `core.py` lo dichiara come principio di design n°4, ma
  `shadow_cash` e `shadow_positions` compaiono solo in `blank_state()` e in nessun
  altro punto del progetto. Non è implementato.
- **Candela incompleta.** Il docstring di `signal_momentum` dichiara di usare "solo
  la chiusura dell'ultima candela completa", ma `.iloc[-1]` prende quella in
  formazione. Con `check_interval_min=15` il filtro anti-whipsaw vale 45 minuti su un
  segnale a 60 giorni.

Nessuno dei due riguarda la persistenza. Vanno affrontati dopo, e separatamente,
perché cambiano il comportamento di trading — questo lavoro no.
