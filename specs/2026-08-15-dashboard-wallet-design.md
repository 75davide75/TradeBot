# Dashboard: i tre wallet diventano distinguibili e misurabili

Data: 2026-08-15
Stato: approvato, da implementare

## Il problema

I tre portafogli esistono per essere confrontati. È l'intera ragione della loro
architettura: girano sugli stessi dati e differiscono per **una variabile
ciascuno** (`core.py:332-472`), che è l'unico modo di attribuire una differenza a
una causa. La dashboard non lo mostra.

Oggi, in `docs/index.html`:

1. **I wallet non si distinguono.** Ombra e IA compaiono come due KPI in coda alla
   fila, con etichette che descrivono la variabile ("Senza volatility targeting")
   invece di nominare il portafoglio. Sul grafico sono due linee smorzate. Non
   esiste un posto in cui i tre siano affiancati e leggibili insieme.
2. **Non si sa quanto sia investito.** Nessun wallet pubblica la propria
   esposizione. Il reale ha 81,31 € di nozionale aperto su 200,66 € di equity —
   il 40,5% — e la pagina non lo dice da nessuna parte.
3. **Il dato non c'è nemmeno.** `publish.py:91-99` esporta `positions`, cioè solo
   il portafoglio reale. `shadow_positions` e `ia_positions` non escono in
   `data.json`: per ombra e IA l'esposizione non è nascosta, è **assente**.

Il punto 3 è quello che decide la forma del lavoro: metà sta in Python, non in
HTML.

## Cosa c'è già, e va sfruttato

Tutti e tre i wallet partono dallo stesso `capitale_versato` e ricevono gli
stessi versamenti negli stessi momenti (`stato.py:232-236`). Quindi
`equity / capitale - 1` è confrontabile fra i tre **senza aggiustamenti**: non
serve una base per wallet, e non serve toccare la contabilità.

Le equity correnti di ombra e IA sono già negli ultimi punti delle rispettive
serie storiche (`publish.py:111,117`). Il blocco nuovo non ha bisogno di prezzi,
quindi non introduce chiamate di rete in `publish.py`.

## Il disegno

Sei pezzi. I primi due sono Python, gli altri quattro HTML.

### 1. `publish.py`: il blocco `wallet`

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
succede, la pagina nuova deve continuare a leggere il file vecchio (§5).

`avviato` distingue "non ha mai operato" da "ha operato e ha chiuso tutto". Per
l'IA oggi sono lo stesso disegno vuoto e significano cose opposte.

**Whitelist, come per le posizioni reali.** Le posizioni secondarie passano per
gli stessi cinque campi già pubblicati (`side`, `entry`, `notional`, `leverage`,
`opened`) attraverso una funzione unica. Il commento in cima a `publish.py` sul
repo pubblico è una regola, non un promemoria: un blocco nuovo che riversa lo
stato grezzo la aggirerebbe alla prima aggiunta di campo in `core.py`.

### 2. `test_publish.py`

Nella convenzione degli altri quattro test: `unittest`, nessuna rete, stato
finto costruito nel test. Copre la costruzione del blocco wallet — che i campi
fuori whitelist non escano, che `avviato` sia falso solo quando il wallet non ha
mai operato, che uno stato privo di `shadow_positions`/`ia_positions` (scritto da
una versione precedente) non sollevi `KeyError`.

Quest'ultimo caso è la stessa classe di bug già pagata due volte in questo
progetto, documentata a `core.py:56`.

### 3. Le tre card

In cima alla pagina, sempre visibili. Per ogni wallet:

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
di equity e dal bordo delle posizioni. Il benchmark BTC resta arancione e
tratteggiato: non è un wallet.

L'IA resta visibile e smorzata finché non opera, invece di sparire. Che non sia
ancora partita è informazione.

### 4. Le posizioni, un wallet alla volta

