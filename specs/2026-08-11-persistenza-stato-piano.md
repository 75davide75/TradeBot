# Persistenza dello stato — piano di implementazione

> **Per chi esegue:** i passi usano caselle `- [ ]`. Spec di riferimento:
> `specs/2026-08-11-persistenza-stato-design.md`

**Obiettivo:** impedire che lo stato del sistema si azzeri durante i deploy, e
rendere visibile l'azzeramento se accade lo stesso.

**Architettura:** la logica di persistenza esce da `core.py` e va in un modulo
nuovo `stato.py` che usa **solo la libreria standard**. `core.py` la reimporta e
la riespone, così `from core import STATE_FILE` continua a funzionare ovunque.
I dati vivono in una cartella separata dal codice, risolta a tempo di import.

**Stack:** Python 3.9+ (il Pi ha 3.9), solo stdlib, `unittest` per i test.

## Vincoli globali

- `stato.py` non può importare `pandas`, `numpy`, né `core`. Nessun Python su
  questa macchina ha pandas: se la persistenza lo richiedesse, non sarebbe
  testabile qui né sul Pi senza dipendenze.
- Ordine di risoluzione della cartella dati: `TRADEBOT_DATI` → `data_dir` in
  `config.json` → `~/trading-dati`.
- Nessuna rete nei test.
- Compatibilità: `STATE_FILE`, `JOURNAL_FILE`, `BASE`, `load_state`,
  `save_state`, `journal`, `blank_state` restano importabili da `core`.

---

### Task 1: `stato.py` — cartella dati e migrazione

**File:**
- Crea: `stato.py`
- Test: `test_stato.py`

**Interfacce prodotte:**
- `cartella_dati() -> str`
- `DATA_DIR: str`, `STATE_FILE: str`, `JOURNAL_FILE: str`, `REPORT_DIR: str`
- `migra_se_serve(origine: str) -> list[str]`

- [ ] **Passo 1: test che falliscono**

```python
import importlib, json, os, sys, tempfile, unittest

def carica_stato(dati_dir, cfg_dir=None):
    """Reimporta stato.py con TRADEBOT_DATI puntato dove vogliamo."""
    os.environ['TRADEBOT_DATI'] = dati_dir
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import stato
    return importlib.reload(stato)

class TestCartellaDati(unittest.TestCase):
    def test_env_ha_precedenza(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            self.assertEqual(s.DATA_DIR, os.path.abspath(d))
            self.assertEqual(s.STATE_FILE, os.path.join(os.path.abspath(d), 'state.json'))

    def test_migrazione_sposta_i_file(self):
        with tempfile.TemporaryDirectory() as dati, tempfile.TemporaryDirectory() as codice:
            with open(os.path.join(codice, 'state.json'), 'w') as f:
                json.dump({'cash': 42.0}, f)
            with open(os.path.join(codice, 'journal.csv'), 'w') as f:
                f.write('ts,action\n')
            s = carica_stato(dati)
            mossi = s.migra_se_serve(codice)
            self.assertEqual(sorted(mossi), ['journal.csv', 'state.json'])
            self.assertFalse(os.path.exists(os.path.join(codice, 'state.json')))
            with open(s.STATE_FILE) as f:
                self.assertEqual(json.load(f)['cash'], 42.0)

    def test_dati_esistenti_vincono_sul_codice(self):
        """E' il caso dello 'scp -r' distratto: non deve sovrascrivere."""
        with tempfile.TemporaryDirectory() as dati, tempfile.TemporaryDirectory() as codice:
            with open(os.path.join(dati, 'state.json'), 'w') as f:
                json.dump({'cash': 999.0}, f)          # il vero
            with open(os.path.join(codice, 'state.json'), 'w') as f:
                json.dump({'cash': 100.0}, f)          # quello copiato per sbaglio
            s = carica_stato(dati)
            mossi = s.migra_se_serve(codice)
            self.assertEqual(mossi, [])
            with open(s.STATE_FILE) as f:
                self.assertEqual(json.load(f)['cash'], 999.0)
```

- [ ] **Passo 2: eseguire e verificare che falliscano**

