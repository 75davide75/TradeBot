# Dashboard e registrazione dei wallet — piano di implementazione

> **Per chi esegue:** i passi usano caselle `- [ ]`. Spec di riferimento:
> `specs/2026-08-15-dashboard-wallet-design.md`

**Obiettivo:** rendere i tre portafogli distinguibili e misurabili nella
dashboard, e cominciare a registrare le operazioni di ombra e IA, che oggi non
lasciano traccia.

**Architettura:** la parte Python aggiunge una colonna `wallet` al registro e la
riempie anche dai portafogli secondari; `publish.py` la pubblica insieme a un
blocco `wallet` nuovo, **accanto** ai campi esistenti, mai al loro posto. La
pagina si divide in tre file (`index.html`, `dashboard.css`, `dashboard.js`) e
legge il blocco nuovo quando c'è, ripiegando sui campi vecchi quando manca.

**Stack:** Python 3.9 (è la versione del Pi), solo libreria standard, `unittest`.
La pagina è HTML/CSS/JS senza build, servita da GitHub Pages, con
`lightweight-charts` 4.2 da CDN come già oggi.

## Vincoli globali

- **Nessuna decisione di trading viene modificata.** Segnale, dimensionamento,
  leva, stop-loss, filtro di negoziabilità, kill switch: intoccabili. Le
  modifiche a `core.py` e `bot.py` aggiungono righe di registro e nient'altro.
- **Le righe dati del registro non si riscrivono mai.** La migrazione tocca solo
  la riga d'intestazione. `journal.csv` è la fonte di verità del sistema.
- **`journal.csv` usa `\r\n`**, perché `csv.DictWriter` scrive con quel
  terminatore. La migrazione lo rileva dalla riga esistente invece di assumerlo:
  su un file scritto a mano il terminatore è `\n`, ed entrambi devono restare
  intatti.
- **pandas e numpy non sono installati su questa macchina.** I test che toccano
  `core.py` li sostituiscono con moduli finti (Task 2). `stato.py` non li importa
  affatto e non deve iniziare.
- **`publish.py` non va eseguito su questo Mac.** Lo `state.json` locale è vuoto
  e sovrascriverebbe `docs/data.json` con un conto da 100 €, committandolo.
- **Il repo è pubblico.** Ogni campo che entra in `data.json` passa da una
  whitelist esplicita, mai da un riversamento dello stato.
- **Nomi dei wallet, ovunque:** `reale`, `ombra`, `ia`. La chiave dello stato per
  l'ombra è invece `shadow` (`shadow_cash`, `shadow_positions`): la traduzione
  avviene in un solo punto, `NOME_WALLET` in `core.py` (Task 2).
- Nessuna rete nei test.

---

## Parte A — la registrazione

### Task 1: `stato.py` — colonna `wallet` e migrazione dell'intestazione

**File:**
- Modifica: `stato.py:276-288` (`journal`)
- Test: `test_stato.py`

**Interfacce prodotte:**
- `COLONNE_JOURNAL: list[str]` — le undici colonne, `wallet` per ultima
- `migra_journal_se_serve() -> bool` — `True` se ha migrato, `False` se non
  c'era niente da fare
- `journal(action: str, wallet: str = "reale", **campi) -> None`

- [ ] **Passo 1: scrivere i test che falliscono**

In coda a `test_stato.py`, prima di `if __name__`:

```python
class TestColonnaWallet(unittest.TestCase):
    """
    Il registro guadagna una colonna. DictWriter scrive l'intestazione solo
    quando il file non esiste (stato.py:286), quindi senza migrazione si
    scriverebbero undici valori sotto dieci nomi e da quel momento DictReader
    assegnerebbe i campi sbagliati — in silenzio, sulla fonte di verita'.
    """

    VECCHIA = ("ts,action,pair,side,price,notional,leverage,equity,reason,confirmed")

    def _registro(self, s, fine="\r\n"):
        with open(s.JOURNAL_FILE, "w", newline="") as f:
            f.write(self.VECCHIA + fine)
            f.write("2026-08-14T00:31:29+00:00,open,XLTCZEUR,-1.0,44.74,17.49,"
                    "0.7,,segnale,True" + fine)

    def test_migrazione_aggiunge_la_colonna(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            self._registro(s)
            self.assertTrue(s.migra_journal_se_serve())
            with open(s.JOURNAL_FILE, newline="") as f:
                prima = f.readline()
            self.assertTrue(prima.startswith(self.VECCHIA + ",wallet"))

    def test_migrazione_preserva_il_terminatore(self):
        """DictWriter usa \\r\\n. Scrivere \\n mescolerebbe i due stili."""
        for fine in ("\r\n", "\n"):
            with tempfile.TemporaryDirectory() as d:
                s = carica_stato(d)
                self._registro(s, fine)
                s.migra_journal_se_serve()
                with open(s.JOURNAL_FILE, "rb") as f:
                    testa = f.read().split(b"wallet")[1][:2]
                self.assertTrue(testa.startswith(fine.encode()))

    def test_migrazione_e_idempotente(self):
        """Il timer di pull la portera' sul Pi senza che nessuno la guardi."""
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            self._registro(s)
            self.assertTrue(s.migra_journal_se_serve())
            dopo_una = open(s.JOURNAL_FILE, "rb").read()
            self.assertFalse(s.migra_journal_se_serve())
            self.assertEqual(open(s.JOURNAL_FILE, "rb").read(), dopo_una)

    def test_migrazione_non_tocca_le_righe_dati(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            self._registro(s)
            prima = open(s.JOURNAL_FILE, "rb").read().split(b"\r\n", 1)[1]
            s.migra_journal_se_serve()
            dopo = open(s.JOURNAL_FILE, "rb").read().split(b"\r\n", 1)[1]
            self.assertEqual(prima, dopo)

    def test_righe_vecchie_valgono_reale(self):
        """Restano a dieci campi: DictReader mette None, e None e' 'reale'."""
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            self._registro(s)
            s.migra_journal_se_serve()
            s.journal("open", wallet="ombra", pair="XLTCZEUR", notional=25.0)
            with open(s.JOURNAL_FILE, newline="") as f:
                righe = list(csv.DictReader(f))
            self.assertEqual(len(righe), 2)
            self.assertIsNone(righe[0]["wallet"])
            self.assertEqual(righe[0]["pair"], "XLTCZEUR")     # niente slittamenti
            self.assertEqual(righe[0]["confirmed"], "True")
            self.assertEqual(righe[1]["wallet"], "ombra")

    def test_journal_scrive_reale_per_difetto(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            s.journal("open", pair="XXBTZEUR", price=1.0)
            with open(s.JOURNAL_FILE, newline="") as f:
                righe = list(csv.DictReader(f))
            self.assertEqual(righe[0]["wallet"], "reale")

    def test_ha_operato_ignora_il_wallet(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            s.journal("open", wallet="ia", pair="SOLEUR", price=1.0)
            self.assertTrue(s.ha_operato())
```

`csv` va aggiunto agli import in cima a `test_stato.py`.

- [ ] **Passo 2: eseguire e verificare che falliscano**

```bash
cd "/Users/davidesogos/Desktop/progetto trading" && python3 -m unittest test_stato -v
```
Atteso: FAIL, `module 'stato' has no attribute 'migra_journal_se_serve'`

- [ ] **Passo 3: modificare `stato.py`**

Sostituire `journal` (righe 276-288) con:

```python
# Undici colonne: 'wallet' e' l'ultima, e questo non e' un dettaglio estetico.
# Le righe scritte prima che esistesse ne hanno dieci, e DictReader restituisce
# None per quella mancante. Mettendola in fondo, quelle righe restano leggibili
# senza riscriverle: nessun campo slitta di posto.
COLONNE_JOURNAL = ["ts", "action", "pair", "side", "price", "notional",
                   "leverage", "equity", "reason", "confirmed", "wallet"]


def migra_journal_se_serve() -> bool:
    """
    Aggiunge 'wallet' all'intestazione del registro. Una volta sola, e
    riscrivendo SOLO la prima riga.

    Serve perche' DictWriter scrive l'intestazione unicamente quando il file
    non esiste: senza migrazione, da qui in avanti finirebbero undici valori
    sotto dieci nomi, e ogni lettura successiva assegnerebbe i campi sbagliati.
    Sul registro, che e' l'unica cosa di valore che questo sistema produce.

    Le righe dati non vengono toccate. Riscrivere tutto il file metterebbe a
    rischio ogni riga in cambio di un allineamento puramente cosmetico: chi
    legge tratta il campo mancante come 'reale', che e' cio' che quelle righe
    sono.

    Idempotente di proposito: il timer di pull la porta sul Pi e la esegue
    senza che nessuno stia guardando.
    """
    if not os.path.exists(JOURNAL_FILE):
        return False
    with open(JOURNAL_FILE, newline="") as f:
        prima = f.readline()
    if not prima.strip():
        return False
    # Il terminatore va rilevato, non deciso: DictWriter scrive \r\n, un file
    # fatto a mano ha \n, e mescolarli dentro lo stesso registro e' il genere
    # di danno che si scopre mesi dopo.
    fine = "\r\n" if prima.endswith("\r\n") else "\n"
    intestazione = prima.rstrip("\r\n").split(",")
    if "wallet" in intestazione:
        return False
    tmp = JOURNAL_FILE + ".tmp"
    with open(JOURNAL_FILE, newline="") as sorgente, \
         open(tmp, "w", newline="") as dest:
        sorgente.readline()                       # scarta la vecchia intestazione
        dest.write(",".join(intestazione + ["wallet"]) + fine)
        shutil.copyfileobj(sorgente, dest)        # le righe dati passano identiche
    os.replace(tmp, JOURNAL_FILE)                 # atomica, come save_state
    print(f"[registro] aggiunta la colonna 'wallet' a {JOURNAL_FILE}")
    return True


def journal(action: str, wallet: str = "reale", **campi) -> None:
    """
    Ogni decisione viene scritta qui. Il journal e' la fonte di verita'.

    'wallet' dice QUALE dei tre portafogli ha agito. Il valore predefinito e'
    'reale' perche' per due anni di righe e' stato l'unico a scrivere, e le
    righe senza il campo sono sue.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    migra_journal_se_serve()
    riga = {"ts": datetime.now(timezone.utc).isoformat(),
            "action": action, "wallet": wallet}
    riga.update(campi)
    esiste = os.path.exists(JOURNAL_FILE)
    with open(JOURNAL_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLONNE_JOURNAL, extrasaction="ignore")
        if not esiste:
            w.writeheader()
        w.writerow(riga)
```

