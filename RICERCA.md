# Cosa funziona davvero — quattro domande, quattro risposte con fonti

## 1. Esistono modelli che prevedono il mercato?

**Sì. E il più credibile dice una cosa scomoda.**

Gu, Kelly e Xiu, *Empirical Asset Pricing via Machine Learning* (Review of
Financial Studies, 2020) — il lavoro di riferimento sul machine learning
applicato ai rendimenti azionari. Risultati out-of-sample reali:

- reti neurali che temporeggiano sull'S&P 500: **Sharpe 0,77** contro 0,51 del
  buy-and-hold
- selezione titoli long-short sui decili: **Sharpe 1,35**

Questi numeri sono veri e replicati. Ma leggi cosa serve per ottenerli: **94
caratteristiche per titolo, 8 variabili macro, 74 dummy settoriali — oltre 900
segnali**, applicati a migliaia di azioni americane per decenni.

E ora la parte che conta. Dopo aver setacciato 900 segnali con reti neurali e
alberi, i predittori dominanti che emergono sono:

> **momentum, liquidità e volatilità**

Cioè esattamente quello che il nostro sistema già usa. Non abbiamo sbagliato
strumento. Abbiamo la scala sbagliata: loro applicano momentum a migliaia di
titoli decorrelati, noi a tre coppie crypto che si muovono insieme.

Uno Sharpe di 1,35 su un long-short di migliaia di azioni non si trasferisce a
tre monete correlate con 20 €. Il segnale è lo stesso; la diversificazione che
lo rende sfruttabile no.

## 2. Ma quanti di questi risultati reggono?

Qui la letteratura litiga, e vale la pena sapere come.

**Hou, Xue e Zhang (2020)** hanno replicato centinaia di anomalie pubblicate:
*"la maggior parte delle anomalie non regge agli standard empirici oggi
accettabili."* Fuori campione i rendimenti calano, le volatilità salgono, le
correlazioni tra anomalie aumentano.

**McLean e Pontiff (2016)** hanno misurato 97 anomalie prima e dopo la
pubblicazione: **il rendimento cala di circa un terzo dopo che il paper esce.**
Gli investitori istituzionali leggono, replicano, e l'edge si consuma.

**Jensen, Kelly e Pedersen (2023)** ribattono: applicando metodologie coerenti,
i tassi di replicabilità sono alti. Non tutto è fumo.

La sintesi onesta: **gli edge esistono, sono piccoli, e si consumano quando
diventano pubblici.** Qualunque strategia che trovi spiegata in un articolo è
già stata letta da migliaia di persone con più capitale e commissioni più
basse di te.

## 3. Copiare i portafogli dei grandi investitori

**Testato dal mercato reale, e i risultati ci sono.**

Esistono ETF che fanno esattamente questo, replicando le posizioni dichiarate
nei moduli 13F: GURU (Global X) e ALFA (AlphaClone).

Su circa un decennio dal lancio nel 2012, **GURU ha sottoperformato l'indice
dell'1,3% annuo e ALFA dell'1,6%**, entrambi con volatilità nettamente
superiore. Alcune varianti hanno battuto l'S&P dal 2016, ma con drawdown
peggiori nelle crisi.

Perché non funziona bene:

- **I 13F escono con 45 giorni di ritardo.** Quando li leggi, il gestore può
  aver già venduto.
- **Mostrano solo le posizioni long su azioni USA.** Niente short, niente
  derivati, niente obbligazioni, niente estero. Vedi una gamba di una strategia
  a più gambe, e non sai cosa bilanciava.
- **Molti fondi non massimizzano il rendimento assoluto** ma quello corretto
  per il rischio. Copiare solo la parte rischiosa di una strategia prudente è
  il modo peggiore di copiarla.

È come copiare metà del compito dal più bravo della classe, con 45 giorni di
ritardo, senza sapere quale metà.

E soprattutto: riguarda **azioni americane**, non crypto. Non è trasferibile al
nostro sistema.

## 4. I robo-advisor di Revolut e JP Morgan

**Non prevedono niente. È letteralmente il loro punto di forza.**

Un robo-advisor fa tre cose:

1. ti fa un questionario sulla propensione al rischio
2. ti assegna un portafoglio modello di ETF diversificati
3. lo ribilancia quando le proporzioni si allontanano dai target

Nessuna previsione. Nessun segnale. Nessun modello che indovina il mercato.
Sono teoria di portafoglio degli anni '50 più automazione, venduti a commissioni
basse.

**Non c'è niente da sfruttare**, perché non c'è nessun vantaggio informativo
dentro. Il valore che offrono è diverso: costi bassi, disciplina, e il fatto di
impedire all'utente di fare cose stupide nei momenti di panico.

Vale la pena fermarsi su questo. Le istituzioni finanziarie più grandi del
mondo, che *potrebbero* permettersi qualunque modello predittivo, quando devono
gestire i soldi dei clienti al dettaglio vendono un prodotto che **non prova
nemmeno a prevedere**.

Non è pigrizia. È la loro risposta professionale alla stessa domanda che ci
siamo fatti noi.

## Cosa ce ne facciamo

**Da tenere:**

- momentum è confermato come predittore reale dalla ricerca più seria
  disponibile — la direzione era giusta
- la diversificazione è ciò che rende il segnale sfruttabile, e noi ne abbiamo
  troppo poca

**Da lasciar perdere:**

- copiare i 13F: sottoperformance documentata, ritardo strutturale, asset class
  sbagliata
- cercare vantaggi nei robo-advisor: non ne contengono

**La domanda che resta aperta**, e che è quella buona: se il segnale funziona
grazie alla diversificazione, la strada non è una strategia più aggressiva su
poche monete. È l'opposto — più strumenti, meno correlati, esposizione più
bassa.

---

### Fonti

- Gu, Kelly, Xiu (2020), *Empirical Asset Pricing via Machine Learning*, Review of Financial Studies 33(5)
- Hou, Xue, Zhang (2020), *Replicating Anomalies*, Review of Financial Studies
- McLean, Pontiff (2016), *Does Academic Research Destroy Stock Return Predictability?*, Journal of Finance
- Jensen, Kelly, Pedersen (2023), *Is There a Replication Crisis in Finance?*, Journal of Finance
- Dati performance GURU/ALFA: CFA Institute, ETF.com
