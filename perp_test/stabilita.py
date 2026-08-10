import glob, os
import numpy as np, pandas as pd
FUT=0.0005
files=sorted(glob.glob('dati/*.pkl'))
D={os.path.basename(f)[:-4]: pd.read_pickle(f) for f in files}
start=max(d['funding'].first_valid_index() for d in D.values() if d['funding'].notna().any())
D={k:v.loc[start:] for k,v in D.items()}
D={k:v for k,v in D.items() if len(v)>250 and v['funding'].notna().mean()>0.9}

def carry(df,n=3): return (-np.sign(df['funding'].rolling(n).mean())).fillna(0)
def vt(df,t=0.20,l=30,c=2.0):
    rv=df['close'].pct_change().rolling(l).std()*np.sqrt(365)
    return (t/rv).clip(0.25,c).fillna(0.5)

serie=[]
for m,df in D.items():
    held=(carry(df)*vt(df)).shift(1).fillna(0)
    turn=held.diff().abs().fillna(held.abs())
    serie.append(held*df['close'].pct_change().fillna(0) - held*df['funding'].fillna(0) - turn*FUT)
R=pd.concat(serie,axis=1).mean(axis=1)

print('=== STABILITA NEL TEMPO: funziona in tutti i sotto-periodi? ===')
print('(un edge vero e stabile; un caso fortunato si concentra in un tratto)')
print()
k=6; blocchi=np.array_split(np.arange(len(R)), k)
pos=0
print('   periodo        giorni   rendimento   Sharpe')
print('   '+'-'*46)
for i,b in enumerate(blocchi,1):
    x=R.iloc[b]
    sh=x.mean()/x.std()*np.sqrt(365) if x.std()>0 else 0
    if x.sum()>0: pos+=1
    print(f'   blocco {i}       {len(b):>4}     {x.sum()*100:>+7.2f}%   {sh:>+6.2f}')
print()
print(f'   sotto-periodi in guadagno: {pos}/{k}')
print()

print('=== TEST CROSS-SECTIONALE: il funding predice il rendimento futuro? ===')
print('(uso tutti i mercati-giorno insieme: molta piu potenza statistica)')
print()
righe=[]
for m,df in D.items():
    f=df['funding'].rolling(3).mean()
    r_fwd=df['close'].pct_change().shift(-1)
    righe.append(pd.DataFrame({'funding':f,'ret_dopo':r_fwd,'mkt':m}).dropna())
X=pd.concat(righe)
print(f'   osservazioni mercato-giorno: {len(X):,}')
q=pd.qcut(X['funding'],5,labels=['piu basso','basso','medio','alto','piu alto'])
g=X.groupby(q,observed=True)['ret_dopo'].agg(['mean','count'])
print()
print('   quintile di funding   rend. medio giorno dopo   annualizzato')
print('   '+'-'*58)
for nome,row in g.iterrows():
    print(f'   {str(nome):20} {row["mean"]*100:>+9.3f}%              {row["mean"]*365*100:>+7.1f}%')
lo=g.loc['piu basso','mean']; hi=g.loc['piu alto','mean']
print()
print(f'   spread (basso - alto): {(lo-hi)*100:+.3f}% al giorno = {(lo-hi)*365*100:+.1f}% annuo')
from scipy import stats
a=X[q=='piu basso']['ret_dopo']; b=X[q=='piu alto']['ret_dopo']
t,p=stats.ttest_ind(a,b,equal_var=False)
print(f'   t-statistic {t:.2f}   p-value {p:.4f}')
print(f'   -> {"SIGNIFICATIVO" if p<0.05 else "non significativo"} al 5%')
print()
print('   NB: i mercati crypto sono fortemente correlati, quindi le osservazioni')
print('   NON sono indipendenti. Il vero numero di scommesse indipendenti e molto')
print('   piu basso di {:,} e questo t-stat e ottimista.'.format(len(X)))
