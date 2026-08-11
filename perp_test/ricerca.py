#!/usr/bin/env python3
"""
Ricerca di segnali, con i costi veri e senza autoinganno.

COSA CAMBIA RISPETTO A test.py

1. I COSTI. test.py addebita solo la commissione (turn * FUT_TAKER). Manca lo
   spread, che sui 57 mercati ha mediana 0,057% e media 0,103%, con MUBARAK
   all'1,28%. Il costo vero per giro sul mercato mediano e' 0,157%, non 0,10%:
   il test precedente sottostimava di meta' i costi sui mercati liquidi e di
   molto di piu' sulla coda illiquida.

2. IL TURNOVER E' RIPORTATO. Senza quel numero non si vede quale strategia e'
   fragile ai costi, e le due cose non si distinguono guardando solo lo Sharpe.

3. L'INTERVALLO DI CONFIDENZA E' UN BLOCK BOOTSTRAP. L'errore standard classico
   presuppone osservazioni indipendenti; i rendimenti crypto sono autocorrelati
   e fortemente correlati fra mercati, quindi quella formula sovrastima la
   precisione. Il bootstrap a blocchi conserva la struttura temporale.

4. SEGNALI CROSS-SECTIONAL. Tutti i segnali di test.py sono time-series: ogni
   mercato guarda solo se stesso, quindi prende esposizione direzionale per
   costruzione. E' il difetto che TEST_PERPETUI.md aveva gia' diagnosticato da
   solo ("il 62% del risultato viene dalla direzione del prezzo"). Le versioni
   cross-sectional classificano i mercati fra loro e sono neutrali al mercato
   per costruzione, non per sottrazione a posteriori.

AVVERTENZA STATISTICA, LA PIU' IMPORTANTE

Piu' strategie si provano sugli stessi giorni fuori campione, piu' e' probabile
che una sembri buona per caso. Qui se ne provano sei: la soglia di significativita'
va corretta di conseguenza (Bonferroni in fondo). Nessun risultato di questo
script promuove una strategia a "funziona": al massimo a "merita di girare in
paper", dove i dati si raccolgono in avanti e non si possono curvare.

Uso:
    python3 scarica.py      # una volta, riempie dati/
    python3 ricerca.py
"""

import glob
import json
import os

import numpy as np
import pandas as pd

FUT_TAKER = 0.0005          # Kraken futures, fascia retail, per lato
SPREAD_DEFAULT = 0.00057    # mediana misurata sui 57 mercati
SPLIT = 0.6                 # 60% per scegliere i parametri, 40% per misurare
TARGET_VOL = 0.20

QUI = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------
# DATI
# --------------------------------------------------------------------------
def carica():
    files = sorted(glob.glob(os.path.join(QUI, "dati", "*.pkl")))
    D = {os.path.basename(f)[:-4]: pd.read_pickle(f) for f in files}

    # Solo il periodo in cui il funding reale esiste per tutti.
    start = max(d["funding"].first_valid_index()
                for d in D.values() if d["funding"].notna().any())
    D = {k: v.loc[start:] for k, v in D.items()}
    D = {k: v for k, v in D.items()
         if len(v) > 250 and v["funding"].notna().mean() > 0.9}

    chiudi = pd.DataFrame({k: v["close"] for k, v in D.items()}).sort_index()
    fund = pd.DataFrame({k: v["funding"] for k, v in D.items()}).sort_index()
    return chiudi, fund.reindex_like(chiudi).fillna(0.0), start


def costi_per_mercato(mercati):
    """
    Costo per unita' di turnover: commissione + meta' spread.

    Meta' spread perche' attraversare il book dal mid all'ask costa meta'
    dello spread denaro-lettera, e un giro completo ne paga due meta'.
    """
    try:
        with open(os.path.join(QUI, "spread.json")) as f:
            sp = json.load(f)
    except Exception:
        sp = {}
    return pd.Series({m: FUT_TAKER + sp.get(m, SPREAD_DEFAULT) / 2
                      for m in mercati})


# --------------------------------------------------------------------------
# SEGNALI
# --------------------------------------------------------------------------
def _normalizza(pesi):
    """Porta l'esposizione lorda a 1, cosi' le strategie sono confrontabili."""
    lordo = pesi.abs().sum(axis=1).replace(0, np.nan)
    return pesi.div(lordo, axis=0).fillna(0.0)