Comando: `cd "/Users/davidesogos/Desktop/progetto trading" && python3 -m unittest test_stato -v`
Atteso: FAIL, `ModuleNotFoundError: No module named 'stato'`

- [ ] **Passo 3: scrivere `stato.py`**

```python
#!/usr/bin/env python3
"""
Persistenza: dove vivono i dati che non si possono perdere.

PERCHE' QUESTO FILE ESISTE

Lo stato del sistema si e' azzerato due volte durante i deploy (10/08 e
11/08/2026), la seconda a 25 secondi dal salvataggio dei file. Sono andati
persi 74 punti di storico e 8 posizioni aperte. La causa e' che i dati
vivevano DENTRO la cartella del codice, e la cartella del codice viene
sovrascritta a ogni deploy.

Qui i dati escono da li'. La cartella del codice torna a essere sacrificabile:
puoi copiarci sopra, cancellarla, rifarla da git, e lo storico non si muove.

Solo libreria standard, di proposito: questo e' il codice piu' critico del
sistema e deve poter girare e essere testato ovunque, anche dove pandas non
c'e'.
"""

import csv
import json
import os
import shutil
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "config.json")


class StatoPerduto(RuntimeError):
    """Lo stato manca, ma il journal dice che il sistema ha gia' operato."""


def cartella_dati() -> str:
    """
    Ordine: variabile d'ambiente, poi config.json, poi il default.

    La variabile viene prima perche' serve ai test e alle esecuzioni una
    tantum senza toccare la configurazione vera.
    """
    d = os.environ.get("TRADEBOT_DATI")
    if not d:
        try:
            with open(CONFIG_FILE) as f:
                d = json.load(f).get("data_dir")
        except Exception:
            d = None
    if not d:
        d = os.path.join("~", "trading-dati")
    return os.path.abspath(os.path.expanduser(d))


DATA_DIR = cartella_dati()
STATE_FILE = os.path.join(DATA_DIR, "state.json")
JOURNAL_FILE = os.path.join(DATA_DIR, "journal.csv")
REPORT_DIR = os.path.join(DATA_DIR, "report")


def migra_se_serve(origine: str = BASE) -> list:
    """
    Sposta i dati dalla cartella del codice a quella dei dati, una volta sola.

    Se il file esiste GIA' nella cartella dati, quello accanto al codice viene
    ignorato e basta. E' esattamente il caso di un 'scp -r' che ha ricopiato
    un state.json vuoto: cosi' diventa innocuo invece che distruttivo.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    mossi = []
    for nome in ("state.json", "journal.csv"):
        vecchio = os.path.join(origine, nome)
        nuovo = os.path.join(DATA_DIR, nome)
        if not os.path.exists(vecchio):
            continue
        if os.path.exists(nuovo):
            print(f"[dati] ignoro {vecchio}: quello buono e' {nuovo}")
            continue
        shutil.move(vecchio, nuovo)      # shutil, non os.replace: puo' essere un altro filesystem
        mossi.append(nome)
        print(f"[dati] spostato {nome} in {DATA_DIR}")
    vecchio_report = os.path.join(origine, "report")
    if os.path.isdir(vecchio_report) and not os.path.isdir(REPORT_DIR):
        shutil.move(vecchio_report, REPORT_DIR)
        mossi.append("report/")
    return mossi
```

- [ ] **Passo 4: eseguire e verificare che passino**

Comando: `cd "/Users/davidesogos/Desktop/progetto trading" && python3 -m unittest test_stato -v`
Atteso: 3 test, tutti PASS

- [ ] **Passo 5: commit**

```bash
git add stato.py test_stato.py
git commit -m "stato.py: i dati escono dalla cartella del codice"
```

---

### Task 2: blocco all'avvio e default dello stato

**File:**
- Modifica: `stato.py`
- Test: `test_stato.py`

**Interfacce prodotte:**
- `default_stato(cfg: dict) -> dict`, `blank_state(cfg: dict) -> dict`
- `load_state(cfg: dict) -> dict`, `save_state(state: dict) -> None`
- `journal(action: str, **campi) -> None`
- `ha_operato() -> bool`

