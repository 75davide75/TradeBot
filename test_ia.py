#!/usr/bin/env python3
"""
Test del livello IA e del terzo portafoglio.

    python3 -m unittest test_ia -v

Il test che conta piu' di tutti e' test_simboli_inventati_vengono_scartati.
Un modello linguistico risponde sempre, anche quando dovrebbe dire "non lo
so", e nella risposta puo' comparire un mercato che non esiste. Se quel
simbolo arrivasse fino ad apri_ia, il portafoglio aprirebbe una posizione su
un prezzo inventato e ogni misura successiva sarebbe spazzatura.

Qui non c'e' nessuna chiamata di rete: il client viene sostituito con un
finto che risponde quello che decidiamo noi. Un test che dipende da cosa
risponde oggi un modello non e' un test, e' un sondaggio.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analisi  # noqa: E402

CFG = {"anthropic_api_key": "finta-per-i-test"}

_UNIVERSO_VERO = None


def setUpModule():
    """
    Questi test descrivono il livello IA SENZA una scelta su file.

    Ma stato_ia() considera il livello attivo quando docs/ia_universo.json e'
    fresco, anche senza chiave API (analisi.py:119-129), e quel file lo scrive
    un'istanza schedulata ogni giorno. Dal primo giorno in cui l'ha scritto,
    undici test qui hanno cominciato a vedere un livello ACCESO dove ne
    descrivevano uno spento, arrivando a 'import anthropic' — che su una
    macchina di sviluppo non c'e'.

    L'accoppiamento era involontario: nessun test di questo file legge
    UNIVERSO_FILE di proposito. Un test che passa o fallisce a seconda di cosa
    ha prodotto stamattina un processo schedulato non sta misurando il codice.

    Qui il percorso viene puntato su un file inesistente per la durata del
    modulo. Un test che voglia provare la lettura da file dovra' impostarselo
    da solo, e sara' esplicito nel farlo.
    """
    global _UNIVERSO_VERO
    _UNIVERSO_VERO = analisi.UNIVERSO_FILE
    analisi.UNIVERSO_FILE = os.path.join(
        tempfile.gettempdir(), "tradebot-nessuna-scelta-su-file.json")


def tearDownModule():
    analisi.UNIVERSO_FILE = _UNIVERSO_VERO


class Blocco:
    def __init__(self, testo, tipo="text"):
        self.type = tipo
        self.text = testo


class Risposta:
    def __init__(self, testo, stop_reason="end_turn", tipo="text"):
        self.content = [Blocco(testo, tipo)]
        self.stop_reason = stop_reason


class ClienteFinto:
    """Sostituisce il client Anthropic: restituisce cio' che gli diciamo."""

    def __init__(self, risposta=None, eccezione=None):
        self.risposta, self.eccezione = risposta, eccezione
        self.chiamate = []
        self.messages = self

    def create(self, **kw):
        self.chiamate.append(kw)
        if self.eccezione:
            raise self.eccezione
        return self.risposta


class BaseIA(unittest.TestCase):

    def cliente(self, *a, **kw):
        """Installa un client finto al posto di quello vero."""
        c = ClienteFinto(*a, **kw)
        self.originale = analisi._cliente
        analisi._cliente = lambda cfg: c
        self.addCleanup(setattr, analisi, "_cliente", self.originale)
        return c


# --------------------------------------------------------------------------
# Degradazione: senza chiave o senza libreria, tutto deve restare in piedi
# --------------------------------------------------------------------------
class TestSenzaIA(unittest.TestCase):

    def setUp(self):
        self.chiave = os.environ.pop("ANTHROPIC_API_KEY", None)
        if self.chiave is not None:
            self.addCleanup(os.environ.__setitem__,
                            "ANTHROPIC_API_KEY", self.chiave)

    def test_senza_chiave_il_riassunto_e_none(self):
        self.assertIsNone(analisi.riassunto({}, {"equity_eur": 200}))

    def test_senza_chiave_l_universo_e_none(self):
        self.assertIsNone(analisi.universo_proposto({}, {"XXBTZEUR": {}}, 3))

    def test_la_chiave_puo_venire_dall_ambiente(self):
        os.environ["ANTHROPIC_API_KEY"] = "x"
        self.addCleanup(os.environ.pop, "ANTHROPIC_API_KEY", None)
        # Non deve piu' uscire per mancanza di chiave: se la libreria non c'e'
        # esce lo stesso, ma per un motivo diverso e stampato.
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.skipTest("libreria anthropic non installata")
        self.assertIsNotNone(analisi._cliente({}))


