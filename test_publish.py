#!/usr/bin/env python3
"""
Test di cio' che esce in docs/data.json.

    python3 -m unittest test_publish -v

Il repo e' pubblico: il test che conta piu' di tutti e'
test_campi_fuori_whitelist_non_escono. Una whitelist che smette di essere una
whitelist non da' nessun segnale — funziona benissimo, pubblicando troppo, e
lo scopre qualcun altro.

publish.py importa core, che importa pandas e numpy: qui non ci sono, e
finti.installa() li sostituisce (vedi finti.py). Nessun test esegue
publish.main(): scriverebbe davvero docs/data.json, e lo pubblicherebbe.
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


def carica_publish(dati_dir):
    os.environ["TRADEBOT_DATI"] = dati_dir
    import stato
    importlib.reload(stato)
    import core
    importlib.reload(core)
    import publish
    return importlib.reload(publish)


POSIZIONE = {"side": -1.0, "entry": 63572.22, "notional": 18.234,
             "leverage": 0.73, "opened": "2026-08-12T00:23:02+00:00"}


class TestWhitelist(unittest.TestCase):

    def test_campi_fuori_whitelist_non_escono(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            grezze = {"XXBTZEUR": dict(POSIZIONE,
                                       note_private="non deve uscire",
                                       chiave_api="nemmeno")}
            fuori = p.posizioni_pubblicabili(grezze)
            self.assertEqual(set(fuori["XXBTZEUR"]),
                             {"side", "entry", "notional", "leverage", "opened"})

    def test_nozionale_arrotondato(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            fuori = p.posizioni_pubblicabili({"XXBTZEUR": POSIZIONE})
            self.assertEqual(fuori["XXBTZEUR"]["notional"], 18.23)


class TestBloccoWallet(unittest.TestCase):

    def test_i_tre_portafogli_escono(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            st = {"positions": {"XXBTZEUR": POSIZIONE},
                  "shadow_positions": {"XXBTZEUR": dict(POSIZIONE, notional=25.0)},
                  "shadow_avviato": True}
            w = p.blocco_wallet(st, 200.66, 201.48, None)
            self.assertEqual(set(w), {"reale", "ombra", "ia"})
            self.assertEqual(w["reale"]["equity"], 200.66)
            self.assertEqual(w["ombra"]["posizioni"]["XXBTZEUR"]["notional"], 25.0)

    def test_stato_senza_le_chiavi_dei_secondari(self):
        """
        Uno state.json scritto da una versione precedente non ha
        shadow_positions ne' ia_positions. La prima riga che le legge come
        state['...'] e' un KeyError — stessa classe di bug documentata a
        core.py:56 e gia' pagata due volte in questo progetto.
        """
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            w = p.blocco_wallet({"cash": 100.0}, 100.0, None, None)
            self.assertEqual(w["ombra"]["posizioni"], {})
            self.assertIsNone(w["ombra"]["equity"])

    def test_avviato_distingue_il_mai_partito_dal_tutto_chiuso(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            mai = p.blocco_wallet({}, 100.0, None, None)
            self.assertFalse(mai["ia"]["avviato"])
            chiuso = p.blocco_wallet({"ia_avviato": True}, 100.0, None, 97.5)
            self.assertTrue(chiuso["ia"]["avviato"])
            self.assertEqual(chiuso["ia"]["posizioni"], {})


class TestInizioStorico(unittest.TestCase):

    INTESTAZIONE = ("ts,action,pair,side,price,notional,leverage,equity,"
                    "reason,confirmed,wallet\r\n")

    def _scrivi(self, percorso, righe):
        with open(percorso, "w", newline="") as f:
            f.write(self.INTESTAZIONE)
            for r in righe:
                f.write(r + "\r\n")

    def test_e_la_prima_riga_marcata(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            self._scrivi(p.JOURNAL_FILE, [
                "2026-08-11T11:28:15+00:00,open,XETHZEUR,1.0,1890.0,6.25,0.5,,segnale,True",
                "2026-08-15T09:00:00+00:00,open,XXBTZEUR,-1.0,63572.0,18.2,0.7,,segnale,True,reale",
                "2026-08-15T09:00:01+00:00,open,XXBTZEUR,-1.0,63572.0,25.0,1.0,,rispecchia,True,ombra",
            ])
            self.assertEqual(p.inizio_storico_wallet(p.JOURNAL_FILE),
                             "2026-08-15T09:00:00+00:00")

    def test_registro_tutto_vecchio_non_ha_inizio(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            self._scrivi(p.JOURNAL_FILE, [
                "2026-08-11T11:28:15+00:00,open,XETHZEUR,1.0,1890.0,6.25,0.5,,segnale,True",
            ])
            self.assertIsNone(p.inizio_storico_wallet(p.JOURNAL_FILE))

    def test_registro_assente(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            self.assertIsNone(p.inizio_storico_wallet(
                os.path.join(d, "non-esiste.csv")))


class TestConteggioOperazioni(unittest.TestCase):
    """
    n_ops alimenta l'avviso "sotto le ~30 operazioni chiuse qualunque
    risultato e' statisticamente indistinguibile dal caso". Contando anche le
    chiusure di ombra e IA — che rispecchiano e affiancano quelle del reale —
    il numero triplicherebbe e l'avviso sparirebbe con un terzo delle prove
    che dichiara di richiedere. Sarebbe una soglia statistica aggirata da un
    cambiamento di contabilita', il che e' peggio che non averla.
    """

    INTESTAZIONE = ("ts,action,pair,side,price,notional,leverage,equity,"
                    "reason,confirmed,wallet\r\n")

    def test_conta_le_chiusure_del_solo_reale(self):
        with tempfile.TemporaryDirectory() as d:
            p = carica_publish(d)
            with open(p.JOURNAL_FILE, "w", newline="") as f:
                f.write(self.INTESTAZIONE)
                for w in ("reale", "ombra", "ia"):
                    f.write(f"2026-08-15T09:00:00+00:00,close,XXBTZEUR,-1.0,"
                            f"63572.0,18.2,0.7,200.0,stop,True,{w}\r\n")
                # Riga d'epoca precedente alla colonna: e' del reale.
                f.write("2026-08-11T09:00:00+00:00,close,XETHZEUR,1.0,1890.0,"
                        "6.25,0.5,100.0,segnale,True\r\n")
            dati = p.costruisci()
            self.assertEqual(dati["n_ops"], 2)
            self.assertEqual(len(dati["ops"]), 4)   # la tabella le mostra tutte


if __name__ == "__main__":
    unittest.main()
