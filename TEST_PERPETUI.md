# Test rigoroso sui futures perpetui — 57 mercati

Il test serio che avevo promesso. Dati: **57 mercati perpetui Kraken**, prezzi
giornalieri e **funding rate reali giorno per giorno**, commissioni futures
effettive (0,05%), volatility targeting, walk-forward out-of-sample.

Questa volta l'ampiezza c'è: 57 mercati invece di 3.

## Il risultato grezzo

Walk-forward, parametro scelto sul primo 60% e misurato sul restante 40%:

| Segnale | Rendimento annuo OOS | Sharpe OOS | Max DD |
|---|---|---|---|
| Momentum | +0,7% | +0,08 | −3,4% |
| Donchian breakout | −1,0% | −0,11 | −6,2% |
| **Carry (funding)** | **+16,1%** | **+2,57** | −2,2% |

Il momentum, che sullo spot a margine perdeva, qui va a zero: **il rollover al
44% annuo era davvero tutto il problema.** Confermato.

E poi c'è il carry, con Sharpe 2,57. Ed è qui che il lavoro comincia davvero,
perché un numero così va smontato prima di essere creduto.

## Smontaggio 1 — da dove viene il guadagno?

La strategia carry va short quando il funding è positivo. Incassa il funding,
ma prende anche **esposizione direzionale**. Non sono la stessa cosa.

| Componente | Contributo OOS | Annualizzato |
|---|---|---|
| Prezzo (direzionale) | +3,46% | +11,3% |
| Funding (incassato) | +2,10% | +6,9% |
| Commissioni | −0,63% | −2,0% |
| **Totale** | **+4,94%** | |

**Il 62% del risultato viene dalla direzione del prezzo, non dal funding.**
Non è arbitraggio: è una scommessa direzionale con un incasso accessorio.

Il che non la rende falsa — c'è un'ipotesi sensata dietro. Funding molto
positivo significa long affollati, cioè posizionamento euforico, che
storicamente precede rendimenti peggiori. È un indicatore di sentiment, non un
premio risk-free.

## Smontaggio 2 — era solo un mercato che scendeva?

No, e questo è a favore del segnale: nel periodo di test **il mercato medio
era +2,8%**, quindi la strategia non stava semplicemente cavalcando un ribasso
stando short su tutto. Andava short i mercati con funding alto e long quelli
con funding negativo: è un effetto trasversale, non direzionale sul mercato.

## Smontaggio 3 — la versione delta-neutral

Isolando il solo funding: +4,8% annuo, Sharpe 13,93.

**Quel Sharpe è un artefatto e non va creduto.** L'ho ottenuto rimuovendo la
componente prezzo per costruzione, non coprendola davvero. Un delta-neutral
reale richiede la gamba spot, con commissioni spot (0,40%, non 0,05%) — ed è
esattamente il conto che avevamo già fatto: **+2,87% netto**, quanto un conto
deposito.

## Smontaggio 4 — il test che decide

Sharpe stimato **+2,57**, errore standard su 111 giorni:

> **intervallo di confidenza al 95%: da −4,77 a +9,92**

**Non distinguibile da zero.**

Stabilità nei sotto-periodi: **4 blocchi su 6 in guadagno**, con un blocco a
−2,83% e Sharpe −2,50. Un edge solido è stabile; questo alterna.

Test trasversale su 15.675 osservazioni mercato-giorno: lo spread tra funding
basso e funding alto è +46,5% annuo, ma **t-statistic 0,78, p-value 0,44 —
non significativo.** E quel test è pure ottimista, perché i mercati crypto sono
fortemente correlati e le osservazioni non sono indipendenti: le scommesse
realmente indipendenti sono molte meno di 15.675.

## Verdetto

**C'è un'ipotesi interessante e non c'è la prova.**

Il segnale carry ha una logica economica sensata, un meccanismo plausibile
(posizionamento affollato → rendimenti futuri peggiori), e numeri che nella
direzione giusta. Ma con 111 giorni di dati fuori campione l'intervallo di
confidenza contiene lo zero con ampio margine, e non c'è modo di stringerlo:
l'API Kraken pubblica solo ~368 giorni di storico funding.

Sarebbe facile, a questo punto, mostrarti il +16,1% annuo e Sharpe 2,57 e
chiamarla una scoperta. Sono numeri veri, ottenuti onestamente, walk-forward.
Ma un intervallo che va da −4,77 a +9,92 significa che quei numeri sono
compatibili con una strategia che perde.

**Quello che sappiamo con certezza dopo questo test:**

- il rollover del margine era il vero killer, e i perpetui lo eliminano — questo
  è solido e replicato su 57 mercati
- momentum sui perpetui va circa a zero: non perde più, non guadagna
- il carry merita di essere osservato in paper, non di essere creduto

## Cosa farei adesso

Aggiungere il segnale carry al bot **in paper, in parallelo** a quello
esistente, e lasciarlo girare. Fra sei mesi avremo dati fuori campione veri,
raccolti in avanti, non ripescati dal passato — che è l'unico tipo di prova che
non si può curvare.

Non è la risposta veloce. È l'unica che non mente.

---

*57 mercati, 278 giorni con funding reale, 111 giorni out-of-sample. Codice in
`perp_test/`.*
