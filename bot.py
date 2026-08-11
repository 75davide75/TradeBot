#!/usr/bin/env python3
"""
Bot Telegram: propone, tu confermi, il sistema esegue (in paper).

ASIMMETRIA DI SICUREZZA — il principio di design piu' importante qui dentro:

    APERTURE  -> richiedono sempre la conferma umana. Aggiungono rischio.
    CHIUSURE  -> si auto-eseguono dopo il timeout. Tolgono rischio.
    STOP-LOSS -> scatta subito, non aspetta nessuno.

Il rifugio in emergenza e' il CASH, non BTC. In un crollo crypto BTC scende
insieme agli altcoin: spostarsi li' non riduce il rischio, cambia solo
l'etichetta sulla perdita e paga due giri di commissioni.

Il bot non ha credenziali Kraken: usa solo dati pubblici. Non puo' muovere
soldi veri neanche volendo.
"""

import json
import os
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from core import (DATA_DIR, LEVA_OMBRA, StatoPerduto, adegua_capitale,
                  allinea_ombra_se_ferma,
                  apri_ombra, avvia_ombra_rispecchiando, check_kill_switch,
                  chiudi_ombra, close_position,
                  equity, equity_ombra, fetch_ohlc, fetch_price, journal,
                  load_config, load_state, migra_se_serve, open_position,
                  order_minimum, save_state, signal_momentum, target_leverage)

CFG = load_config()
API = f"https://api.telegram.org/bot{CFG['telegram_token']}"
CHAT = CFG["telegram_chat_id"]

pending = {}    # cid -> proposta in attesa (solo se auto_execute e' spento)

# Il contatore delle conferme VIVE SU DISCO, dentro state.json.
# Tenerlo in memoria era un bug reale: ogni riavvio del servizio azzerava il
# conteggio, e con riavvii piu' frequenti della soglia il sistema non
# raggiungeva mai le conferme necessarie e non operava MAI.
# Un contatore che si azzera da solo non e' un filtro, e' un blocco.


def leggi_conferme(state) -> dict:
    return {k: tuple(v) for k, v in state.get("conferme", {}).items()}


def scrivi_conferme(state, c: dict) -> None:
    state["conferme"] = {k: list(v) for k, v in c.items()}


def tg(method: str, **params):
    """
    Chiamata all'API Telegram.

    Intercetta DUE tipi di fallimento, non uno solo: l'errore di rete e la
    risposta con ok=false. Il secondo mancava, ed e' costato ore di
    diagnosi: il bot apriva posizioni e le notifiche venivano rifiutate da
    Telegram per un problema di formattazione, senza che nulla lo segnalasse.
    Un errore silenzioso e' peggio di un crash: il crash almeno si vede.
    """
    data = urllib.parse.urlencode(
        {k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
         for k, v in params.items()}).encode()
    try:
        with urllib.request.urlopen(f"{API}/{method}", data=data, timeout=40) as r:
            res = json.load(r)
        if not res.get("ok", False):
            print(f"[tg] {method} RIFIUTATO da Telegram: {res.get('description')}")
        return res
    except Exception as e:
        print(f"[tg] {method} errore di rete: {e}")
        return {"ok": False, "description": str(e)}


def send(text: str, keyboard=None):
    """
    Invia un messaggio. Se Telegram rifiuta l'HTML, ritenta in testo semplice:
    meglio una notifica brutta che nessuna notifica.
    """
    p = {"chat_id": CHAT, "text": text, "parse_mode": "HTML"}
    if keyboard:
        p["reply_markup"] = {"inline_keyboard": keyboard}
    res = tg("sendMessage", **p)

    if not res.get("ok", False):
        import re
        semplice = re.sub(r"</?[bi]>", "", text)
        p2 = {"chat_id": CHAT, "text": semplice}
        if keyboard:
            p2["reply_markup"] = {"inline_keyboard": keyboard}
        res = tg("sendMessage", **p2)
        if not res.get("ok", False):
            print(f"[send] messaggio NON consegnato: {text[:80]}")
    return res


def snapshot(state, eq, prices=None):
    """Registra equity, ombra e prezzo BTC insieme: servono ai confronti."""
    try:
        btc = fetch_price("XXBTZEUR")
    except Exception:
        btc = None
    try:
        ombra = round(equity_ombra(state, prices or {}), 4)
    except Exception:
        ombra = None
    # 'versato' viaggia con ogni punto: senza, il confronto con il buy&hold
    # sarebbe falsato dopo un versamento (il benchmark non avrebbe ricevuto
    # gli stessi soldi nello stesso momento).
    state["history"].append({"ts": datetime.now(timezone.utc).isoformat(),
                             "equity": round(eq, 4), "btc": btc,
                             "ombra": ombra,
                             "versato": round(float(state.get(
                                 "capitale_versato", CFG["capital"])), 4)})
    state["history"] = state["history"][-5000:]


