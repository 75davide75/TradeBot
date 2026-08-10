#!/usr/bin/env python3
"""
Backtest engine onesto per strategie su Kraken, con modello di costi reale.

Principio guida: il backtest deve poter DIRE DI NO. Ogni scelta di design qui
e' fatta per rendere piu' difficile illudersi, non piu' facile.

Difese anti-autoinganno implementate:
  1. Segnale calcolato sulla chiusura t, eseguito all'apertura t+1 (no look-ahead)
  2. Fee Kraken reali incluse (taker + apertura margine + rollover per barra)
  3. Walk-forward: parametri scelti su train, misurati su test mai visto
  4. Universo multi-asset: niente cherry-picking di una coppia fortunata
  5. Benchmark buy&hold sempre affiancato
  6. Confronto contro strategie casuali (baseline di rumore)
"""

import json
import time
import urllib.request
from dataclasses import dataclass

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# COSTI REALI KRAKEN (fascia volume piu' bassa = quella di un conto da 20 EUR)
# --------------------------------------------------------------------------
TAKER_FEE = 0.0040        # 0.40% per lato, sul nozionale
MARGIN_OPEN_FEE = 0.0002  # 0.02% all'apertura posizione a margine
ROLLOVER_4H = 0.0002      # 0.02% ogni 4 ore di posizione aperta
ROLLOVER_DAILY = ROLLOVER_4H * 6   # 0.12% al giorno

UNIVERSE = [
    "XXBTZEUR", "XETHZEUR", "SOLEUR", "ADAEUR", "LINKEUR", "XXRPZEUR",
    "XLTCZEUR", "XDGEUR", "AVAXEUR", "DOTEUR", "BCHEUR", "XXMRZEUR",
    "ATOMEUR", "FILEUR", "XXLMZEUR", "XETCZEUR", "UNIEUR", "NEAREUR",
]


# --------------------------------------------------------------------------
# DATI
# --------------------------------------------------------------------------
def fetch_ohlc(pair: str, interval: int = 1440) -> pd.DataFrame:
    """Scarica candele da Kraken. L'endpoint pubblico ne restituisce max ~720."""
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}"
    with urllib.request.urlopen(url, timeout=30) as r:
        payload = json.load(r)
    if payload.get("error"):
        raise RuntimeError(f"{pair}: {payload['error']}")
    key = [k for k in payload["result"] if k != "last"][0]
    df = pd.DataFrame(
        payload["result"][key],
        columns=["time", "open", "high", "low", "close", "vwap", "volume", "count"],
    )
    for c in ["open", "high", "low", "close", "vwap", "volume"]:
        df[c] = df[c].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df.set_index("time")


def load_universe(pairs=UNIVERSE, interval=1440) -> dict:
    out = {}
    for p in pairs:
        try:
            df = fetch_ohlc(p, interval)
            if len(df) > 200:
                out[p] = df
        except Exception as e:  # pragma: no cover
            print(f"  skip {p}: {e}")
        time.sleep(0.4)  # rate limit cortese
    return out


# --------------------------------------------------------------------------
# STRATEGIE
# Ognuna restituisce una Series di posizione desiderata in {-1, 0, +1},
# calcolata usando SOLO dati fino a t incluso.
# --------------------------------------------------------------------------
def s_ma_cross(df, fast=20, slow=50, allow_short=False):
    f = df["close"].rolling(fast).mean()
    s = df["close"].rolling(slow).mean()
    pos = (f > s).astype(float)
    if allow_short:
        pos = pos * 2 - 1
    return pos

def s_donchian(df, n=20, allow_short=False):
    hi = df["high"].rolling(n).max().shift(1)
    lo = df["low"].rolling(n).min().shift(1)
    pos = pd.Series(np.nan, index=df.index)
    pos[df["close"] > hi] = 1.0
    pos[df["close"] < lo] = -1.0 if allow_short else 0.0
    return pos.ffill().fillna(0.0)

def s_rsi_meanrev(df, n=14, lo_th=30, hi_th=70):
    d = df["close"].diff()
    gain = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    pos = pd.Series(np.nan, index=df.index)
    pos[rsi < lo_th] = 1.0
    pos[rsi > hi_th] = 0.0
    return pos.ffill().fillna(0.0)

def s_momentum(df, n=30, allow_short=False):
    r = df["close"].pct_change(n)
    pos = (r > 0).astype(float)
    if allow_short:
        pos = pos * 2 - 1
    return pos

def s_buyhold(df, **kw):
    return pd.Series(1.0, index=df.index)

def s_random(df, seed=0, p=0.5, **kw):
    """Baseline di rumore: se una strategia non batte questa, non e' una strategia."""
    rng = np.random.default_rng(seed)
    return pd.Series(rng.choice([0.0, 1.0], len(df), p=[1 - p, p]), index=df.index)