def ts_momentum(chiudi, fund, n):
    """Time-series: ogni mercato guarda il proprio rendimento a n giorni."""
    return _normalizza(np.sign(chiudi.pct_change(n)).fillna(0.0))


def ts_carry(chiudi, fund, n):
    """Time-series: short dove il funding e' positivo."""
    return _normalizza(-np.sign(fund.rolling(n).mean()).fillna(0.0))


def _tercili(punteggio, frazione=1 / 3):
    """
    Long il tercile alto, short quello basso, esposizione netta zero.

    Neutrale al mercato PER COSTRUZIONE: qualunque cosa faccia il mercato nel
    suo insieme, questo portafoglio non ci scommette sopra.
    """
    valido = punteggio.notna().sum(axis=1) >= 6
    r = punteggio.rank(axis=1, pct=True)
    lungo = (r > 1 - frazione).astype(float)
    corto = (r < frazione).astype(float)
    nl = lungo.sum(axis=1).replace(0, np.nan)
    nc = corto.sum(axis=1).replace(0, np.nan)
    pesi = (lungo.div(nl, axis=0) - corto.div(nc, axis=0)).fillna(0.0)
    return pesi.mul(valido.astype(float), axis=0) * 0.5


def xs_momentum(chiudi, fund, n):
    """Cross-sectional: long i vincitori, short i perdenti, fra loro."""
    return _tercili(chiudi.pct_change(n))


def xs_carry(chiudi, fund, n):
    """
    Cross-sectional: short dove il funding e' piu' alto, long dove e' piu'
    basso. E' l'ipotesi di TEST_PERPETUI.md — posizionamento affollato,
    rendimenti futuri peggiori — testata senza la componente direzionale.
    """
    return _tercili(-fund.rolling(n).mean())


def xs_carry_freno(chiudi, fund, n, soglia=1.0):
    """
    Come xs_carry, ma classifica SOLO i mercati con funding a un estremo.

    Attacca direttamente il costo: la scomposizione del carry mostrava −2,0%
    annuo di commissioni, ed e' la voce che si mangia il risultato.

    NOTA SU UN BUG GIA' FATTO QUI: la prima versione filtrava i mercati e poi
    rinormalizzava i pesi. Rinormalizzare dopo il filtro distrugge la
    neutralita' (esposizione netta salita a +0,22) e concentra il libro su
    6 mercati con pesi fino al 13%. Il risultato era un +129,6% annuo che era
    tutto concentrazione e direzione, non segnale. Mascherare PRIMA del
    ranking, come si fa qui, mantiene i terzili neutrali.
    """
    f = fund.rolling(n).mean()
    z = f.sub(f.mean(axis=1), axis=0).div(f.std(axis=1).replace(0, np.nan), axis=0)
    estremo = f.where(z.abs() > soglia)      # NaN altrove: non entra nel ranking
    return _tercili(-estremo)