# --------------------------------------------------------------------------
# Riassunto: spiega, e se non puo' tace
# --------------------------------------------------------------------------
class TestRiassunto(BaseIA):

    def test_restituisce_il_testo(self):
        self.cliente(Risposta("Giornata senza operazioni."))
        self.assertEqual(analisi.riassunto(CFG, {"equity_eur": 200}),
                         "Giornata senza operazioni.")

    def test_salta_i_blocchi_di_ragionamento(self):
        c = self.cliente(Risposta("visibile"))
        c.risposta.content.insert(0, Blocco("ragionamento", tipo="thinking"))
        self.assertEqual(analisi.riassunto(CFG, {}), "visibile")

    def test_un_rifiuto_non_diventa_un_riassunto(self):
        self.cliente(Risposta("", stop_reason="refusal"))
        self.assertIsNone(analisi.riassunto(CFG, {}))

    def test_un_errore_di_rete_non_propaga(self):
        # Il messaggio delle 9 deve partire anche se l'IA non risponde: la
        # diagnostica vale piu' del commento alla diagnostica.
        self.cliente(eccezione=RuntimeError("timeout"))
        self.assertIsNone(analisi.riassunto(CFG, {}))

    def test_una_risposta_vuota_e_none_non_stringa_vuota(self):
        self.cliente(Risposta("   "))
        self.assertIsNone(analisi.riassunto(CFG, {}))


# --------------------------------------------------------------------------
# Universo proposto: qui il modello puo' fare danni, quindi si valida tutto
# --------------------------------------------------------------------------
CANDIDATI = {"XXBTZEUR": {"spread_pct": 0.01},
             "XETHZEUR": {"spread_pct": 0.02},
             "SOLEUR": {"spread_pct": 0.03}}


def scelta(mercati, fiducia="media"):
    return Risposta(json.dumps({"mercati": mercati,
                                "motivazione": "perche' si", "fiducia": fiducia}))


class TestUniversoProposto(BaseIA):

    def test_scelta_valida_passa(self):
        self.cliente(scelta(["XXBTZEUR", "SOLEUR"]))
        r = analisi.universo_proposto(CFG, CANDIDATI, 2)
        self.assertEqual(r["mercati"], ["XXBTZEUR", "SOLEUR"])
        self.assertEqual(r["fiducia"], "media")

    def test_simboli_inventati_vengono_scartati(self):
        # IL test. Un mercato che non esiste non deve arrivare ad apri_ia.
        self.cliente(scelta(["XXBTZEUR", "DOGEMOON", "SOLEUR"]))
        r = analisi.universo_proposto(CFG, CANDIDATI, 3)
        self.assertEqual(r["mercati"], ["XXBTZEUR", "SOLEUR"])

    def test_tutti_inventati_annulla_la_scelta(self):
        # Meglio nessun universo che un universo finto: senza universo il
        # portafoglio sperimentale semplicemente non opera.
        self.cliente(scelta(["PIPPO", "PLUTO"]))
        self.assertIsNone(analisi.universo_proposto(CFG, CANDIDATI, 2))

    def test_non_puo_chiedere_piu_mercati_del_dovuto(self):
        self.cliente(scelta(["XXBTZEUR", "XETHZEUR", "SOLEUR"]))
        r = analisi.universo_proposto(CFG, CANDIDATI, 2)
        self.assertEqual(len(r["mercati"]), 2)

    def test_json_malformato_non_esplode(self):
        self.cliente(Risposta("non sono json"))
        self.assertIsNone(analisi.universo_proposto(CFG, CANDIDATI, 2))

    def test_un_rifiuto_non_sceglie_niente(self):
        self.cliente(Risposta("{}", stop_reason="refusal"))
        self.assertIsNone(analisi.universo_proposto(CFG, CANDIDATI, 2))

    def test_senza_candidati_non_chiama_nemmeno(self):
        c = self.cliente(scelta(["XXBTZEUR"]))
        self.assertIsNone(analisi.universo_proposto(CFG, {}, 3))
        self.assertEqual(c.chiamate, [])

    def test_chiede_l_uscita_strutturata(self):
        # Senza schema la risposta sarebbe prosa, e il parsing diventerebbe
        # indovinare. Con lo schema o e' valida o fallisce subito.
        c = self.cliente(scelta(["XXBTZEUR"]))
        analisi.universo_proposto(CFG, CANDIDATI, 1)
        formato = c.chiamate[0]["output_config"]["format"]
        self.assertEqual(formato["type"], "json_schema")
        self.assertEqual(formato["schema"]["required"],
                         ["mercati", "motivazione", "fiducia"])

    def test_il_modello_si_puo_cambiare_da_config(self):
        # Su un conto da 200 EUR il costo dell'IA conta: chi vuole spendere
        # meno deve poterlo fare senza toccare il codice.
        c = self.cliente(scelta(["XXBTZEUR"]))
        analisi.universo_proposto(dict(CFG, anthropic_model="claude-haiku-4-5"),
                                  CANDIDATI, 1)
        self.assertEqual(c.chiamate[0]["model"], "claude-haiku-4-5")

    def test_senza_indicazioni_usa_il_modello_predefinito(self):
        vecchio = os.environ.pop("ANTHROPIC_MODEL", None)
        if vecchio is not None:
            self.addCleanup(os.environ.__setitem__, "ANTHROPIC_MODEL", vecchio)
        c = self.cliente(scelta(["XXBTZEUR"]))
        analisi.universo_proposto(CFG, CANDIDATI, 1)
        self.assertEqual(c.chiamate[0]["model"], analisi.MODELLO)

    def test_i_candidati_arrivano_al_modello(self):
        c = self.cliente(scelta(["XXBTZEUR"]))
        analisi.universo_proposto(CFG, CANDIDATI, 1)
        inviato = json.loads(c.chiamate[0]["messages"][0]["content"])
        self.assertEqual(inviato["scegline"], 1)
        self.assertEqual(set(inviato["mercati_disponibili"]), set(CANDIDATI))


