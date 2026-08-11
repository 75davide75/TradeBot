# Analisi tecnica: testata sui dati, non discussa

## Primo: la stiamo già usando

Le quattro strategie che avevo testato nei primi giorni **sono** analisi
tecnica, e sono l'ossatura di qualunque manuale:

| Strategia | Come la chiamano i libri |
|---|---|
| MA crossover | Incrocio delle medie mobili |
| Donchian breakout | Rottura dei massimi (metodo Turtle Traders) |
| RSI mean reversion | Ipercomprato / ipervenduto |
| Momentum | Forza relativa, trend following |

Risultati: al netto dei costi, tutte tra il negativo e lo zero. Non erano
tecniche scelte a caso — sono le più diffuse e le più documentate.

## Secondo: cosa dice la ricerca accademica

Il verdetto è **misto, non negativo**. La rassegna di Park e Irwin conta
**56 studi su 95 con risultati positivi**. L'analisi tecnica risulta redditizia
nei mercati valutari e nei futures su materie prime; sulle azioni americane
funzionava fino a fine anni '80 e poi ha smesso.

Lo, Mamaysky e Wang (2000), studio del MIT, hanno testato i pattern grafici
classici — testa e spalle inclusa — trovando che **alcuni contengono
informazione incrementale su grandi campioni**, ma con la profittabilità che
dipende interamente da costi e implementazione.

L'avvertenza che ricorre in tutta la letteratura è il **data snooping**: se
provi cento pattern, cinque risulteranno significativi per puro caso.

## Terzo: li ho testati

Otto pattern a candela classici, 15 mercati crypto, 721 giorni ciascuno,
oltre 10.000 osservazioni di controllo.

| Pattern | Casi | Rendimento il giorno dopo | p-value | |
|---|---|---|---|---|
| (nessun pattern) | 10.800 | +0,019% | — | riferimento |
| Engulfing rialzista | 605 | +0,283% | 0,226 | rumore |
| **Engulfing ribassista** | 729 | **−0,496%** | **0,000** | significativo |
| **Martello** | 474 | **−0,589%** | **0,002** | significativo |
| Stella cadente | 432 | +0,010% | 0,954 | rumore |
| Doji | 550 | +0,102% | 0,624 | rumore |
| Tre soldati bianchi | 1.118 | −0,041% | 0,669 | rumore |
| **Tre corvi neri** | 1.408 | **+0,383%** | **0,001** | significativo |
| Harami rialzista | 621 | +0,051% | 0,840 | rumore |

Soglia corretta per test multipli (Bonferroni, 8 test): p < 0,00625. Tre
pattern la superano.

### E due su tre funzionano al contrario del manuale

- **Martello** — i libri lo insegnano come segnale di **inversione rialzista**.
  Nei dati dà **−0,589%**: ribassista.
- **Tre corvi neri** — insegnato come segnale **ribassista**. Nei dati dà
  **+0,383%**: rialzista.
- **Engulfing ribassista** — questo sì, ribassista come previsto.

Chi avesse operato secondo il manuale su due di questi tre avrebbe sistemati­
camente sbagliato direzione.

### Il controllo che serviva

L'effetto poteva venire non dal pattern ma dal movimento che lo precede: un
martello si forma dopo una discesa, e magari è la discesa a predire, non la
candela. Ho confrontato i giorni col pattern contro giorni **senza** pattern ma
con lo stesso movimento nei tre giorni precedenti (stesso decile):

| Pattern | Con pattern | Stesso contesto, senza pattern | Differenza | p |
|---|---|---|---|---|
| Engulfing ribassista | −0,496% | +0,047% | **−0,543%** | 0,000 |
| Martello | −0,594% | +0,038% | **−0,633%** | 0,002 |
| Tre corvi neri | +0,383% | −0,045% | **+0,429%** | 0,000 |

**Il pattern aggiunge informazione oltre il contesto.** Tutti e tre reggono. È
il risultato più solido che l'analisi tecnica abbia prodotto nei nostri test.

## Quarto: e poi muore, come sempre

| Pattern | Effetto | Costo andata+ritorno | Netto |
|---|---|---|---|
| Engulfing ribassista | 0,543% | 0,80% | **−0,257%** |
| Martello | 0,633% | 0,80% | **−0,167%** |
| Tre corvi neri | 0,429% | 0,80% | **−0,371%** |

**Nessuno dei tre supera il costo di una singola operazione.**

L'effetto è reale, statisticamente solido, e più piccolo della commissione che
pagheresti per sfruttarlo. È la quarta volta in questo progetto che troviamo
esattamente questa forma: un segnale vero, sepolto sotto i costi di
transazione.

## Cosa ne ricaviamo

**L'analisi tecnica non è superstizione.** Tre pattern su otto contengono
informazione statistica genuina, verificata contro un controllo serio. Chi la
liquida come astrologia sta sbagliando quanto chi la vende come una macchina
per fare soldi.

**Ma due su tre insegnano la direzione sbagliata.** Il che dice qualcosa sul
metodo con cui quei manuali sono stati scritti: osservazione a occhio su
campioni piccoli, senza controlli e senza test statistici.

**E l'effetto è più piccolo dei costi.** Con commissioni istituzionali (0,02%
invece di 0,40%) i tre pattern diventerebbero sfruttabili. È di nuovo la stessa
barriera del funding rate arbitrage: l'edge esiste ed è fuori portata per
struttura, non per bravura.

---

*15 mercati, 721 giorni, 8 pattern, oltre 10.000 osservazioni di controllo.
Correzione di Bonferroni applicata. Controllo sul contesto per decili del
movimento precedente.*

### Fonti

- Park, Irwin, *The Profitability of Technical Analysis: A Review*, AgMAS Project Research Report
- Lo, Mamaysky, Wang (2000), *Foundations of Technical Analysis*, NBER Working Paper 7613
