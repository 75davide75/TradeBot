#!/usr/bin/env python3
"""
Revisione giornaliera: misura, riporta, applica regole scritte in anticipo.

Cosa questo script NON fa, deliberatamente:
  - non cambia i parametri della strategia perche' ieri e' andata male
  - non alza la leva dopo una serie di vincite
  - non introduce filtri nuovi per "spiegare" una perdita

Quelle sono tutte forme di overfitting in tempo reale, ed e' il modo piu'
affidabile di rovinare una strategia che funzionava. L'unica cosa che si
muove e' l'esposizione, in risposta alla volatilita' realizzata, secondo
una formula decisa prima di vedere i dati.

Ogni intervento viene loggato e confrontato con un portafoglio ombra a leva
fissa 1x, cosi' tra qualche settimana si potra' dire con i numeri se gli
aggiustamenti hanno aiutato o fatto danni.
"""

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from core import (JOURNAL_FILE, REPORT_DIR, equity, fetch_ohlc, fetch_price,
                  load_config, load_state, realized_vol, target_leverage)

CFG = load_config()


def send(text: str):
    url = f"https://api.telegram.org/bot{CFG['telegram_token']}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": CFG["telegram_chat_id"], "text": text,
        "parse_mode": "HTML"}).encode()
    try:
        urllib.request.urlopen(url, data=data, timeout=30).read()
    except Exception as e:
        print(f"telegram: {e}")


def main():
    os.makedirs(REPORT_DIR, exist_ok=True)
    state = load_state(CFG)
    today = datetime.now(timezone.utc).date()

    # ---------------------------------------------------- 1. stato del conto
    prices = {}
    for pair in set(list(state["positions"]) + CFG["universe"]):
        try:
            prices[pair] = fetch_price(pair)
        except Exception:
            pass
    eq = equity(state, prices)
    ret_tot = eq / CFG["capital"] - 1

    hist = pd.DataFrame(state.get("history", []))
    ret_24h = None
    if len(hist) > 1:
        hist["ts"] = pd.to_datetime(hist["ts"])
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        old = hist[hist["ts"] <= cutoff]
        if len(old):
            ret_24h = eq / old["equity"].iloc[-1] - 1

    # ------------------------------------------- 2. cosa ha fatto il mercato
    mkt, vols = [], []
    for pair in CFG["universe"]:
        try:
            df = fetch_ohlc(pair)
            d1 = df["close"].iloc[-1] / df["close"].iloc[-2] - 1
            d7 = df["close"].iloc[-1] / df["close"].iloc[-8] - 1
            rv = realized_vol(df, CFG["vol_lookback"])
            lev, _ = target_leverage(df, CFG)
            mkt.append({"pair": pair, "d1": d1, "d7": d7, "vol": rv, "lev": lev})
            vols.append(rv)
        except Exception as e:
            print(f"{pair}: {e}")

    m = pd.DataFrame(mkt)
    vol_med = float(np.median(vols)) if vols else 0.0
    lev_med = float(m["lev"].median()) if len(m) else 0.0

    # ------------------------------------- 3. regime: la sola regola attiva
    if vol_med > CFG["target_vol"] * 1.5:
        regime = "volatilita' ALTA → esposizione ridotta automaticamente"
    elif vol_med < CFG["target_vol"] * 0.7:
        regime = "volatilita' BASSA → esposizione aumentata, entro il cap"
    else:
        regime = "volatilita' nella norma → esposizione neutra"

    # ------------------------------------------------ 4. operazioni del giorno
    trades_today = 0
    if os.path.exists(JOURNAL_FILE):
        j = pd.read_csv(JOURNAL_FILE)
        j["ts"] = pd.to_datetime(j["ts"], format="mixed", utc=True)
        tj = j[(j["ts"].dt.date == today) & (j["action"].isin(["open", "close"]))]
        trades_today = len(tj)

    # ------------------------------------------------------------ 5. report
    r24 = f"{ret_24h:+.2%}" if ret_24h is not None else "n/d"
    top = m.nlargest(3, "d1")[["pair", "d1"]].values if len(m) else []
    bot = m.nsmallest(3, "d1")[["pair", "d1"]].values if len(m) else []

    txt = [
        f"📊 <b>Revisione {today}</b>",
        "",
        f"<b>Conto</b> (paper): {eq:.2f} € — {ret_tot:+.1%} dal via, {r24} in 24h",
        f"Posizioni aperte: {len(state['positions'])} · operazioni oggi: {trades_today}",
        "",
        f"<b>Mercato</b>: vol mediana {vol_med:.0%} (obiettivo {CFG['target_vol']:.0%})",
        f"{regime}",
        f"Leva calcolata dalla regola: <b>{lev_med}x</b> (cap {CFG['max_leverage']}x)",
        "",
        "<b>Migliori 24h</b>: " + ", ".join(f"{p} {v:+.1%}" for p, v in top),
        "<b>Peggiori 24h</b>: " + ", ".join(f"{p} {v:+.1%}" for p, v in bot),
    ]
    if state.get("halted"):
        txt += ["", f"🛑 <b>SISTEMA FERMO</b>: {state['halt_reason']}"]
    txt += ["", "<i>Nessun parametro della strategia e' stato modificato. "
            "L'unica variabile che si muove e' l'esposizione, in funzione "
            "della volatilita'.</i>"]

    report = "\n".join(txt)
    print(report.replace("<b>", "").replace("</b>", "")
          .replace("<i>", "").replace("</i>", ""))
    send(report)

    with open(os.path.join(REPORT_DIR, f"{today}.json"), "w") as f:
        json.dump({"date": str(today), "equity": eq, "ret_tot": ret_tot,
                   "ret_24h": ret_24h, "vol_median": vol_med,
                   "leverage": lev_med, "regime": regime,
                   "trades": trades_today, "market": mkt}, f, indent=2)


if __name__ == "__main__":
    main()