# --------------------------------------------------------------------------
# Il terzo portafoglio non deve toccare gli altri due
# --------------------------------------------------------------------------
try:
    import core
    CORE = True
except ImportError:
    CORE = False


@unittest.skipUnless(CORE, "core richiede pandas e numpy")
class TestPortafoglioIA(unittest.TestCase):

    def stato(self):
        return {"cash": 200.0, "positions": {},
                "shadow_cash": 200.0, "shadow_positions": {},
                "ia_cash": 200.0, "ia_positions": {}}

    def test_aprire_nell_ia_non_tocca_il_vero_ne_l_ombra(self):
        s = self.stato()
        core.apri_ia(s, "XXBTZEUR", 1.0, 100.0, 50.0, 0.5)
        self.assertEqual(s["cash"], 200.0)
        self.assertEqual(s["shadow_cash"], 200.0)
        self.assertEqual(s["positions"], {})
        self.assertEqual(s["shadow_positions"], {})
        self.assertIn("XXBTZEUR", s["ia_positions"])
        self.assertLess(s["ia_cash"], 200.0)      # ha pagato le commissioni

    def test_apertura_segna_l_avvio(self):
        # Finche' non e' avviato, la dashboard non deve disegnare la linea.
        s = self.stato()
        self.assertFalse(s.get("ia_avviato"))
        core.apri_ia(s, "XXBTZEUR", 1.0, 100.0, 50.0, 0.5)
        self.assertTrue(s["ia_avviato"])

    def test_chiudere_un_mercato_mai_aperto_non_fa_niente(self):
        s = self.stato()
        self.assertEqual(core.chiudi_ia(s, "SOLEUR", 100.0), 0.0)
        self.assertEqual(s["ia_cash"], 200.0)

    def test_equity_senza_posizioni_e_la_cassa(self):
        s = self.stato()
        self.assertEqual(core.equity_ia(s, {}), 200.0)

    def test_un_guadagno_si_vede_nell_equity(self):
        s = self.stato()
        core.apri_ia(s, "XXBTZEUR", 1.0, 100.0, 50.0, 0.5)
        eq_fermo = core.equity_ia(s, {"XXBTZEUR": 100.0})
        eq_su = core.equity_ia(s, {"XXBTZEUR": 110.0})
        self.assertAlmostEqual(eq_su - eq_fermo, 5.0, places=4)   # 10% di 50

    def test_uno_short_guadagna_quando_il_prezzo_scende(self):
        s = self.stato()
        core.apri_ia(s, "XXBTZEUR", -1.0, 100.0, 50.0, 0.5)
        eq_fermo = core.equity_ia(s, {"XXBTZEUR": 100.0})
        self.assertGreater(core.equity_ia(s, {"XXBTZEUR": 90.0}), eq_fermo)

    def test_un_prezzo_mancante_non_azzera_la_posizione(self):
        # Se il prezzo non arriva, la posizione va contata al valore
        # d'ingresso, non a zero: un buco di rete non e' una perdita.
        s = self.stato()
        core.apri_ia(s, "XXBTZEUR", 1.0, 100.0, 50.0, 0.5)
        self.assertAlmostEqual(core.equity_ia(s, {}), s["ia_cash"], places=6)


if __name__ == "__main__":
    unittest.main()
