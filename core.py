#!/usr/bin/env python3
"""
Core del sistema: dati, segnale, layer di rischio, portafoglio paper.

Filosofia di design, in ordine di importanza:
  1. Non perdere soldi veri finche' non c'e' evidenza. Default = paper.
  2. Le regole di rischio sono scritte in anticipo e meccaniche.
     Nessun aggiustamento discrezionale basato su come e' andata ieri.
  3. Ogni decisione finisce nel journal. Se non e' loggato, non e' successo.
  4. Un portafoglio ombra NON aggiustato gira in parallelo, per misurare
     se gli aggiustamenti aiutano o fanno danni.
"""

import json
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# La persistenza sta in stato.py, che non importa pandas ne' numpy: e' il
# codice piu' critico del sistema e deve poter girare e essere testato anche
# dove le librerie scientifiche non ci sono. Qui viene riesposta, cosi'
# 'from core import STATE_FILE' continua a funzionare ovunque.
from stato import (BASE, CONFIG_FILE, DATA_DIR, JOURNAL_FILE,  # noqa: F401
                   REPORT_DIR, STATE_FILE, StatoPerduto, adegua_capitale,
                   allinea_ombra_se_ferma,
                   blank_state, ha_operato, journal, load_state,
                   migra_se_serve, save_state)

# Costi Kraken reali, fascia volume piu' bassa
TAKER_FEE = 0.0040
MARGIN_OPEN_FEE = 0.0002
ROLLOVER_DAILY = 0.0012

# Su quale mercato operiamo. Impostato da load_config().
#
#   spot_margin : commissione 0,26%/lato + rollover 0,12% AL GIORNO (44%/anno)
#   perpetual   : commissione 0,05%/lato, nessun rollover, funding che
#                 stando short spesso si INCASSA invece di pagarlo
#
# Nel backtest la differenza valeva 19 punti percentuali su tre coppie.
_MODO = {"perp": False}


def modo_perp() -> bool:
    return _MODO["perp"]


def costi_correnti() -> tuple:
    """(commissione per lato, fee apertura, costo di mantenimento giornaliero)."""
    if _MODO["perp"]:
        import perp
        return perp.FUT_TAKER, 0.0, 0.0      # il carry lo gestisce il funding
    return TAKER_FEE, MARGIN_OPEN_FEE, ROLLOVER_DAILY


# Valori di riserva per ogni parametro. Servono perche' config.json e' escluso
# da git (contiene il token), quindi codice e configurazione possono
# disallinearsi: il codice arriva aggiornato, la config resta vecchia.
#
# E' successo davvero, ed e' costato 37 riavvii in loop: bot.py cercava
# 'stop_loss_pct' su un config.json copiato prima che quel campo esistesse.
#
# Un bot di trading non deve morire perche' manca una chiave. Deve partire
# con un valore prudente e dirti cosa ha fatto.
DEFAULTS = {
    "capital": 20.0,
    "max_leverage": 2.0,
    "min_leverage": 0.25,
    "target_vol": 0.20,
    "vol_lookback": 30,
    "momentum_n": 60,
    "allow_short": True,
    "universe": ["XXBTZEUR", "XETHZEUR", "XXRPZEUR"],
    "check_interval_min": 240,
    "max_drawdown_halt": 0.25,
    "risk_check_sec": 60,
    "stop_loss_pct": 0.08,
    "auto_close_timeout_sec": 60,
    "safe_asset": "EUR",
    "dashboard_port": 8080,
    # Esecuzione automatica: nessun bottone, solo notifica a cosa fatta.
    # Vale SOLO in paper. Se un giorno ci fossero soldi veri, la conferma
    # umana e' l'ultima cosa tra un bug e il conto.
    "auto_execute": True,
    # Il segnale deve restare invariato per N controlli prima di agire.
    # Su candele giornaliere ancora aperte il segnale oscilla durante la
    # giornata: senza questo filtro il sistema entrerebbe e uscirebbe
    # in continuazione, pagando commissioni a ogni oscillazione.
    "conferme_richieste": 3,
}

OBBLIGATORI = ("telegram_token", "telegram_chat_id")


def load_config() -> dict:
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)

    # I segreti non hanno default: senza, il bot non ha senso di esistere.
    mancanti = [k for k in OBBLIGATORI if not cfg.get(k) or "IL_TUO" in str(cfg[k])]
    if mancanti:
        raise SystemExit(f"config.json: campi obbligatori mancanti: {mancanti}")

    riempiti = []
    for k, v in DEFAULTS.items():
        if k not in cfg:
            cfg[k] = v
            riempiti.append(f"{k}={v}")
    if riempiti:
        print(f"[config] parametri mancanti, uso i default: {', '.join(riempiti)}")

    _MODO["perp"] = cfg.get("market_type") == "perpetual"
    if _MODO["perp"]:
        print("[config] mercato: FUTURES PERPETUI "
              "(commissione 0.05%/lato, nessun rollover, funding attivo)")
    return cfg


