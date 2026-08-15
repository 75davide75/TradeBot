#!/usr/bin/env python3
"""
Test della registrazione dei portafogli secondari.

    python3 -m unittest test_portafogli -v

Il test che conta piu' di tutti e' test_ombra_e_ia_finiscono_nel_registro:
per mesi _apri e _chiudi hanno mosso due portafogli su tre senza scrivere una
riga da nessuna parte. Il registro raccontava un sistema con un portafoglio
solo. Se quel test sparisce, il confronto fra i tre torna a essere
un'opinione — che e' esattamente cio' che i tre portafogli esistono per non
essere.

core.py importa pandas e numpy, che qui non ci sono: finti.installa() li
sostituisce quando mancano, e si fa da parte quando ci sono. Il perche' e le
due trappole sono documentati in finti.py. Nessun test qui tocca la rete.
"""

import csv
import importlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import finti  # noqa: E402

finti.installa()


def carica_core(dati_dir):
    """Reimporta stato e core con la cartella dati puntata dove vogliamo noi."""
    os.environ["TRADEBOT_DATI"] = dati_dir
    import stato
    importlib.reload(stato)
    import core
    return importlib.reload(core)


def righe(percorso):
    with open(percorso, newline="") as f:
        return list(csv.DictReader(f))


class TestFinti(unittest.TestCase):
    """
    finti.py e' infrastruttura di test, ma il modo in cui puo' sbagliare non
    e' un problema di test: installare uno stub sopra un pandas vero
    romperebbe il segnale sul Pi, in silenzio e solo in produzione.
    """

    def test_non_sostituisce_una_libreria_vera(self):
        import json                             # importabile di sicuro, ovunque
        vero = sys.modules.pop("json")          # ...e ora fuori da sys.modules
        try:
            sostituiti = finti.installa_questi((("json", {"DataFrame": object}),))
            self.assertEqual(sostituiti, [])
            self.assertFalse(finti.e_finto(sys.modules["json"]))
            self.assertTrue(hasattr(sys.modules["json"], "loads"))
        finally:
            sys.modules["json"] = vero

    def test_sostituisce_una_libreria_assente_e_la_marca(self):
        nome = "libreria_che_non_esiste_davvero"
        try:
            sostituiti = finti.installa_questi(((nome, {"DataFrame": object}),))
            self.assertEqual(sostituiti, [nome])
            self.assertTrue(finti.e_finto(sys.modules[nome]))
        finally:
            sys.modules.pop(nome, None)


class TestRegistrazione(unittest.TestCase):

    def test_ombra_e_ia_finiscono_nel_registro(self):
        with tempfile.TemporaryDirectory() as d:
            c = carica_core(d)
            st = {"shadow_cash": 200.0, "ia_cash": 200.0}
            c.apri_ombra(st, "XXBTZEUR", -1.0, 63572.0, 25.0)
            c.apri_ia(st, "SOLEUR", 1.0, 76.09, 12.0, 0.48)
            r = righe(c.JOURNAL_FILE)
            self.assertEqual([x["wallet"] for x in r], ["ombra", "ia"])
            self.assertEqual([x["action"] for x in r], ["open", "open"])
            self.assertEqual(r[0]["pair"], "XXBTZEUR")
            self.assertEqual(float(r[0]["leverage"]), 1.0)
            self.assertEqual(float(r[1]["notional"]), 12.0)

    def test_chiusura_registra_il_cash_del_proprio_portafoglio(self):
        """
        close_position scrive state['cash'] in 'equity' (core.py:328). I
        secondari devono scrivere il PROPRIO cash: con quello del reale, la
        colonna che dovrebbe separare i tre li renderebbe indistinguibili.
        """
        with tempfile.TemporaryDirectory() as d:
            c = carica_core(d)
            st = {"cash": 999.0, "shadow_cash": 200.0}
            c.apri_ombra(st, "XXBTZEUR", 1.0, 100.0, 25.0)
            c.chiudi_ombra(st, "XXBTZEUR", 110.0)
            chiusura = righe(c.JOURNAL_FILE)[-1]
            self.assertEqual(chiusura["action"], "close")
            self.assertEqual(chiusura["wallet"], "ombra")
            self.assertNotEqual(float(chiusura["equity"]), 999.0)
            self.assertAlmostEqual(float(chiusura["equity"]),
                                   round(st["shadow_cash"], 2), places=2)

    def test_chiusura_di_una_posizione_assente_non_registra(self):
        """_chiudi esce con 0.0 se il mercato non c'e': niente riga fantasma."""
        with tempfile.TemporaryDirectory() as d:
            c = carica_core(d)
            st = {"shadow_cash": 200.0}
            self.assertEqual(c.chiudi_ombra(st, "MAI_APERTO", 1.0), 0.0)
            self.assertFalse(os.path.exists(c.JOURNAL_FILE))

    def test_il_reale_resta_marcato_reale(self):
        with tempfile.TemporaryDirectory() as d:
            c = carica_core(d)
            st = {"cash": 200.0, "positions": {}}
            c.open_position(st, "ADAEUR", -1.0, 0.18, 8.74, 0.35, "segnale")
            self.assertEqual(righe(c.JOURNAL_FILE)[0]["wallet"], "reale")


if __name__ == "__main__":
    unittest.main()
