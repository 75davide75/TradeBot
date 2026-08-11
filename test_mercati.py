#!/usr/bin/env python3
"""
Test del filtro di negoziabilita'. Solo libreria standard.

    python3 -m unittest test_mercati -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mercati import scarta, valuta


def ticker(bid=100.0, ask=100.05, mark=100.0, volume=5_000_000.0, **extra):
    t = {"bid": bid, "ask": ask, "markPrice": mark, "volumeQuote": volume}
    t.update(extra)
    return t


class TestValuta(unittest.TestCase):

    def test_mercato_sano_passa(self):
        ok, motivo = valuta(ticker())
        self.assertTrue(ok, motivo)

    def test_spread_troppo_largo(self):
        # 1,28% come MUBARAK l'11 agosto 2026
        ok, motivo = valuta(ticker(bid=100.0, ask=101.28))
        self.assertFalse(ok)
        self.assertIn("spread", motivo)

    def test_spread_al_limite_passa(self):
        """La soglia e' un massimo incluso, non un divieto a toccarla."""
        ok, _ = valuta(ticker(bid=100.0, ask=100.15))   # esattamente 0,15%
        self.assertTrue(ok)

    def test_volume_troppo_basso(self):
        ok, motivo = valuta(ticker(volume=1_000.0))
        self.assertFalse(ok)
        self.assertIn("volume", motivo)

    def test_contratto_sospeso(self):
        ok, motivo = valuta(ticker(suspended=True))
        self.assertFalse(ok)
        self.assertIn("sospeso", motivo)

    def test_solo_ordini_passivi(self):
        """postOnly significa che non si puo' entrare a mercato: inutile."""
        ok, motivo = valuta(ticker(postOnly=True))
        self.assertFalse(ok)

    def test_mercato_delistato_non_ha_ticker(self):
        ok, motivo = valuta(None)
        self.assertFalse(ok)
        self.assertIn("nessun dato", motivo)

    def test_book_vuoto(self):
        self.assertFalse(valuta(ticker(bid=0, ask=0))[0])

    def test_book_incrociato(self):
        """ask sotto bid: dato corrotto, non un'occasione."""
        self.assertFalse(valuta(ticker(bid=101.0, ask=100.0))[0])

    def test_prezzo_mancante(self):
        self.assertFalse(valuta(ticker(mark=None, last=None))[0])

    def test_volume_assente_non_scarta(self):
        """Se Kraken non manda il volume non lo si puo' usare per escludere."""
        t = ticker(); del t["volumeQuote"]
        self.assertTrue(valuta(t)[0])

    def test_soglie_personalizzabili(self):
        stretto = {"spread_massimo": 0.0001}
        self.assertFalse(valuta(ticker(), stretto)[0])


class TestScarta(unittest.TestCase):

    def test_divide_universo_e_spiega_le_esclusioni(self):
        mappa = {"AAA": "PF_AAAUSD", "BBB": "PF_BBBUSD", "CCC": "PF_CCCUSD"}
        tickers = {
            "PF_AAAUSD": ticker(),                        # sano
            "PF_BBBUSD": ticker(bid=100.0, ask=102.0),    # spread 2%
            # PF_CCCUSD assente: delistato
        }
        tenuti, fuori = scarta(["AAA", "BBB", "CCC"], tickers, mappa)
        self.assertEqual(tenuti, ["AAA"])
        self.assertEqual(set(fuori), {"BBB", "CCC"})
        self.assertIn("spread", fuori["BBB"])

    def test_universo_tutto_sano_non_scarta_nulla(self):
        mappa = {"AAA": "PF_AAAUSD"}
        tenuti, fuori = scarta(["AAA"], {"PF_AAAUSD": ticker()}, mappa)
        self.assertEqual(tenuti, ["AAA"])
        self.assertEqual(fuori, {})


if __name__ == "__main__":
    unittest.main()
