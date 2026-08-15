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

import csv
import json
import os
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import analisi
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


def righe_journal(ora, giorni=7):
    """Le ultime righe del journal, gia' pronte per essere lette dall'IA."""
    if not os.path.exists(JOURNAL_FILE):
        return []
    limite = (ora - timedelta(days=giorni)).isoformat()
    fuori = []
    try:
        with open(JOURNAL_FILE) as f:
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
    except Exception:
        return []
    return fuori[-60:]      # basta l'ultima settimana, non tutto il registro


def per_ia(st, ora, problemi, righe):
    """
    Prepara il quadro che l'IA deve riassumere.

    Solo numeri gia' calcolati e righe di registro: nessuna richiesta di
    previsione, nessuna domanda su cosa fare. Il modello serve a spiegare
    cio' che e' successo, non a decidere cosa succedera'.
    """
    hist = st.get("history", []) or []
    ultimo = hist[-1] if hist else {}
    cap = float(st.get("capitale_versato", CFG["capital"]))
    eq = float(ultimo.get("equity", st.get("cash", 0.0)))
    picco = float(st.get("peak_equity", cap) or cap)

    def var(chiave, giorni):
        """Variazione di una serie sugli ultimi N giorni."""
        limite = (ora - timedelta(days=giorni)).isoformat()
        passati = [p for p in hist if p.get("ts", "") <= limite
                   and p.get(chiave) is not None]
        if not passati or ultimo.get(chiave) is None:
            return None
        prima = float(passati[-1][chiave])
        return round(float(ultimo[chiave]) / prima - 1, 5) if prima else None

    posizioni = []
    for pair, p in (st.get("positions") or {}).items():
        posizioni.append({
            "mercato": pair,
            "direzione": "long" if p.get("side", 0) > 0 else "short",
            "leva": p.get("leverage"),
            "aperta_il": (p.get("opened") or "")[:10],
            "prezzo_ingresso": p.get("entry"),
        })

    return {
        "data": ora.date().isoformat(),
        "capitale_versato_eur": cap,
        "equity_eur": round(eq, 2),
        "rendimento_totale": round(eq / cap - 1, 5) if cap else None,
        "rendimento_7_giorni": var("equity", 7),
        "drawdown_dal_picco": round(eq / picco - 1, 5) if picco else None,
        "kill_switch_a": -float(CFG["max_drawdown_halt"]),
        "portafoglio_ombra_eur": ultimo.get("ombra"),
        "portafoglio_ia_eur": ultimo.get("ia"),
        "universo_scelto_dall_ia": st.get("ia_universo") or [],
        "benchmark_btc_eur": ultimo.get("btc"),
        "posizioni_aperte": posizioni,
        "universo_configurato": list(CFG["universe"]),
        "segnale": f"momentum a {CFG['momentum_n']} giorni, "
                   f"{'con' if CFG['allow_short'] else 'senza'} short",
        "problemi_rilevati": problemi,
        "diagnostica": list(righe),
        "registro_ultimi_7_giorni": righe_journal(ora),
    }


def main():
    migra_se_serve()      # puo' partire prima del bot dopo un aggiornamento
    ora = datetime.now(timezone.utc)
    utente = os.environ.get("USER") or os.environ.get("LOGNAME") or "davide"
    problemi, righe = [], []
    stato = None

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
        st = stato = json.load(open(STATE_FILE))
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
        cap = float(st.get("capitale_versato", CFG["capital"]))
        righe.append(f"💰 equity {eq:.2f} € ({eq/cap-1:+.2%} su {cap:.0f} € versati)")
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

    # --- terzo portafoglio: dire se e' spento e PERCHE'
    #
    # Senza questa riga, un braccio dell'esperimento fermo e un braccio rotto
    # sono indistinguibili dall'esterno. E' gia' costato due giorni.
    try:
        attiva, motivo = analisi.stato_ia(CFG)
        if attiva:
            righe.append(f"🤖 portafoglio IA: {motivo}")
        elif CFG.get("portafoglio_ia") is False:
            righe.append("⚪ portafoglio IA: disattivato per scelta — "
                         "il sistema gira con due portafogli")
        else:
            righe.append(f"⚠️ portafoglio IA: inattivo — {motivo}")
            problemi.append(f"portafoglio IA inattivo ({motivo}). Per spegnerlo "
                            'di proposito: "portafoglio_ia": false in config.json')
    except Exception as e:
        righe.append(f"⚠️ stato del portafoglio IA non verificabile: {e}")

    testa = ("🟢 <b>Tutto in ordine</b>" if not problemi
             else f"🔴 <b>{len(problemi)} "
                  f"{'PROBLEMI' if len(problemi) > 1 else 'PROBLEMA'}</b>")
    corpo = [f"{testa}", f"<i>controllo delle {ora.astimezone().strftime('%H:%M del %d/%m')}</i>", ""]
    if problemi:
        corpo += ["<b>Da sistemare:</b>"] + [f"• {p}" for p in problemi] + [""]
    corpo += righe
    corpo += ["", f"<i>mercato: {'perpetui' if modo_perp() else 'spot a margine'} · "
                  f"{len(CFG['universe'])} coppie</i>"]

    # --- lettura in italiano, scritta dall'IA
    #
    # Sta in fondo e non blocca niente: senza chiave API la funzione
    # restituisce None e il messaggio esce identico a prima. La diagnostica
    # sopra e' fatta di numeri e resta la fonte di verita'; questo e' un
    # commento a quei numeri, e va letto per quello che e'.
    if stato is not None:
        try:
            testo = analisi.riassunto(CFG, per_ia(stato, ora, problemi, righe))
        except Exception as e:
            print(f"[ia] riassunto saltato: {e}")
            testo = None
        if testo:
            corpo += ["", "🧠 <b>Lettura della giornata</b>", testo]

    msg = "\n".join(corpo)
    print(msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
    invia(msg)


if __name__ == "__main__":
    main()