STRATEGIES = {
    "ma_cross":   (s_ma_cross,    {"fast": [5, 10, 20, 30], "slow": [30, 50, 100, 150]}),
    "donchian":   (s_donchian,    {"n": [10, 20, 30, 55]}),
    "rsi_mr":     (s_rsi_meanrev, {"n": [7, 14, 21], "lo_th": [20, 25, 30], "hi_th": [65, 70, 75]}),
    "momentum":   (s_momentum,    {"n": [10, 20, 30, 60, 90]}),
}


# --------------------------------------------------------------------------
# MOTORE
# --------------------------------------------------------------------------
@dataclass
class Result:
    total_return: float
    sharpe: float
    max_dd: float
    n_trades: float
    fee_drag: float
    win_rate: float
    final_equity: float


def backtest(df: pd.DataFrame, pos: pd.Series, leverage: float = 1.0,
             capital: float = 20.0, bars_per_day: float = 1.0) -> Result:
    """
    Esegue il backtest con costi reali.

    ANTI LOOK-AHEAD: la posizione decisa con la chiusura di t viene applicata
    al rendimento da t a t+1. `pos.shift(1)` e' la riga che rende il test onesto;
    senza di essa qualunque strategia sembra geniale.
    """
    ret = df["close"].pct_change().fillna(0.0)
    held = pos.shift(1).fillna(0.0)

    # Rendimento lordo della posizione a leva
    gross = held * ret * leverage

    # Costi: turnover pagato al taker + fee apertura margine
    turnover = held.diff().abs().fillna(held.abs())
    trade_cost = turnover * (TAKER_FEE + MARGIN_OPEN_FEE) * leverage

    # Rollover: pagato su ogni barra in cui la posizione e' aperta
    roll = ROLLOVER_DAILY / bars_per_day
    carry_cost = held.abs() * roll * leverage

    net = gross - trade_cost - carry_cost

    equity = capital * (1 + net).cumprod()

    # Liquidazione: a leva L, una perdita di ~1/L sul nozionale azzera il conto.
    # Se l'equity tocca zero il gioco finisce li'.
    blown = equity <= capital * 0.05
    if blown.any():
        first = blown.idxmax()
        equity.loc[first:] = 0.0
        net.loc[first:] = 0.0

    ann = 365 * bars_per_day
    sharpe = (net.mean() / net.std() * np.sqrt(ann)) if net.std() > 0 else 0.0
    dd = float((equity / equity.cummax() - 1).min())
    trades = float(turnover.sum() / 2)
    active = net[held.abs() > 0]
    win = float((active > 0).mean()) if len(active) else 0.0

    return Result(
        total_return=float(equity.iloc[-1] / capital - 1),
        sharpe=float(sharpe),
        max_dd=dd,
        n_trades=trades,
        fee_drag=float((trade_cost + carry_cost).sum()),
        win_rate=win,
        final_equity=float(equity.iloc[-1]),
    )


def param_grid(space: dict):
    import itertools
    keys = list(space)
    for combo in itertools.product(*[space[k] for k in keys]):
        d = dict(zip(keys, combo))
        if "fast" in d and "slow" in d and d["fast"] >= d["slow"]:
            continue
        yield d


def walk_forward(data: dict, name: str, leverage: float, split: float = 0.6):
    """
    Sceglie i parametri sul primo 60% dei dati (train), li misura sul
    restante 40% mai visto (test). Il numero che conta e' quello di test.
    """
    fn, space = STRATEGIES[name]
    train_scores, test_rows = {}, []

    # --- fase 1: ottimizzazione sul solo train, aggregata su tutto l'universo
    for params in param_grid(space):
        sharpes = []
        for pair, df in data.items():
            cut = int(len(df) * split)
            tr = df.iloc[:cut]
            if len(tr) < 150:
                continue
            r = backtest(tr, fn(tr, **params), leverage)
            sharpes.append(r.sharpe)
        if sharpes:
            train_scores[tuple(sorted(params.items()))] = np.mean(sharpes)

    if not train_scores:
        return None, []
    best = dict(max(train_scores, key=train_scores.get))

    # --- fase 2: misurazione out-of-sample con i parametri congelati
    for pair, df in data.items():
        cut = int(len(df) * split)
        te = df.iloc[cut:]
        if len(te) < 60:
            continue
        r = backtest(te, fn(te, **best), leverage)
        bh = backtest(te, s_buyhold(te), leverage=1.0)
        test_rows.append({
            "pair": pair, "ret": r.total_return, "sharpe": r.sharpe,
            "max_dd": r.max_dd, "trades": r.n_trades, "fees": r.fee_drag,
            "bh_ret": bh.total_return, "final": r.final_equity,
        })
    return best, test_rows
