# Installazione su Raspberry Pi (o qualunque Linux)

Testato per Raspberry Pi OS 64-bit. Funziona identico su Debian/Ubuntu,
incluse le VM ARM gratuite di Oracle Cloud.

## 1. Copia il progetto sul Pi

Dal Mac, sostituendo `pi@raspberrypi.local` con il tuo utente e hostname:

```bash
cd "/Users/davidesogos/Desktop"
scp -r "progetto trading" pi@raspberrypi.local:~/trading
```

## 2. Dipendenze

Collegati al Pi (`ssh pi@raspberrypi.local`) e installa:

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

`%i` nei file viene sostituito dal nome utente. Se il tuo utente è `pi`:

```bash
cd ~/trading/linux
sudo cp tradingbot.service /etc/systemd/system/tradingbot@.service
sudo cp dailyreview.service /etc/systemd/system/dailyreview@.service
sudo cp dailyreview.timer /etc/systemd/system/dailyreview@.timer

sudo systemctl daemon-reload
sudo systemctl enable --now tradingbot@pi.service
sudo systemctl enable --now dailyreview@pi.timer
```

## 6. Verifica

```bash
systemctl status tradingbot@pi        # deve dire "active (running)"
journalctl -u tradingbot@pi -f        # log in tempo reale, Ctrl+C per uscire
systemctl list-timers dailyreview@pi  # quando parte la prossima revisione
```

## Comandi utili

| Comando | Cosa fa |
|---|---|
| `sudo systemctl restart tradingbot@pi` | Riavvia il bot |
| `sudo systemctl stop tradingbot@pi` | Ferma il bot |
| `journalctl -u tradingbot@pi -n 100` | Ultime 100 righe di log |
| `sudo systemctl start dailyreview@pi` | Forza subito la revisione |

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
- l'utente di default è `ubuntu`, quindi usa `tradingbot@ubuntu.service`
- non serve aprire porte in ingresso: il bot fa solo chiamate in uscita
  verso Telegram e Kraken