def ts_momentum_multi(chiudi, fund, n):
    """
    Media dei segnali su piu' orizzonti invece di sceglierne uno.

    Non e' un'idea nuova: e' una riduzione del rischio di aver pescato il
    parametro fortunato, che con due anni di dati e' un rischio serio.
    """
    orizzonti = [max(5, n // 3), n, n * 2]
    s = sum(np.sign(chiudi.pct_change(o)).fillna(0.0) for o in orizzonti)
    return _normalizza(s / len(orizzonti))


STRATEGIE = {
    "ts_momentum":      (ts_momentum,       [10, 20, 30, 60, 90, 120]),
    "ts_carry":         (ts_carry,          [3, 7, 14, 30]),
    "xs_momentum":      (xs_momentum,       [10, 20, 30, 60, 90, 120]),
    "xs_carry":         (xs_carry,          [3, 7, 14, 30]),
    "xs_carry_freno":   (xs_carry_freno,    [3, 7, 14, 30]),
    "ts_momentum_multi": (ts_momentum_multi, [10, 20, 30, 60]),
}


# --------------------------------------------------------------------------
# RENDIMENTI E METRICHE
# --------------------------------------------------------------------------
def rendimenti(pesi, chiudi, fund, costo, con_costi=True):
    """
    Rendimento giornaliero del portafoglio.

    I pesi sono ritardati di un giorno: la posizione di oggi si decide con i
    dati di ieri. Senza questo si sta guardando il futuro.
    """
    held = pesi.shift(1).fillna(0.0)
    ret = chiudi.pct_change().fillna(0.0)
    lordo = (held * ret).sum(axis=1) - (held * fund).sum(axis=1)
    if not con_costi:
        return lordo, pd.Series(0.0, index=lordo.index)
    turn = (held - held.shift(1)).abs().fillna(held.abs())
    spesa = turn.mul(costo, axis=1).sum(axis=1)
    return lordo - spesa, spesa


def metriche(r):
    r = r.dropna()
    if len(r) < 10 or r.std() == 0:
        return dict(ann=0.0, sharpe=0.0, dd=0.0, tot=0.0)
    eq = (1 + r).cumprod()
    return dict(ann=float(r.mean() * 365),
                sharpe=float(r.mean() / r.std() * np.sqrt(365)),
                dd=float((eq / eq.cummax() - 1).min()),
                tot=float(eq.iloc[-1] - 1))


def bootstrap_sharpe(r, n_blocchi=12, n_camp=3000, seme=0):
    """
    Intervallo di confidenza sullo Sharpe, a blocchi.

    A blocchi e non a estrazioni indipendenti perche' i rendimenti sono
    autocorrelati: ricampionare giorno per giorno spezzerebbe la struttura
    temporale e restituirebbe un intervallo troppo stretto, cioe' una
    sicurezza che non abbiamo.
    """
    x = np.asarray(r.dropna(), dtype=float)
    if len(x) < 30 or x.std() == 0:
        return (float("nan"), float("nan"))
    L = max(2, len(x) // n_blocchi)
    nb = int(np.ceil(len(x) / L))
    rng = np.random.default_rng(seme)
    out = np.empty(n_camp)
    for i in range(n_camp):
        idx = rng.integers(0, len(x) - L + 1, nb)
        c = np.concatenate([x[j:j + L] for j in idx])[:len(x)]
        sd = c.std()
        out[i] = c.mean() / sd * np.sqrt(365) if sd > 0 else 0.0
    return tuple(np.percentile(out, [2.5, 97.5]))


# --------------------------------------------------------------------------
def main():
    chiudi, fund, start = carica()
    costo = costi_per_mercato(chiudi.columns)
    taglio = int(len(chiudi) * SPLIT)
    print(f"{chiudi.shape[1]} mercati · {len(chiudi)} giorni · dal {start.date()}")
    print(f"costo per unita' di turnover: mediana {costo.median()*100:.4f}% "
          f"(commissione {FUT_TAKER*100:.3f}% + meta' spread)")
    print(f"in campione: {taglio} giorni · fuori campione: {len(chiudi)-taglio} giorni")
    print()

    print("=" * 92)
    print("WALK-FORWARD — parametro scelto sul 60%, misurato sul 40% mai visto")
    print("=" * 92)
    print(f"{'strategia':<20}{'n':>4}{'rend.ann':>10}{'Sharpe':>8}"
          f"{'IC 95% (bootstrap)':>22}{'maxDD':>8}{'turnov.':>9}{'costi/anno':>11}")
    print("-" * 92)

    risultati = {}
    for nome, (f, griglia) in STRATEGIE.items():
        # --- scelta del parametro SOLO sul primo 60%
        migliore, punteggio_migliore = griglia[0], -99.0
        for n in griglia:
            pesi = f(chiudi, fund, n)
            r, _ = rendimenti(pesi.iloc[:taglio], chiudi.iloc[:taglio],
                              fund.iloc[:taglio], costo)
            s = metriche(r)["sharpe"]
            if s > punteggio_migliore:
                migliore, punteggio_migliore = n, s

        # --- misura sul 40% restante
        pesi = f(chiudi, fund, migliore)
        r, spesa = rendimenti(pesi.iloc[taglio:], chiudi.iloc[taglio:],
                              fund.iloc[taglio:], costo)
        m = metriche(r)
        lo, hi = bootstrap_sharpe(r)
        held = pesi.iloc[taglio:].shift(1).fillna(0.0)
        turnover = float((held - held.shift(1)).abs().sum(axis=1).mean())
        costo_anno = float(spesa.mean() * 365)
        risultati[nome] = dict(n=migliore, lo=lo, hi=hi, r=r,
                               turnover=turnover, costo=costo_anno, **m)

        print(f"{nome:<20}{migliore:>4}{m['ann']:>+9.1%}{m['sharpe']:>+8.2f}"
              f"{f'[{lo:+.2f}, {hi:+.2f}]':>22}{m['dd']:>+8.1%}"
              f"{turnover:>9.3f}{costo_anno:>+10.2%}")

    # ----------------------------------------------------------------------
    print()
    print("=" * 92)
    print("QUANTO PESANO I COSTI — stessa strategia, con e senza")
    print("=" * 92)
    print(f"{'strategia':<20}{'Sharpe lordo':>14}{'Sharpe netto':>14}{'differenza':>13}")
    print("-" * 92)
    for nome, (f, _) in STRATEGIE.items():
        n = risultati[nome]["n"]
        pesi = f(chiudi, fund, n)
        lordo, _ = rendimenti(pesi.iloc[taglio:], chiudi.iloc[taglio:],
                              fund.iloc[taglio:], costo, con_costi=False)
        sl = metriche(lordo)["sharpe"]
        sn = risultati[nome]["sharpe"]
        print(f"{nome:<20}{sl:>+14.2f}{sn:>+14.2f}{sn-sl:>+13.2f}")

    # ----------------------------------------------------------------------
    # La verifica che smonta i risultati buoni. Va fatta SEMPRE, e non e'
    # opzionale: un risultato che dipende da pochi giorni non e' una strategia,
    # e' una manciata di eventi fortunati che non si ripeteranno su richiesta.
    print()
    print("=" * 92)
    print("ROBUSTEZZA — il risultato regge senza i giorni migliori?")
    print("=" * 92)
    print(f"{'strategia':<20}{'totale':>10}{'-1 gg':>10}{'-3 gg':>10}"
          f"{'-5 gg':>10}{'-10 gg':>10}{'gg +':>7}{'concentraz.':>13}")
    print("-" * 92)
    for nome, v in risultati.items():
        r = v["r"].dropna()
        tot = (1 + r).prod() - 1
        riga = f"{nome:<20}{tot:>+9.1%}"
        for k in (1, 3, 5, 10):
            senza = r.drop(r.nlargest(k).index)
            riga += f"{(1 + senza).prod() - 1:>+9.1%}"
        # quota del guadagno totale che arriva dai 5 giorni migliori
        top5 = r.nlargest(5).sum()
        quota = top5 / r.sum() if r.sum() != 0 else float("nan")
        riga += f"{(r > 0).mean():>6.0%}{quota:>12.0%}"
        print(riga)
    print()
    print("  'concentraz.' = quota del guadagno totale prodotta dai 5 giorni")
    print("  migliori. Sopra il 100% significa che senza quei 5 giorni la")
    print("  strategia perde: il resto del periodo e' in rosso.")

    # --- da quale mercato viene il guadagno?
    print()
    print("=" * 92)
    print("CONCENTRAZIONE PER MERCATO — un solo mercato regge tutto?")
    print("=" * 92)
    for nome, (f, _) in STRATEGIE.items():
        n = risultati[nome]["n"]
        pesi = f(chiudi, fund, n).iloc[taglio:]
        held = pesi.shift(1).fillna(0.0)
        ret = chiudi.iloc[taglio:].pct_change().fillna(0.0)
        pnl = (held * ret - held * fund.iloc[taglio:]).sum()
        primo = pnl.sort_values(ascending=False).head(3)
        tot = pnl.sum()
        etichette = ", ".join(
            f"{m.replace('PF_','').replace('USD','')} {v/tot*100:.0f}%"
            if tot != 0 else m for m, v in primo.items())
        print(f"  {nome:<20} i 3 mercati migliori valgono: {etichette}")

    # ----------------------------------------------------------------------
    # La prova che conta per un conto piccolo: il segnale sopravvive se si
    # tolgono i mercati illiquidi? Con 100 EUR non si va su MUBARAK, che ha
    # 1,28% di spread: il nozionale per posizione e' di pochi euro e il costo
    # di entrata e uscita si mangia qualunque margine.
    print()
    print("=" * 92)
    print("SOLO MERCATI LIQUIDI — spread sotto lo 0,10%")
    print("=" * 92)
    try:
        with open(os.path.join(QUI, "spread.json")) as fh:
            sp = json.load(fh)
    except Exception:
        sp = {}
    liquidi = [m for m in chiudi.columns if sp.get(m, SPREAD_DEFAULT) < 0.001]
    print(f"  {len(liquidi)} mercati su {chiudi.shape[1]} passano il filtro")
    if len(liquidi) >= 9:
        cl, fl = chiudi[liquidi], fund[liquidi]
        col = costo[liquidi]
        print(f"{'strategia':<20}{'rend.ann':>10}{'Sharpe':>9}"
              f"{'IC 95%':>22}{'-10 gg':>10}")
        print("-" * 92)
        for nome, (f, _) in STRATEGIE.items():
            n = risultati[nome]["n"]
            pesi = f(cl, fl, n)
            r, _ = rendimenti(pesi.iloc[taglio:], cl.iloc[taglio:],
                              fl.iloc[taglio:], col)
            r = r.dropna()
            m = metriche(r)
            lo, hi = bootstrap_sharpe(r)
            s10 = (1 + r.drop(r.nlargest(10).index)).prod() - 1
            print(f"{nome:<20}{m['ann']:>+9.1%}{m['sharpe']:>+9.2f}"
                  f"{f'[{lo:+.2f}, {hi:+.2f}]':>22}{s10:>+10.1%}")
    else:
        print("  troppo pochi mercati liquidi per un test cross-sectional")

    # ----------------------------------------------------------------------
    print()
    print("=" * 92)
    print("VERDETTO")
    print("=" * 92)
    k = len(STRATEGIE)
    print(f"Strategie provate: {k}. Con {k} test la soglia va corretta:")
    print(f"  un intervallo al 95% su un singolo test corrisponde a un "
          f"{100*(1-0.05/k):.1f}% con Bonferroni.")
    print("  In pratica: perche' un risultato conti, l'intervallo di confidenza")
    print("  deve stare LARGAMENTE sopra lo zero, non sfiorarlo.")
    print()
    # Una strategia passa solo se soddisfa TUTTE le condizioni: intervallo
    # sopra lo zero, e risultato che regge togliendo i 10 giorni migliori.
    # La seconda condizione e' quella che smaschera i risultati da lotteria.
    promosse = []
    for n, v in risultati.items():
        r = v["r"].dropna()
        senza10 = (1 + r.drop(r.nlargest(10).index)).prod() - 1
        if v["lo"] == v["lo"] and v["lo"] > 0 and senza10 > 0:
            promosse.append(n)
        elif v["lo"] == v["lo"] and v["lo"] > 0:
            print(f"  {n}: intervallo sopra zero [{v['lo']:+.2f}, {v['hi']:+.2f}], "
                  f"MA senza i 10 giorni migliori fa {senza10:+.1%}.")
            print(f"     Il risultato e' prodotto da pochi giorni: non e' un "
                  f"segnale, e' una manciata di eventi.")
    print()
    if promosse:
        for n in promosse:
            v = risultati[n]
            print(f"  {n}: IC [{v['lo']:+.2f}, {v['hi']:+.2f}], e regge anche "
                  f"senza i 10 giorni migliori.")
        print()
        print("  Anche cosi', questo NON dimostra che funzioni: dimostra che su")
        print("  questi giorni non ha perso. La prova vera si raccoglie in avanti,")
        print("  in paper, dove i dati non si possono ripescare.")
    else:
        print("  NESSUNA strategia supera entrambe le prove.")
        print("  E' un risultato onesto e utile: dice di non metterci soldi.")

    with open(os.path.join(QUI, "risultati_ricerca.json"), "w") as f:
        json.dump({n: {k2: v2 for k2, v2 in v.items() if k2 != "r"}
                   for n, v in risultati.items()}, f, indent=1)
    print()
    print("dettagli in perp_test/risultati_ricerca.json")


if __name__ == "__main__":
    main()
