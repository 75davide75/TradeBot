#!/usr/bin/env python3
"""
Adattatore per i futures perpetui Kraken.

PERCHE' ESISTE QUESTO FILE

Sullo spot a margine paghiamo un rollover dello 0,12% al giorno — il 44%
all'anno — e commissioni dello 0,26% per lato. Sui perpetui il rollover non
esiste (c'e' il funding, che spesso si INCASSA stando short) e la commissione
scende a 0,05%.

Nel backtest su tre coppie la differenza valeva 19 punti percentuali, coerente
su tutte e tre. E' il risultato piu' solido di tutto il progetto.

COSA CAMBIA RISPETTO ALLO SPOT

  costo del giro   0,52%  ->  0,10%      (cinque volte meno)
  mantenimento     -44%/anno  ->  funding, spesso positivo per gli short
  denominazione    EUR    ->  USD        (attenzione: espone al cambio EUR/USD)

L'ultima riga e' un costo nuovo, non un pasto gratis: i contratti PF_ sono
denominati in dollari, quindi un conto in euro assume anche il rischio di
cambio, storicamente intorno al 7-8% di volatilita' annua.
"""

import json
import urllib.request
from datetime import datetime, timezone

import pandas as pd

# Commissioni Kraken Futures, fascia base
FUT_MAKER = 0.0002
FUT_TAKER = 0.0005

BASE_D = "https://futures.kraken.com/derivatives/api/v3"
BASE_C = "https://futures.kraken.com/api/charts/v1"

# Corrispondenza tra le coppie spot che gia' usiamo e i perpetui
MAPPA = {
    "XXBTZEUR": "PF_XBTUSD",
    "XETHZEUR": "PF_ETHUSD",
    "XXRPZEUR": "PF_XRPUSD",
    "SOLEUR":   "PF_SOLUSD",
    "LINKEUR":  "PF_LINKUSD",
    "XLTCZEUR": "PF_LTCUSD",
    "ADAEUR":   "PF_ADAUSD",
    "DOTEUR":   "PF_DOTUSD",
    "AVAXEUR":  "PF_AVAXUSD",
    "BCHEUR":   "PF_BCHUSD",
    "XXMRZEUR": "PF_XMRUSD",
    "ATOMEUR":  "PF_ATOMUSD",
    "FILEUR":   "PF_FILUSD",
    "UNIEUR":   "PF_UNIUSD",
}

_cache_tickers = {"quando": None, "dati": {}}


def _get(url: str, timeout: int = 30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def simbolo(pair: str) -> str:
    """Da coppia spot a simbolo perpetuo. Accetta gia' i simboli PF_."""
    if pair.upper().startswith("PF_"):
        return pair.upper()
    if pair not in MAPPA:
        raise KeyError(f"nessun perpetuo noto per {pair}")
    return MAPPA[pair]


def tickers(max_eta_sec: int = 20) -> dict:
    """Tutti i ticker, con una cache breve: una chiamata copre tutto l'universo."""
    ora = datetime.now(timezone.utc)
    q = _cache_tickers["quando"]
    if q is None or (ora - q).total_seconds() > max_eta_sec:
        d = _get(f"{BASE_D}/tickers")["tickers"]
        _cache_tickers["dati"] = {x["symbol"].upper(): x for x in d}
        _cache_tickers["quando"] = ora
    return _cache_tickers["dati"]


def fetch_price(pair: str) -> float:
    """
    Prezzo corrente. Usa markPrice, non 'last'.

    Il mark price e' il riferimento con cui l'exchange calcola margine e
    liquidazioni: e' meno manipolabile dell'ultimo scambio e non salta per
    un singolo ordine anomalo. Simulare sul 'last' darebbe P&L piu' ottimisti
    di quelli che otterresti davvero.
    """
    t = tickers().get(simbolo(pair))
    if not t:
        raise RuntimeError(f"{pair}: ticker non disponibile")
    return float(t.get("markPrice") or t.get("last"))


def funding_corrente(pair: str) -> float:
    """
    Tasso di funding relativo per ora, come frazione.

    Segno: positivo significa che i long pagano gli short. Chi e' short
    INCASSA. E' il contrario del rollover dello spot, dove paghi comunque.
    """
    t = tickers().get(simbolo(pair), {})
    prezzo = float(t.get("markPrice") or t.get("last") or 0)
    fr = t.get("fundingRate")
    if fr is None or prezzo <= 0:
        return 0.0
    return float(fr) / prezzo


def fetch_ohlc(pair: str, risoluzione: str = "1d", giorni: int = 720) -> pd.DataFrame:
    """Candele storiche. Restituisce le stesse colonne della versione spot."""
    da = int(datetime.now(timezone.utc).timestamp()) - giorni * 86400
    d = _get(f"{BASE_C}/trade/{simbolo(pair)}/{risoluzione}?from={da}", timeout=45)
    c = d.get("candles", [])
    if not c:
        raise RuntimeError(f"{pair}: nessuna candela")
    df = pd.DataFrame(c)
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df.set_index("time")[["open", "high", "low", "close", "volume"]]


def order_minimum(pair: str, prezzo: float) -> float:
    """
    Nozionale minimo eseguibile, in valuta del contratto.

    La precisione di negoziazione dice quanti decimali di contratto sono
    ammessi: con precisione 4, il minimo e' 0,0001 contratti.
    """
    try:
        ins = _get(f"{BASE_D}/instruments")["instruments"]
        spec = {x["symbol"].upper(): x for x in ins}.get(simbolo(pair), {})
        prec = int(spec.get("contractValueTradePrecision", 4))
        size = float(spec.get("contractSize", 1))
        return (10 ** -prec) * size * prezzo
    except Exception:
        return 1.0


def costo_giro() -> float:
    """Commissione totale per aprire e chiudere, come taker."""
    return FUT_TAKER * 2


def mercati_disponibili(universo: list) -> list:
    """Filtra l'universo tenendo solo le coppie con un perpetuo negoziabile."""
    t = tickers()
    fuori = []
    for p in universo:
        try:
            if simbolo(p) in t:
                fuori.append(p)
        except KeyError:
            pass
    return fuori