Aggiungere poi la chiamata in coda a `migra_se_serve`, subito prima del
`return mossi`, così la migrazione compare anche nel log di avvio del Pi:

```python
    if migra_journal_se_serve():
        mossi.append("journal.csv (colonna wallet)")
    return mossi
```

`shutil` è già importato in `stato.py`.

- [ ] **Passo 4: eseguire e verificare che passino**

```bash
cd "/Users/davidesogos/Desktop/progetto trading" && python3 -m unittest test_stato -v
```
Atteso: tutti PASS, compresi i test preesistenti. In particolare
`test_journal_scrive_intestazione_una_volta_sola` deve continuare a passare: la
sua asserzione è che le righe siano tre e che la prima inizi con `ts,action`.

- [ ] **Passo 5: commit**

```bash
git add stato.py test_stato.py
git commit -m "Il registro guadagna la colonna wallet, con migrazione della sola intestazione"
```

---

### Task 2: `core.py` — ombra e IA registrano le loro operazioni

**File:**
- Modifica: `core.py:358-381` (`_apri`, `_chiudi`)
- Crea: `test_portafogli.py`

**Interfacce consumate:** `journal(action, wallet=…, **campi)` dal Task 1.

**Interfacce prodotte:**
- `NOME_WALLET: dict` — `{"shadow": "ombra", "ia": "ia"}`, l'unico punto in cui
  la chiave dello stato diventa il nome pubblico del wallet

- [ ] **Passo 1: scrivere il test che fallisce**

Crea `test_portafogli.py`:

```python
#!/usr/bin/env python3
"""
Test della registrazione dei portafogli secondari.

    python3 -m unittest test_portafogli -v

Il test che conta piu' di tutti e' test_ombra_e_ia_finiscono_nel_registro:
per mesi _apri e _chiudi hanno mosso due portafogli su tre senza scrivere una
riga da nessuna parte. Se quel test sparisce, il confronto fra i tre torna a
essere un'opinione.

pandas e numpy non sono installati su questa macchina e core.py li importa.
Vengono sostituiti con moduli finti: servono solo perche' le annotazioni
'-> pd.DataFrame' vengono valutate quando la funzione viene definita. Nessuna
delle funzioni sotto test li usa.
"""

import csv
import importlib
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _nome, _attributi in (("numpy", {}), ("pandas", {"DataFrame": object})):
    _m = types.ModuleType(_nome)
    for _k, _v in _attributi.items():
        setattr(_m, _k, _v)
    sys.modules.setdefault(_nome, _m)


def carica_core(dati_dir):
    """Reimporta stato e core con la cartella dati puntata dove vogliamo noi."""
    os.environ["TRADEBOT_DATI"] = dati_dir
    import stato
    importlib.reload(stato)
    import core
    return importlib.reload(core)


def righe(percorso):
    with open(percorso, newline="") as f:
        return list(csv.DictReader(f))


class TestRegistrazione(unittest.TestCase):

    def test_ombra_e_ia_finiscono_nel_registro(self):
        with tempfile.TemporaryDirectory() as d:
            c = carica_core(d)
            st = {"shadow_cash": 200.0, "ia_cash": 200.0}
            c.apri_ombra(st, "XXBTZEUR", -1.0, 63572.0, 25.0)
            c.apri_ia(st, "SOLEUR", 1.0, 76.09, 12.0, 0.48)
            r = righe(c.JOURNAL_FILE)
            self.assertEqual([x["wallet"] for x in r], ["ombra", "ia"])
            self.assertEqual([x["action"] for x in r], ["open", "open"])
            self.assertEqual(r[0]["pair"], "XXBTZEUR")
            self.assertEqual(float(r[0]["leverage"]), 1.0)
            self.assertEqual(float(r[1]["notional"]), 12.0)

    def test_chiusura_registra_il_cash_del_proprio_portafoglio(self):
        """
        close_position scrive state['cash'] in 'equity' (core.py:328). I
        secondari devono scrivere il PROPRIO cash: con quello del reale, la
        colonna che dovrebbe separare i tre li renderebbe indistinguibili.
        """
        with tempfile.TemporaryDirectory() as d:
            c = carica_core(d)
            st = {"cash": 999.0, "shadow_cash": 200.0}
            c.apri_ombra(st, "XXBTZEUR", 1.0, 100.0, 25.0)
            c.chiudi_ombra(st, "XXBTZEUR", 110.0)
            chiusura = righe(c.JOURNAL_FILE)[-1]
            self.assertEqual(chiusura["action"], "close")
            self.assertEqual(chiusura["wallet"], "ombra")
            self.assertNotEqual(float(chiusura["equity"]), 999.0)
            self.assertAlmostEqual(float(chiusura["equity"]),
                                   round(st["shadow_cash"], 2), places=2)

    def test_chiusura_di_una_posizione_assente_non_registra(self):
        """_chiudi esce con 0.0 se il mercato non c'e': niente riga fantasma."""
        with tempfile.TemporaryDirectory() as d:
            c = carica_core(d)
            st = {"shadow_cash": 200.0}
            self.assertEqual(c.chiudi_ombra(st, "MAI_APERTO", 1.0), 0.0)
            self.assertFalse(os.path.exists(c.JOURNAL_FILE))

    def test_il_reale_resta_marcato_reale(self):
        with tempfile.TemporaryDirectory() as d:
            c = carica_core(d)
            st = {"cash": 200.0, "positions": {}}
            c.open_position(st, "ADAEUR", -1.0, 0.18, 8.74, 0.35, "segnale")
            self.assertEqual(righe(c.JOURNAL_FILE)[0]["wallet"], "reale")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Passo 2: eseguire e verificare che fallisca**

```bash
cd "/Users/davidesogos/Desktop/progetto trading" && python3 -m unittest test_portafogli -v
```
Atteso: FAIL su `test_ombra_e_ia_finiscono_nel_registro`, perché
`c.JOURNAL_FILE` non esiste: nessuna riga è stata scritta. È esattamente il
guasto che il task risolve.

- [ ] **Passo 3: modificare `core.py`**

Sostituire `_apri` e `_chiudi` (righe 358-381) con:

```python
# La chiave dello stato e' 'shadow' per ragioni storiche, ma il nome pubblico
# del portafoglio e' 'ombra' — nel registro, in data.json e nella dashboard.
# La traduzione avviene qui e in nessun altro posto: due mappature che possono
# divergere sono una mappatura che divergera'.
NOME_WALLET = {"shadow": "ombra", "ia": "ia"}


def _apri(state, chiave, pair, side, price, notional, leverage):
    """Apre in un portafoglio secondario qualsiasi (ombra o sperimentale)."""
    taker, apert, _ = costi_correnti()
    state[f"{chiave}_avviato"] = True
    state[f"{chiave}_cash"] = (state.get(f"{chiave}_cash", 0.0)
                               - notional * (taker + apert))
    state.setdefault(f"{chiave}_positions", {})[pair] = {
        "side": side, "entry": price, "notional": notional,
        "leverage": leverage,
        "opened": datetime.now(timezone.utc).isoformat(),
    }
    # Senza questa riga il portafoglio si muove e il registro non lo sa. E'
    # stato cosi' per mesi: due portafogli su tre operavano senza lasciare
    # traccia, e il confronto fra i tre — l'unica cosa che questo sistema
    # esiste per misurare — non era ricostruibile a posteriori.
    journal("open", wallet=NOME_WALLET[chiave], pair=pair, side=side,
            price=price, notional=round(notional, 2), leverage=leverage,
            equity=round(state[f"{chiave}_cash"], 2),
            reason=("rispecchia il reale, leva fissa 1x" if chiave == "shadow"
                    else "universo scelto dall'IA"),
            confirmed=True)


