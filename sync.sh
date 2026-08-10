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

# I file di stato NON vengono toccati: state.json, journal.csv e report/
# vivono sul Pi e contengono la storia reale. Sovrascriverli cancellerebbe
# i dati che stiamo raccogliendo, che sono l'unica cosa di valore qui.
scp core.py bot.py daily_review.py backtest.py config.json \
    "${PI_USER}@${PI_HOST}:${PI_DIR}/"

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
