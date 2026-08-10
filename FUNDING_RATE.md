# Funding rate arbitrage — l'edge esiste. Non è per te.

Analisi su **8.841 osservazioni orarie** dei funding rate dei perpetui Kraken,
un anno pieno (ago 2025 → ago 2026). Dati reali dall'API, nessuna stima.

## Come funziona

Sui futures perpetui c'è un pagamento periodico tra chi è long e chi è short,
il *funding rate*, che serve a tenere il prezzo del perpetuo agganciato allo
spot. Quando il mercato è ottimista i long pagano gli short.

L'arbitraggio: **compri spot e shortai il perpetuo per lo stesso importo**. Sei
delta-neutral — se il prezzo sale guadagni sullo spot e perdi sul perpetuo, e
viceversa — ma incassi il funding. Non è una scommessa direzionale, è la
raccolta di un premio strutturale.

## L'edge è reale

| Asset | Funding annualizzato | Ore positive |
|---|---|---|
| BTC | **+3,77%** | 72,0% |
| ETH | **+3,39%** | 69,1% |
| SOL | +0,14% | 55,5% |

Positivo il 72% delle ore su BTC. Non è rumore, è una struttura persistente:
sui perpetui crypto la domanda di leva long è cronicamente superiore a quella
short, e chi sta dall'altra parte viene pagato.

Questo è il primo edge documentato che troviamo in tutto il progetto.

## E qui muore

Costo di un giro completo (aprire e chiudere entrambe le gambe, fascia retail):

```
spot taker 0,40% × 2  +  futures taker 0,05% × 2  =  0,90%
```

Con un funding del 3,77% annuo, **servono 87 giorni di posizione aperta solo
per ripagare le commissioni.**

| Durata | Lordo | Netto | Annualizzato |
|---|---|---|---|
| 7 giorni | +0,07% | −0,83% | **−43,2%** |
| 30 giorni | +0,31% | −0,59% | −7,2% |
| 90 giorni | +0,93% | +0,03% | +0,1% |
| 365 giorni | +3,77% | +2,87% | **+2,87%** |

## "Ma se entro solo quando il funding è alto?"

È la prima idea che viene, ed è sbagliata — l'ho testata:

| Soglia d'ingresso | Tempo dentro | Funding medio | Netto annuo |
|---|---|---|---|
| sempre dentro | 100% | +3,77% | **+2,87%** |
| solo top 25% | 25% | +12,64% | +0,46% |
| solo top 10% | 10% | +16,75% | +0,60% |

Controintuitivo ma logico: essere selettivi significa entrare e uscire più
spesso, e ogni ciclo costa 0,90%. Il funding più alto non compensa le
commissioni aggiuntive. **La versione "furba" rende sei volte meno di quella
stupida.**

## Perché lo fanno gli istituzionali e non i retail

Stessa strategia, cambia solo la fascia commissionale:

| Profilo | Fee per giro | Break-even | Netto sempre dentro | Netto selettivo |
|---|---|---|---|---|
| Retail | 0,90% | 87 giorni | +2,87% | +0,46% |
| Volume medio | 0,36% | 35 giorni | +3,41% | +2,08% |
| Market maker (rebate) | −0,01% | immediato | +3,78% | **+3,19%** |

Per un market maker con rebate le commissioni sono *negative*: viene pagato per
fornire liquidità. Il break-even sparisce e la selettività torna a funzionare.

**L'edge non è nella strategia. È nella struttura dei costi.** Loro non sono
più intelligenti di te: pagano commissioni diverse. È questa la barriera, e non
si supera con codice migliore.

## Il confronto che chiude la questione

| | Rendimento netto |
|---|---|
| Funding arb retail, tutto l'anno | +2,87% lordo → **+2,12%** dopo il 26% di tasse |
| Conto deposito vincolato 12-24 mesi | +1,60% / +2,40% netto |
| Tasso BCE sui depositi | +2,25% |

Il funding arbitrage retail rende **quanto un conto deposito**. Ma in cambio
richiede:

- capitale immobilizzato su due gambe contemporaneamente
- rischio di liquidazione sulla gamba short se il prezzo corre
- rischio controparte: i soldi stanno su un exchange, non in una banca
- gestione attiva del margine, tutti i giorni

Stesso rendimento, incomparabilmente più rischio e lavoro.

## E con 20 €

Servirebbero circa 10 € per gamba più il margine di sicurezza sullo short. I
minimi d'ordine e il margine di mantenimento rendono la cosa semplicemente non
eseguibile.

E anche se lo fosse: il 2,87% annuo su 20 € fa **0,57 €**. Cinquantasette
centesimi, in un anno, gestendo due posizioni e un rischio di liquidazione
ogni giorno.

## Cosa ci portiamo a casa

Avevo detto che il funding rate arbitrage era l'unica cosa in crypto con un
edge strutturale documentato. **Era vero, e i dati lo confermano: +3,77% annuo
su BTC, positivo il 72% del tempo.**

Quello che i dati aggiungono, e che non sapevo prima di misurarlo, è che
quell'edge viene interamente consumato dalle commissioni retail. Esiste, è
reale, ed è fuori portata — non per bravura, per struttura.

È comunque la cosa più utile imparata in tutto il progetto: **il vantaggio
competitivo, quando esiste, sta quasi sempre nei costi e nell'accesso, non
nell'idea.** Ed è per questo che le idee di trading si trovano gratis su
internet mentre le fasce commissionali istituzionali no.

---

*Dati: [Kraken Futures API](https://futures.kraken.com/derivatives/api/v4/historicalfundingrates?symbol=PF_XBTUSD),
8.841 osservazioni orarie, ago 2025 – ago 2026. Riproducibile con `funding_analysis.py`.*
