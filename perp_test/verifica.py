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

print('=== DECOMPOSIZIONE: da dove viene il guadagno? ===')
print('La strategia carry va SHORT quando il funding e positivo. Quindi incassa')
print('il funding MA prende anche esposizione direzionale. Separo le due cose.')
print()
pz,fd,cs=[],[],[]
for m,df in D.items():
    held=(carry(df)*vt(df)).shift(1).fillna(0)
    turn=held.diff().abs().fillna(held.abs())
    pz.append(held*df['close'].pct_change().fillna(0))     # componente PREZZO
    fd.append(-held*df['funding'].fillna(0))               # componente FUNDING
    cs.append(-turn*FUT)                                   # commissioni
P=pd.concat(pz,axis=1).mean(axis=1); F=pd.concat(fd,axis=1).mean(axis=1); C=pd.concat(cs,axis=1).mean(axis=1)
oos=slice(int(len(P)*0.6),None)
for nome,s in [('prezzo (direzionale)',P),('funding (incassato)',F),('commissioni',C)]:
    x=s.iloc[oos]
    print(f'  {nome:24} {x.sum()*100:+7.2f}%   annualizzato {x.mean()*365*100:+7.1f}%')
tot=(P+F+C).iloc[oos]
print(f'  {"TOTALE":24} {tot.sum()*100:+7.2f}%   Sharpe {tot.mean()/tot.std()*np.sqrt(365):+.2f}')
print()
q=P.iloc[oos].sum()/(P.iloc[oos].sum()+F.iloc[oos].sum())
print(f'  Quota del risultato dovuta alla DIREZIONE del prezzo: {q:.0%}')
print()
print('=== IL TEST CHE CONTA: era solo un bear market? ===')
mkt=pd.concat([d['close'].pct_change() for d in D.values()],axis=1).mean(axis=1)
print(f'  mercato medio nel periodo OOS: {mkt.iloc[oos].sum()*100:+.1f}%')
print(f'  se il mercato scende e tu sei short, guadagni comunque.')
print()
print('=== VERSIONE DELTA-NEUTRAL: isolo il solo funding ===')
print('(incasso il funding SENZA prendere esposizione: e il vero arbitraggio)')
dn=(F+C).iloc[oos]
print(f'  rendimento OOS {dn.sum()*100:+.2f}%   annualizzato {dn.mean()*365*100:+.1f}%   Sharpe {dn.mean()/dn.std()*np.sqrt(365):+.2f}')
print()
print('=== SIGNIFICATIVITA: 111 giorni bastano? ===')
n=len(tot); sh=tot.mean()/tot.std()*np.sqrt(365)
err=np.sqrt((1+sh**2/2)/n)*np.sqrt(365)
print(f'  Sharpe stimato {sh:+.2f}  ±  {1.96*err:.2f}  (intervallo 95%)')
print(f'  intervallo: da {sh-1.96*err:+.2f} a {sh+1.96*err:+.2f}')
if sh-1.96*err>0: print('  -> significativo, ma su un campione corto e un solo regime')
else: print('  -> NON distinguibile da zero')