- [ ] **Passo 1: test che falliscono**

```python
CFG = {'capital': 100.0}

class TestCaricamento(unittest.TestCase):
    def test_installazione_pulita(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            st = s.load_state(CFG)
            self.assertEqual(st['cash'], 100.0)
            self.assertEqual(st['positions'], {})
            self.assertIn('created', st)

    def test_stato_esistente_viene_caricato(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            with open(s.STATE_FILE, 'w') as f:
                json.dump({'cash': 55.5, 'positions': {'X': {}}, 'history': []}, f)
            st = s.load_state(CFG)
            self.assertEqual(st['cash'], 55.5)

    def test_stato_mancante_con_journal_pieno_rifiuta(self):
        """Il cuore del lavoro: non ripartire mai da zero in silenzio."""
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            with open(s.JOURNAL_FILE, 'w') as f:
                f.write('ts,action,pair\n2026-08-11T00:00:00,open,XXBTZEUR\n')
            with self.assertRaises(s.StatoPerduto):
                s.load_state(CFG)

    def test_via_di_uscita_esplicita(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            with open(s.JOURNAL_FILE, 'w') as f:
                f.write('ts,action,pair\n2026-08-11T00:00:00,open,XXBTZEUR\n')
            os.environ['TRADEBOT_NUOVO_CONTO'] = '1'
            try:
                st = s.load_state(CFG)
                self.assertEqual(st['cash'], 100.0)
            finally:
                del os.environ['TRADEBOT_NUOVO_CONTO']

    def test_journal_con_sola_intestazione_non_blocca(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            with open(s.JOURNAL_FILE, 'w') as f:
                f.write('ts,action,pair\n')
            self.assertEqual(s.load_state(CFG)['cash'], 100.0)

    def test_default_riempiono_le_chiavi_mancanti(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            with open(s.STATE_FILE, 'w') as f:
                json.dump({'cash': 20.0, 'history': [{'ts': '2026-01-01T00:00:00+00:00'}]}, f)
            st = s.load_state(CFG)
            self.assertIn('shadow_cash', st)
            self.assertIn('positions', st)
            # created non deve essere "adesso": falsificherebbe la continuita'
            self.assertEqual(st['created'], '2026-01-01T00:00:00+00:00')
```

- [ ] **Passo 2: eseguire e verificare che falliscano**

Comando: `python3 -m unittest test_stato -v`
Atteso: FAIL, `module 'stato' has no attribute 'load_state'`

- [ ] **Passo 3: aggiungere a `stato.py`**

```python
def default_stato(cfg: dict) -> dict:
    cap = cfg["capital"]
    return {
        "mode": "paper",
        "cash": cap,
        "positions": {},
        "peak_equity": cap,
        "halted": False,
        "halt_reason": "",
        "paused": False,
        "conferme": {},
        "shadow_cash": cap,          # portafoglio ombra: previsto dal design
        "shadow_positions": {},
        "created": datetime.now(timezone.utc).isoformat(),
        "history": [],
    }


def blank_state(cfg: dict) -> dict:
    return default_stato(cfg)


def _con_default(state: dict, cfg: dict) -> dict:
    """
    Riempie le chiavi mancanti, come load_config fa con la configurazione.

    Serve perche' uno state.json scritto da una versione precedente non ha le
    chiavi aggiunte dopo, e la prima riga che le legge e' un KeyError. E' la
    stessa classe di bug gia' pagata una volta con 37 riavvii in loop.
    """
    d = default_stato(cfg)
    for k, v in d.items():
        if k in state:
            continue
        if k == "created":
            # Non inventare "adesso": farebbe sembrare azzerato uno stato che
            # non lo e', e il controllo di continuita' urlerebbe a vuoto.
            storia = state.get("history") or []
            v = storia[0].get("ts", v) if storia else v
        state[k] = v
    return state


def ha_operato() -> bool:
    """Vero se il journal contiene almeno un'apertura o una chiusura."""
    if not os.path.exists(JOURNAL_FILE):
        return False
    try:
        with open(JOURNAL_FILE) as f:
            for riga in csv.DictReader(f):
                if riga.get("action") in ("open", "close"):
                    return True
    except Exception:
        return False
    return False


def load_state(cfg: dict) -> dict:
    if not os.path.exists(STATE_FILE):
        if ha_operato() and os.environ.get("TRADEBOT_NUOVO_CONTO") != "1":
            raise StatoPerduto(
                f"{STATE_FILE} non esiste, ma {JOURNAL_FILE} contiene operazioni "
                f"gia' eseguite. Ripartire da zero cancellerebbe la storia del "
                f"conto senza dirlo. Ripristina lo stato, oppure riparti "
                f"deliberatamente con TRADEBOT_NUOVO_CONTO=1.")
        s = default_stato(cfg)
        save_state(s)
        return s
    with open(STATE_FILE) as f:
        return _con_default(json.load(f), cfg)


def save_state(state: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)   # scrittura atomica: niente stato corrotto


def journal(action: str, **campi) -> None:
    """Ogni decisione viene scritta qui. Il journal e' la fonte di verita'."""
    os.makedirs(DATA_DIR, exist_ok=True)
    riga = {"ts": datetime.now(timezone.utc).isoformat(), "action": action}
    riga.update(campi)
    cols = ["ts", "action", "pair", "side", "price", "notional",
            "leverage", "equity", "reason", "confirmed"]
    esiste = os.path.exists(JOURNAL_FILE)
    with open(JOURNAL_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if not esiste:
            w.writeheader()
        w.writerow(riga)
```

