#!/usr/bin/env python3
"""
Test della persistenza.

Si lanciano cosi', senza dipendenze e senza rete:

    python3 -m unittest test_stato -v

Il test che conta piu' di tutti e' test_stato_mancante_con_journal_pieno_rifiuta:
descrive il guasto che ha distrutto 74 punti di storico e 8 posizioni aperte
l'11 agosto 2026. Se un giorno quel test diventa scomodo e viene tolto, il
guasto torna.
"""

import importlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CFG = {"capital": 100.0}


def carica_stato(dati_dir):
    """Reimporta stato.py con la cartella dati puntata dove vogliamo noi."""
    os.environ["TRADEBOT_DATI"] = dati_dir
    import stato
    return importlib.reload(stato)


class TestCartellaDati(unittest.TestCase):

    def test_env_ha_precedenza(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            self.assertEqual(s.DATA_DIR, os.path.abspath(d))
            self.assertEqual(s.STATE_FILE,
                             os.path.join(os.path.abspath(d), "state.json"))
            self.assertEqual(s.JOURNAL_FILE,
                             os.path.join(os.path.abspath(d), "journal.csv"))

    def test_migrazione_sposta_i_file(self):
        with tempfile.TemporaryDirectory() as dati, \
             tempfile.TemporaryDirectory() as codice:
            with open(os.path.join(codice, "state.json"), "w") as f:
                json.dump({"cash": 42.0}, f)
            with open(os.path.join(codice, "journal.csv"), "w") as f:
                f.write("ts,action\n")

            s = carica_stato(dati)
            mossi = s.migra_se_serve(codice)

            self.assertEqual(sorted(mossi), ["journal.csv", "state.json"])
            self.assertFalse(os.path.exists(os.path.join(codice, "state.json")))
            with open(s.STATE_FILE) as f:
                self.assertEqual(json.load(f)["cash"], 42.0)

    def test_dati_esistenti_vincono_sul_codice(self):
        """E' il caso dello 'scp -r' distratto: non deve sovrascrivere niente."""
        with tempfile.TemporaryDirectory() as dati, \
             tempfile.TemporaryDirectory() as codice:
            with open(os.path.join(dati, "state.json"), "w") as f:
                json.dump({"cash": 999.0}, f)      # lo stato vero
            with open(os.path.join(codice, "state.json"), "w") as f:
                json.dump({"cash": 100.0}, f)      # quello ricopiato per sbaglio

            s = carica_stato(dati)
            mossi = s.migra_se_serve(codice)

            self.assertEqual(mossi, [])
            with open(s.STATE_FILE) as f:
                self.assertEqual(json.load(f)["cash"], 999.0)


class TestCaricamento(unittest.TestCase):

    def test_installazione_pulita(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            st = s.load_state(CFG)
            self.assertEqual(st["cash"], 100.0)
            self.assertEqual(st["positions"], {})
            self.assertIn("created", st)

    def test_stato_esistente_viene_caricato(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            with open(s.STATE_FILE, "w") as f:
                json.dump({"cash": 55.5, "positions": {"X": {}}, "history": []}, f)
            self.assertEqual(s.load_state(CFG)["cash"], 55.5)

    def test_stato_mancante_con_journal_pieno_rifiuta(self):
        """
        Il cuore di tutto il lavoro: non ripartire MAI da zero in silenzio.

        E' il guasto dell'11 agosto 2026: lo stato sparisce, il bot riparte
        con 100 € puliti, e ogni misura di rendimento ricomincia senza dirlo.
        """
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            with open(s.JOURNAL_FILE, "w") as f:
                f.write("ts,action,pair\n2026-08-11T00:00:00,open,XXBTZEUR\n")
            with self.assertRaises(s.StatoPerduto):
                s.load_state(CFG)

    def test_via_di_uscita_esplicita(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            with open(s.JOURNAL_FILE, "w") as f:
                f.write("ts,action,pair\n2026-08-11T00:00:00,open,XXBTZEUR\n")
            os.environ["TRADEBOT_NUOVO_CONTO"] = "1"
            try:
                self.assertEqual(s.load_state(CFG)["cash"], 100.0)
            finally:
                del os.environ["TRADEBOT_NUOVO_CONTO"]

    def test_journal_con_sola_intestazione_non_blocca(self):
        """Installazione nuova che ha solo sfiorato il journal: deve partire."""
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            with open(s.JOURNAL_FILE, "w") as f:
                f.write("ts,action,pair\n")
            self.assertEqual(s.load_state(CFG)["cash"], 100.0)

    def test_default_riempiono_le_chiavi_mancanti(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            with open(s.STATE_FILE, "w") as f:
                json.dump({"cash": 20.0,
                           "history": [{"ts": "2026-01-01T00:00:00+00:00"}]}, f)
            st = s.load_state(CFG)
            self.assertIn("shadow_cash", st)
            self.assertIn("positions", st)
            self.assertIn("conferme", st)

    def test_created_non_viene_inventato(self):
        """
        Riempire 'created' con adesso farebbe sembrare azzerato uno stato
        che non lo e', e il controllo di continuita' urlerebbe a vuoto.
        """
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            with open(s.STATE_FILE, "w") as f:
                json.dump({"cash": 20.0,
                           "history": [{"ts": "2026-01-01T00:00:00+00:00"}]}, f)
            self.assertEqual(s.load_state(CFG)["created"],
                             "2026-01-01T00:00:00+00:00")

    def test_salvataggio_e_riletto_uguale(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            st = s.load_state(CFG)
            st["cash"] = 77.7
            s.save_state(st)
            self.assertEqual(s.load_state(CFG)["cash"], 77.7)

    def test_journal_scrive_intestazione_una_volta_sola(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            s.journal("open", pair="XXBTZEUR", price=1.0)
            s.journal("close", pair="XXBTZEUR", price=2.0)
            with open(s.JOURNAL_FILE) as f:
                righe = [r for r in f.read().splitlines() if r.strip()]
            self.assertEqual(len(righe), 3)          # intestazione + due operazioni
            self.assertTrue(righe[0].startswith("ts,action"))
            self.assertTrue(s.ha_operato())


if __name__ == "__main__":
    unittest.main()