# --------------------------------------------------------------------------
# DATI
# --------------------------------------------------------------------------
def fetch_ohlc(pair: str, interval: int = 1440) -> pd.DataFrame:
    if _MODO["perp"]:
        import perp
        return perp.fetch_ohlc(pair, "1d" if interval >= 1440 else "1h")
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}"
    with urllib.request.urlopen(url, timeout=30) as r:
        payload = json.load(r)
    if payload.get("error"):
        raise RuntimeError(f"{pair}: {payload['error']}")
    key = [k for k in payload["result"] if k != "last"][0]
    df = pd.DataFrame(payload["result"][key], columns=[
        "time", "open", "high", "low", "close", "vwap", "volume", "count"])
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df.set_index("time")


def fetch_price(pair: str) -> float:
    if _MODO["perp"]:
        import perp
        return perp.fetch_price(pair)
    url = f"https://api.kraken.com/0/public/Ticker?pair={pair}"
    with urllib.request.urlopen(url, timeout=20) as r:
        res = json.load(r)["result"]
    return float(list(res.values())[0]["c"][0])


_MIN_CACHE: dict = {}


def order_minimum(pair: str, price: float) -> float:
    """
    Nozionale minimo in EUR che Kraken accetta davvero per questa coppia.

    Esiste perche' senza questo controllo il paper trading simula operazioni
    che con soldi veri verrebbero RIFIUTATE dall'exchange: con 20 EUR divisi
    su piu' coppie le posizioni scendono sotto il minimo d'ordine, e un
    backtest che le conta produce risultati irraggiungibili.

    Un simulatore che ignora i vincoli di esecuzione non e' un simulatore,
    e' un generatore di illusioni.
    """
    if _MODO["perp"]:
        import perp
        return perp.order_minimum(pair, price)
    if not _MIN_CACHE:
        url = "https://api.kraken.com/0/public/AssetPairs"
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.load(r)["result"]
        for k, v in data.items():
            _MIN_CACHE[k] = (float(v.get("ordermin", 0)), float(v.get("costmin", 0)))
    ordermin, costmin = _MIN_CACHE.get(pair, (0.0, 0.0))
    return max(ordermin * price, costmin)


# --------------------------------------------------------------------------
# SEGNALE
# --------------------------------------------------------------------------
def solo_candele_chiuse(df: pd.DataFrame, interval_min: int = 1440) -> pd.DataFrame:
    """
    Toglie l'ultima candela se il suo periodo non e' ancora finito.

    Kraken restituisce come ultimo elemento la candela IN FORMAZIONE, il cui
    prezzo di chiusura e' semplicemente il prezzo di adesso e cambia in
    continuazione. Un segnale calcolato su quella oscilla durante la giornata
    e poi rientra da solo alla mezzanotte.

    Misurato sui dati orari veri degli 8 mercati, 31 giorni: 8 cambi di segnale
    reali contro 14 oscillazioni intragiornaliere che rientravano da sole.
    Agire su quelle costerebbe circa il 3,2% annuo in commissioni inutili,
    contro un rendimento stimato il cui intervallo di confidenza contiene gia'
    lo zero.
    """
    if len(df) < 2:
        return df
    fine = pd.Timestamp(df.index[-1]) + pd.Timedelta(minutes=interval_min)
    adesso = pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)
    return df.iloc[:-1] if fine > adesso else df


def signal_momentum(df: pd.DataFrame, n: int = 60, allow_short: bool = True,
                    interval_min: int = 1440) -> float:
    """Ritorna la direzione desiderata: +1 long, -1 short, 0 flat.

    Usa SOLO la chiusura dell'ultima candela completa. Nessun dato futuro.
    """
    d = solo_candele_chiuse(df, interval_min)
    if len(d) <= n:
        return 0.0
    r = d["close"].pct_change(n).iloc[-1]
    if np.isnan(r):
        return 0.0
    if r > 0:
        return 1.0
    return -1.0 if allow_short else 0.0


# --------------------------------------------------------------------------
# LAYER DI RISCHIO — volatility targeting
# --------------------------------------------------------------------------
def realized_vol(df: pd.DataFrame, lookback: int = 30) -> float:
    """Volatilita' annualizzata realizzata sugli ultimi `lookback` giorni."""
    return float(df["close"].pct_change().tail(lookback).std() * np.sqrt(365))


