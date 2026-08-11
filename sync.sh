#!/bin/bash
# Sincronizza il progetto dal Mac al Raspberry Pi e riavvia il bot.
#
# Uso:  ./sync.sh
#
# Da lanciare SUL MAC, dalla cartella del progetto.

set -e

# ---------------------------------------------------------------------------
# CONFIGURA QUI (una volta sola)
# ---------------------------------------------------------------------------
PI_USER="davide"
PI_HOST="raspberrypi.local"    # oppure l'IP, es. "192.168.1.50"
PI_DIR="~/trading"
# ---------------------------------------------------------------------------

CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
cd "$(dirname "$0")"

echo -e "${CYAN}→ Sincronizzo verso ${PI_USER}@${PI_HOST}${NC}"

if ! command -v rsync >/dev/null 2>&1; then
    echo -e "${RED}✗ rsync non disponibile.${NC} Installalo con: brew install rsync"
    exit 1
fi

# ESCLUSIONI, non inclusioni.
#
# Prima qui c'era una lista di file da copiare, ed e' invecchiata in silenzio:
# perp.py, publish.py, healthcheck.py e linux/ non erano nell'elenco, quindi
# non venivano piu' sincronizzati. Chi doveva fare un deploy completo ripiegava
# sull'scp -r di INSTALLA.md, che copiava anche state.json e cancellava lo
# storico. E' successo due volte, il 10 e l'11 agosto 2026.
#
# Con una lista di esclusioni un file nuovo viene sincronizzato per default:
# e' l'inversione che impedisce il ripetersi del guasto.
#
# I dati (state.json, journal.csv, report/) vivono in ~/trading-dati sul Pi,
# fuori da questa cartella. Le esclusioni qui sotto sono comunque una seconda
# rete, per le installazioni non ancora migrate.
# -v e non --info=stats1: su macOS rsync e' openrsync, che non conosce --info.
rsync -avz \
    --exclude '.git/' --exclude '__pycache__/' --exclude '*.pyc' \
    --exclude '.venv/' --exclude 'venv/' --exclude '.DS_Store' --exclude '*.log' \
    --exclude 'state.json' --exclude 'state.json.tmp' \
    --exclude 'journal.csv' --exclude 'report/' \
    ./ "${PI_USER}@${PI_HOST}:${PI_DIR}/"

echo -e "${CYAN}→ Riavvio il servizio${NC}"
if ssh "${PI_USER}@${PI_HOST}" "sudo systemctl restart tradingbot@${PI_USER}" 2>/dev/null; then
    sleep 3
    STATO=$(ssh "${PI_USER}@${PI_HOST}" \
            "systemctl is-active tradingbot@${PI_USER}" 2>/dev/null || echo "sconosciuto")
    if [ "$STATO" = "active" ]; then
        echo -e "${GREEN}✓ Bot attivo e aggiornato${NC}"
    else
        echo -e "${RED}✗ Servizio in stato: ${STATO}${NC}"
        echo "  Controlla i log:"
        echo "  ssh ${PI_USER}@${PI_HOST} 'journalctl -u tradingbot@${PI_USER} -n 40'"
    fi
else
    echo -e "${CYAN}  Servizio non ancora installato — file copiati comunque.${NC}"
fi