def _chiudi(state, chiave, pair, price) -> float:
    p = state.get(f"{chiave}_positions", {}).pop(pair, None)
    if not p:
        return 0.0
    move = (price - p["entry"]) / p["entry"] * p["side"]
    pnl = p["notional"] * move
    carry = p["notional"] * carry_giornaliero(pair, p["side"]) * _giorni_aperta(p)
    taker, _, _ = costi_correnti()
    netto = pnl - carry - p["notional"] * taker
    state[f"{chiave}_cash"] = state.get(f"{chiave}_cash", 0.0) + netto
    # In 'equity' va il cash di QUESTO portafoglio, non quello del reale:
    # e' la colonna in cui close_position scrive state["cash"] (core.py:328),
    # e riempirla col conto sbagliato renderebbe i tre indistinguibili proprio
    # dove devono separarsi.
    journal("close", wallet=NOME_WALLET[chiave], pair=pair, side=p["side"],
            price=price, notional=round(p["notional"], 2),
            leverage=p["leverage"], equity=round(state[f"{chiave}_cash"], 2),
            reason=("rispecchia il reale" if chiave == "shadow"
                    else "universo scelto dall'IA"),
            confirmed=True)
    return netto
```

- [ ] **Passo 4: eseguire e verificare che passi**

```bash
cd "/Users/davidesogos/Desktop/progetto trading" && python3 -m unittest test_portafogli -v
```
Atteso: 4 test, tutti PASS.

- [ ] **Passo 5: commit**

```bash
git add core.py test_portafogli.py
git commit -m "Ombra e IA registrano le loro operazioni nel journal"
```

---

### Task 3: `bot.py` — `ia_stop` smette di scrivere il P&L nel nozionale

**File:**
- Modifica: `bot.py:186-189`

**Interfacce consumate:** `chiudi_ia` del Task 2, che ora registra da sé la
chiusura.

- [ ] **Passo 1: sostituire il blocco**

Al posto di:

```python
            netto = chiudi_ia(state, pair, px)
            journal("ia_stop", pair=pair, price=px, notional=round(netto, 2),
                    reason=f"stop-loss portafoglio IA a {perdita:.1%}",
                    confirmed=True)
```

scrivere:

```python
            netto = chiudi_ia(state, pair, px)
            # chiudi_ia registra gia' la chiusura con nozionale e prezzo veri
            # (Task 2). Qui resta solo il MOTIVO, che e' l'informazione che
            # nessun'altra riga porta. Prima questa riga scriveva il P&L netto
            # dentro la colonna 'notional': un numero che in una tabella
            # affiancata agli altri portafogli si legge come un nozionale.
            journal("ia_stop", wallet="ia", pair=pair, price=px,
                    equity=round(netto, 2),
                    reason=f"stop-loss portafoglio IA a {perdita:.1%}",
                    confirmed=True)
```

- [ ] **Passo 2: verificare la sintassi**

```bash
cd "/Users/davidesogos/Desktop/progetto trading" && python3 -c "
import ast; ast.parse(open('bot.py').read()); print('sintassi ok: bot.py')
"
```
Atteso: `sintassi ok: bot.py`

Nota: `bot.py` importa pandas e non è eseguibile qui. La verifica funzionale
avviene sul Pi.

- [ ] **Passo 3: commit**

```bash
git add bot.py
git commit -m "ia_stop registra il motivo, non un P&L travestito da nozionale"
```

---

### Task 4: `healthcheck.py` — la finestra delle 60 righe resta sul reale

**File:**
- Modifica: `healthcheck.py:56-70` (`righe_journal`)

- [ ] **Passo 1: sostituire il corpo del ciclo**

Al posto di:

```python
            for r in csv.DictReader(f):
                if r.get("ts", "") < limite:
                    continue
                fuori.append({k: v for k, v in r.items() if v not in ("", None)})
```

scrivere:

```python
            for r in csv.DictReader(f):
                if r.get("ts", "") < limite:
                    continue
                # Solo il portafoglio reale. Da quando anche ombra e IA
                # registrano, le righe sono circa il triplo: senza questo
                # filtro le ultime 60 coprirebbero un terzo del tempo, e il
                # riassunto del mattino perderebbe giorni di contesto senza
                # che niente lo dica. Le righe scritte prima della colonna
                # 'wallet' non ce l'hanno, e sono del reale.
                if (r.get("wallet") or "reale") != "reale":
                    continue
                fuori.append({k: v for k, v in r.items() if v not in ("", None)})
```

- [ ] **Passo 2: verificare la sintassi**

```bash
cd "/Users/davidesogos/Desktop/progetto trading" && python3 -c "
import ast; ast.parse(open('healthcheck.py').read()); print('sintassi ok: healthcheck.py')
"
```
Atteso: `sintassi ok: healthcheck.py`

- [ ] **Passo 3: commit**

```bash
git add healthcheck.py
git commit -m "Il riassunto delle 9:00 legge il registro del solo portafoglio reale"
```

---

## Parte B — la pubblicazione

### Task 5: `publish.py` — blocco `wallet`, operazioni marcate, data d'inizio

**File:**
- Modifica: `publish.py:34` (`CAMPI_OP`), `publish.py:76-133` (`costruisci`)
- Crea: `test_publish.py`

**Interfacce prodotte:**
- `posizioni_pubblicabili(grezze: dict) -> dict` — whitelist a cinque campi,
  usata per tutti e tre i portafogli
- `blocco_wallet(state: dict, eq_ora, ombra_ora, ia_ora) -> dict`
- `inizio_storico_wallet(percorso: str) -> str | None`

- [ ] **Passo 1: scrivere i test che falliscono**

Crea `test_publish.py`:

```python
#!/usr/bin/env python3
"""
Test di cio' che esce in docs/data.json.

    python3 -m unittest test_publish -v

Il repo e' pubblico: il test che conta piu' di tutti e'
test_campi_fuori_whitelist_non_escono. Una whitelist che smette di essere una
whitelist non da' nessun segnale — funziona benissimo, pubblicando troppo.

pandas e numpy non sono installati qui e publish.py importa core, che li
importa. Vengono sostituiti con moduli finti, come in test_portafogli.py.
"""

import csv
import importlib
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for _nome, _attributi in (("numpy", {}), ("pandas", {"DataFrame": object})):
    _m = types.ModuleType(_nome)
    for _k, _v in _attributi.items():
        setattr(_m, _k, _v)
    sys.modules.setdefault(_nome, _m)


def carica_publish(dati_dir):
    os.environ["TRADEBOT_DATI"] = dati_dir
    import stato
    importlib.reload(stato)
    import core
    importlib.reload(core)
    import publish
    return importlib.reload(publish)


POSIZIONE = {"side": -1.0, "entry": 63572.22, "notional": 18.234,
             "leverage": 0.73, "opened": "2026-08-12T00:23:02+00:00"}


