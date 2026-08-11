#!/usr/bin/env python3
"""
Test del segnale. Richiede pandas e numpy, quindi si salta da solo dove non
ci sono (per esempio sul Pi appena installato).

    python3 -m unittest test_segnale -v

Il test che conta e' test_la_candela_aperta_non_influenza_il_segnale: descrive
il bug per cui il segnale oscillava durante la giornata seguendo il prezzo del
momento invece della chiusura, generando 1,8 falsi cambi per ogni cambio vero.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import pandas as pd
    PANDAS = True
except ImportError:
    PANDAS = False


def serie(prezzi, fino_a_oggi=True):
    """DataFrame giornaliero che finisce oggi (candela aperta) o ieri."""
    fine = datetime.now(timezone.utc).date()
    if not fino_a_oggi:
        fine -= timedelta(days=1)
    giorni = pd.date_range(end=pd.Timestamp(fine), periods=len(prezzi), freq="D")
    return pd.DataFrame({"close": prezzi}, index=giorni)


@unittest.skipUnless(PANDAS, "pandas non disponibile")
class TestCandelaAperta(unittest.TestCase):

    def test_la_candela_di_oggi_viene_scartata(self):
        df = serie([100.0] * 70, fino_a_oggi=True)
        from core import solo_candele_chiuse
        self.assertEqual(len(solo_candele_chiuse(df)), 69)

    def test_una_serie_gia_chiusa_resta_intera(self):
        df = serie([100.0] * 70, fino_a_oggi=False)
        from core import solo_candele_chiuse
        self.assertEqual(len(solo_candele_chiuse(df)), 70)

    def test_la_candela_aperta_non_influenza_il_segnale(self):
        """
        Il cuore della correzione: durante la giornata il prezzo si muove, ma
        il segnale non deve muoversi con lui. Prima cambiava, e poi rientrava
        da solo alla chiusura — pagando due giri di commissioni per niente.
        """
        from core import signal_momentum
        # 70 giorni in salita lenta: momentum a 60 giorni positivo
        base = [100.0 + i * 0.5 for i in range(69)]

        # oggi il prezzo crolla del 40%: la candela aperta direbbe SHORT
        crollo = serie(base + [70.0], fino_a_oggi=True)
        # oggi il prezzo esplode: direbbe LONG comunque
        rally = serie(base + [500.0], fino_a_oggi=True)

        self.assertEqual(signal_momentum(crollo, n=60),
                         signal_momentum(rally, n=60),
                         "il prezzo di oggi sta ancora cambiando il segnale")
        self.assertEqual(signal_momentum(crollo, n=60), 1.0)

    def test_il_segnale_segue_le_chiusure_vere(self):
        """Se la tendenza si inverte davvero, il segnale deve accorgersene."""
        from core import signal_momentum
        salita = [100.0 + i for i in range(70)]
        discesa = [100.0 - i for i in range(70)]
        self.assertEqual(signal_momentum(serie(salita), n=60), 1.0)
        self.assertEqual(signal_momentum(serie(discesa), n=60), -1.0)

    def test_senza_short_resta_flat_invece_di_vendere(self):
        from core import signal_momentum
        discesa = [100.0 - i for i in range(70)]
        self.assertEqual(signal_momentum(serie(discesa), n=60, allow_short=False), 0.0)

    def test_storico_troppo_corto_non_inventa_un_segnale(self):
        from core import signal_momentum
        self.assertEqual(signal_momentum(serie([100.0] * 10), n=60), 0.0)


if __name__ == "__main__":
    unittest.main()