Segmented control con i conteggi (`Reale · 8`, `Ombra · 8`, `IA · 0`). Filtra
solo questa sezione: le card di §3 restano sempre in vista, perché il confronto
fra wallet è la cosa che la pagina esiste per mostrare e non deve costare un
click.

Mescolarle non è un'alternativa: ombra rispecchia gli stessi mercati del reale
con nozionali diversi, quindi sedici riquadri quasi identici a coppie.

**Le candele si scaricano una volta per mercato e restano vive.** Cambiare
wallet aggiorna la linea d'ingresso e i numeri, non rifà otto chiamate a Kraken:
il codice attuale ne fa già al massimo tre in parallelo per non prendersi un
rifiuto per eccesso di traffico (`index.html:409-414`), e triplicarle a ogni
click romperebbe quella difesa.

Il WebSocket si iscrive all'unione dei mercati dei tre wallet, così il cambio di
scheda non richiede una nuova sottoscrizione.

Quando il wallet selezionato non ha posizioni aperte la sezione mostra i mercati
di `universo` in stato "in attesa", come già fa oggi la pagina quando il reale è
scarico: una griglia vuota non dice se il sistema sta lavorando o è fermo. Per
l'IA non ancora avviata `ia_universo` è vuoto, quindi la sezione dichiara
esplicitamente che il wallet non ha ancora scelto un universo, invece di
prendere in prestito quello del reale — sarebbe un universo che quel wallet non
ha mai avuto.

### 5. Ripiego sul `data.json` vecchio

Se `wallet` manca, la pagina lo ricostruisce dai campi legacy: il reale completo
di posizioni, ombra e IA con valore e percentuale, esposizione `—`.

Non è un caso teorico: fra il push e il primo publish del Pi passano fino a
cinquanta minuti (pull ogni 20, publish ogni 30), e se il pull fallisce passa di
più. Senza ripiego, quella finestra è una dashboard rotta.

### 6. Tema chiaro e scuro

Palette Apple in variabili CSS, `prefers-color-scheme`, nessun interruttore in
pagina: la scelta è già stata fatta nelle impostazioni di sistema.

I colori oggi scritti a mano dentro le opzioni di `lightweight-charts`
(`index.html:180-184`) passano alle stesse variabili e vengono riapplicati al
cambio tema. È l'unico punto in cui il tema può rompersi in silenzio, perché i
grafici sono disegnati su canvas e non ereditano niente dal CSS.

## Verifica

- `python3 -m unittest test_publish -v`
- pagina servita in locale con il `data.json` **attuale** → percorso di ripiego,
  nessun `NaN`, nessuna sezione vuota
- pagina servita con un `data.json` **arricchito a mano** → percorso nuovo, con
  l'IA in stato "non avviato" e con l'IA che ha posizioni
- chiaro e scuro, incluse le candele
- 1280 px e 375 px

## Fuori perimetro

- **`ricerca.html`** — stessa famiglia visiva, ma è un documento, non un
  cruscotto. Va rifatto quando serve a lui, non per simmetria.
- **Equity in diretta.** Il valore grande resta quello pubblicato dal Pi, con la
  sua ora. Il live aggiunge il P&L aperto per wallet, non ricalcola l'equity: due
  numeri che si muovono di loro iniziativa e non tornano identici sono il modo
  più rapido per far dubitare di entrambi.
- **Logica di trading, rischio, contabilità.** Nessun file di `core.py`,
  `bot.py`, `stato.py` viene toccato. Questo lavoro cambia solo ciò che si vede.

## Nota operativa

`publish.py` **non va eseguito da questo Mac**: lo `state.json` locale è vuoto
(176 byte, `cash 100.0`, `history []`) e sovrascriverebbe `docs/data.json` con un
conto da 100 € e zero posizioni, committandolo. È lo stesso file che ha già
causato l'azzeramento diagnosticato nello spec dell'11 agosto. La verifica del
punto 1 passa dal test, non dall'esecuzione.
