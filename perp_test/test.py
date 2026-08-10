import glob, os
import numpy as np, pandas as pd

FUT_TAKER = 0.0005          # Kraken futures, fascia retail
files = sorted(glob.glob('dati/*.pkl'))
D = {os.path.basename(f)[:-4]: pd.read_pickle(f) for f in files}

# uso solo il periodo in cui esiste il funding reale
start = max(d['funding'].first_valid_index() for d in D.values() if d['funding'].notna().any())
D = {k: v.loc[start:] for k, v in D.items()}
D = {k: v for k, v in D.items() if len(v) > 250 and v['funding'].notna().mean() > 0.9}
n_gg = len(list(D.values())[0])
print(f'{len(D)} mercati · {n_gg} giorni · dal {start.date()}')
print()

def segnale(df, n, tipo='mom'):
    if tipo == 'mom':
        return np.sign(df['close'].pct_change(n)).fillna(0)
    if tipo == 'don':
        hi = df['high'].rolling(n).max().shift(1)
        lo = df['low'].rolling(n).min().shift(1)
        s = pd.Series(np.nan, index=df.index)
        s[df['close'] > hi] = 1.0
        s[df['close'] < lo] = -1.0
        return s.ffill().fillna(0)
    if tipo == 'carry':          # posizione dettata dal funding: short se positivo
        f = df['funding'].rolling(n).mean()
        return (-np.sign(f)).fillna(0)

def voltarget(df, target=0.20, look=30, cap=2.0):
    rv = df['close'].pct_change().rolling(look).std() * np.sqrt(365)
    return (target / rv).clip(0.25, cap).fillna(0.5)

def rendimenti(df, pos, lev):
    """Serie dei rendimenti netti giornalieri di un singolo mercato."""
    held = pos.shift(1).fillna(0) * lev.shift(1).fillna(0)
    ret = df['close'].pct_change().fillna(0)
    turn = held.diff().abs().fillna(held.abs())
    fund = df['funding'].fillna(0)
    return held * ret - turn * FUT_TAKER - held * fund

def portafoglio(mercati, tipo, n, split=0.6, solo_test=True):
    """Portafoglio equipesato. Restituisce la serie dei rendimenti."""
    serie = []
    for m in mercati:
        df = D[m]
        pos = segnale(df, n, tipo)
        lev = voltarget(df)
        r = rendimenti(df, pos, lev)
        if solo_test:
            r = r.iloc[int(len(r) * split):]
        serie.append(r)
    return pd.concat(serie, axis=1).mean(axis=1)

def metriche(r):
    eq = (1 + r).cumprod()
    ann = r.mean() * 365
    sh = r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0
    dd = float((eq / eq.cummax() - 1).min())
    return ann, sh, dd, float(eq.iloc[-1] - 1)

print('=== WALK-FORWARD: parametro scelto sul 60%, misurato sul 40% ===')
print()
tutti = list(D)
print('  segnale   miglior n   rend.ann OOS   Sharpe OOS   maxDD    totale OOS')
print('  ' + '-'*68)
best_overall = None
for tipo, griglia in [('mom',[10,20,30,60,90,120]), ('don',[10,20,30,55]), ('carry',[3,7,14,30])]:
    # ottimizzo su TRAIN
    punteggi = {}
    for n in griglia:
        serie = []
        for m in tutti:
            r = rendimenti(D[m], segnale(D[m],n,tipo), voltarget(D[m]))
            serie.append(r.iloc[:int(len(r)*0.6)])
        rp = pd.concat(serie,axis=1).mean(axis=1)
        punteggi[n] = rp.mean()/rp.std()*np.sqrt(365) if rp.std()>0 else -9
    n_best = max(punteggi, key=punteggi.get)
    rp = portafoglio(tutti, tipo, n_best)
    a,s,dd,tot = metriche(rp)
    print(f'  {tipo:8}  {n_best:>7}     {a:>+9.1%}    {s:>+8.2f}   {dd:>7.1%}   {tot:>+9.1%}')
    if best_overall is None or s > best_overall[1]: best_overall=(tipo,s,n_best)
print()
print(f'  giorni out-of-sample: {int(n_gg*0.4)}')
