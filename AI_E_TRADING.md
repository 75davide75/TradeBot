# Chi ha provato a usare l'AI per il trading, e com'è andata

Avevi ragione: gli studi esistono, sono seri, e alcuni sono pubblicati su
riviste di primo livello. Ecco cosa dicono davvero.

---

## 1. Lo studio che ha acceso tutto

**Lopez-Lira & Tang (2023)** — *"Can ChatGPT Forecast Stock Price Movements?"*

Il lavoro che ha fatto partire l'intero filone. Metodo semplice: dare a ChatGPT
i titoli delle notizie e chiedergli se sono buoni, cattivi o irrilevanti per il
titolo. Poi verificare se quel giudizio prevedeva i rendimenti del giorno dopo.

**Risultato: sì.** Correlazione positiva tra i punteggi di ChatGPT e i
rendimenti successivi. E ChatGPT batteva i metodi tradizionali di analisi del
sentiment.

Gli autori hanno costruito il test con attenzione: campione da ottobre 2021 in
poi, cioè **dopo la data di addestramento** del modello, proprio per evitare
che il modello "ricordasse" invece di prevedere.

Questo è il risultato positivo, ed è reale. Ora arriva la parte che quasi
nessuno cita.

---

## 2. Gli stessi autori, due anni dopo, hanno demolito le fondamenta

**Lopez-Lira, Tang & Zhu (2025)** — *"The Memorization Problem: Can We Trust
LLMs' Economic Forecasts?"*

Gli stessi ricercatori sono tornati sul tema e hanno pubblicato la prima
valutazione sistematica di quanto gli LLM **ricordino** i dati economici. Le
conclusioni:

> Gli LLM **non sono affidabili** per previsioni economiche nei periodi coperti
> dai loro dati di addestramento.

I dettagli sono impietosi:

- i modelli **ricordano i valori numerici esatti** di indicatori economici,
  rendimenti azionari e titoli di giornale precedenti al loro cutoff
- **istruire il modello a ignorare il futuro non funziona**: continua a
  rispondere con accuratezza da memoria
- **mascherare i dati non funziona**: ricostruisce entità e date da pochissimo
  contesto

E il punto teorico che chiude la questione:

> Quando il modello ha già visto i valori realizzati, **qualunque risultato è
> compatibile sia con una capacità reale sia con la memorizzazione.** Non sono
> distinguibili.

**Cosa significa concretamente per noi:** ogni backtest in cui si chiede a un
LLM di prevedere qualcosa su dati precedenti al suo cutoff è privo di valore.
Non "meno affidabile" — proprio non identificabile. È la ragione per cui il
nostro sistema sul Pi non chiede a me di prevedere niente, ma usa regole
matematiche esplicite su dati di prezzo.

---

## 3. Il test in condizioni reali: Agent Market Arena

**When Agents Trade (ACM Web Conference 2026)** — il primo benchmark
continuativo e in tempo reale per agenti di trading basati su LLM.

Hanno messo alla prova quattro architetture di agente (da un agente singolo a
un sistema con memoria) su cinque modelli diversi: GPT-4o, GPT-4.1,
Claude 3.5 Haiku, Claude Sonnet 4, Gemini 2.0 Flash.

Risultati:

- gli agenti hanno mostrato **profittabilità e stabilità** in condizioni reali —
  quindi non è tutto fumo
- ma la performance **varia enormemente per asset**: HedgeFundAgent ha
  guadagnato molto su ETH e BMRN e perso molto su TSLA e BTC
- il risultato più interessante: **conta più l'architettura dell'agente che il
  modello sottostante.** Cambiare da GPT a Claude sposta meno che cambiare come
  l'agente ragiona e gestisce il rischio

Tradotto: il vantaggio, dove c'è, non sta nell'intelligenza del modello. Sta
nella struttura del sistema — gestione del rischio, dimensionamento, disciplina.
Esattamente le cose che abbiamo costruito.

---

## 4. Il machine learning "classico" batte gli LLM

**Gu, Kelly & Xiu (2020)**, *Review of Financial Studies* — resta il
riferimento più solido.