# --------------------------------------------------------------------------
# LAYER DI SICUREZZA — gira ogni 60 secondi
# --------------------------------------------------------------------------
def risk_check():
    """
    Controllo rapido sulle sole posizioni aperte.

    Due compiti:
      1. Stop-loss: se una posizione perde oltre la soglia, la chiude SUBITO,
         senza chiedere niente a nessuno. Aspettare una conferma umana mentre
         una posizione affonda e' esattamente il fallimento da evitare.
      2. Auto-chiusura: le proposte di CHIUSURA in attesa da piu' del timeout
         vengono eseguite da sole. Le aperture no, mai: quelle scadono.
    """
    state = load_state(CFG)
    if not state["positions"] and not pending:
        return

    prices, chiuse = {}, []
    for pair, p in list(state["positions"].items()):
        try:
            px = fetch_price(pair)
            prices[pair] = px
        except Exception as e:
            print(f"[risk] {pair}: {e}")
            continue

        # perdita sul capitale impegnato, non sul nozionale
        move = (px - p["entry"]) / p["entry"] * p["side"]
        perdita = move * p["leverage"] if p["leverage"] else move

        if perdita <= -CFG["stop_loss_pct"]:
            close_position(state, pair, px,
                           f"STOP-LOSS automatico a {perdita:.1%}")
            # L'ombra esce insieme: cambia la leva, non le decisioni.
            chiudi_ombra(state, pair, px)
            chiuse.append(f"{pair} a {perdita:+.1%}")

    if chiuse:
        save_state(state)
        eq = equity(state, prices)
        send("🔴 <b>STOP-LOSS ESEGUITO</b> (automatico, senza conferma)\n"
             + "\n".join(f"• {c}" for c in chiuse)
             + f"\n\nEquity: {eq:.2f} €\n"
             "<i>Capitale tornato in cash. Il cash e' il rifugio: BTC in un "
             "crollo scende insieme agli altcoin.</i>")

    # auto-esecuzione delle sole CHIUSURE in attesa
    ora = time.time()
    for cid in list(pending):
        p = pending[cid]
        if p["want"] == 0.0 and ora - p["creato"] > CFG["auto_close_timeout_sec"]:
            msg = execute(cid, auto=True)
            send(f"⏱️ <b>Chiusura auto-eseguita</b> (nessuna risposta entro "
                 f"{CFG['auto_close_timeout_sec']}s)\n{msg}")