- [ ] **Passo 4: eseguire e verificare che passino**

Comando: `python3 -m unittest test_stato -v`
Atteso: 9 test, tutti PASS

- [ ] **Passo 5: commit**

```bash
git add stato.py test_stato.py
git commit -m "Blocco all'avvio se lo stato sparisce, e default per lo stato"
```

---

### Task 3: `core.py` usa `stato.py`

**File:**
- Modifica: `core.py` (rimuove `STATE_FILE`, `JOURNAL_FILE`, `blank_state`,
  `load_state`, `save_state`, `journal`; li reimporta)

**Interfacce consumate:** tutto quanto prodotto dai Task 1 e 2.

- [ ] **Passo 1: sostituire le costanti in `core.py`**

Al posto delle righe 23-25 (`BASE`, `STATE_FILE`, `JOURNAL_FILE`, `CONFIG_FILE`):

```python
from stato import (BASE, CONFIG_FILE, DATA_DIR, JOURNAL_FILE, REPORT_DIR,
                   STATE_FILE, StatoPerduto, blank_state, journal, load_state,
                   migra_se_serve, save_state)
```

- [ ] **Passo 2: cancellare da `core.py` le funzioni ora duplicate**

Rimuovere `blank_state`, `load_state`, `save_state`, `journal` (righe 223-265
della versione attuale). `equity`, `open_position`, `close_position`,
`check_kill_switch` restano dove sono: usano `journal` importato.

- [ ] **Passo 3: verificare che tutto importi ancora**

Comando:
```bash
cd "/Users/davidesogos/Desktop/progetto trading" && TRADEBOT_DATI=/tmp/td-verifica python3 -c "
import ast, sys
for f in ('core.py','bot.py','publish.py','healthcheck.py','daily_review.py','stato.py'):
    ast.parse(open(f).read()); print('sintassi ok:', f)
import stato; print('DATA_DIR =', stato.DATA_DIR)
"
```
Atteso: sei righe "sintassi ok" e il `DATA_DIR` di prova.

Nota: `core.py` importa numpy/pandas, non installati qui. Il controllo e'
sintattico piu' l'import del solo `stato`. La verifica funzionale completa
avviene sul Pi.

- [ ] **Passo 4: commit**

```bash
git add core.py
git commit -m "core.py delega la persistenza a stato.py"
```

---

### Task 4: `bot.py` intercetta `StatoPerduto`

**File:**
- Modifica: `bot.py` (import, e `main()`)
- Modifica: `linux/tradingbot.service`

- [ ] **Passo 1: import in `bot.py`**