def target_leverage(df: pd.DataFrame, cfg: dict) -> tuple[float, str]:
    """
    Leva = volatilita' obiettivo / volatilita' realizzata, con cap duri.

    Questa e' l'UNICA cosa che si muove nel tempo, e si muove in risposta
    alla volatilita' del mercato, mai ai profitti recenti. Reagire ai propri
    profitti e' performance chasing: fa danni misurabili.

    Il cap massimo viene dal backtest: a 3x il 44% dei conti veniva
    liquidato, a 5x l'89%. Sopra 2x non ci si va, punto.
    """
    rv = realized_vol(df, cfg["vol_lookback"])
    if rv <= 0:
        return 0.0, "volatilita' nulla o non calcolabile"
    lev = cfg["target_vol"] / rv
    lev = float(np.clip(lev, cfg["min_leverage"], cfg["max_leverage"]))
    return round(lev, 2), f"vol realizzata {rv:.0%} vs obiettivo {cfg['target_vol']:.0%}"


# --------------------------------------------------------------------------
# PORTAFOGLIO PAPER
#
# blank_state, load_state, save_state e journal vivono in stato.py: sono
# importati in cima a questo file e riesposti. Qui restano solo le funzioni
# che fanno conti, che e' il mestiere di core.py.
# --------------------------------------------------------------------------
def carry_giornaliero(pair: str, side: float) -> float:
    """
    Costo (o ricavo) di tenere aperta una posizione, per giorno, come frazione
    del nozionale.

    Spot a margine: rollover fisso, si paga SEMPRE, in entrambe le direzioni.
    Perpetui: funding. Con segno positivo lo pagano i long e lo incassano gli
    short, quindi per una posizione short il valore restituito e' NEGATIVO —
    cioe' un ricavo. E' la differenza che vale 19 punti nel backtest.
    """
    if not _MODO["perp"]:
        return ROLLOVER_DAILY
    import perp
    try:
        return perp.funding_corrente(pair) * 24 * side
    except Exception:
        return 0.0


def equity(state: dict, prices: dict) -> float:
    """Valore corrente del conto: cash + P&L aperto, al netto del carry."""
    eq = state["cash"]
    for pair, p in state["positions"].items():
        px = prices.get(pair)
        if px is None:
            continue
        move = (px - p["entry"]) / p["entry"] * p["side"]
        eq += p["notional"] * move
        days = max(0.0, (datetime.now(timezone.utc) -
                         datetime.fromisoformat(p["opened"])).days)
        eq -= p["notional"] * carry_giornaliero(pair, p["side"]) * days
    return eq


def open_position(state, pair, side, price, notional, leverage, reason):
    taker, apert, _ = costi_correnti()
    fee = notional * (taker + apert)
    state["cash"] -= fee
    state["positions"][pair] = {
        "side": side, "entry": price, "notional": notional,
        "leverage": leverage, "opened": datetime.now(timezone.utc).isoformat(),
    }
    journal("open", pair=pair, side=side, price=price, notional=round(notional, 2),
            leverage=leverage, reason=reason, confirmed=True)


def close_position(state, pair, price, reason):
    p = state["positions"].pop(pair)
    move = (price - p["entry"]) / p["entry"] * p["side"]
    pnl = p["notional"] * move
    days = max(0.0, (datetime.now(timezone.utc) -
                     datetime.fromisoformat(p["opened"])).days)
    carry = p["notional"] * carry_giornaliero(pair, p["side"]) * days
    taker, _, _ = costi_correnti()
    fee = p["notional"] * taker
    state["cash"] += pnl - carry - fee
    journal("close", pair=pair, side=p["side"], price=price,
            notional=round(p["notional"], 2), leverage=p["leverage"],
            equity=round(state["cash"], 2), reason=reason, confirmed=True)
    return pnl - carry - fee


# --------------------------------------------------------------------------
# PORTAFOGLIO OMBRA
#
# Gira in parallelo a quello vero, rispecchiando OGNI sua azione: apre quando
# apre, chiude quando chiude, sugli stessi mercati e nella stessa direzione.
# Cambia una cosa sola: la leva e' fissa a 1x invece di seguire la volatilita'.
#
# Serve a rispondere a una domanda che altrimenti resta un'opinione: il
# volatility targeting aiuta o fa danni? Con un solo portafoglio non lo si puo'
# sapere, perche' non esiste il controfattuale. Con due che differiscono in una
# sola variabile, la differenza fra i due E' l'effetto di quella variabile.
#
# ATTENZIONE nel leggere il confronto: a leva 1x l'ombra e' piu' esposta (oggi
# le leve reali stanno fra 0,33 e 0,70), quindi ci si aspetta che guadagni E
# perda di piu'. Il confronto onesto non e' fra le due equity, ma fra
# rendimento e rischio: per questo pubblichiamo anche la volatilita' di
# entrambe.
# --------------------------------------------------------------------------
LEVA_OMBRA = 1.0