# --------------------------------------------------------------------------
# VALUTAZIONE COMPLETA — gira ogni 4 ore
# --------------------------------------------------------------------------
def evaluate():
    state = load_state(CFG)
    if state.get("halted") or state.get("paused"):
        return

    prices, proposals = {}, []
    conferme = leggi_conferme(state)
    for pair in CFG["universe"]:
        try:
            df = fetch_ohlc(pair)
            px = float(df["close"].iloc[-1])
            prices[pair] = px
            want = signal_momentum(df, CFG["momentum_n"], CFG["allow_short"])
            lev, why = target_leverage(df, CFG)
            have = state["positions"].get(pair)
            attuale = have["side"] if have else 0.0

            # Filtro anti-whipsaw: conto per quanti controlli di fila il
            # segnale resta lo stesso. Agisco solo quando si e' stabilizzato.
            visto, n = conferme.get(pair, (None, 0))
            n = n + 1 if visto == want else 1
            conferme[pair] = (want, n)

            if want != attuale and n >= CFG["conferme_richieste"]:
                proposals.append({"pair": pair, "want": want, "price": px,
                                  "leverage": lev, "why": why})
        except Exception as e:
            print(f"[eval] {pair}: {e}")

    # posizioni su coppie uscite dall'universo: vanno chiuse, altrimenti
    # resterebbero aperte per sempre pagando rollover
    for pair in list(state["positions"]):
        if pair not in CFG["universe"]:
            try:
                px = fetch_price(pair)
                prices[pair] = px
                proposals.append({"pair": pair, "want": 0.0, "price": px,
                                  "leverage": 0.0,
                                  "why": "coppia uscita dall'universo"})
            except Exception as e:
                print(f"[orfana] {pair}: {e}")

    eq = equity(state, prices)
    if check_kill_switch(state, eq, CFG):
        save_state(state)
        send(f"🛑 <b>SISTEMA FERMATO</b>\n{state['halt_reason']}\n"
             f"Equity {eq:.2f} €. Serve /resume manuale.")
        return

    snapshot(state, eq, prices)
    scrivi_conferme(state, conferme)
    save_state(state)

    scartate = []
    for i, p in enumerate(proposals):
        alloc = eq / max(1, len(CFG["universe"]))
        notional = alloc * p["leverage"]
        verso = {1.0: "LONG", -1.0: "SHORT", 0.0: "CHIUDI"}[p["want"]]

        if p["want"] != 0.0:
            minimo = order_minimum(p["pair"], p["price"])
            if notional < minimo:
                scartate.append(f"{p['pair']} ({notional:.2f}€ < min {minimo:.2f}€)")
                journal("skip_min", pair=p["pair"], notional=round(notional, 2),
                        reason=f"sotto minimo Kraken {minimo:.2f} EUR", confirmed=False)
                continue

        cid = f"{int(time.time())}_{i}"
        pending[cid] = {**p, "notional": notional, "creato": time.time()}

        # --- esecuzione automatica: nessun bottone, solo notifica ---
        if CFG.get("auto_execute", False):
            esito = execute(cid)
            icona = {1.0: "🟢", -1.0: "🔴", 0.0: "⚪"}[p["want"]]
            send(f"{icona} <b>{p['pair']} — {verso} eseguito</b>\n"
                 f"prezzo {p['price']:.4f} · leva {p['leverage']}x · "
                 f"nozionale {notional:.2f} €\n"
                 f"{p['why']}\n\n{esito}\n"
                 f"<i>automatico · /pausa per fermare tutto</i>")
            continue

        if p["want"] == 0.0:
            txt = (f"<b>{p['pair']}</b> — proposta: <b>CHIUDI</b>\n"
                   f"prezzo {p['price']:.4f}\n{p['why']}\n\n"
                   f"<i>si auto-esegue tra {CFG['auto_close_timeout_sec']}s "
                   f"se non rispondi</i>")
        else:
            txt = (f"<b>{p['pair']}</b> — proposta: <b>{verso}</b>\n"
                   f"prezzo {p['price']:.4f}\n"
                   f"leva {p['leverage']}x  ({p['why']})\n"
                   f"nozionale {notional:.2f} €  su equity {eq:.2f} €\n\n"
                   f"<i>paper trading — richiede la tua conferma</i>")

        send(txt, keyboard=[[
            {"text": "✅ Conferma", "callback_data": f"y:{cid}"},
            {"text": "❌ Salta", "callback_data": f"n:{cid}"}]])

    if scartate:
        send("⚠️ <b>Scartate, sotto il minimo d'ordine Kraken:</b>\n"
             + "\n".join(f"• {s}" for s in scartate))


def execute(cid: str, auto: bool = False) -> str:
    p = pending.pop(cid, None)
    if not p:
        return "proposta scaduta"
    state = load_state(CFG)
    px = fetch_price(p["pair"])

    if p["pair"] in state["positions"]:
        close_position(state, p["pair"], px,
                       "auto-chiusura" if auto else "conferma utente")
        chiudi_ombra(state, p["pair"], px)          # l'ombra rispecchia
    if p["want"] != 0.0 and not auto:
        open_position(state, p["pair"], p["want"], px, p["notional"],
                      p["leverage"], p["why"])
        # Stesso mercato, stessa direzione, stesso momento. L'unica differenza
        # e' la leva: fissa a 1x invece che tarata sulla volatilita'.
        alloc_o = equity_ombra(state, {p["pair"]: px}) / max(1, len(CFG["universe"]))
        apri_ombra(state, p["pair"], p["want"], px, alloc_o * LEVA_OMBRA)

    save_state(state)
    eq = equity(state, {p["pair"]: px})
    verso = {1.0: "LONG", -1.0: "SHORT", 0.0: "FLAT"}[p["want"]]
    return f"{verso} {p['pair']} @ {px:.4f} — equity {eq:.2f} €"


# --------------------------------------------------------------------------
# PAUSA / RIPRESA
# --------------------------------------------------------------------------
def chiudi_tutto(state, motivo: str) -> list:
    """
    Liquida ogni posizione e parcheggia il capitale nell'asset rifugio.

    Se il rifugio e' una stablecoin invece di EUR, la conversione costa il
    taker fee. Viene addebitato davvero: un simulatore che regala le
    conversioni fa sembrare gratis una cosa che non lo e'.
    """
    chiuse = []
    for pair in list(state["positions"]):
        try:
            px = fetch_price(pair)
            pnl = close_position(state, pair, px, motivo)
            chiudi_ombra(state, pair, px)
            chiuse.append(f"{pair} ({pnl:+.2f} €)")
        except Exception as e:
            chiuse.append(f"{pair} ERRORE: {e}")

    rifugio = CFG.get("safe_asset", "EUR").upper()
    if rifugio != "EUR" and chiuse:
        from core import TAKER_FEE
        costo = state["cash"] * TAKER_FEE
        state["cash"] -= costo
        journal("convert", pair=f"EUR->{rifugio}", notional=round(state["cash"], 2),
                reason=f"conversione in {rifugio}, costo {costo:.4f} EUR", confirmed=True)
        chiuse.append(f"conversione in {rifugio}: −{costo:.4f} €")
    return chiuse