Aggiungere `StatoPerduto` e `migra_se_serve` alla `from core import (...)`.

- [ ] **Passo 2: all'inizio di `main()`**

```python
def main():
    # La migrazione gira una volta sola: se i dati sono gia' al loro posto,
    # non fa nulla.
    for nome in migra_se_serve():
        print(f"[avvio] migrato {nome}")

    try:
        load_state(CFG)
    except StatoPerduto as e:
        # Il marcatore evita che systemd, riavviando ogni 30 secondi, mandi
        # lo stesso allarme all'infinito.
        marcatore = os.path.join(DATA_DIR, ".allarme_stato_inviato")
        if not os.path.exists(marcatore):
            send("🛑 <b>AVVIO BLOCCATO — stato non trovato</b>\n\n"
                 f"{e}\n\n<i>Il bot non riparte da solo: ripartire da zero "
                 "cancellerebbe lo storico senza dirlo.</i>")
            try:
                open(marcatore, "w").close()
            except Exception:
                pass
        raise SystemExit(1)
    ...
```

`os` e `DATA_DIR` vanno importati in `bot.py` (`import os`, e `DATA_DIR` nella
`from core import`).

- [ ] **Passo 3: cancellare il marcatore quando l'avvio riesce**

Subito dopo il `try/except`, in caso di successo:

```python
    marcatore = os.path.join(DATA_DIR, ".allarme_stato_inviato")
    if os.path.exists(marcatore):
        os.remove(marcatore)
```

- [ ] **Passo 4: `linux/tradingbot.service`**

Aggiungere nella sezione `[Unit]`, così systemd smette di riprovare e il
servizio resta in stato `failed`, che `healthcheck.py` vede e segnala:

```ini
StartLimitIntervalSec=300
StartLimitBurst=3
```

- [ ] **Passo 5: commit**

```bash
git add bot.py linux/tradingbot.service
git commit -m "Il bot si ferma e avvisa invece di ripartire da zero"
```

---

### Task 5: report, continuità nell'healthcheck, sync

**File:**
- Modifica: `daily_review.py:33`
- Modifica: `healthcheck.py`
- Modifica: `sync.sh`

- [ ] **Passo 1: `daily_review.py`**

Sostituire `REPORT_DIR = os.path.join(BASE, "report")` con l'import da `core`
(che lo riespone da `stato`):

```python
from core import REPORT_DIR
```
rimuovendo `BASE` dall'import se non serve altrove nel file.

- [ ] **Passo 2: continuità in `healthcheck.py`**

Dopo il blocco che legge lo stato, prima del calcolo di `testa`:

```python
    # --- lo stato e' lo STESSO di ieri, o e' stato azzerato?
    # Il controllo precedente guardava se lo stato era RECENTE. Uno stato
    # appena azzerato e' recentissimo: e' il motivo per cui i due
    # azzeramenti di agosto sono passati inosservati.
    segna = os.path.join(DATA_DIR, "ultimo_controllo.json")
    try:
        prec = json.load(open(segna)) if os.path.exists(segna) else {}
        adesso = {"created": st.get("created"), "n_storico": len(st.get("history", []))}
        if prec:
            if prec.get("created") and adesso["created"] and prec["created"] != adesso["created"]:
                problemi.append(
                    f"lo stato e' stato AZZERATO (era del {prec['created'][:19]}, "
                    f"ora e' del {adesso['created'][:19]})")
                righe.append("🔴 stato azzerato dall'ultimo controllo")
            elif adesso["n_storico"] < prec.get("n_storico", 0):
                problemi.append(f"lo storico si e' accorciato: da "
                                f"{prec['n_storico']} a {adesso['n_storico']} punti")
                righe.append("🔴 storico accorciato")
        with open(segna, "w") as f:
            json.dump(adesso, f)
    except Exception as e:
        righe.append(f"⚠️ controllo di continuita' non eseguito: {e}")
```

Aggiungere `DATA_DIR` all'import da `core`.

- [ ] **Passo 3: `sync.sh` da lista di file a esclusioni**

Sostituire il blocco `scp ...` con:

```bash
if ! command -v rsync >/dev/null 2>&1; then
    echo -e "${RED}✗ rsync non disponibile. Installalo: sudo apt install rsync${NC}"
    exit 1
fi

# Elenco di ESCLUSIONI, non di inclusioni. Una lista di file da copiare
# invecchia in silenzio a ogni file nuovo: e' successo con perp.py,
# publish.py e healthcheck.py, che non venivano piu' sincronizzati.
rsync -az --info=stats1 \
    --exclude '.git/' --exclude '__pycache__/' --exclude '*.pyc' \
    --exclude '.venv/' --exclude 'venv/' --exclude '.DS_Store' --exclude '*.log' \
    --exclude 'state.json' --exclude 'state.json.tmp' \
    --exclude 'journal.csv' --exclude 'report/' \
    ./ "${PI_USER}@${PI_HOST}:${PI_DIR}/"
```

- [ ] **Passo 4: verifica a secco**

Comando:
```bash
cd "/Users/davidesogos/Desktop/progetto trading" && rsync -an --info=name \
  --exclude '.git/' --exclude '__pycache__/' --exclude '*.pyc' \
  --exclude '.venv/' --exclude 'venv/' --exclude '.DS_Store' --exclude '*.log' \
  --exclude 'state.json' --exclude 'state.json.tmp' \
  --exclude 'journal.csv' --exclude 'report/' \
  ./ /tmp/sync-prova/ | sort
```
Atteso: compaiono `perp.py`, `publish.py`, `healthcheck.py`, `stato.py` e
`linux/`; **non** compaiono `state.json` né `journal.csv`.

- [ ] **Passo 5: commit**

```bash
git add daily_review.py healthcheck.py sync.sh
git commit -m "Report nella cartella dati, continuita' nell'healthcheck, sync per esclusioni"
```

---

### Task 6: nota di migrazione per il Pi

**File:**
- Modifica: `linux/INSTALLA.md`

- [ ] **Passo 1: sostituire il comando di copia pericoloso**

`INSTALLA.md` documenta `scp -r "progetto trading" pi@raspberrypi.local:~/trading`,
che copia anche `state.json`. Sostituirlo con il `rsync` del Task 5 e aggiungere:

```markdown
## Dove vivono i dati

`state.json`, `journal.csv` e `report/` **non** stanno nella cartella del
codice: stanno in `~/trading-dati/`. La cartella del codice e' sacrificabile —
puoi sovrascriverla, cancellarla, rifarla da git.

Al primo avvio dopo l'aggiornamento il bot sposta da solo i file dalla vecchia
posizione e lo scrive nel log. Non serve fare nulla a mano.

Se il bot trova il journal ma non lo stato, **non riparte**: manda un messaggio
su Telegram e si ferma, perche' ripartire da zero cancellerebbe la storia del
conto. Per azzerare di proposito:
`TRADEBOT_NUOVO_CONTO=1 python3 bot.py`
```

- [ ] **Passo 2: commit**

```bash
git add linux/INSTALLA.md
git commit -m "INSTALLA.md: niente piu' scp -r, e dove vivono i dati"
```

---

## Auto-revisione

**Copertura della spec:** §1 DATA_DIR → Task 1. §2 migrazione → Task 1. §3
blocco all'avvio → Task 2 (logica) + Task 4 (allarme). §4 default → Task 2.
§5 sync.sh → Task 5. §6 continuità healthcheck → Task 5. `REPORT_DIR` di
`daily_review.py` → Task 5. Nessuna sezione scoperta.

**Segnaposto:** nessuno. Ogni passo che tocca codice mostra il codice.

**Coerenza dei nomi:** `cartella_dati`, `migra_se_serve`, `default_stato`,
`blank_state`, `load_state`, `save_state`, `journal`, `ha_operato`,
`StatoPerduto`, `DATA_DIR`, `STATE_FILE`, `JOURNAL_FILE`, `REPORT_DIR` — usati
con gli stessi nomi nei Task 1-5.

**Fuori perimetro, come da spec:** portafoglio ombra (lo stato ora ha le
chiavi, ma nessuna logica le usa) e candela incompleta nel segnale.