def _giorni_aperta(p: dict) -> float:
    return max(0.0, (datetime.now(timezone.utc) -
                     datetime.fromisoformat(p["opened"])).days)


def apri_ombra(state, pair, side, price, notional):
    taker, apert, _ = costi_correnti()
    # Da qui in poi l'ombra ha una storia sua e non va piu' riallineata.
    state["shadow_avviato"] = True
    state["shadow_cash"] = state.get("shadow_cash", 0.0) - notional * (taker + apert)
    state.setdefault("shadow_positions", {})[pair] = {
        "side": side, "entry": price, "notional": notional,
        "leverage": LEVA_OMBRA,
        "opened": datetime.now(timezone.utc).isoformat(),
    }


def avvia_ombra_rispecchiando(state: dict, cfg: dict) -> int:
    """
    Se l'ombra non ha mai operato ma il portafoglio vero ha gia' posizioni
    aperte, l'ombra le apre alle stesse condizioni: stesso mercato, stessa
    direzione, stesso prezzo d'ingresso, stessa data di apertura.

    Senza questo l'ombra resterebbe in liquidita' mentre il vero e' investito,
    e per settimane il grafico mostrerebbe una linea piatta accanto a una che
    si muove. Non sarebbe un confronto, sarebbe un invito a leggerlo male: il
    portafoglio vero sembrerebbe battere l'ombra solo perche' l'ombra non sta
    giocando.

    Le posizioni ereditate pagano la commissione d'ingresso, come le avesse
    aperte davvero: un'ombra che non paga i costi non e' un metro di paragone,
    e' un vantaggio regalato.
    """
    if state.get("shadow_avviato") or state.get("shadow_positions"):
        return 0
    pos = state.get("positions") or {}
    if not pos:
        return 0
    n = max(1, len(cfg.get("universe") or pos))
    alloc = float(state.get("shadow_cash", 0.0)) / n
    taker, apert, _ = costi_correnti()
    for pair, p in pos.items():
        notional = alloc * LEVA_OMBRA
        state["shadow_cash"] -= notional * (taker + apert)
        state.setdefault("shadow_positions", {})[pair] = {
            "side": p["side"], "entry": p["entry"], "notional": notional,
            "leverage": LEVA_OMBRA, "opened": p["opened"],
        }
    state["shadow_avviato"] = True
    print(f"[ombra] avviata rispecchiando {len(pos)} posizioni gia' aperte, "
          f"{alloc:.2f} EUR ciascuna a leva {LEVA_OMBRA:.0f}x")
    return len(pos)


def chiudi_ombra(state, pair, price) -> float:
    p = state.get("shadow_positions", {}).pop(pair, None)
    if not p:
        return 0.0
    move = (price - p["entry"]) / p["entry"] * p["side"]
    pnl = p["notional"] * move
    carry = p["notional"] * carry_giornaliero(pair, p["side"]) * _giorni_aperta(p)
    taker, _, _ = costi_correnti()
    netto = pnl - carry - p["notional"] * taker
    state["shadow_cash"] = state.get("shadow_cash", 0.0) + netto
    return netto


def equity_ombra(state: dict, prices: dict) -> float:
    eq = state.get("shadow_cash", 0.0)
    for pair, p in state.get("shadow_positions", {}).items():
        px = prices.get(pair)
        if px is None:
            continue
        move = (px - p["entry"]) / p["entry"] * p["side"]
        eq += p["notional"] * move
        eq -= p["notional"] * carry_giornaliero(pair, p["side"]) * _giorni_aperta(p)
    return eq


def check_kill_switch(state: dict, eq: float, cfg: dict) -> bool:
    """
    Interruttore di sicurezza. Se il conto perde piu' della soglia dal picco,
    il sistema si ferma e richiede riavvio manuale.

    Serve a impedire che un bug o un regime imprevisto svuotino il conto
    mentre nessuno guarda. Un sistema automatico senza kill switch non e'
    un sistema automatico, e' una perdita che non hai ancora notato.
    """
    if eq > state["peak_equity"]:
        state["peak_equity"] = eq
    dd = eq / state["peak_equity"] - 1 if state["peak_equity"] > 0 else 0
    if dd <= -cfg["max_drawdown_halt"]:
        state["halted"] = True
        state["halt_reason"] = f"drawdown {dd:.1%} oltre la soglia di {-cfg['max_drawdown_halt']:.0%}"
        journal("HALT", reason=state["halt_reason"], equity=round(eq, 2))
        return True
    return False
