#!/usr/bin/env python3
"""
Filtro di negoziabilita': un mercato e' ancora operabile o no?

PERCHE' ESISTE QUESTO FILE

'universe' in config.json e' una lista scritta a mano che niente controllava
mai. Se Kraken sospende una coppia, se la liquidita' evapora, se lo spread
triplica, il bot continuava a operarci sopra come nulla fosse.

Le regole qui sono NUMERICHE, non giudizi: soglie su spread, volume e stato
del contratto. Sono verificabili, backtestabili e non richiedono un modello
che decida al posto nostro. Un filtro di negoziabilita' e' manutenzione, non
previsione — e la differenza conta, perche' l'unica cosa che possiamo davvero
misurare in anticipo sono i costi.

Solo libreria standard: la decisione e' una funzione pura sui numeri del
ticker, cosi' e' testabile ovunque, anche dove pandas non c'e'.
"""

# Le soglie vengono dalle misure reali sui 57 mercati perpetui Kraken
# (11 agosto 2026): spread mediano 0,057%, medio 0,103%, massimo 1,279%.
#
# spread_massimo 0,15% tiene fuori la coda illiquida — MUBARAK 1,28%,
# COOKIE 0,65%, ACE 0,34%, CTSI 0,28%, BICO 0,24% — e lascia dentro con
# ampio margine tutti gli 8 mercati attualmente operati, il cui spread
# peggiore e' LTC allo 0,044%.
#
# Non e' una soglia di prudenza generica: su un conto da 200 EUR il costo
# per giro e' commissione + spread, e su un mercato all'1,3% di spread
# nessun segnale sopravvive al costo di entrarci e uscirne.
SOGLIE = {
    "spread_massimo": 0.0015,        # 0,15% denaro-lettera
    "volume_minimo_usd": 250_000.0,  # scambiato nelle 24 ore
}


def valuta(ticker: dict, soglie: dict = None) -> tuple:
    """
    Decide se un mercato e' negoziabile. Restituisce (esito, motivo).

    Funzione pura: prende i numeri, restituisce una decisione. Nessuna rete,
    nessuno stato. E' il pezzo che si puo' testare senza dipendere da cosa
    sta facendo il mercato adesso.
    """
    s = dict(SOGLIE, **(soglie or {}))

    if not ticker:
        return False, "nessun dato di mercato"
    if ticker.get("suspended"):
        return False, "contratto sospeso da Kraken"
    if ticker.get("postOnly"):
        return False, "solo ordini passivi: non si puo' entrare a mercato"

    px = _numero(ticker.get("markPrice")) or _numero(ticker.get("last"))
    if not px or px <= 0:
        return False, "prezzo non disponibile"

    bid, ask = _numero(ticker.get("bid")), _numero(ticker.get("ask"))
    if not bid or not ask or ask <= bid:
        return False, "book vuoto o incrociato"

    # Arrotondato prima del confronto: (100.15-100.0)/100.0 in virgola mobile
    # fa 0.0015000000000000568, che supererebbe una soglia di 0,15% per puro
    # rumore numerico. Oltre la decima cifra uno spread non significa niente.
    spread = round((ask - bid) / px, 10)
    if spread > s["spread_massimo"]:
        return False, (f"spread {spread:.3%} oltre il limite di "
                       f"{s['spread_massimo']:.2%}")

    volume = _numero(ticker.get("volumeQuote"))
    if volume is not None and volume < s["volume_minimo_usd"]:
        return False, (f"volume 24h {volume:,.0f} USD sotto il minimo di "
                       f"{s['volume_minimo_usd']:,.0f}")

    return True, f"spread {spread:.3%}"


def _numero(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None      # scarta i NaN


def scarta(universo: list, tickers: dict, mappa: dict, soglie: dict = None):
    """
    Applica il filtro a un universo. Restituisce (tenuti, {scartato: motivo}).

    'mappa' traduce la coppia interna nel simbolo del perpetuo, perche' il
    ticker di Kraken e' indicizzato su quest'ultimo.
    """
    tenuti, fuori = [], {}
    for p in universo:
        simbolo = (mappa.get(p) or p).upper()
        ok, motivo = valuta(tickers.get(simbolo), soglie)
        if ok:
            tenuti.append(p)
        else:
            fuori[p] = motivo
    return tenuti, fuori
