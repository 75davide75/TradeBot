# Ricerca: sei segnali, costi veri, nessun vincitore

Seguito di `TEST_PERPETUI.md`, che si chiudeva con "il carry merita di essere
osservato in paper, non di essere creduto". Questo test prova a stringere quel
verdetto, e lo stringe — nella direzione opposta a quella sperata.

Dati: 57 mercati perpetui Kraken, 279 giorni con funding reale, 112 giorni
out-of-sample. Codice in `perp_test/ricerca.py`.

## Cosa è cambiato nel metodo

**1. I costi erano sottostimati di circa metà.** `test.py` addebitava solo la
commissione (`turn * FUT_TAKER`, 0,05% per lato). Lo spread mancava. Misurato
sui 57 mercati: mediana **0,057%**, media **0,103%**, massimo **1,279%**
(MUBARAK). Il costo vero per giro sul mercato mediano è **0,157%**, non 0,10%.

**2. Il turnover ora è riportato.** Senza quel numero non si distingue una
strategia solida da una che vive di rendita lorda e muore di commissioni.

**3. Intervalli di confidenza con block bootstrap.** L'errore standard classico
presuppone osservazioni indipendenti; i rendimenti crypto sono autocorrelati e
correlati fra mercati, quindi restituiva intervalli troppo stretti.

**4. Segnali cross-sectional.** Tutti i segnali precedenti erano time-series:
ogni mercato guardava solo sé stesso, prendendo esposizione direzionale per
costruzione. È il difetto che `TEST_PERPETUI.md` aveva già diagnosticato ("il
62% del risultato viene dalla direzione del prezzo"). Le versioni
cross-sectional classificano i mercati fra loro: neutrali al mercato per
costruzione, non per sottrazione a posteriori.

## Risultati out-of-sample

| Segnale | Rend. annuo | Sharpe | IC 95% bootstrap | Turnover | Costi/anno |
|---|---|---|---|---|---|
| ts_momentum | −6,7% | −0,25 | [−3,02, +2,61] | 0,135 | 5,1% |
| ts_carry | +50,6% | +2,28 | [−1,11, +6,28] | 0,313 | 11,4% |
| xs_momentum | −3,2% | −0,13 | [−3,27, +2,78] | 0,190 | 8,3% |
| **xs_carry** | **+67,6%** | **+3,75** | **[+0,37, +7,30]** | 0,249 | 9,7% |
| xs_carry_freno | +30,5% | +0,87 | [−2,52, +5,20] | 0,190 | 16,3% |
| ts_momentum_multi | +2,0% | +0,06 | [−3,76, +3,56] | 0,345 | 12,9% |

Un solo candidato con l'intervallo sopra lo zero: `xs_carry`. Ed è lì che
comincia il lavoro vero.

## Smontaggio di `xs_carry`

### Prova 1 — regge senza i giorni migliori?

| | totale | −1 gg | −3 gg | −5 gg | −10 gg |
|---|---|---|---|---|---|
| xs_carry | +22,4% | +16,7% | +10,4% | +6,0% | **−1,0%** |

Su 112 giorni, **togliendone 10 il risultato diventa negativo**. Il 71% del
guadagno arriva da 5 giorni. Non è un segnale: è una manciata di eventi.

### Prova 2 — da dove vengono quei giorni?

I sei giorni-mercato con funding più estremo:

```
2026-07-22  DEXE   −18,62%   in un giorno
2026-07-23  DEXE   −16,79%
2026-07-21  DEXE   −11,11%
2026-07-26  DEXE   −10,43%
2026-08-07  ACE     −7,98%
2026-07-24  DEXE    −7,90%
```

Un singolo mercato illiquido, in una singola settimana. Il contributo per
mercato conferma: BICO 23%, ACE 10%, RIVER 9% — tutti nella coda illiquida.

### Prova 3 — sopravvive sull'universo negoziabile?

Con un conto piccolo non si opera su MUBARAK all'1,28% di spread. Filtrando ai
43 mercati con spread sotto lo 0,10%:

| Segnale | Rend. annuo | Sharpe | IC 95% | −10 gg |
|---|---|---|---|---|
| xs_carry | +33,4% | +2,74 | **[−0,71, +6,73]** | −3,4% |
| xs_carry_freno | +34,9% | +2,21 | [−3,22, +5,72] | −8,6% |
| ts_carry | +31,2% | +1,54 | [−1,53, +5,73] | −11,6% |

Sull'universo che si può davvero negoziare **l'intervallo torna a contenere lo
zero**. Il vantaggio apparente viveva nei mercati dove i costi reali lo
avrebbero mangiato.

## Un errore che ho fatto, e che vale la pena raccontare

La prima versione di `xs_carry_freno` dava **+129,6% annuo**. Sembrava la
scoperta della giornata. Era un bug: filtravo i mercati per funding estremo e
*poi* rinormalizzavo i pesi. Rinormalizzare dopo il filtro distrugge la
neutralità — l'esposizione netta era salita a +0,22 — e concentra il libro su
6 mercati con pesi fino al 13%. Quel rendimento era concentrazione e direzione,
non segnale.

Mascherando prima del ranking, come va fatto, la stessa strategia scende a
+30,5% con Sharpe 0,87 e intervallo che contiene lo zero.

Lo scrivo perché è il modo tipico in cui nascono le strategie miracolose: non
per disonestà, ma per un errore di costruzione che spinge il risultato nella
direzione che si sperava, dove nessuno lo va a controllare.

## Verdetto

**Nessuno dei sei segnali supera entrambe le prove** (intervallo sopra lo zero
*e* tenuta senza i 10 giorni migliori). Con sei test provati, la soglia andrebbe
pure corretta: un IC al 95% su un test singolo equivale a un 99,2% con
Bonferroni, e nessun candidato ci arriva neanche lontanamente.

Il momentum resta a zero, come già sapevamo. Il carry, in tutte e tre le
varianti provate, è compatibile con il caso una volta tolti i pochi giorni
anomali e i mercati che non si possono negoziare.

**Cosa sappiamo in più rispetto a prima:**

- i costi reali sono circa il doppio di quelli modellati, e su alcuni mercati
  dieci volte tanto
- il carry non diventa credibile passando alla versione cross-sectional: il
  problema non era la componente direzionale, era che il segnale vive di pochi
  eventi estremi su mercati illiquidi
- l'orizzonte di 112 giorni fuori campione non basta e non si può allungare:
  l'API Kraken pubblica ~368 giorni di storico funding

**Cosa resta da fare:** raccogliere dati in avanti, in paper. È l'unica prova
che non si può curvare, ed è la stessa conclusione di `TEST_PERPETUI.md` — ora
però con un motivo in più per non saltarla.

---

*57 mercati · 279 giorni · 112 out-of-sample · costi con spread reali per
mercato · block bootstrap · `perp_test/ricerca.py`*
