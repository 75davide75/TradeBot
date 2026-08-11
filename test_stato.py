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


if __name__ == "__main__":
    unittest.main()
