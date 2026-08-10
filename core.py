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

import csv
import json
import os
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "state.json")
JOURNAL_FILE = os.path.join(BASE, "journal.csv")
CONFIG_FILE = os.path.join(BASE, "config.json")

# Costi Kraken reali, fascia volume piu' bassa
TAKER_FEE = 0.0040
MARGIN_OPEN_FEE = 0.0002
ROLLOVER_DAILY = 0.0012


def load_config() -> dict:
    with open(CONFIG_FILE) as f:
        return json.load(f)


# --------------------------------------------------------------------------
# DATI
# --------------------------------------------------------------------------
def fetch_ohlc(pair: str, interval: int = 1440) -> pd.DataFrame:
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
def signal_momentum(df: pd.DataFrame, n: int = 60, allow_short: bool = True) -> float:
    """Ritorna la direzione desiderata: +1 long, -1 short, 0 flat.

    Usa SOLO la chiusura dell'ultima candela completa. Nessun dato futuro.
    """
    r = df["close"].pct_change(n).iloc[-1]
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
# --------------------------------------------------------------------------
def blank_state(cfg: dict) -> dict:
    return {
        "mode": "paper",
        "cash": cfg["capital"],
        "positions": {},
        "peak_equity": cfg["capital"],
        "halted": False,
        "halt_reason": "",
        "shadow_cash": cfg["capital"],      # portafoglio ombra: leva fissa 1x
        "shadow_positions": {},
        "created": datetime.now(timezone.utc).isoformat(),
        "history": [],
    }


def load_state(cfg: dict) -> dict:
    if not os.path.exists(STATE_FILE):
        s = blank_state(cfg)
        save_state(s)
        return s
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state: dict) -> None:
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)   # scrittura atomica: niente stato corrotto


def journal(action: str, **fields) -> None:
    """Ogni decisione viene scritta qui. Il journal e' la fonte di verita'."""
    row = {"ts": datetime.now(timezone.utc).isoformat(), "action": action}
    row.update(fields)
    exists = os.path.exists(JOURNAL_FILE)
    cols = ["ts", "action", "pair", "side", "price", "notional",
            "leverage", "equity", "reason", "confirmed"]
    with open(JOURNAL_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if not exists:
            w.writeheader()
        w.writerow(row)


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
        eq -= p["notional"] * ROLLOVER_DAILY * days
    return eq


def open_position(state, pair, side, price, notional, leverage, reason):
    fee = notional * (TAKER_FEE + MARGIN_OPEN_FEE)
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
    carry = p["notional"] * ROLLOVER_DAILY * days
    fee = p["notional"] * TAKER_FEE
    state["cash"] += pnl - carry - fee
    journal("close", pair=pair, side=p["side"], price=price,
            notional=round(p["notional"], 2), leverage=p["leverage"],
            equity=round(state["cash"], 2), reason=reason, confirmed=True)
    return pnl - carry - fee


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
