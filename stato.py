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

    # Anche journal() la richiama da sola, quindi la migrazione avverrebbe
    # comunque alla prima scrittura. Qui serve perche' avvenga all'AVVIO, e
    # finisca nel log: una migrazione che si vede e' una migrazione che si puo'
    # verificare.
    #
    # Il suo esito NON entra in 'mossi': questa lista dice quali FILE sono
    # stati spostati, e chi la legge ci itera sopra stampando "migrato <nome>".
    # Infilarci la descrizione di una migrazione di schema la trasformerebbe in
    # una lista di cose eterogenee — che e' il modo in cui un valore di ritorno
    # smette di avere un tipo. Il log lo scrive migra_journal_se_serve.
    migra_journal_se_serve()
    return mossi


# --------------------------------------------------------------------------
# STATO
# --------------------------------------------------------------------------
def default_stato(cfg: dict) -> dict:
    cap = cfg["capital"]
    return {
        "mode": "paper",
        "cash": cap,
        # Quanto capitale e' stato messo dentro in totale. Diverso da
        # cfg["capital"], che e' solo il valore di partenza: se domani versi
        # altri 100 EUR, i rendimenti vanno calcolati su 200, non su 100.
        # Senza questa distinzione un versamento apparirebbe come una perdita.
        "capitale_versato": cap,
        "positions": {},
        "peak_equity": cap,
        "halted": False,
        "halt_reason": "",
        "paused": False,
        "conferme": {},
        "shadow_cash": cap,          # portafoglio ombra: leva fissa 1x
        "shadow_positions": {},
        "shadow_avviato": False,
        # Terzo portafoglio: universo scelto dall'IA, stesso segnale.
        "ia_cash": cap,
        "ia_positions": {},
        "ia_avviato": False,
        "ia_universo": [],
        "ia_scelto_il": None,
        "ia_motivazione": "",
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
        elif k == "capitale_versato":
            # NON prendere cfg["capital"]: se il capitale e' appena stato
            # alzato in configurazione, copiarlo qui farebbe sparire il
            # versamento prima che adegua_capitale possa accorgersene.
            # Il capitale d'origine e' il primo punto dello storico.
            storia = state.get("history") or []
            v = float(storia[0].get("equity", v)) if storia else v
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


def adegua_capitale(state: dict, cfg: dict) -> float:
    """
    Allinea lo stato a un aumento di 'capital' in configurazione, trattandolo
    per quello che e': un VERSAMENTO, non un capitale iniziale diverso.

    Perche' non basta cambiare il numero in config.json: i rendimenti si
    calcolano come equity / capitale_versato - 1. Se alzi il capitale da 100 a
    200 mentre in cassa ci sono 100 EUR, quella formula restituisce -50%, cioe'
    una perdita che non e' mai avvenuta. Qui i 100 EUR nuovi entrano davvero in
    cassa e il denominatore sale insieme a loro.

    peak_equity sale della stessa cifra, altrimenti il kill switch vedrebbe un
    drawdown istantaneo del 50% e fermerebbe tutto.

    Restituisce l'importo versato (0.0 se non c'era nulla da fare).

    Una diminuzione di 'capital' NON produce un prelievo automatico: togliere
    soldi da un conto e' un'operazione che deve restare manuale.
    """
    versato = float(state.get("capitale_versato", cfg["capital"]))
    voluto = float(cfg["capital"])
    delta = round(voluto - versato, 8)
    if delta <= 0:
        if delta < 0:
            print(f"[capitale] config dice {voluto:.2f} EUR ma ne risultano "
                  f"versati {versato:.2f}. Non tolgo nulla da solo: se vuoi "
                  f"ridurre il conto, fallo a mano.")
        return 0.0
    state["cash"] = float(state.get("cash", 0.0)) + delta
    state["capitale_versato"] = voluto
    state["peak_equity"] = float(state.get("peak_equity", 0.0)) + delta
    # Anche l'ombra riceve il versamento. Senza, il portafoglio vero avrebbe
    # soldi che l'ombra non ha mai ricevuto e il confronto fra i due — che e'
    # tutto il motivo per cui l'ombra esiste — sarebbe truccato.
    state["shadow_cash"] = float(state.get("shadow_cash", versato)) + delta
    state["ia_cash"] = float(state.get("ia_cash", versato)) + delta
    journal("deposit", notional=round(delta, 2), equity=round(state["cash"], 2),
            reason=f"versamento: capitale da {versato:.2f} a {voluto:.2f} EUR",
            confirmed=True)
    print(f"[capitale] versati {delta:.2f} EUR: da {versato:.2f} a {voluto:.2f}")
    return delta


def allinea_ombra_se_ferma(state: dict) -> bool:
    """
    Finche' l'ombra non ha mai aperto una posizione, la sua cassa segue il
    capitale versato.

    Serve alle installazioni dove l'ombra e' stata aggiunta a conto gia'
    avviato: senza questo partirebbe dal capitale sbagliato e ogni confronto
    successivo sarebbe falsato di quella differenza, per sempre.

    Il flag 'shadow_avviato' e' necessario: non basta guardare se ci sono
    posizioni aperte, perche' un'ombra che ha gia' operato e poi chiuso tutto
    ne avrebbe zero, e riallinearla le cancellerebbe il P&L accumulato.
    """
    if state.get("shadow_avviato"):
        return False
    atteso = float(state.get("capitale_versato", state.get("cash", 0.0)))
    if abs(float(state.get("shadow_cash", 0.0)) - atteso) < 0.005:
        return False
    print(f"[ombra] non ha ancora operato: cassa allineata da "
          f"{state.get('shadow_cash', 0.0):.2f} a {atteso:.2f} EUR")
    state["shadow_cash"] = atteso
    return True


def save_state(state: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)   # scrittura atomica: niente stato corrotto


# Undici colonne: 'wallet' e' l'ultima, e non e' un dettaglio estetico. Le
# righe scritte prima che esistesse ne hanno dieci, e DictReader restituisce
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
    sono, visto che per tutta la loro esistenza il reale era l'unico a
    scrivere.

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
        sorgente.readline()                    # scarta la vecchia intestazione
        dest.write(",".join(intestazione + ["wallet"]) + fine)
        shutil.copyfileobj(sorgente, dest)     # le righe dati passano identiche
    os.replace(tmp, JOURNAL_FILE)              # atomica, come save_state
    print(f"[registro] aggiunta la colonna 'wallet' a {JOURNAL_FILE}")
    return True


def journal(action: str, wallet: str = "reale", **campi) -> None:
    """
    Ogni decisione viene scritta qui. Il journal e' la fonte di verita'.

    'wallet' dice QUALE dei tre portafogli ha agito. Il valore predefinito e'
    'reale' perche' per tutte le righe scritte finora e' stato l'unico a
    scrivere, e le righe senza il campo sono sue.
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