def pausa() -> str:
    """Sospensione temporanea: chiude tutto, riprendibile con /riprendi."""
    state = load_state(CFG)
    chiuse = chiudi_tutto(state, "/pausa richiesta utente")
    state["paused"] = True
    save_state(state)
    pending.clear()
    journal("PAUSA", reason="richiesta utente", equity=round(state["cash"], 2))
    rifugio = CFG.get("safe_asset", "EUR").upper()
    corpo = "\n".join(f"• {c}" for c in chiuse) if chiuse else "nessuna posizione aperta"
    return (f"⏸️ <b>SISTEMA IN PAUSA</b>\n\n{corpo}\n\n"
            f"Capitale in {rifugio}: {state['cash']:.2f} €\n"
            "Nessuna nuova posizione verra' aperta. Riprendi con /riprendi.")


def stop() -> str:
    """
    Arresto d'emergenza: liquida tutto E blocca il sistema.

    Differenza da /pausa: la pausa e' una sospensione prevista, lo stop e' un
    freno d'emergenza. Richiede /resume esplicito per ripartire, cosi' non
    puo' riaccendersi da solo mentre non stai guardando.
    """
    state = load_state(CFG)
    chiuse = chiudi_tutto(state, "/stop emergenza")
    state["paused"] = True
    state["halted"] = True
    state["halt_reason"] = "arresto d'emergenza (/stop)"
    save_state(state)
    pending.clear()
    journal("STOP", reason="arresto emergenza utente", equity=round(state["cash"], 2))
    rifugio = CFG.get("safe_asset", "EUR").upper()
    corpo = "\n".join(f"• {c}" for c in chiuse) if chiuse else "nessuna posizione aperta"
    return (f"🟥 <b>ARRESTO D'EMERGENZA</b>\n\n{corpo}\n\n"
            f"Tutto liquidato. Capitale in {rifugio}: {state['cash']:.2f} €\n"
            "Sistema bloccato. Serve <b>/resume</b> esplicito per ripartire.")


def riprendi() -> str:
    state = load_state(CFG)
    state["paused"] = False
    save_state(state)
    journal("RIPRESA", reason="richiesta utente")
    return "▶️ <b>Sistema ripreso.</b> Al prossimo controllo tornera' a proporre."


def status() -> str:
    state = load_state(CFG)
    prices = {}
    for pair in state["positions"]:
        try:
            prices[pair] = fetch_price(pair)
        except Exception:
            pass
    eq = equity(state, prices)
    versato = float(state.get("capitale_versato", CFG["capital"]))
    righe = [f"<b>Equity:</b> {eq:.2f} € ({eq / versato - 1:+.1%} su {versato:.0f} € versati)",
             f"<b>Cash:</b> {state['cash']:.2f} €",
             f"<b>Posizioni:</b> {len(state['positions'])}"]
    for pair, p in state["positions"].items():
        px = prices.get(pair, p["entry"])
        mv = (px - p["entry"]) / p["entry"] * p["side"] * 100
        v = "LONG" if p["side"] > 0 else "SHORT"
        stop = -CFG["stop_loss_pct"] * 100 / max(p["leverage"], 0.01)
        righe.append(f"  {pair} {v} {p['leverage']}x → {mv:+.2f}% "
                     f"(stop a {stop:.1f}%)")
    if state.get("paused"):
        righe.append("\n⏸️ IN PAUSA — /riprendi per ripartire")
    if state.get("halted"):
        righe.append(f"\n🛑 FERMATO: {state['halt_reason']}")
    return "\n".join(righe)


# --------------------------------------------------------------------------
MARCATORE_ALLARME = os.path.join(DATA_DIR, ".allarme_stato_inviato")


