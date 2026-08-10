import json, os, time, urllib.request
import pandas as pd

SEL = json.load(open('universo.json'))

def get(url, tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=45) as r:
                return json.load(r)
        except Exception:
            time.sleep(2)
    return None

os.makedirs('dati', exist_ok=True)
ok = 0
for s in SEL:
    f = f'dati/{s}.pkl'
    if os.path.exists(f):
        ok += 1
        continue
    c = get(f'https://futures.kraken.com/api/charts/v1/trade/{s}/1d?from=1690000000')
    fu = get(f'https://futures.kraken.com/derivatives/api/v4/historicalfundingrates?symbol={s}')
    if not c or not c.get('candles') or not fu or not fu.get('rates'):
        continue
    px = pd.DataFrame(c['candles'])
    px['t'] = pd.to_datetime(px['time'], unit='ms')
    for col in ['open','high','low','close','volume']:
        px[col] = px[col].astype(float)
    px = px.set_index('t')[['open','high','low','close','volume']]

    fd = pd.DataFrame(fu['rates'])
    fd['t'] = pd.to_datetime(fd['timestamp']).dt.tz_localize(None)
    fd = fd.set_index('t')['relativeFundingRate'].resample('1D').sum()

    df = px.join(fd.rename('funding'), how='left')
    if len(df) < 200:
        continue
    df.to_pickle(f)
    ok += 1
    time.sleep(0.25)

print(f'scaricati {ok} mercati su {len(SEL)}')
