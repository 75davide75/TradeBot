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


class TestCapitale(unittest.TestCase):
    """
    Alzare 'capital' in configurazione e' un VERSAMENTO, non un capitale
    iniziale diverso. Se il denominatore dei rendimenti salisse senza che
    salga anche la cassa, la dashboard mostrerebbe una perdita mai avvenuta.
    """

    def _conto_avviato(self, s, cash=100.0, capitale=100.0):
        st = s.load_state({"capital": capitale})
        st["cash"] = cash
        st["history"] = [{"ts": "2026-08-01T00:00:00+00:00", "equity": capitale}]
        s.save_state(st)
        return st

    def test_versamento_aumenta_cassa_e_denominatore(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            self._conto_avviato(s, cash=97.0, capitale=100.0)
            st = s.load_state({"capital": 200.0})
            delta = s.adegua_capitale(st, {"capital": 200.0})
            self.assertEqual(delta, 100.0)
            self.assertAlmostEqual(st["cash"], 197.0)
            self.assertEqual(st["capitale_versato"], 200.0)

    def test_il_rendimento_non_diventa_una_perdita_finta(self):
        """Il bug che questo test impedisce: 100/200-1 = -50% dal nulla."""
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            self._conto_avviato(s, cash=100.0, capitale=100.0)
            st = s.load_state({"capital": 200.0})
            s.adegua_capitale(st, {"capital": 200.0})
            rendimento = st["cash"] / st["capitale_versato"] - 1
            self.assertAlmostEqual(rendimento, 0.0)

    def test_peak_equity_sale_col_versamento(self):
        """Altrimenti il kill switch vede un drawdown del 50% e ferma tutto."""
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            self._conto_avviato(s, cash=100.0, capitale=100.0)
            st = s.load_state({"capital": 200.0})
            prima = st["peak_equity"]
            s.adegua_capitale(st, {"capital": 200.0})
            self.assertAlmostEqual(st["peak_equity"], prima + 100.0)
            dd = st["cash"] / st["peak_equity"] - 1
            self.assertAlmostEqual(dd, 0.0)

    def test_e_idempotente(self):
        """Il bot lo chiama a ogni avvio: non deve versare due volte."""
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            self._conto_avviato(s, cash=100.0, capitale=100.0)
            st = s.load_state({"capital": 200.0})
            self.assertEqual(s.adegua_capitale(st, {"capital": 200.0}), 100.0)
            self.assertEqual(s.adegua_capitale(st, {"capital": 200.0}), 0.0)
            self.assertAlmostEqual(st["cash"], 200.0)

    def test_ridurre_il_capitale_non_preleva_da_solo(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            self._conto_avviato(s, cash=100.0, capitale=100.0)
            st = s.load_state({"capital": 50.0})
            self.assertEqual(s.adegua_capitale(st, {"capital": 50.0}), 0.0)
            self.assertAlmostEqual(st["cash"], 100.0)

    def test_versamento_finisce_nel_journal(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            self._conto_avviato(s, cash=100.0, capitale=100.0)
            st = s.load_state({"capital": 200.0})
            s.adegua_capitale(st, {"capital": 200.0})
            with open(s.JOURNAL_FILE) as f:
                testo = f.read()
            self.assertIn("deposit", testo)
            self.assertIn("100.0", testo)


class TestOmbra(unittest.TestCase):
    """
    Il portafoglio ombra serve a rispondere a 'il volatility targeting aiuta?'.
    Perche' quel confronto significhi qualcosa, l'ombra deve partire dallo
    stesso capitale e ricevere gli stessi versamenti: qualunque differenza
    iniziale si trascina per sempre nel confronto.
    """

    def test_il_versamento_arriva_anche_all_ombra(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            st = s.load_state({"capital": 100.0})
            st["cash"] = 100.0
            st["shadow_cash"] = 100.0
            s.save_state(st)

            st = s.load_state({"capital": 200.0})
            s.adegua_capitale(st, {"capital": 200.0})
            self.assertAlmostEqual(st["cash"], 200.0)
            self.assertAlmostEqual(st["shadow_cash"], 200.0,
                                   msg="l'ombra non ha ricevuto il versamento")

    def test_ombra_mai_avviata_viene_allineata(self):
        """Caso di un conto gia' in corso a cui l'ombra viene aggiunta dopo."""
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            st = s.load_state({"capital": 200.0})
            st["capitale_versato"] = 200.0
            st["shadow_cash"] = 100.0          # rimasta indietro
            self.assertTrue(s.allinea_ombra_se_ferma(st))
            self.assertAlmostEqual(st["shadow_cash"], 200.0)

    def test_ombra_gia_avviata_non_viene_toccata(self):
        """Riallinearla cancellerebbe il P&L che ha accumulato."""
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            st = s.load_state({"capital": 200.0})
            st["capitale_versato"] = 200.0
            st["shadow_cash"] = 173.5          # ha perso operando: e' un dato
            st["shadow_avviato"] = True
            self.assertFalse(s.allinea_ombra_se_ferma(st))
            self.assertAlmostEqual(st["shadow_cash"], 173.5)

    def test_ombra_gia_allineata_non_fa_nulla(self):
        with tempfile.TemporaryDirectory() as d:
            s = carica_stato(d)
            st = s.load_state({"capital": 200.0})
            st["capitale_versato"] = 200.0
            st["shadow_cash"] = 200.0
            self.assertFalse(s.allinea_ombra_se_ferma(st))


if __name__ == "__main__":
    unittest.main()