def controlla_stato_allavvio():
    """
    Prima di ogni altra cosa: i dati sono al loro posto?

    Se il journal dice che il sistema ha gia' operato ma lo stato non c'e',
    il bot NON riparte. Ripartire da zero con il capitale iniziale cancella
    la storia del conto senza che nessuno se ne accorga: e' successo il 10 e
    l'11 agosto 2026, e sono andati persi 74 punti di storico e 8 posizioni.
    """
    for nome in migra_se_serve():
        print(f"[avvio] migrato {nome} nella cartella dati")

    try:
        load_state(CFG)
    except StatoPerduto as e:
        # systemd riavvia ogni 30 secondi: senza il marcatore manderebbe lo
        # stesso allarme all'infinito.
        if not os.path.exists(MARCATORE_ALLARME):
            send("🛑 <b>AVVIO BLOCCATO — stato non trovato</b>\n\n"
                 f"{e}\n\n"
                 "<i>Il bot non riparte da solo: ripartire da zero "
                 "cancellerebbe lo storico senza dirlo.</i>")
            try:
                open(MARCATORE_ALLARME, "w").close()
            except Exception:
                pass
        print(f"[avvio] BLOCCATO: {e}")
        raise SystemExit(1)

    if os.path.exists(MARCATORE_ALLARME):
        os.remove(MARCATORE_ALLARME)

    # Se 'capital' e' stato alzato in configurazione, la differenza entra in
    # cassa come versamento. Cambiare solo il numero senza aggiungere i soldi
    # farebbe apparire una perdita che non e' mai avvenuta.
    st = load_state(CFG)
    delta = adegua_capitale(st, CFG)
    cambiato = allinea_ombra_se_ferma(st)
    # L'ordine conta: prima la cassa giusta, poi le posizioni da rispecchiare.
    if avvia_ombra_rispecchiando(st, CFG):
        cambiato = True
    if cambiato or delta:
        save_state(st)
        send(f"💶 <b>Versamento registrato</b>\n"
             f"Capitale portato a {st['capitale_versato']:.2f} € "
             f"(+{delta:.2f} €).\n"
             f"Cassa ora {st['cash']:.2f} €.\n"
             f"<i>I rendimenti da qui in poi si calcolano sul nuovo totale.</i>")


def main():
    controlla_stato_allavvio()

    modo = ("ESECUZIONE AUTOMATICA" if CFG.get("auto_execute")
            else "conferma manuale")
    send("🤖 <b>Bot avviato</b> — paper trading\n"
         f"Capitale: {CFG['capital']} € · modo: <b>{modo}</b>\n"
         f"Controllo segnali ogni {CFG['check_interval_min']} min "
         f"({CFG['conferme_richieste']} conferme prima di agire)\n"
         f"Stop-loss a {CFG['stop_loss_pct']:.0%} · rischio ogni "
         f"{CFG['risk_check_sec']}s · rifugio {CFG.get('safe_asset','EUR').upper()}\n\n"
         "/status /check /pausa /riprendi /stop /resume")

    offset = None
    ultimo_eval, ultimo_risk = 0.0, 0.0

    while True:
        try:
            ora = time.time()
            if ora - ultimo_risk > CFG["risk_check_sec"]:
                risk_check()
                ultimo_risk = ora
            if ora - ultimo_eval > CFG["check_interval_min"] * 60:
                evaluate()
                ultimo_eval = ora

            r = tg("getUpdates", offset=offset, timeout=20)
            for u in r.get("result", []):
                offset = u["update_id"] + 1

                if "callback_query" in u:
                    cb = u["callback_query"]
                    kind, cid = cb["data"].split(":", 1)
                    if kind == "y":
                        msg = execute(cid)
                    else:
                        pending.pop(cid, None)
                        msg = "saltata"
                        journal("skip", reason="rifiutata da utente", confirmed=False)
                    tg("answerCallbackQuery", callback_query_id=cb["id"], text=msg[:190])
                    send(f"→ {msg}")

                elif "message" in u:
                    t = u["message"].get("text", "")
                    if t.startswith("/status"):
                        send(status())
                    elif t.startswith("/check"):
                        send("controllo in corso…")
                        evaluate()
                        ultimo_eval = time.time()
                        send("fatto.")
                    elif t.startswith("/pausa"):
                        send(pausa())
                    elif t.startswith("/stop"):
                        send(stop())
                    elif t.startswith("/riprendi"):
                        send(riprendi())
                    elif t.startswith("/halt"):
                        s = load_state(CFG)
                        s["halted"] = True
                        s["halt_reason"] = "stop manuale"
                        save_state(s)
                        send("🛑 fermato.")
                    elif t.startswith("/resume"):
                        s = load_state(CFG)
                        s["halted"] = False
                        s["halt_reason"] = ""
                        save_state(s)
                        send("▶️ ripreso.")
        except Exception:
            traceback.print_exc()
            time.sleep(10)


if __name__ == "__main__":
    main()
