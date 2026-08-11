#!/usr/bin/env python3
"""
Controllo automatico dello stato di salute del sistema, ogni mattina alle 9.

Serve a una cosa sola: distinguere il SILENZIO CORRETTO dal GUASTO.

Il bot puo' legittimamente non scrivere per giorni — se nessun segnale si
inverte, non c'e' niente da comunicare. Ma un bot morto tace esattamente allo
stesso modo. Senza questo controllo i due casi sono indistinguibili, ed e'
successo davvero: abbiamo passato ore a cercare un guasto che non c'era.

Questo messaggio arriva TUTTI I GIORNI, anche quando va tutto bene. La sua
assenza e' essa stessa l'allarme.
"""

import json
import os
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from core import (BASE, DATA_DIR, JOURNAL_FILE, STATE_FILE, fetch_price,
                  load_config, migra_se_serve, modo_perp)

CFG = load_config()


def invia(testo: str):
    url = f"https://api.telegram.org/bot{CFG['telegram_token']}/sendMessage"
    for modo in ("HTML", None):
        p = {"chat_id": CFG["telegram_chat_id"], "text": testo}
        if modo:
            p["parse_mode"] = modo
        try:
            with urllib.request.urlopen(url, data=urllib.parse.urlencode(p).encode(),
                                        timeout=30) as r:
                if json.load(r).get("ok"):
                    return True
        except Exception:
            pass
    return False


def servizio_attivo(nome: str) -> bool:
    try:
        r = subprocess.run(["systemctl", "is-active", nome],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() == "active"
    except Exception:
        return False


def main():
    migra_se_serve()      # puo' partire prima del bot dopo un aggiornamento
    ora = datetime.now(timezone.utc)
    utente = os.environ.get("USER") or os.environ.get("LOGNAME") or "davide"
    problemi, righe = [], []

    # --- servizi
    for s, etichetta in [(f"tradingbot@{utente}", "bot"),
                         (f"dashboard@{utente}", "dashboard")]:
        att = servizio_attivo(s)
        righe.append(f"{'✅' if att else '❌'} servizio {etichetta}: "
                     f"{'attivo' if att else 'NON ATTIVO'}")
        if not att:
            problemi.append(f"il servizio {etichetta} non gira")

    # --- lo stato si aggiorna?
    try:
        st = json.load(open(STATE_FILE))
        hist = st.get("history", [])
        if hist:
            ultimo = datetime.fromisoformat(hist[-1]["ts"])
            eta = (ora - ultimo).total_seconds() / 60
            ok = eta < 90     # controlla ogni 15 min: oltre 90 e' anomalo
            righe.append(f"{'✅' if ok else '❌'} ultimo controllo del mercato: "
                         f"{eta:.0f} minuti fa")
            if not ok:
                problemi.append(f"nessun controllo del mercato da {eta:.0f} minuti")
        else:
            righe.append("⚠️ nessuno storico ancora registrato")

        eq = hist[-1]["equity"] if hist else st.get("cash", 0)
        cap = CFG["capital"]
        righe.append(f"💰 equity {eq:.2f} € ({eq/cap-1:+.2%} dal via)")
        righe.append(f"📊 posizioni aperte: {len(st.get('positions', {}))}")

        if st.get("halted"):
            problemi.append(f"sistema BLOCCATO: {st.get('halt_reason','')}")
            righe.append(f"🛑 bloccato: {st.get('halt_reason','')}")
        if st.get("paused"):
            righe.append("⏸️ in pausa")

        # --- e' lo STESSO stato di ieri, o e' stato azzerato?
        #
        # Il controllo qui sopra guarda se lo stato e' RECENTE. Uno stato
        # appena azzerato e' recentissimo: e' esattamente il motivo per cui i
        # due azzeramenti di agosto sono passati inosservati, con questo
        # messaggio che scriveva "tutto in ordine" mentre lo storico spariva.
        segna = os.path.join(DATA_DIR, "ultimo_controllo.json")
        try:
            prec = json.load(open(segna)) if os.path.exists(segna) else {}
            adesso = {"created": st.get("created"),
                      "n_storico": len(st.get("history", []))}
            if prec:
                if (prec.get("created") and adesso["created"]
                        and prec["created"] != adesso["created"]):
                    problemi.append(
                        f"lo stato e' stato AZZERATO (era del "
                        f"{prec['created'][:19]}, ora e' del "
                        f"{adesso['created'][:19]})")
                    righe.append("🔴 stato azzerato dall'ultimo controllo")
                elif adesso["n_storico"] < prec.get("n_storico", 0):
                    problemi.append(
                        f"lo storico si e' accorciato: da "
                        f"{prec['n_storico']} a {adesso['n_storico']} punti")
                    righe.append("🔴 storico accorciato")
            with open(segna, "w") as f:
                json.dump(adesso, f)
        except Exception as e:
            righe.append(f"⚠️ controllo di continuita' non eseguito: {e}")
    except Exception as e:
        problemi.append(f"state.json illeggibile: {e}")
        righe.append(f"❌ stato non leggibile: {e}")

    # --- i dati di mercato arrivano?
    try:
        p = CFG["universe"][0]
        px = fetch_price(p)
        righe.append(f"✅ dati di mercato: {p} a {px:.4f}")
    except Exception as e:
        problemi.append(f"dati di mercato irraggiungibili: {e}")
        righe.append(f"❌ dati di mercato: {e}")

    # --- attivita' recente
    try:
        n = 0
        if os.path.exists(JOURNAL_FILE):
            limite = (ora - timedelta(days=7)).isoformat()
            with open(JOURNAL_FILE) as f:
                next(f, None)
                n = sum(1 for r in f if r.split(",")[0] > limite
                        and r.split(",")[1] in ("open", "close"))
        righe.append(f"📈 operazioni negli ultimi 7 giorni: {n}")
        if n == 0:
            righe.append("   <i>zero e' normale: significa che nessun trend si e' invertito</i>")
    except Exception:
        pass

    # --- pubblicazione della dashboard
    try:
        f = os.path.join(BASE, "docs", "data.json")
        eta = (ora.timestamp() - os.path.getmtime(f)) / 60
        ok = eta < 90
        righe.append(f"{'✅' if ok else '⚠️'} dashboard pubblicata {eta:.0f} minuti fa")
        if not ok:
            problemi.append("la dashboard non si aggiorna")
    except Exception:
        righe.append("⚠️ dashboard mai pubblicata")

    testa = ("🟢 <b>Tutto in ordine</b>" if not problemi
             else f"🔴 <b>{len(problemi)} "
                  f"{'PROBLEMI' if len(problemi) > 1 else 'PROBLEMA'}</b>")
    corpo = [f"{testa}", f"<i>controllo delle {ora.astimezone().strftime('%H:%M del %d/%m')}</i>", ""]
    if problemi:
        corpo += ["<b>Da sistemare:</b>"] + [f"• {p}" for p in problemi] + [""]
    corpo += righe
    corpo += ["", f"<i>mercato: {'perpetui' if modo_perp() else 'spot a margine'} · "
                  f"{len(CFG['universe'])} coppie</i>"]

    msg = "\n".join(corpo)
    print(msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
    invia(msg)


if __name__ == "__main__":
    main()
