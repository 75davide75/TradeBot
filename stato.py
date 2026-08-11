#!/usr/bin/env python3
"""
Persistenza: dove vivono i dati che non si possono perdere.

PERCHE' ESISTE QUESTO FILE

Lo stato del sistema si e' azzerato due volte durante i deploy, il 10 e l'11
agosto 2026, la seconda a 25 secondi dal salvataggio dei file sul Mac. Sono
andati persi 74 punti di storico e 8 posizioni aperte, e nessuno se n'e'
accorto: il controllo di salute verificava che lo stato fosse RECENTE, e uno
stato appena azzerato e' recentissimo.

La causa era che i dati vivevano DENTRO la cartella del codice, e la cartella
del codice viene sovrascritta a ogni deploy.

Qui i dati escono da li'. La cartella del codice torna a essere sacrificabile:
ci puoi copiare sopra, cancellarla, rifarla da git, e lo storico non si muove.

Solo libreria standard, di proposito. Questo e' il codice piu' critico del
sistema: deve poter girare e essere testato ovunque, anche dove pandas non c'e'
— compreso il Pi appena installato.
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

    La variabile viene per prima perche' serve ai test e alle esecuzioni una
    tantum senza dover toccare la configurazione vera.
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
    uno state.json vuoto sopra quello buono: cosi' diventa innocuo invece che
    distruttivo.
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
        # shutil.move e non os.replace: la cartella dati puo' stare su un
        # filesystem diverso da quello del codice.
        shutil.move(vecchio, nuovo)
        mossi.append(nome)
        print(f"[dati] spostato {nome} in {DATA_DIR}")

    vecchio_report = os.path.join(origine, "report")
    if os.path.isdir(vecchio_report) and not os.path.isdir(REPORT_DIR):
        shutil.move(vecchio_report, REPORT_DIR)
        mossi.append("report/")
        print(f"[dati] spostata report/ in {DATA_DIR}")
    return mossi


# --------------------------------------------------------------------------
# STATO
# --------------------------------------------------------------------------
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
    chiavi aggiunte dopo, e la prima riga di codice che le legge e' un
    KeyError. E' la stessa classe di bug gia' pagata una volta con 37 riavvii
    in loop, documentata in core.py.
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
    """
    Carica lo stato. Se manca ma il journal dice che il sistema ha gia'
    operato, si RIFIUTA di ripartire da zero.

    Un bot che riparte in silenzio con il capitale iniziale distrugge l'unica
    cosa di valore prodotta finora, che e' il registro delle misure — e lo fa
    senza che nessuno se ne accorga, perche' da fuori sembra tutto normale.
    Meglio un bot fermo che ti chiama, di un bot che riparte e ti mente.
    """
    if not os.path.exists(STATE_FILE):
        if ha_operato() and os.environ.get("TRADEBOT_NUOVO_CONTO") != "1":
            raise StatoPerduto(
                f"{STATE_FILE} non esiste, ma {JOURNAL_FILE} contiene "
                f"operazioni gia' eseguite. Ripartire da zero cancellerebbe la "
                f"storia del conto senza dirlo. Ripristina lo stato, oppure "
                f"riparti deliberatamente con TRADEBOT_NUOVO_CONTO=1.")
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