class TestWhitelist(unittest.TestCase):

    def test_campi_fuori_whitelist_non_escono(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            grezze = {"XXBTZEUR": dict(POSIZIONE,
                                       note_private="non deve uscire",
                                       chiave_api="nemmeno")}
            fuori = p.posizioni_pubblicabili(grezze)
            self.assertEqual(set(fuori["XXBTZEUR"]),
                             {"side", "entry", "notional", "leverage", "opened"})

    def test_nozionale_arrotondato(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            fuori = p.posizioni_pubblicabili({"XXBTZEUR": POSIZIONE})
            self.assertEqual(fuori["XXBTZEUR"]["notional"], 18.23)


class TestBloccoWallet(unittest.TestCase):

    def test_i_tre_portafogli_escono(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            st = {"positions": {"XXBTZEUR": POSIZIONE},
                  "shadow_positions": {"XXBTZEUR": dict(POSIZIONE, notional=25.0)},
                  "shadow_avviato": True}
            w = p.blocco_wallet(st, 200.66, 201.48, None)
            self.assertEqual(set(w), {"reale", "ombra", "ia"})
            self.assertEqual(w["reale"]["equity"], 200.66)
            self.assertEqual(w["ombra"]["posizioni"]["XXBTZEUR"]["notional"], 25.0)

    def test_stato_senza_le_chiavi_dei_secondari(self):
        """
        Uno state.json scritto da una versione precedente non ha
        shadow_positions ne' ia_positions. La prima riga che le legge come
        state['...'] e' un KeyError — stessa classe di bug documentata a
        core.py:56 e gia' pagata due volte.
        """
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            w = p.blocco_wallet({"cash": 100.0}, 100.0, None, None)
            self.assertEqual(w["ombra"]["posizioni"], {})
            self.assertIsNone(w["ombra"]["equity"])

    def test_avviato_distingue_il_mai_partito_dal_tutto_chiuso(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            mai = p.blocco_wallet({}, 100.0, None, None)
            self.assertFalse(mai["ia"]["avviato"])
            chiuso = p.blocco_wallet({"ia_avviato": True}, 100.0, None, 97.5)
            self.assertTrue(chiuso["ia"]["avviato"])
            self.assertEqual(chiuso["ia"]["posizioni"], {})


class TestInizioStorico(unittest.TestCase):

    INTESTAZIONE = ("ts,action,pair,side,price,notional,leverage,equity,"
                    "reason,confirmed,wallet\r\n")

    def _scrivi(self, percorso, righe):
        with open(percorso, "w", newline="") as f:
            f.write(self.INTESTAZIONE)
            for r in righe:
                f.write(r + "\r\n")

    def test_e_la_prima_riga_marcata(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            self._scrivi(p.JOURNAL_FILE, [
                "2026-08-11T11:28:15+00:00,open,XETHZEUR,1.0,1890.0,6.25,0.5,,segnale,True",
                "2026-08-15T09:00:00+00:00,open,XXBTZEUR,-1.0,63572.0,18.2,0.7,,segnale,True,reale",
                "2026-08-15T09:00:01+00:00,open,XXBTZEUR,-1.0,63572.0,25.0,1.0,,rispecchia,True,ombra",
            ])
            self.assertEqual(p.inizio_storico_wallet(p.JOURNAL_FILE),
                             "2026-08-15T09:00:00+00:00")

    def test_registro_tutto_vecchio_non_ha_inizio(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            self._scrivi(p.JOURNAL_FILE, [
                "2026-08-11T11:28:15+00:00,open,XETHZEUR,1.0,1890.0,6.25,0.5,,segnale,True",
            ])
            self.assertIsNone(p.inizio_storico_wallet(p.JOURNAL_FILE))

    def test_registro_assente(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            self.assertIsNone(p.inizio_storico_wallet(
                os.path.join(d, "non-esiste.csv")))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Passo 2: eseguire e verificare che falliscano**

```bash
cd "/Users/davidesogos/Desktop/progetto trading" && python3 -m unittest test_publish -v
```
Atteso: FAIL, `module 'publish' has no attribute 'posizioni_pubblicabili'`

- [ ] **Passo 3: modificare `publish.py`**

Sostituire la riga 34 (`CAMPI_OP`) con:

```python
CAMPI_OP = ("ts", "action", "pair", "price", "notional", "leverage",
            "reason", "wallet")

# Gli stessi cinque campi per tutti e tre i portafogli. Una funzione sola:
# tre whitelist copiate divergono alla prima aggiunta di campo in core.py, e
# la copia dimenticata e' quella che pubblica troppo.
CAMPI_POS = ("side", "entry", "notional", "leverage", "opened")

# Chiave nello stato -> nome pubblico del wallet. Rispecchia NOME_WALLET in
# core.py, con in piu' il portafoglio reale, che nello stato non ha prefisso.
WALLET = (("reale", ""), ("ombra", "shadow_"), ("ia", "ia_"))
```

Aggiungere, prima di `costruisci`:

```python
def posizioni_pubblicabili(grezze: dict) -> dict:
    """Whitelist campo per campo, per un portafoglio qualsiasi."""
    fuori = {}
    for pair, v in (grezze or {}).items():
        d = {k: v.get(k) for k in CAMPI_POS}
        d["notional"] = round(v.get("notional", 0), 2)
        fuori[pair] = d
    return fuori


def blocco_wallet(state: dict, eq_ora, ombra_ora, ia_ora) -> dict:
    """
    I tre portafogli in una forma sola, cosi' che la dashboard non debba
    conoscere le loro differenze storiche di nome.

    'avviato' distingue "non ha mai operato" da "ha operato e ha chiuso
    tutto": nello stato sono lo stesso dizionario vuoto, e significano cose
    opposte. Per l'IA e' la differenza fra un esperimento non ancora partito e
    uno che sta misurando.

    Tutti gli accessi passano da .get(): uno state.json scritto prima che i
    portafogli secondari esistessero non ha quelle chiavi, e leggerle come
    state['...'] sarebbe un KeyError alla prima esecuzione dopo un
    aggiornamento.
    """
    equity_di = {"reale": eq_ora, "ombra": ombra_ora, "ia": ia_ora}
    fuori = {}
    for nome, pref in WALLET:
        posizioni = state.get(f"{pref}positions") or {}
        avviato = (True if nome == "reale"
                   else bool(state.get(f"{pref}avviato") or posizioni
                             or equity_di[nome] is not None))
        fuori[nome] = {
            "equity": equity_di[nome],
            "avviato": avviato,
            "posizioni": posizioni_pubblicabili(posizioni),
        }
    return fuori


def inizio_storico_wallet(percorso: str):
    """
    Da quando il registro contiene tutti e tre i portafogli.

    Non e' una data da salvare da qualche parte: e' deducibile dal registro
    stesso, perche' le righe scritte prima della colonna 'wallet' ce l'hanno
    vuota e quelle scritte dopo no. Una data conservata altrove e' una data
    che prima o poi diverge da cio' che descrive.
    """
    if not os.path.exists(percorso):
        return None
    try:
        with open(percorso, newline="") as f:
            for r in csv.DictReader(f):
                if r.get("wallet"):
                    return r.get("ts")
    except Exception:
        return None
    return None
```

Dentro `costruisci`, sostituire il blocco delle posizioni (righe 91-99) con:

```python
    pos = posizioni_pubblicabili(state.get("positions"))
```

e aggiungere al dizionario restituito, subito dopo `"posizioni": pos,`:

```python
        # I tre portafogli in forma uniforme. AGGIUNTO ai campi sopra, non al
        # loro posto: data.json lo scrive il Pi e la pagina la scrive il Mac,
        # e i due si allineano solo dopo un pull. Finche' non succede, la
        # dashboard nuova deve poter leggere il file vecchio.
        "wallet": blocco_wallet(state, equity[-1]["y"] if equity else cap,
                                ombra[-1]["y"] if ombra else None,
                                ia[-1]["y"] if ia else None),
        "storico_wallet_dal": inizio_storico_wallet(JOURNAL_FILE),
```

Infine, la riga 123: `"ops": ops[:100],` diventa

```python
        # 250 e non 100: con tre portafogli che scrivono, cento righe
        # coprirebbero un terzo del tempo di prima, e la tabella sembrerebbe
        # dire che il sistema ha iniziato a operare piu' tardi di quanto abbia
        # fatto. Pesano circa 27 KB su un data.json che sta sotto i 60.
        "ops": ops[:250],
```

- [ ] **Passo 4: eseguire e verificare che passino**

```bash
cd "/Users/davidesogos/Desktop/progetto trading" && python3 -m unittest test_publish -v
```
Atteso: 8 test, tutti PASS.

- [ ] **Passo 5: verificare che la suite intera regga**

```bash
cd "/Users/davidesogos/Desktop/progetto trading" && python3 -m unittest discover -p "test_*.py" -v 2>&1 | tail -20
```
Atteso: nessun FAIL né ERROR. `test_segnale` può risultare saltato: richiede
pandas e si salta da sé.

- [ ] **Passo 6: commit**

```bash
git add publish.py test_publish.py
git commit -m "data.json pubblica i tre portafogli e marca le operazioni"
```

---

## Parte C — la pagina

### Task 6: dividere `docs/` in tre file e introdurre i token di tema

Nessun cambiamento funzionale: la pagina deve fare esattamente quello che fa
ora, in chiaro e in scuro. È il task che rende governabili i tre successivi.

**File:**
- Crea: `docs/dashboard.css`, `docs/dashboard.js`
- Modifica: `docs/index.html`
- Modifica: `.gitignore`

- [ ] **Passo 1: creare `docs/dashboard.css` con i token**

Il file si apre con i token e prosegue con le regole attuali di `index.html`
(righe 13-98), riscritte per usare le variabili invece dei colori letterali:

```css
/* Palette di sistema Apple. Definita due volte, una per tema, e mai
   referenziata per valore altrove: i grafici sono disegnati su canvas e non
   ereditano nulla dal CSS, quindi devono poter leggere da qui (dashboard.js). */
:root{
  --bg:#f5f5f7; --surf:#ffffff; --surf2:#f0f0f2;
  --line:rgba(0,0,0,.09); --line2:rgba(0,0,0,.14);
  --txt:#1d1d1f; --dim:#6e6e73; --faint:#8e8e93;
  --up:#248A3D; --down:#D70015; --warn:#B25000;
  --w-reale:#0071E3; --w-ombra:#8944AB; --w-ia:#248A3D; --bench:#C93400;
  --ombra-card:0 1px 2px rgba(0,0,0,.06), 0 0 0 .5px rgba(0,0,0,.05);
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#000000; --surf:#1c1c1e; --surf2:#2c2c2e;
    --line:rgba(255,255,255,.10); --line2:rgba(255,255,255,.16);
    --txt:#f5f5f7; --dim:#98989d; --faint:#8e8e93;
    --up:#30D158; --down:#FF453A; --warn:#FFD60A;
    --w-reale:#0A84FF; --w-ombra:#BF5AF2; --w-ia:#30D158; --bench:#FF9F0A;
    --ombra-card:none;
  }
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);
     font:15px/1.55 -apple-system,BlinkMacSystemFont,'SF Pro Text',Inter,system-ui,sans-serif;
     -webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
.wrap{max-width:1180px;margin:0 auto;padding:28px 22px 80px}
.mono{font-family:ui-monospace,'SF Mono','JetBrains Mono',monospace;
      font-variant-numeric:tabular-nums}
```

Le regole rimanenti di `index.html` (da `header{` fino alla media query finale)
si spostano qui **invariate nella struttura**, sostituendo ogni colore letterale
con la variabile corrispondente: `#0a0b0d`→`var(--bg)`, `#131519`→`var(--surf)`,
`#1a1d23`→`var(--surf2)`, `#23262d`→`var(--line)`, `#2d313a`→`var(--line2)`,
`#e8eaed`→`var(--txt)`, `#8b9099`→`var(--dim)`, `#5c626b`→`var(--faint)`,
`#26a69a`→`var(--up)`, `#ef5350`→`var(--down)`, `#3b82f6`→`var(--w-reale)`,
`#e3b341`→`var(--warn)`.

Raggi e superfici passano allo stile Apple: `.kpi`, `.card`, `.pos` da
`border-radius:12px` a `16px`, e `box-shadow:var(--ombra-card)`.

- [ ] **Passo 2: creare `docs/dashboard.js`**

Tutto il contenuto del `<script>` attuale (righe 141-553), invariato tranne le
opzioni dei grafici, che smettono di essere costanti e diventano una funzione
che legge i token:

```js
/* I grafici sono su canvas: non ereditano niente dal CSS, quindi i colori
   vanno letti dalle variabili e riapplicati a mano quando il tema cambia.
   E' l'unico punto in cui il tema puo' rompersi in silenzio. */
const tok=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const perTema=[];                 // ogni grafico registra qui come ricolorarsi

function opzioni(){
  return {layout:{background:{color:'transparent'},textColor:tok('--dim'),
      fontFamily:"ui-monospace,'SF Mono',monospace",fontSize:11},
    grid:{vertLines:{color:tok('--line')},horzLines:{color:tok('--line')}},
    rightPriceScale:{borderColor:tok('--line')},
    timeScale:{borderColor:tok('--line')},
    crosshair:{mode:1,vertLine:{color:tok('--line2'),labelBackgroundColor:tok('--surf2')},
               horzLine:{color:tok('--line2'),labelBackgroundColor:tok('--surf2')}}};
}

function crea(el,extra){
  const c=LightweightCharts.createChart(el,{...opzioni(),autoSize:true,...extra});
  grafici.push(c);
  perTema.push(()=>c.applyOptions(opzioni()));
  return c;
}

// pulisci() svuota anche perTema, altrimenti ogni ricarica lascia closure
// attaccate a grafici gia' rimossi e il cambio tema le richiama.
function pulisci(){
  grafici.forEach(c=>{try{c.remove()}catch(e){}});
  grafici=[]; perTema.length=0;
}

matchMedia('(prefers-color-scheme: dark)')
  .addEventListener('change',()=>perTema.forEach(f=>f()));
```

La costante `opt` sparisce: ogni sua occorrenza (`{...opt.timeScale,…}` in
`candele()`) diventa `{...opzioni().timeScale,…}`.

I colori delle serie passano ai token: nell'equity `'#3b82f6'`→`tok('--w-reale')`,
`'#eb6834'`→`tok('--bench')`, `'#9b8bd6'`→`tok('--w-ombra')`,
`'#3fb98c'`→`tok('--w-ia')`; nelle candele `'#26a69a'`→`tok('--up')` e
`'#ef5350'`→`tok('--down')`. Le serie a candela registrano il proprio ricoloro
in `perTema` accanto al grafico:

```js
      perTema.push(()=>s.applyOptions({upColor:tok('--up'),downColor:tok('--down'),
        borderUpColor:tok('--up'),borderDownColor:tok('--down'),
        wickUpColor:tok('--up'),wickDownColor:tok('--down')}));
```

- [ ] **Passo 3: ridurre `docs/index.html`**

`<style>` e `<script>` spariscono; restano `<head>` e la struttura. Nel `<head>`:

```html
<meta name="color-scheme" content="light dark">
<link rel="stylesheet" href="dashboard.css?v=2">
```

e prima di `</body>`, dopo lo script della CDN:

```html
<script src="dashboard.js?v=2"></script>
```

Il `?v=2` va incrementato a ogni pubblicazione: GitHub Pages serve questi file
con cache, e senza il numero un aggiornamento della pagina puo' arrivare al
browser mezzo vecchio e mezzo nuovo. `data.json` ha già la sua marca temporale.

`meta color-scheme` serve perché senza di esso i controlli nativi e lo sfondo di
scorrimento restano chiari anche in tema scuro.

- [ ] **Passo 4: aggiungere la cartella di verifica al `.gitignore`**

```bash
cd "/Users/davidesogos/Desktop/progetto trading" && printf '\n# Copie della dashboard con dati finti, per la verifica locale\n.verifica/\n' >> .gitignore
```

- [ ] **Passo 5: verificare che la pagina sia identica a prima**

```bash
cd "/Users/davidesogos/Desktop/progetto trading/docs" && python3 -m http.server 8765
```

Aprire `http://localhost:8765/`. Attesi: KPI popolati, grafico equity con
quattro linee, riquadri dei mercati con le candele, tabella operazioni piena.
Poi cambiare il tema del sistema e verificare che testi degli assi, griglia e
candele seguano senza ricaricare. Fermare il server con Ctrl+C.

- [ ] **Passo 6: commit**

```bash
git add docs/index.html docs/dashboard.css docs/dashboard.js .gitignore
git commit -m "docs: pagina divisa in tre file, colori a token, tema chiaro e scuro"
```

---

### Task 7: le tre card wallet

**File:**
- Modifica: `docs/dashboard.js`, `docs/dashboard.css`, `docs/index.html`

**Interfacce consumate:** `D.wallet` e `D.capitale` dal Task 5.

**Interfacce prodotte:**
- `walletDaDati(D) -> [{id, nome, colore, equity, avviato, posizioni}]` —
  normalizza il blocco nuovo **o** i campi legacy
- `esposizione(posizioni) -> {lorda, lunga, corta, nLunghe, nCorte}`

- [ ] **Passo 1: sostituire `<div class="kpis" id="kpis">` in `index.html`**

```html
<div class="wallets" id="wallets"></div>
<div class="kpis" id="kpis"></div>
```

- [ ] **Passo 2: aggiungere a `dashboard.js`**

```js
const WALLET=[
  {id:'reale', nome:'Reale', colore:'--w-reale', nota:'leva da volatility targeting'},
  {id:'ombra', nome:'Ombra', colore:'--w-ombra', nota:'stesse decisioni, leva fissa 1x'},
  {id:'ia',    nome:'IA',    colore:'--w-ia',    nota:'universo scelto dal modello'}];

/* Il blocco 'wallet' lo scrive il Pi, questa pagina la scrive il Mac, e i due
   si allineano solo dopo un pull: fino a cinquanta minuti, di piu' se il pull
   fallisce. Senza questo ripiego quella finestra e' una dashboard rotta. */
function walletDaDati(D){
  const W=D.wallet||null;
  return WALLET.map(w=>{
    const d=W?(W[w.id]||{}):null;
    const legacy={reale:{equity:D.eq_ora, posizioni:D.posizioni||{}, avviato:true},
                  ombra:{equity:D.ombra_ora, posizioni:null, avviato:D.ombra_ora!=null},
                  ia:   {equity:D.ia_ora,    posizioni:null, avviato:D.ia_ora!=null}}[w.id];
    const base=d||legacy;
    return {...w, equity:base.equity, avviato:!!base.avviato,
            // null = "non pubblicato", diverso da {} = "nessuna posizione".
            // Confonderli mostrerebbe 0 € di esposizione su un portafoglio
            // che potrebbe averne 200.
            posizioni:d?(d.posizioni||{}):legacy.posizioni};
  });
}

function esposizione(posizioni){
  if(!posizioni) return null;
  const v=Object.values(posizioni);
  const somma=f=>v.filter(f).reduce((s,p)=>s+Math.abs(+p.notional||0),0);
  return {lorda:somma(()=>true),
          lunga:somma(p=>p.side>0), corta:somma(p=>p.side<0),
          nLunghe:v.filter(p=>p.side>0).length,
          nCorte:v.filter(p=>p.side<0).length};
}

function cardWallet(D){
  document.getElementById('wallets').innerHTML=walletDaDati(D).map(w=>{
    const r=w.equity==null?null:w.equity/D.capitale-1;
    const e=esposizione(w.posizioni);
    const q=e&&w.equity?e.lorda/w.equity:null;
    return `<div class="wc${w.avviato?'':' spento'}" style="--wc:var(${w.colore})">
      <div class="wc-nome"><span class="wc-dot"></span>${w.nome}</div>
      <div class="wc-eq mono">${w.equity==null?'—':eur(w.equity)}</div>
      <div class="wc-pc ${cls(r)}">${w.avviato?pct(r):'non ancora avviato'}</div>
      ${e?`<div class="wc-esp"><span>esposizione ${eur(e.lorda)}</span>
             <span class="mono">${q==null?'':(q*100).toFixed(0)+'%'}</span></div>
           <div class="wc-bar">
             <i style="width:${Math.min(100,(e.lunga/w.equity)*100)}%;background:var(--up)"></i>
             <i style="width:${Math.min(100,(e.corta/w.equity)*100)}%;background:var(--down)"></i>
           </div>
           <div class="wc-ls">${eur(e.lunga)} long · ${e.nLunghe} · ${eur(e.corta)} short · ${e.nCorte}</div>`
        :`<div class="wc-esp"><span>esposizione —</span></div>
          <div class="wc-ls">in attesa che il Pi pubblichi il dato</div>`}
      <div class="wc-nota">${w.nota}</div></div>`;
  }).join('');
}
```

`cardWallet(D)` va chiamata in cima a `render()`, prima del blocco `kpis`. Dai
KPI spariscono le due tessere "Senza volatility targeting" e "Mercati scelti
dall'IA": ora sono card.

**Non viene mostrata alcuna liquidità.** In questa contabilità aprire una
posizione non sottrae nulla dal cash — `open_position` scala solo le commissioni
— quindi un "non investito" affiancato all'esposizione darebbe 281 € su un conto
da 200.

- [ ] **Passo 3: aggiungere a `dashboard.css`**

```css
.wallets{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:22px}
.wc{background:var(--surf);border-radius:16px;padding:16px 18px;position:relative;
    overflow:hidden;box-shadow:var(--ombra-card)}
.wc::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--wc)}
.wc.spento{opacity:.5}
.wc-nome{display:flex;align-items:center;gap:6px;font-size:11px;font-weight:600;
         letter-spacing:.05em;text-transform:uppercase;color:var(--wc);margin-bottom:8px}
.wc-dot{width:7px;height:7px;border-radius:50%;background:var(--wc)}
.wc-eq{font-size:26px;font-weight:600;letter-spacing:-.02em;line-height:1.1}
.wc-pc{font-size:13px;margin-top:3px}
.wc-esp{display:flex;justify-content:space-between;font-size:12px;
        color:var(--dim);margin-top:12px}
.wc-bar{height:5px;border-radius:3px;background:var(--surf2);margin-top:6px;
        overflow:hidden;display:flex}
.wc-bar i{display:block;height:100%}
.wc-ls{font-size:11px;color:var(--faint);margin-top:6px}
.wc-nota{font-size:11px;color:var(--faint);margin-top:10px;
         padding-top:9px;border-top:1px solid var(--line)}
@media(max-width:760px){.wallets{grid-template-columns:1fr}}
```

- [ ] **Passo 4: verificare**

Con il server del Task 6 su `http://localhost:8765/`: tre card in cima, Reale e
Ombra con valore e percentuale, IA smorzata e "non ancora avviato". Con il
`data.json` attuale l'esposizione dell'ombra legge "in attesa che il Pi
pubblichi il dato" — è il percorso di ripiego, ed è il comportamento corretto.

- [ ] **Passo 5: commit**

```bash
git add docs/index.html docs/dashboard.js docs/dashboard.css
git commit -m "Tre card wallet con valore, variazione ed esposizione long/short"
```

---

### Task 8: le posizioni in due sezioni

Reale e Ombra sullo stesso mercato, quindi sulla stessa card. L'IA sui suoi.

**File:**
- Modifica: `docs/dashboard.js`, `docs/dashboard.css`, `docs/index.html`

**Interfacce consumate:** `walletDaDati` dal Task 7.

**Interfacce prodotte:**
- `mercatiSegnale(D) -> [[pair, {reale, ombra}]]`
- `mercatiIA(D) -> [[pair, {ia}]]`

- [ ] **Passo 1: sostituire in `index.html` il blocco delle posizioni**

```html
<h2 id="postit">Segnale momentum · Reale e Ombra</h2>
<div class="grid" id="pos"><div class="skel">caricamento…</div></div>

<h2 id="iatit">Mercati scelti dall'IA</h2>
<div id="ianota" class="nota-sez"></div>
<div class="grid" id="posia"></div>
```

- [ ] **Passo 2: aggiungere a `dashboard.js`**

```js
/* Reale e ombra tengono gli STESSI mercati: l'ombra rispecchia ogni apertura
   e chiusura, cambiando solo il nozionale. Su card separate sarebbero sedici
   riquadri quasi identici a coppie; sulla stessa card sono l'esperimento —
   stesso ingresso, una sola variabile diversa, due P&L a fianco. */
function mercatiSegnale(D){
  const W=Object.fromEntries(walletDaDati(D).map(w=>[w.id,w.posizioni]));
  const chiavi=o=>Object.keys(o||{});
  const pairs=[...new Set([...chiavi(W.reale),...chiavi(W.ombra)])];
  if(!pairs.length) return ((D.universo)||[]).map(p=>[p,{}]);
  // null ("non pubblicato") va tenuto distinto da undefined ("non ha questa
  // posizione"). Durante il ripiego le posizioni dell'ombra non ci sono
  // ancora, e scrivere che l'ombra non ha la posizione sarebbe falso: ce
  // l'ha quasi certamente, visto che rispecchia il reale.
  return pairs.map(p=>[p,{reale:(W.reale||{})[p],
                          ombra:W.ombra===null?null:(W.ombra||{})[p]}]);
}

function mercatiIA(D){
  const ia=walletDaDati(D).find(w=>w.id==='ia').posizioni||{};
  const pairs=Object.keys(ia);
  if(pairs.length) return pairs.map(p=>[p,{ia:ia[p]}]);
  return ((D.ia_universo)||[]).map(p=>[p,{}]);
}

// Una riga per wallet dentro la card. Tre stati, non due: 'v' assente non e'
// zero (e' un mercato che quel portafoglio non ha), e null non e' assente
// (e' un dato che il Pi non ha ancora pubblicato). Mostrare 0,00 € per uno
// qualsiasi dei due sarebbe un'affermazione che non abbiamo.
function rigaWallet(id,nome,colore,v){
  if(v===null) return `<div class="wr assente" style="--wc:var(${colore})">
      <span class="wr-n">${nome}</span>
      <span class="wr-x">dato non ancora pubblicato dal Pi</span></div>`;
  if(!v) return `<div class="wr assente" style="--wc:var(${colore})">
      <span class="wr-n">${nome}</span><span class="wr-x">non ha questa posizione</span></div>`;
  return `<div class="wr" style="--wc:var(${colore})" data-w="${id}">
      <span class="wr-n">${nome}</span>
      <span class="wr-q mono">${(+v.notional).toFixed(2)} € · ${(+v.leverage).toFixed(2)}x</span>
      <span class="wr-p mono" data-pnl>—</span></div>`;
}

function cardMercato(p,slot,soloIA){
  const rif=slot.reale||slot.ombra||slot.ia;
  const righe=soloIA
    ? rigaWallet('ia','IA','--w-ia',slot.ia)
    : rigaWallet('reale','Reale','--w-reale',slot.reale)
      +rigaWallet('ombra','Ombra','--w-ombra',slot.ombra);
  return `<div class="pos" data-p="${p}">
    <header><div><div class="sym">${nome(p)}
      ${rif?`<span class="side ${rif.side>0?'long':'short'}">${rif.side>0?'LONG':'SHORT'}</span>`
          :'<span class="side attesa">IN ATTESA</span>'}</div>
      <div class="meta mono">${rif?`ingresso ${cifre(+rif.entry)}`:'nessuna posizione'}</div></div>
      <div class="pnl"><div class="q mono" data-px>—</div></div></header>
    <div class="chart" data-chart></div>
    ${rif?`<div class="wrighe">${righe}</div>`:''}
    <div class="foot"><span data-fonte class="fonte"></span></div></div>`;
}
```

`candele()` si divide in due chiamate sullo stesso motore. La funzione riceve il
contenitore e la lista, e **la cache dei grafici resta la sola `serie`**, indicizzata
per mercato: se un mercato comparisse in entrambe le sezioni verrebbe scaricato
una volta sola.

```js
async function candele(){
  const seg=mercatiSegnale(D), ia=mercatiIA(D);
  document.getElementById('postit').textContent=
    Object.keys(walletDaDati(D).find(w=>w.id==='reale').posizioni||{}).length
      ? 'Segnale momentum · Reale e Ombra'
      : 'Segnale momentum · mercati sorvegliati (nessuna posizione aperta)';
  const nota=document.getElementById('ianota');
  const iaW=walletDaDati(D).find(w=>w.id==='ia');
  nota.textContent=!iaW.avviato
    ? "Il portafoglio sperimentale non ha ancora scelto un universo. Non mostra i mercati del reale: sarebbe un universo che questo portafoglio non ha mai avuto."
    : '';
  await disegna(document.getElementById('pos'),seg,false);
  await disegna(document.getElementById('posia'),ia,true);
}

async function disegna(box,lista,soloIA){
  if(!lista.length){box.innerHTML=
    `<div class="skel">${soloIA?'nessun mercato scelto':'nessun mercato configurato'}</div>`;return}
  box.innerHTML=lista.map(([p,slot])=>cardMercato(p,slot,soloIA)).join('');
  const guai=[];
  await inParallelo(lista,3,async([p,slot])=>{
    const el=box.querySelector(`.pos[data-p="${p}"] [data-chart]`);
    if(!el) return;
    try{
      const {dati,fonte}=await storico(p);
      if(!dati.length) throw new Error('nessuna candela restituita');
      const ch=crea(el,{timeScale:{...opzioni().timeScale,timeVisible:true,secondsVisible:false}});
      const s=ch.addCandlestickSeries({upColor:tok('--up'),downColor:tok('--down'),
        borderUpColor:tok('--up'),borderDownColor:tok('--down'),
        wickUpColor:tok('--up'),wickDownColor:tok('--down')});
      perTema.push(()=>s.applyOptions({upColor:tok('--up'),downColor:tok('--down'),
        borderUpColor:tok('--up'),borderDownColor:tok('--down'),
        wickUpColor:tok('--up'),wickDownColor:tok('--down')}));
      s.setData(dati);
      const rif=slot.reale||slot.ombra||slot.ia;
      if(rif) s.createPriceLine({price:+rif.entry,color:tok('--faint'),lineWidth:1,
        lineStyle:2,axisLabelVisible:true,title:'ingresso'});
      ch.timeScale().fitContent();
      serie[p]={ch,s,fonte,ultima:{...dati[dati.length-1]}};
      const f=el.parentElement.querySelector('[data-fonte]');
      if(f) f.textContent=fonte;
      mostra(p,slot,dati[dati.length-1].close,false);
    }catch(e){
      el.innerHTML=`<div class="skel">grafico non disponibile — ${e.message}</div>`;
      guai.push(nome(p));
    }});
  if(guai.length) avviso(`Candele non caricate per ${guai.join(', ')}. Il resto della pagina resta valido.`);
}
```

`mostra` calcola un P&L per riga invece che uno solo:

```js
function mostra(p,slot,px,vivo){
  prezzi[p]=px;
  const card=document.querySelector(`.pos[data-p="${p}"]`); if(!card) return;
  const q=card.querySelector('[data-px]');
  card.querySelectorAll('.wr[data-w]').forEach(riga=>{
    const v=slot[riga.dataset.w]; const e=riga.querySelector('[data-pnl]');
    if(!v||!e) return;
    const mv=(px-v.entry)/v.entry*v.side, pl=v.notional*mv;
    e.textContent=(pl>=0?'+':'')+pl.toFixed(2)+' €';
    e.className='wr-p mono '+(pl>=0?'up':'down');
  });
  const rif=slot.reale||slot.ombra||slot.ia;
  q.textContent=rif?`${cifre(px)} (${pct((px-rif.entry)/rif.entry*rif.side)})`
                   :`${cifre(px)} · ${vivo?'in diretta':'ultima chiusura'}`;
  card.classList.toggle('vivo',!!vivo);
}
```

`mercatiMostrati()` — usata da `apriLive()` per la sottoscrizione WebSocket —
diventa l'unione delle due sezioni, così il flusso copre tutti e tre i wallet:

```js
function mercatiMostrati(){
  return [...mercatiSegnale(D),...mercatiIA(D)];
}
```

e in `ws.onmessage` la riga `mostra(p,(D.posizioni||{})[p],px,true)` diventa:

```js
    const tutte=Object.fromEntries(mercatiMostrati());
    mostra(p,tutte[p]||{},px,true);
```

- [ ] **Passo 3: aggiungere a `dashboard.css`**

```css
.wrighe{border-top:1px solid var(--line)}
.wr{display:flex;align-items:center;gap:10px;padding:9px 16px;font-size:12.5px;
    border-left:3px solid var(--wc)}
.wr+.wr{border-top:1px solid var(--line)}
.wr-n{font-weight:600;color:var(--wc);min-width:52px}
.wr-q{color:var(--dim);flex:1}
.wr-p{font-weight:600}
.wr.assente{color:var(--faint)}
.wr-x{font-size:11.5px;color:var(--faint)}
.side.attesa{background:var(--surf2);color:var(--dim)}
.nota-sez{font-size:12.5px;color:var(--faint);margin:-6px 0 13px}
```

- [ ] **Passo 4: verificare**

Su `http://localhost:8765/`: una card per mercato con dentro la riga Reale e la
riga Ombra. Con il `data.json` attuale l'ombra deve leggere **"dato non ancora
pubblicato dal Pi"**, non "non ha questa posizione": è il ripiego, e le due
frasi dicono cose diverse. La sezione IA mostra la nota sull'universo non
ancora scelto. Premere **Avvia live** e verificare che i P&L di riga si muovano
e che la riga dell'ombra resti ferma sul suo messaggio.

- [ ] **Passo 5: commit**

```bash
git add docs/index.html docs/dashboard.js docs/dashboard.css
git commit -m "Posizioni in due sezioni: reale e ombra sulla stessa card, IA a parte"
```

---

### Task 9: lo storico unificato

**File:**
- Modifica: `docs/dashboard.js`, `docs/dashboard.css`, `docs/index.html`

**Interfacce consumate:** `o.wallet` e `D.storico_wallet_dal` dal Task 5.

- [ ] **Passo 1: sostituire in `index.html` il blocco operazioni**

```html
<h2>Storico operazioni</h2>
<div id="opsnota" class="nota-sez"></div>
<div class="filtri" id="filtri"></div>
<div class="card"><table><thead><tr>
  <th>Data</th><th>Portafoglio</th><th>Tipo</th><th>Mercato</th>
  <th>Prezzo</th><th>Nozionale</th><th>Leva</th><th>Motivo</th>
</tr></thead><tbody id="ops"></tbody></table></div>
```

- [ ] **Passo 2: aggiungere a `dashboard.js`**

```js
let filtroWallet='tutti';

function nomeWallet(id){
  return {reale:'Reale', ombra:'Ombra', ia:'IA'}[id]||id;
}

function tabellaOps(){
  const ETICHETTA={open:'apre',close:'chiude',deposit:'versa',ia_stop:'stop IA'};
  const CLASSE={open:'op',close:'cl',deposit:'dep',ia_stop:'cl'};
  // Le righe scritte prima della colonna 'wallet' non ce l'hanno, e sono del
  // portafoglio reale: era l'unico che scrivesse.
  const ops=(D.ops||[]).map(o=>({...o,wallet:o.wallet||'reale'}))
    .filter(o=>filtroWallet==='tutti'||o.wallet===filtroWallet);
  document.getElementById('ops').innerHTML=ops.map(o=>`<tr>
    <td class="mono">${new Date(o.ts).toLocaleString('it-IT',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</td>
    <td><span class="wpill" style="--wc:var(--w-${o.wallet})">${nomeWallet(o.wallet)}</span></td>
    <td><span class="pill ${CLASSE[o.action]||'cl'}">${ETICHETTA[o.action]||o.action}</span></td>
    <td>${o.action==='deposit'?'—':nome(o.pair)}</td>
    <td class="mono">${o.action!=='deposit'&&o.price?(+o.price).toFixed(4):''}</td>
    <td class="mono">${o.notional?(+o.notional).toFixed(2)+' €':''}</td>
    <td class="mono">${o.action!=='deposit'&&o.leverage&&+o.leverage?(+o.leverage).toFixed(2)+'x':''}</td>
    <td class="why">${esc(o.reason||'')}</td></tr>`).join('')
    ||'<tr><td colspan="8" class="skel">nessuna operazione per questo filtro</td></tr>';
}

function filtriOps(){
  const conta=id=>(D.ops||[]).filter(o=>(o.wallet||'reale')===id).length;
  document.getElementById('filtri').innerHTML=
    `<button class="seg${filtroWallet==='tutti'?' on':''}" data-f="tutti">Tutti · ${(D.ops||[]).length}</button>`
    +WALLET.map(w=>`<button class="seg${filtroWallet===w.id?' on':''}" data-f="${w.id}"
        style="--wc:var(${w.colore})"><i></i>${w.nome} · ${conta(w.id)}</button>`).join('');
  document.querySelectorAll('#filtri .seg').forEach(b=>b.onclick=()=>{
    filtroWallet=b.dataset.f; filtriOps(); tabellaOps();
  });
}

/* Senza questa riga si vede il reale con decine di operazioni e l'ombra con
   poche, e si conclude che l'ombra non abbia quasi operato: la lettura
   esattamente sbagliata, su un confronto che e' il motivo per cui i due
   portafogli esistono. */
function notaStorico(){
  const el=document.getElementById('opsnota');
  const dal=D.storico_wallet_dal;
  const prima=(D.ops||[]).length?D.ops[D.ops.length-1].ts:null;
  if(!dal||(prima&&prima>=dal)){el.textContent='';return}
  el.innerHTML=`Le operazioni di ombra e IA sono registrate dal
    <b>${new Date(dal).toLocaleString('it-IT',{day:'2-digit',month:'long',year:'numeric'})}</b>.
    Prima di quella data il registro conteneva solo il portafoglio reale.`;
}
```

In `render()`, il blocco che riempiva `#ops` viene sostituito da:

```js
  notaStorico(); filtriOps(); tabellaOps();
```

- [ ] **Passo 3: aggiungere a `dashboard.css`**

```css
.filtri{display:inline-flex;background:var(--surf2);border-radius:10px;
        padding:3px;gap:3px;margin-bottom:12px;flex-wrap:wrap}
.seg{font:inherit;font-size:12.5px;font-weight:500;color:var(--dim);cursor:pointer;
     background:transparent;border:0;border-radius:8px;padding:6px 14px;
     display:flex;align-items:center;gap:6px;transition:.15s}
.seg i{width:7px;height:7px;border-radius:50%;background:var(--wc,var(--faint))}
.seg.on{background:var(--surf);color:var(--txt);box-shadow:var(--ombra-card)}
.wpill{font-size:10.5px;font-weight:700;letter-spacing:.03em;padding:2.5px 8px;
       border-radius:5px;color:var(--wc);
       background:color-mix(in srgb,var(--wc) 16%,transparent)}
```

- [ ] **Passo 4: verificare**

Su `http://localhost:8765/`: la tabella mostra la colonna Portafoglio con tutte
pastiglie "Reale" (il `data.json` attuale non ha `wallet`), i filtri contano
`Ombra · 0` e `IA · 0`, e la nota non compare perché `storico_wallet_dal` è
assente. Cliccando **Ombra** la tabella dice "nessuna operazione per questo
filtro".

- [ ] **Passo 5: commit**

```bash
git add docs/index.html docs/dashboard.js docs/dashboard.css
git commit -m "Storico unificato con la colonna del portafoglio e i filtri"
```

---

### Task 10: verifica con dati finti, in tutti gli stati

I task 6-9 sono stati verificati sul `data.json` reale, che percorre solo il
ripiego. Qui si prova il percorso nuovo, che in produzione arriverà quando
nessuno sta guardando.

**File:**
- Crea: `.verifica/` (ignorata da git, creata al Passo 4 del Task 6)

- [ ] **Passo 1: costruire le tre varianti**

```bash
cd "/Users/davidesogos/Desktop/progetto trading" && mkdir -p .verifica && python3 - <<'PY'
import json, os, shutil
BASE = os.path.abspath('.')
D = json.load(open('docs/data.json'))
pos = D['posizioni']
ombra = {p: dict(v, notional=round(200/8, 2), leverage=1.0) for p, v in pos.items()}
iapos = {'AVAXEUR': {'side': 1.0, 'entry': 21.4, 'notional': 33.3, 'leverage': 0.66,
                     'opened': '2026-08-15T09:00:00+00:00'},
         'ATOMEUR': {'side': -1.0, 'entry': 4.12, 'notional': 28.9, 'leverage': 0.58,
                     'opened': '2026-08-15T09:00:00+00:00'}}

def marca(ops, quante):
    fuori = []
    for i, o in enumerate(ops):
        o = dict(o)
        o['wallet'] = 'reale' if i >= quante else ('ombra' if i % 2 else 'ia')
        fuori.append(o)
    return fuori

varianti = {
    'ia-spenta': dict(D, wallet={
        'reale': {'equity': D['eq_ora'], 'avviato': True, 'posizioni': pos},
        'ombra': {'equity': D['ombra_ora'], 'avviato': True, 'posizioni': ombra},
        'ia': {'equity': None, 'avviato': False, 'posizioni': {}}},
        storico_wallet_dal='2026-08-15T09:00:00+00:00',
        ops=marca(D['ops'], 6)),
    'ia-attiva': dict(D, wallet={
        'reale': {'equity': D['eq_ora'], 'avviato': True, 'posizioni': pos},
        'ombra': {'equity': D['ombra_ora'], 'avviato': True, 'posizioni': ombra},
        'ia': {'equity': 197.4, 'avviato': True, 'posizioni': iapos}},
        ia_universo=['AVAXEUR', 'ATOMEUR'],
        ia_motivazione='Liquidità in aumento su entrambi.',
        ia_scelto_il='2026-08-15T09:00:00+00:00',
        storico_wallet_dal='2026-08-15T09:00:00+00:00',
        ops=marca(D['ops'], 6)),
    'ombra-divergente': dict(D, wallet={
        'reale': {'equity': D['eq_ora'], 'avviato': True, 'posizioni': pos},
        'ombra': {'equity': D['ombra_ora'], 'avviato': True,
                  'posizioni': {k: v for k, v in list(ombra.items())[:3]}},
        'ia': {'equity': None, 'avviato': False, 'posizioni': {}}},
        storico_wallet_dal='2026-08-15T09:00:00+00:00',
        ops=marca(D['ops'], 6)),
}

for nome, dati in varianti.items():
    d = os.path.join('.verifica', nome)
    os.makedirs(d, exist_ok=True)
    for f in ('index.html', 'dashboard.css', 'dashboard.js'):
        shutil.copy(os.path.join('docs', f), d)
    with open(os.path.join(d, 'data.json'), 'w') as f:
        json.dump(dati, f)
    print('creata', d)
PY
```

Atteso: tre righe "creata .verifica/…". `docs/data.json` non viene toccato: lo
script lo apre in sola lettura.

- [ ] **Passo 2: provare le tre varianti**

```bash
cd "/Users/davidesogos/Desktop/progetto trading/.verifica" && python3 -m http.server 8765
```

| Indirizzo | Cosa deve mostrare |
|---|---|
| `localhost:8765/ia-spenta/` | Ombra con esposizione ~199 € e 99%, IA smorzata; sezione IA con la nota sull'universo non scelto; nota dello storico presente |
| `localhost:8765/ia-attiva/` | IA a 197,40 € in rosso, due card sue (AVAX, ATOM) con le loro candele; filtro `IA` popolato |
| `localhost:8765/ombra-divergente/` | cinque card con "Ombra: non ha questa posizione", tre con entrambe le righe |

In ciascuna: cambiare il tema del sistema e verificare che griglia, assi e
candele seguano; restringere la finestra a 375 px e verificare che le card
wallet si impilino e che la tabella scorra orizzontalmente senza far scorrere la
pagina.

- [ ] **Passo 3: verificare che il ripiego regga ancora**

```bash
cd "/Users/davidesogos/Desktop/progetto trading/docs" && python3 -m http.server 8766
```

Su `localhost:8766/`: nessun `NaN`, nessuna sezione vuota, la console del
browser senza errori. È lo stato in cui la pagina resterà fino al primo publish
del Pi.

- [ ] **Passo 4: la suite intera, un'ultima volta**

```bash
cd "/Users/davidesogos/Desktop/progetto trading" && python3 -m unittest discover -p "test_*.py" -v 2>&1 | tail -15
```
Atteso: nessun FAIL né ERROR.

- [ ] **Passo 5: commit**

```bash
git add -A
git commit -m "Verifica della dashboard nei tre stati dei portafogli"
```

---

## Dopo il piano: la messa in produzione

Non fa parte dei task perché non è codice, ma senza non succede niente.

1. `git push origin main` — da fare **con il consenso esplicito**: il Pi tira
   ogni 20 minuti ed esegue quello che trova.
2. Al primo `journal()` dopo l'aggiornamento, il Pi migra l'intestazione del
   registro e lo scrive nel log. Verificabile con
   `head -1 ~/trading-dati/journal.csv`, che deve finire con `,wallet`.
3. Entro 30 minuti `publish.py` pubblica il `data.json` con il blocco `wallet`,
   e la dashboard passa dal ripiego al percorso nuovo da sola.
4. Le card di ombra e IA mostrano l'esposizione solo dopo il punto 3. Fino ad
   allora "in attesa che il Pi pubblichi il dato" è il comportamento previsto,
   non un guasto.

---

## Auto-revisione

**Copertura della spec.** §A1 colonna `wallet` e migrazione → Task 1. §A2 data
d'inizio → Task 1 (il campo vuoto che la rende deducibile) + Task 5
(`inizio_storico_wallet`) + Task 9 (la nota). §A3 `_apri`/`_chiudi` registrano →
Task 2. §A4 `ia_stop` → Task 3. §A5 finestra dell'healthcheck → Task 4. §B1
blocco wallet → Task 5. §B2 `CAMPI_OP` e tetto a 250 → Task 5. §B3 test → Task 1
(migrazione, in `test_stato.py` come previsto), Task 2, Task 5. §C1 tre card →
Task 7. §C2 due sezioni → Task 8. §C3 storico unificato → Task 9. §C4 ripiego →
Task 7 (`walletDaDati`), verificato al Task 10 Passo 3. §C5 tema → Task 6.
Nessuna sezione della spec resta scoperta.

**Segnaposto:** nessuno. Ogni passo che tocca codice mostra il codice; le
sostituzioni meccaniche del Task 6 elencano una per una le corrispondenze fra
colore letterale e token.

**Coerenza dei nomi.** `reale` / `ombra` / `ia` sono gli stessi in
`NOME_WALLET` (core.py, Task 2), `WALLET` (publish.py, Task 5), `WALLET`
(dashboard.js, Task 7) e nelle variabili CSS `--w-reale` / `--w-ombra` /
`--w-ia` (Task 6), da cui il Task 9 costruisce `var(--w-${o.wallet})`: se un
nome divergesse, la pastiglia perderebbe il colore, il che è il modo più
economico per accorgersene. `posizioni_pubblicabili`, `blocco_wallet`,
`inizio_storico_wallet`, `walletDaDati`, `esposizione`, `mercatiSegnale`,
`mercatiIA`, `rigaWallet`, `cardMercato`, `disegna`, `mostra` compaiono con la
stessa firma in tutti i task che li usano. `opzioni()` sostituisce `opt`
ovunque, incluso `candele()` (Task 6 Passo 2, riusato al Task 8).

**Un difetto trovato in auto-revisione e corretto.** La prima stesura del Task 8
faceva collassare `null` (posizioni non pubblicate) e `undefined` (mercato che
quel portafoglio non ha) nello stesso ramo. Durante i cinquanta minuti di
ripiego ogni card avrebbe dichiarato "Ombra: non ha questa posizione" — falso,
visto che l'ombra rispecchia il reale e quelle posizioni ce le ha. `rigaWallet`
ha ora tre stati, e la verifica del Task 8 Passo 4 controlla che compaia la
frase giusta.

**Un debito accettato e dichiarato.** `mostra()` cambia firma al Task 8: il
secondo parametro passa da una posizione singola a un dizionario per wallet.
Tutte e tre le chiamate (in `disegna`, in `ws.onmessage`, e nessun'altra)
vengono aggiornate nello stesso task, perché una firma cambiata a metà è un
guasto che si manifesta solo con il live acceso.
