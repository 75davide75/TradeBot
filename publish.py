#!/usr/bin/env python3
"""
Genera docs/data.json e lo pubblica sul repo GitHub.

La dashboard su GitHub Pages e' statica: non puo' interrogare il Pi, che sta
dietro NAT e non e' raggiungibile da internet. Quindi e' il Pi a spingere
fuori i dati, non la pagina ad andarseli a prendere.

ATTENZIONE — il repo e' PUBBLICO: tutto quello che finisce in data.json
diventa leggibile da chiunque. Per questo qui dentro ci va solo cio' che
serve al grafico, filtrato esplicitamente campo per campo. Mai riversare
lo stato grezzo: contiene piu' di quanto serva.

Uso:  python3 publish.py            genera e pubblica
      python3 publish.py --solo-dati genera senza pubblicare
"""

import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from core import (BASE, JOURNAL_FILE, STATE_FILE, ha_operato, load_config,
                  migra_se_serve)

CFG = load_config()
DOCS = os.path.join(BASE, "docs")
DATA = os.path.join(DOCS, "data.json")

# Solo questi campi escono dal journal. Whitelist, non blacklist: con una
# blacklist basta aggiungere un campo domani per pubblicarlo per sbaglio.
CAMPI_OP = ("ts", "action", "pair", "price", "notional", "leverage", "reason")


def costruisci() -> dict:
    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
    hist = state.get("history", [])
    # Il capitale di riferimento e' quello VERSATO, non quello di partenza:
    # dopo un versamento sono numeri diversi, e usare il secondo mostrerebbe
    # una perdita mai avvenuta.
    cap = float(state.get("capitale_versato", CFG["capital"]))

    # Il benchmark buy&hold riceve gli stessi versamenti negli stessi momenti,
    # altrimenti il confronto e' truccato: il nostro portafoglio avrebbe soldi
    # in piu' che il benchmark non ha mai ricevuto.
    equity, bench = [], []
    prec_btc = prec_vers = None
    valore = None
    for h in hist:
        equity.append({"x": h["ts"], "y": round(h["equity"], 4)})
        btc = h.get("btc")
        vers = float(h.get("versato", CFG["capital"]))
        if not btc:
            continue
        if valore is None:
            valore = vers                      # primo punto: il benchmark parte da li'
        else:
            valore = valore * (btc / prec_btc) + (vers - prec_vers)
        prec_btc, prec_vers = btc, vers
        bench.append({"x": h["ts"], "y": round(valore, 4)})

    ops = []
    if os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE) as f:
            for r in csv.DictReader(f):
                if r.get("action") in ("open", "close"):
                    ops.append({k: r.get(k, "") for k in CAMPI_OP})
    ops.reverse()

    # Dettaglio posizioni: serve alla dashboard per disegnare i grafici a
    # candela e calcolare il P&L in diretta nel browser. Anche qui whitelist:
    # esce solo cio' che serve al disegno.
    pos = {}
    for pair, v in state.get("positions", {}).items():
        pos[pair] = {
            "side": v.get("side"),
            "entry": v.get("entry"),
            "notional": round(v.get("notional", 0), 2),
            "leverage": v.get("leverage"),
            "opened": v.get("opened"),
        }

    return {
        "aggiornato": datetime.now(timezone.utc).isoformat(),
        "mercato": ("perpetui" if CFG.get("market_type") == "perpetual"
                    else "spot a margine"),
        "capitale": cap,
        "equity": equity,
        "benchmark": bench,
        "eq_ora": equity[-1]["y"] if equity else cap,
        "bh_ora": bench[-1]["y"] if bench else None,
        "ops": ops[:100],
        "n_ops": sum(1 for o in ops if o["action"] == "close"),
        "n_pos": len(pos),
        "posizioni": pos,
        # L'universo serve alla dashboard per mostrare i grafici dei mercati
        # sorvegliati anche quando non c'e' nessuna posizione aperta.
        "universo": CFG.get("universe", []),
        "paused": state.get("paused", False),
        "halted": state.get("halted", False),
        "halt_reason": state.get("halt_reason", ""),
    }


def git(*args) -> tuple:
    p = subprocess.run(["git", *args], cwd=BASE, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def main():
    # Anche qui, non solo in bot.py: publish gira da un timer suo ogni 30
    # minuti e puo' benissimo partire prima del bot dopo un aggiornamento.
    # Senza questa riga non troverebbe lo stato nella nuova posizione e
    # pubblicherebbe un data.json vuoto, committandolo.
    migra_se_serve()

    # Se lo stato manca ma il journal dice che abbiamo operato, NON pubblicare:
    # un data.json vuoto sovrascriverebbe la dashboard con "capitale 100, zero
    # posizioni", cioe' una bugia, e la committerebbe pure.
    if not os.path.exists(STATE_FILE) and ha_operato():
        print(f"STOP: {STATE_FILE} non esiste ma il journal contiene operazioni.")
        print("      Non pubblico: sovrascriverei la dashboard con dati vuoti.")
        sys.exit(1)

    os.makedirs(DOCS, exist_ok=True)
    dati = costruisci()
    with open(DATA, "w") as f:
        json.dump(dati, f, separators=(",", ":"))
    print(f"data.json scritto — {len(dati['equity'])} punti, "
          f"{dati['n_ops']} operazioni chiuse, equity {dati['eq_ora']:.2f} EUR")

    if "--solo-dati" in sys.argv:
        return

    # Ultima difesa: se per qualsiasi motivo config.json risultasse tracciato,
    # meglio fermarsi che pubblicare un token su un repo pubblico.
    rc, out = git("ls-files", "--error-unmatch", "config.json")
    if rc == 0:
        print("STOP: config.json risulta tracciato da git. Non pubblico.")
        print("      Rimuovilo con:  git rm --cached config.json")
        sys.exit(1)

    git("add", "docs/data.json")
    rc, out = git("diff", "--cached", "--quiet")
    if rc == 0:
        print("nessuna modifica da pubblicare")
        return

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    git("commit", "-m", f"dati dashboard {stamp}")
    rc, out = git("push", "origin", "HEAD")
    print("push OK" if rc == 0 else f"push fallito:\n{out}")


if __name__ == "__main__":
    main()