Reti neurali su oltre 900 segnali, migliaia di azioni, decenni di dati:

- Sharpe **1,35** su long-short di titoli
- Sharpe **0,77** nel temporeggiare sull'S&P 500, contro 0,51 del buy-and-hold

E i predittori dominanti che emergono da tutto quel setaccio sono **momentum,
liquidità e volatilità** — cioè quello che il nostro sistema già usa.

Nessun LLM ha prodotto risultati confrontabili con questi. Il machine learning
statistico su dati numerici funziona meglio dei modelli linguistici, per un
motivo semplice: il problema è numerico, non linguistico.

---

## 5. E chi ci prova davvero, come finisce?

Qui i dati non sono ambigui.

**Barber & Odean**, borsa di Taiwan, 15 anni (1992-2006), milioni di operazioni
individuali:

> circa **l'1%** dei day trader genera profitti statisticamente affidabili anno
> dopo anno, al netto dei costi

**Chague & De-Losso**, Brasile: 19.646 persone che hanno iniziato a fare day
trading sui futures azionari tra il 2013 e il 2015, seguite fino al 2019:

> tra chi ha persistito oltre 300 giorni di contrattazione, il **97% perdeva
> soldi**, e **meno dell'1%** guadagnava più del salario minimo brasiliano

Sintesi della letteratura: il 10-15% dei day trader retail chiude in utile su
un singolo anno; **l'1-3% resta in utile su tre anni o più**, contando costi,
tasse e slippage.

Nota la struttura di quei numeri: su un anno il 10-15% ce la fa, su tre anni
l'1-3%. È la firma della fortuna che si esaurisce, la stessa cosa che vedevi
nella simulazione dei 100.000 trader.

---

## Cosa ci portiamo a casa

**Quello che funziona davvero, secondo la ricerca:**

1. **Momentum, volatilità e liquidità** come segnali — confermati dal lavoro
   più rigoroso disponibile
2. **L'architettura del sistema** conta più del modello che lo guida: gestione
   del rischio, dimensionamento, disciplina
3. **Diversificazione ampia** — è ciò che rende sfruttabile un segnale debole

Sono esattamente i tre pilastri di quello che abbiamo costruito, e ci siamo
arrivati testando invece che leggendo.

**Quello che non funziona:**

1. Chiedere a un LLM di prevedere i prezzi — non identificabile dalla
   memorizzazione, quindi non verificabile
2. Backtestare un LLM su dati precedenti al suo cutoff — privo di valore
3. Il day trading discrezionale — 1% di successo a tre anni, misurato su
   milioni di persone

**La cosa più onesta che posso dirti su me stesso:** la ricerca dice che io non
sono lo strumento giusto per prevedere i prezzi, e che chiedermelo produrrebbe
risultati che né io né tu potremmo distinguere dalla memoria. Sono invece lo
strumento giusto per costruire e testare l'architettura — che secondo l'Agent
Market Arena è la parte che conta di più.

È esattamente quello che abbiamo fatto in questi due giorni, e senza saperlo
avevamo già preso la strada che la letteratura indica.

---

### Fonti

- Lopez-Lira, Tang (2023), *Can ChatGPT Forecast Stock Price Movements? Return Predictability and Large Language Models* — [arXiv:2304.07619](https://arxiv.org/abs/2304.07619)
- Lopez-Lira, Tang, Zhu (2025), *The Memorization Problem: Can We Trust LLMs' Economic Forecasts?* — [arXiv:2504.14765](https://arxiv.org/abs/2504.14765)
- *When Agents Trade: Live Multi-Market Trading Benchmark for LLM Agents*, ACM Web Conference 2026 — [arXiv:2510.11695](https://arxiv.org/pdf/2510.11695)
- Gu, Kelly, Xiu (2020), *Empirical Asset Pricing via Machine Learning*, Review of Financial Studies 33(5)
- Barber, Odean et al., *Do Individual Day Traders Make Money? Evidence from Taiwan*
- Chague, De-Losso, *Day Trading for a Living?* (Brasile, 2013-2019)
