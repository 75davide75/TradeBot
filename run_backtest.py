#!/usr/bin/env python3
"""Esegue la validazione walk-forward su tutto l'universo e stampa il verdetto."""

import numpy as np
import pandas as pd

from backtest import (STRATEGIES, backtest, load_universe, s_buyhold,
                      s_random, walk_forward)

CAPITALE = 20.0
LEVE = [1, 3, 5, 10]

print("Scarico dati da Kraken (candele daily)...")
data = load_universe()
lens = [len(d) for d in data.values()]
print(f"  {len(data)} coppie, {min(lens)}-{max(lens)} candele "
      f"({min(lens)/365:.1f}-{max(lens)/365:.1f} anni)")
span = list(data.values())[0]
print(f"  periodo: {span.index[0].date()} -> {span.index[-1].date()}\n")

# ---------------------------------------------------------------- baseline
print("=" * 78)
print("BASELINE: cosa succede senza strategia")
print("=" * 78)
bh = [backtest(d, s_buyhold(d), 1.0, CAPITALE).total_return for d in data.values()]
print(f"Buy & hold, mediana su {len(data)} coppie: {np.median(bh):+.1%}")

rnd = []
for seed in range(30):
    for d in data.values():
        rnd.append(backtest(d, s_random(d, seed=seed), 5.0, CAPITALE).total_return)
print(f"Strategia CASUALE a leva 5x, mediana su {len(rnd)} run: {np.median(rnd):+.1%}")
print(f"  -> quota di run casuali che azzerano il conto: "
      f"{np.mean([r <= -0.95 for r in rnd]):.0%}")

# ------------------------------------------------------- walk-forward reale
print()
print("=" * 78)
print("WALK-FORWARD: parametri scelti sul 60% iniziale, misurati sul 40% finale")
print("=" * 78)

righe = []
for lev in LEVE:
    for nome in STRATEGIES:
        best, rows = walk_forward(data, nome, leverage=float(lev))
        if not rows:
            continue
        df = pd.DataFrame(rows)
        righe.append({
            "strategia": nome,
            "leva": f"{lev}x",
            "ret_mediano_OOS": df["ret"].median(),
            "sharpe_mediano": df["sharpe"].median(),
            "max_dd_mediano": df["max_dd"].median(),
            "%coppie_in_utile": (df["ret"] > 0).mean(),
            "%conti_azzerati": (df["final"] <= 0.01).mean(),
            "fee_pagate": df["fees"].mean(),
            "params": best,
        })

res = pd.DataFrame(righe)
pd.set_option("display.width", 200, "display.max_columns", 50)
print()
for lev in LEVE:
    sub = res[res["leva"] == f"{lev}x"]
    print(f"--- LEVA {lev}x ---")
    for _, r in sub.iterrows():
        print(f"  {r['strategia']:10} ret_OOS={r['ret_mediano_OOS']:+7.1%}  "
              f"sharpe={r['sharpe_mediano']:+5.2f}  maxDD={r['max_dd_mediano']:6.1%}  "
              f"in_utile={r['%coppie_in_utile']:.0%}  azzerati={r['%conti_azzerati']:.0%}")
    print()

# -------------------------------------------------------------- il verdetto
print("=" * 78)
print("VERDETTO")
print("=" * 78)

vincitrici = res[(res["sharpe_mediano"] > 0.5) & (res["ret_mediano_OOS"] > 0) &
                 (res["%coppie_in_utile"] > 0.6) & (res["%conti_azzerati"] < 0.1)]

if len(vincitrici) == 0:
    print("Nessuna strategia supera i criteri minimi out-of-sample.")
    print("Criteri richiesti: Sharpe>0.5, rendimento OOS>0, >60% delle coppie in")
    print("utile, <10% di conti azzerati.")
else:
    print(f"{len(vincitrici)} configurazioni superano i criteri minimi:")
    for _, r in vincitrici.iterrows():
        print(f"  {r['strategia']} @ {r['leva']} -> {r['ret_mediano_OOS']:+.1%} "
              f"OOS, sharpe {r['sharpe_mediano']:.2f}, params {r['params']}")

# --- la domanda che l'utente ha davvero fatto
print()
print("-" * 78)
print("DOMANDA ORIGINALE: 20 EUR -> 200 EUR (10x) in 7 giorni")
print("-" * 78)
best_row = res.loc[res["sharpe_mediano"].idxmax()]
print(f"Migliore configurazione trovata: {best_row['strategia']} @ {best_row['leva']}")
print(f"  rendimento mediano out-of-sample sul periodo intero: "
      f"{best_row['ret_mediano_OOS']:+.1%}")
n_giorni = int(np.median(lens) * 0.4)
print(f"  su un test di ~{n_giorni} giorni")
if best_row["ret_mediano_OOS"] > 0:
    daily = (1 + best_row["ret_mediano_OOS"]) ** (1 / n_giorni) - 1
    print(f"  = {daily:+.3%} al giorno composto")
    settimana = (1 + daily) ** 7 - 1
    print(f"  -> su 7 giorni: {settimana:+.2%}  (su 20 EUR = "
          f"{20 * (1 + settimana):.2f} EUR)")
    print(f"  servirebbe invece {(10 ** (1/7) - 1):+.1%} al giorno per fare 10x")
else:
    print("  negativo: il capitale si riduce, non si moltiplica")

res.to_csv("risultati_backtest.csv", index=False)
print("\nRisultati completi -> risultati_backtest.csv")
