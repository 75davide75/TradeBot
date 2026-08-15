# Dashboard: i tre wallet diventano distinguibili, misurabili e tracciati

Data: 2026-08-15
Stato: approvato, da implementare

## Il problema

I tre portafogli esistono per essere confrontati. È l'intera ragione della loro
architettura: girano sugli stessi dati e differiscono per **una variabile
ciascuno** (`core.py:332-472`), che è l'unico modo di attribuire una differenza a
una causa. Niente di tutto questo arriva alla dashboard.

1. **I wallet non si distinguono.** Ombra e IA compaiono come due KPI in coda
   alla fila, con etichette che descrivono la variabile ("Senza volatility
   targeting") invece di nominare il portafoglio. Sul grafico sono due linee
   smorzate. Non esiste un posto in cui i tre siano affiancati e leggibili
   insieme.
2. **Non si sa quanto sia investito.** Nessun wallet pubblica la propria
   esposizione. Il reale ha 81,31 € di nozionale aperto su 200,66 € di equity —
   il 40,5% — e la pagina non lo dice da nessuna parte.
3. **Il dato delle posizioni non esce.** `publish.py:91-99` esporta `positions`,
   cioè solo il portafoglio reale. `shadow_positions` e `ia_positions` non
   arrivano in `data.json`: per ombra e IA l'esposizione non è nascosta, è
   **assente**.
4. **Le operazioni di ombra e IA non vengono registrate.** `_apri` e `_chiudi`
   (`core.py:358-381`) non chiamano mai `journal()`. Nel registro — che il codice
   stesso chiama "la fonte di verità" (`stato.py:277`) — finiscono solo le
   operazioni del portafoglio reale. Due terzi del sistema operano senza lasciare
   traccia.

I punti 3 e 4 decidono la forma del lavoro: la maggior parte sta in Python.
Il punto 4 in particolare non è una lettura mancante, è una **scrittura
mancante**: lo storico unificato non si può estrarre, si può solo cominciare a
registrare.

### L'eccezione che conferma il buco

Una sola operazione secondaria viene registrata: lo stop-loss dell'IA
(`bot.py:187-189`). E lo fa scrivendo il **P&L netto nella colonna `notional`**.
Finché quella riga è sola in mezzo alle altre l'incoerenza non si vede; in una
tabella che affianca i tre portafogli diventa un nozionale negativo accanto a
nozionali veri.

## Cosa c'è già, e va sfruttato

**I tre wallet condividono la base di calcolo.** Partono dallo stesso
`capitale_versato` e ricevono gli stessi versamenti negli stessi momenti
(`stato.py:232-236`). Quindi `equity / capitale - 1` è confrontabile fra i tre
senza aggiustamenti: non serve una base per wallet, e non si tocca la
contabilità.

**Le equity di ombra e IA sono già calcolate.** Stanno negli ultimi punti delle
rispettive serie storiche (`publish.py:111,117`). Il blocco nuovo non ha bisogno
di prezzi, quindi non introduce chiamate di rete in `publish.py`.

**L'ombra rispecchia il reale 1:1.** Apre e chiude insieme a lui, sullo stesso
mercato, nella stessa direzione, allo stesso prezzo d'ingresso; cambia solo il
nozionale (`bot.py:483-490`, `bot.py:514`). L'IA invece opera su un universo suo
(`bot.py:338-340`). Questa asimmetria non è un dettaglio da appianare: è la
forma che la pagina deve prendere.

## Il disegno

Tredici pezzi in tre parti. La parte A è la sola che tocca il sistema in
produzione, ed è quella da leggere con più attenzione.

---

## Parte A — la registrazione

Nessun pezzo di questa parte cambia una decisione di trading. Non cambia una
posizione, una dimensione, una direzione, una soglia. Cambia **solo cosa viene
scritto nel registro**. La distinzione fra registrare e decidere è la ragione per
cui è accettabile toccare `core.py` in un lavoro sulla dashboard.

### A1. `journal()`: la colonna `wallet`

`stato.py:281` fissa dieci colonne. Ne serve un'undicesima, `wallet`, con valori
`reale` / `ombra` / `ia`.

**La migrazione riscrive solo la riga d'intestazione.** `csv.DictWriter` scrive
l'intestazione unicamente quando il file non esiste (`stato.py:286`): aggiungere
una colonna senza migrare significa scrivere undici valori sotto dieci nomi, e
`DictReader` da quel momento assegna i campi sbagliati. Il registro si
corromperebbe in silenzio, e il registro è l'unica cosa di valore che questo
sistema produce.

Le righe storiche **non vengono riscritte**: restano a dieci campi, e
`DictReader` restituisce `None` per `wallet`. Ogni lettore tratta `None` e
stringa vuota come `reale`, che è ciò che quelle righe sono. Toccare solo
l'intestazione è deliberato — una riscrittura completa del file mette a rischio
tutte le righe per un beneficio cosmetico.

Scrittura atomica: file temporaneo e `os.replace`, come già fa `save_state`.

### A2. Da quando lo storico è completo

Poiché le righe vecchie hanno `wallet` vuoto e le nuove no, la data di inizio
della registrazione completa è **deducibile dal registro stesso**: è il `ts`
della prima riga con `wallet` valorizzato. Nessun marcatore da inventare,
nessuna data da salvare da qualche altra parte che poi diverge.

`publish.py` la pubblica come `storico_wallet_dal`, e la pagina la dichiara
(§C3). Le operazioni passate di ombra e IA **non vengono ricostruite**: l'ombra
rispecchiava il reale, quindi mercato, direzione e data sarebbero deducibili, ma
il nozionale dipendeva dall'equity dell'ombra in quell'istante e non è
registrato da nessuna parte. Sarebbero righe stimate, indistinguibili dalle vere
dentro la stessa tabella. Un buco dichiarato vale più di un riempimento
plausibile.

### A3. `_apri` e `_chiudi` registrano

Le due funzioni dei portafogli secondari (`core.py:358-381`) chiamano `journal()`
con `wallet=` la chiave del portafoglio, negli stessi campi già usati per il
reale. In chiusura `_chiudi` scrive in `equity` il cash del proprio portafoglio,
non quello del reale: è la colonna che `close_position` riempie con
`state["cash"]` (`core.py:328`), e riempirla con il conto sbagliato renderebbe
tre portafogli indistinguibili proprio nella colonna che dovrebbe separarli.

Nota sul volume: l'ombra rispecchia ogni operazione del reale, quindi le righe
scritte all'incirca triplicano. `journal()` apre e chiude il file a ogni riga, e
a questo ritmo — una manciata di operazioni al giorno — resta irrilevante.

### A4. `ia_stop` diventa una chiusura normale

Lo stop-loss dell'IA (`bot.py:186-189`) smette di scrivere il P&L dentro
`notional`. Con A3 la chiusura viene già registrata da `chiudi_ia`; alla riga
`ia_stop` resta il compito che le è proprio, cioè dire **perché** si è chiuso.

### A5. `healthcheck.py`: la finestra delle 60 righe

`righe_journal` (`healthcheck.py:70`) passa all'IA le ultime 60 righe degli
ultimi 7 giorni per il riassunto delle 9:00. Con il triplo delle righe, quella
finestra si riempirebbe di duplicati dell'ombra e coprirebbe un terzo del tempo:
il riassunto del mattino perderebbe giorni di contesto senza che niente lo dica.

Il filtro passa a `wallet` vuoto o `reale`. Il riassunto continua a parlare del
portafoglio che conta, con la stessa profondità storica di oggi.

---

## Parte B — la pubblicazione

### B1. Il blocco `wallet` in `data.json`

Un campo nuovo, **aggiunto** accanto a quelli esistenti senza toccarne nessuno:

```json
"wallet": {
  "reale": {"equity": 200.66, "avviato": true,  "posizioni": {…}},
  "ombra": {"equity": 201.48, "avviato": true,  "posizioni": {…}},
  "ia":    {"equity": null,   "avviato": false, "posizioni": {}}
}
```

Aggiungere invece di ristrutturare non è timidezza: `data.json` lo scrive il Pi,
la pagina la scrive il Mac, e i due si allineano solo dopo un pull. Finché non
succede, la pagina nuova deve continuare a leggere il file vecchio (§C4).

`avviato` distingue "non ha mai operato" da "ha operato e ha chiuso tutto". Per
l'IA oggi sono lo stesso disegno vuoto e significano cose opposte.

**Whitelist, come per le posizioni reali.** Le posizioni secondarie passano per
gli stessi cinque campi già pubblicati (`side`, `entry`, `notional`, `leverage`,
`opened`) attraverso una funzione unica. Il commento in cima a `publish.py` sul
repo pubblico è una regola, non un promemoria: un blocco nuovo che riversa lo
stato grezzo la aggirerebbe alla prima aggiunta di campo in `core.py`.

### B2. Le operazioni escono con il loro wallet

`CAMPI_OP` (`publish.py:34`) guadagna `wallet`; le righe che non ce l'hanno
escono come `reale`. Si aggiunge `storico_wallet_dal` (§A2).

Il tetto passa da 100 a 250 righe (`publish.py:123`). Con tre portafogli che
scrivono, 100 righe coprirebbero un terzo del tempo di oggi, e la tabella
sembrerebbe dire che il sistema ha iniziato a operare più tardi di quanto abbia
fatto. 250 righe pesano circa 27 KB su un `data.json` che oggi sta a 59 KB.

### B3. `test_publish.py`

Nella convenzione degli altri quattro test: `unittest`, nessuna rete, stato e
registro finti costruiti nel test. Copre:

- il blocco wallet: campi fuori whitelist che non escono, `avviato` falso solo
  quando il wallet non ha mai operato
- uno stato privo di `shadow_positions`/`ia_positions`, scritto da una versione
  precedente, che non solleva `KeyError` — stessa classe di bug già pagata due
  volte in questo progetto, documentata a `core.py:56`
- un registro con righe miste (dieci campi e undici) letto senza disallineamenti,
  con le righe vecchie attribuite al reale
- `storico_wallet_dal` che coincide con la prima riga marcata

La migrazione dell'intestazione va coperta in `test_stato.py`, dove vivono già i
test del registro: registro vecchio → intestazione riscritta, righe intatte,
`ha_operato()` che continua a rispondere come prima.

---

## Parte C — la pagina

### C1. Le tre card

In cima, sempre visibili. Per ogni wallet:

| Riga | Contenuto |
|---|---|
| valore | equity pubblicata |
| variazione | `equity / capitale - 1` |
| esposizione | somma dei nozionali, in € e in % dell'equity |
| barra | ripartizione long / short |

Oggi il reale mostrerebbe 81,31 € — 40,5% — con 18,62 € long su 3 mercati e
62,69 € short su 5.

**Non viene mostrata una "liquidità".** In questa contabilità aprire una
posizione non sottrae nulla dal cash: `open_position` scala solo le commissioni
(`core.py:304-313`). Il cash resta quindi intorno ai 200 € mentre l'esposizione è
81 €, e affiancarli darebbe 281 € su un conto da 200. Un numero che sembra il
complemento di un altro e non lo è vale meno di un numero assente.

Un colore fisso per wallet — blu, viola, verde — ripreso dalle linee del grafico
di equity, dai bordi delle posizioni e dalle righe dello storico. Il benchmark
BTC resta arancione e tratteggiato: non è un wallet.

L'IA resta visibile e smorzata finché non opera. Che non sia ancora partita è
informazione.

### C2. Le posizioni: due sezioni, non tre schede

La struttura segue quella del sistema (§"Cosa c'è già"), non una simmetria che
non esiste.

**Sezione 1 — "Segnale momentum · Reale e Ombra".** Una card per mercato, con
**entrambi i wallet sulla stessa card**. Mercato, direzione e prezzo d'ingresso
sono condivisi e stanno nell'intestazione; sotto, due righe colorate con
nozionale, leva e P&L di ciascuno.

È la presentazione che rende visibile l'esperimento: stesso mercato, stesso
ingresso, **una sola variabile diversa** — la leva — e due P&L differenti a
fianco. Tre schede paritarie avrebbero nascosto proprio questo, costringendo a
tenere a mente i numeri dell'una mentre si guarda l'altra.

Se un mercato compare in un wallet e non nell'altro — l'ombra avviata dopo, una
chiusura andata a vuoto — la riga mancante mostra `—` e lo dichiara, invece di
lasciare intendere una posizione a zero.

**Sezione 2 — "Mercati scelti dall'IA".** Card sue, un wallet solo, accanto alla
motivazione e alla data della scelta già pubblicate. Se l'IA non ha ancora scelto
un universo, la sezione lo dice: non prende in prestito quello del reale, che
sarebbe un universo che quel wallet non ha mai avuto.

**Le candele si scaricano una volta per mercato e restano vive.** Il codice
attuale ne fa già al massimo tre in parallelo per non prendersi un rifiuto per
eccesso di traffico (`index.html:409-414`); ridisegnare a ogni interazione
romperebbe quella difesa. Il WebSocket si iscrive all'unione dei mercati dei tre
wallet.

### C3. Lo storico unificato

Una tabella sola, in ordine di tempo, con una colonna **Portafoglio**: pastiglia
colorata con lo stesso colore delle card. Filtri rapidi per wallet e per tipo di
operazione, che agiscono sulla tabella già caricata.

In testa alla tabella, una riga di contesto:

> Le operazioni di ombra e IA sono registrate dal **‹data›**. Prima di quella
> data il registro conteneva solo il portafoglio reale.

Non è una nota a piè di pagina: senza, un lettore vede il reale con 34 operazioni
e l'ombra con poche e conclude che l'ombra non abbia quasi operato — la lettura
esattamente sbagliata, su un confronto che è il motivo per cui i due portafogli
esistono.

La riga sparisce da sola quando la prima operazione registrata è più recente
della data di inizio, cioè quando lo storico è integralmente completo.

### C4. Ripiego sul `data.json` vecchio

Se `wallet` manca, la pagina lo ricostruisce dai campi legacy: il reale completo
di posizioni, ombra e IA con valore e percentuale, esposizione `—`. Se le
operazioni non hanno `wallet`, la colonna mostra tutte righe "reale", che è
quello che sono.

Non è un caso teorico: fra il push e il primo publish del Pi passano fino a
cinquanta minuti (pull ogni 20, publish ogni 30), e se il pull fallisce passa di
più. Senza ripiego, quella finestra è una dashboard rotta.

### C5. Tema chiaro e scuro

Palette Apple in variabili CSS, `prefers-color-scheme`, nessun interruttore in
pagina: la scelta è già stata fatta nelle impostazioni di sistema.

I colori oggi scritti a mano dentro le opzioni di `lightweight-charts`
(`index.html:180-184`) passano alle stesse variabili e vengono riapplicati al
cambio tema. È l'unico punto in cui il tema può rompersi in silenzio, perché i
grafici sono disegnati su canvas e non ereditano niente dal CSS.

---

## Verifica

```bash
python3 -m unittest discover -p "test_*.py" -v
```

I quattro test esistenti devono continuare a passare: `test_stato.py` tocca il
registro ed è il primo posto in cui una migrazione sbagliata si vede.

Sul registro, in aggiunta:

- registro vecchio a dieci colonne → intestazione migrata, righe dati non
  toccate, `ha_operato()` invariato
- registro già migrato → la migrazione non fa nulla e non duplica l'intestazione
- righe miste rilette da `DictReader` senza disallineamento di campi

Sulla pagina:

- servita in locale con il `data.json` **attuale** → percorso di ripiego, nessun
  `NaN`, nessuna sezione vuota
- servita con un `data.json` **arricchito a mano** → percorso nuovo, in tre
  varianti: IA non avviata, IA con posizioni, mercato presente nel reale ma non
  nell'ombra
- chiaro e scuro, incluse le candele
- 1280 px e 375 px

## Fuori perimetro

- **`ricerca.html`** — stessa famiglia visiva, ma è un documento, non un
  cruscotto. Va rifatto quando serve a lui, non per simmetria.
- **Equity in diretta.** Il valore grande resta quello pubblicato dal Pi, con la
  sua ora. Il live aggiunge il P&L aperto per wallet, non ricalcola l'equity: due
  numeri che si muovono di loro iniziativa e non tornano identici sono il modo
  più rapido per far dubitare di entrambi.
- **Ricostruzione retroattiva** delle operazioni di ombra e IA — §A2.
- **Ogni decisione di trading.** Segnale, dimensionamento, leva, stop, filtro di
  negoziabilità, kill switch: nulla di tutto questo viene toccato. Le modifiche a
  `core.py` e `bot.py` aggiungono righe di registro e nient'altro.

## Nota operativa

`publish.py` **non va eseguito da questo Mac**: lo `state.json` locale è vuoto
(176 byte, `cash 100.0`, `history []`) e sovrascriverebbe `docs/data.json` con un
conto da 100 € e zero posizioni, committandolo. È lo stesso file che ha già
causato l'azzeramento diagnosticato nello spec dell'11 agosto. La verifica passa
dai test, non dall'esecuzione.

La migrazione del registro (§A1) gira **sul Pi**, sul `journal.csv` vero in
`~/trading-dati/`. Va eseguita una volta sola e in modo idempotente, perché il
timer di pull la porterà lì senza che nessuno la stia guardando.
