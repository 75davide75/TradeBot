# Installazione su Raspberry Pi (o qualunque Linux)

Testato per Raspberry Pi OS 64-bit. Funziona identico su Debian/Ubuntu,
incluse le VM ARM gratuite di Oracle Cloud.

## 0. Dove vivono i dati — leggi questo prima di tutto

`state.json`, `journal.csv` e `report/` **non** stanno nella cartella del
codice: stanno in `~/trading-dati/`.

La cartella del codice è **sacrificabile**: ci puoi copiare sopra, cancellarla,
rifarla da git, e lo storico non si muove. Questo non è un dettaglio di gusto —
quando i dati stavano dentro la cartella del codice si sono azzerati due volte
durante i deploy, il 10 e l'11 agosto 2026, portandosi via 74 punti di storico e
8 posizioni aperte.

Al primo avvio dopo l'aggiornamento il bot **sposta i file da solo** dalla
vecchia posizione e lo scrive nel log. Non devi fare nulla a mano.

Se il bot trova il journal ma non lo stato, **non riparte**: manda un messaggio
su Telegram e si ferma, perché ripartire da zero cancellerebbe la storia del
conto senza dirlo. Per azzerare di proposito:

```bash
TRADEBOT_NUOVO_CONTO=1 python3 bot.py
```

## 1. Copia il progetto sul Pi

Dal Mac, usa `./sync.sh` (configuralo una volta con utente e hostname del Pi).
Per la primissima copia, dalla cartella del progetto:

```bash
rsync -avz --exclude '.git/' --exclude '__pycache__/' --exclude '*.pyc' \
      --exclude 'state.json' --exclude 'journal.csv' --exclude 'report/' \
      ./ davide@raspberrypi.local:~/trading/
```

L'utente è quello configurato in `sync.sh` (`PI_USER`), e su questa macchina è
`davide`. Se lo cambi, cambialo in tutti e due i posti.

**Non usare `scp -r` della cartella intera:** copierebbe anche `state.json`,
sovrascrivendo lo storico del Pi con quello del Mac. È esattamente il guasto
descritto al punto 0.

## 2. Dipendenze

Collegati al Pi (`ssh davide@raspberrypi.local`) e installa:

```bash
sudo apt update
sudo apt install -y python3-pandas python3-numpy
```

Meglio i pacchetti apt che `pip3` su Pi: sono precompilati per ARM e non
devi aspettare mezz'ora di compilazione di numpy.

## 3. Fuso orario

Serve, altrimenti la revisione delle 9:00 parte all'ora sbagliata:

```bash
sudo timedatectl set-timezone Europe/Rome
```

## 4. Prova a mano

```bash
cd ~/trading && python3 bot.py
```

Se arriva il messaggio di avvio su Telegram, fermalo con `Ctrl+C` e prosegui.

## 5. Installa i servizi

I servizi sono **templati**: il pezzo dopo la `@` è il tuo nome utente Unix, e
systemd lo sostituisce a `%i` dentro `User=` e nei percorsi. Quindi l'unità non
si chiama `tradingbot@pi` per convenzione: si chiama come l'utente che la fa
girare, e su questa macchina è `davide`.

Qui sotto si usa `$USER` invece di scrivere un nome a mano. Copiaincollalo così
com'è: è corretto su qualunque macchina, e ti risparmia l'errore descritto in
fondo a questa pagina.

```bash
cd ~/trading/linux
for u in tradingbot dailyreview publish healthcheck gitpull; do
  sudo cp $u.service /etc/systemd/system/$u@.service
done
for t in dailyreview publish healthcheck gitpull; do
  sudo cp $t.timer /etc/systemd/system/$t@.timer
done

sudo systemctl daemon-reload
sudo systemctl enable --now tradingbot@$USER.service   # il bot, sempre attivo
sudo systemctl enable --now dailyreview@$USER.timer    # revisione giornaliera
sudo systemctl enable --now publish@$USER.timer        # dashboard, ogni 30 min
sudo systemctl enable --now healthcheck@$USER.timer    # controllo delle 9:00
sudo systemctl enable --now gitpull@$USER.timer        # aggiornamenti, ogni 20 min
```

