# Backtest: sistema di trading a leva su Kraken

Test su 18 coppie EUR con margine abilitato, 721 candele daily
(19 ago 2024 → 9 ago 2026), costi Kraken reali inclusi.

## Metodo

- Segnale calcolato sulla chiusura di t, eseguito all'apertura di t+1 (no look-ahead)
- Fee: taker 0,40% per lato + apertura margine 0,02% + rollover 0,12%/giorno
- Walk-forward: parametri ottimizzati sul primo 60%, misurati sul restante 40% mai visto
- Universo multi-asset: niente cherry-picking della coppia fortunata
- Baseline di rumore: strategia casuale, per verificare che l'edge non sia caso

## Risultato principale

Nessuna delle 4 strategie (MA crossover, Donchian breakout, RSI mean reversion,
momentum) supera i criteri minimi out-of-sample, a nessun livello di leva,
né long-only né long+short.

## Il confondente, e perché non salva il risultato

La finestra di test è un bear market: mediana buy-and-hold **-54,9%**, mentre
il train era **+40,3%**. Le strategie long-only perdevano quindi a prescindere,
e il primo risultato da solo non provava nulla.

Test rifatto con short abilitati, e poi separando i due regimi. Verdetto:
a leva 3x le stesse strategie perdono **in entrambi i regimi** (bull -100%,
bear da -92% a -100%). Non è il mercato: è la leva.

## Il numero che conta davvero

Stessa identica strategia (momentum 60 giorni, long+short), cambia solo la leva:

| Leva | Ret. medio | Ret. mediano | Liquidati | Da 20 € a |
|------|-----------|--------------|-----------|-----------|
| 0,5x | -4,0% | -5,3% | 0% | 18,94 € |
| 1x | -12,0% | -15,4% | 0% | 16,93 € |
| 2x | -40,4% | -43,3% | 17% | 11,35 € |
| 3x | -74,5% | -84,0% | 44% | 3,20 € |
| 5x | -99,0% | -100,0% | 89% | 0,00 € |
| 7x | -100,0% | -100,0% | 100% | 0,00 € |
| 10x | -100,0% | -100,0% | 100% | 0,00 € |

A leva 5x con short, alcune configurazioni mostravano uno **Sharpe positivo**
(+0,35) con **rendimento mediano -100%** e 89% di conti azzerati.

Questo non è un bug: è il punto centrale. La media può essere positiva mentre
la mediana è -100%, perché **la liquidazione è assorbente**: da zero non si
torna indietro. La media descrive mille universi paralleli; tu ne vivi uno solo.
È lo stesso motivo per cui una scommessa con valore atteso positivo può
rovinarti con certezza se la ripeti abbastanza a lungo con size sbagliata.

## L'unica cosa che ha funzionato

A leva 1x, nel bear market:

- buy and hold: **-68,3%**
- momentum long+short: **-15,4%**

Il trend following ha ridotto la perdita di **53 punti percentuali**. Non ha
predetto nulla. Ha gestito il rischio, che è il suo vero mestiere. Chi lo vende
come "algoritmo di predizione" sta descrivendo male uno strumento di controllo
del drawdown.

## Limiti di questo studio

Da dire, altrimenti sto facendo io quello che critico:

- Solo 2 anni di dati (limite dell'endpoint pubblico Kraken: 720 candele)
- Solo candele daily
- 18 coppie correlate tra loro: il campione effettivo è più piccolo di quanto sembri
- 4 famiglie di strategie classiche, non esaustive
- Nessun test su timeframe intraday, order book, funding rate

Un risultato negativo su un campione limitato non dimostra che nessun edge
esista. Dimostra che **queste** strategie, su **questi** dati, al netto dei
costi reali, non ne hanno. Che è comunque l'informazione che serviva prima di
mettere soldi veri.

## File

- `backtest.py` — motore, strategie, modello di costi
- `run_backtest.py` — esegue la validazione walk-forward completa
- `risultati_backtest.csv` — risultati grezzi per strategia e leva

Per rieseguirlo sul tuo Mac:

```bash
pip3 install pandas numpy
python3 run_backtest.py
```