`dashboard.service` non è in elenco: serve solo se vuoi la dashboard servita
anche in locale dal Pi, cosa che GitHub Pages già fa. Installalo allo stesso
modo se ti serve.

**`gitpull` scarica ma non riavvia niente**, di proposito. I *dati* — la scelta
dell'universo IA — fluiscono da soli, perché il bot rilegge quel file a ogni
controllo. Il *codice* no: un aggiornamento entra in vigore solo al prossimo
riavvio manuale del bot. Un sistema che esegue codice nuovo senza supervisione
deploya da solo anche i bug.

Dopo ogni `git pull` che tocchi il codice, quindi:

```bash
sudo systemctl restart tradingbot@$USER
```

## 6. Verifica

```bash
systemctl status tradingbot@$USER          # deve dire "active (running)"
journalctl -u tradingbot@$USER -f          # log in tempo reale, Ctrl+C per uscire
systemctl list-timers '*@'$USER            # quando parte ciascun timer
```

## Comandi utili

| Comando | Cosa fa |
|---|---|
| `sudo systemctl restart tradingbot@$USER` | Riavvia il bot (serve dopo ogni aggiornamento del codice) |
| `sudo systemctl stop tradingbot@$USER` | Ferma il bot |
| `journalctl -u tradingbot@$USER -n 100` | Ultime 100 righe di log |
| `sudo systemctl start dailyreview@$USER` | Forza subito la revisione |
| `sudo systemctl start publish@$USER` | Forza subito la pubblicazione della dashboard |
| `head -1 ~/trading-dati/journal.csv` | Intestazione del registro (deve finire con `,wallet`) |

## Se un servizio muore con `status=217/USER`

```
Active: activating (auto-restart) (Result: exit-code)
Process: ExecStart=/usr/bin/python3 /home/pi/trading/bot.py (code=exited, status=217/USER)
```

Vuol dire che hai avviato l'istanza con il nome sbagliato: `tradingbot@pi`
quando l'utente è `davide`. systemd non riesce a diventare un utente che non
esiste, e muore **prima** di eseguire una riga di Python — quindi non ha fatto
danni, ma cicla ogni 30 secondi e il bot vero non è stato riavviato.

```bash
whoami                                    # il nome giusto e' questo
sudo systemctl disable --now tradingbot@pi   # ferma il fantasma
sudo systemctl restart tradingbot@$USER      # riavvia quello vero
```

## Note sull'affidabilità

**Riavvio automatico.** `Restart=always` con `RestartSec=30`: se il bot
crasha, systemd lo riavvia dopo 30 secondi. Se il Pi si riavvia, riparte da
solo. Lo stato del portafoglio è su disco e le scritture sono atomiche, quindi
un'interruzione improvvisa non lo corrompe.

**Log su journald, non su file.** Evita che i log crescano all'infinito e
consumino la SD. journald ruota da solo.

**SD card.** Le scritture di questo sistema sono minime (state.json ogni 4
ore, journal solo sulle operazioni), quindi l'usura non è un problema reale.
Se comunque il Pi ti serve per altro e sta acceso da anni, valuta un SSD USB.

**Se il Pi è spento** all'ora della revisione, `Persistent=true` la fa
recuperare al riavvio. Il bot invece ricalcola i segnali al primo controllo
utile: non c'è nulla da recuperare, la strategia lavora su candele daily.

## Se usi Oracle Cloud invece del Pi

Identico, ma:

- crea una VM `VM.Standard.A1.Flex` (ARM, gratis a vita: 4 core / 24 GB)
- immagine Ubuntu 22.04
- l'utente di default è `ubuntu` invece di quello del Pi — ma i comandi del
  punto 5 usano `$USER`, quindi restano corretti senza modifiche
- non serve aprire porte in ingresso: il bot fa solo chiamate in uscita
  verso Telegram e Kraken
