#!/usr/bin/env python3
"""
Moduli finti per pandas e numpy, a uso dei soli test.

PERCHE' ESISTE QUESTO FILE

core.py importa pandas e numpy, ma le funzioni che riguardano la contabilita'
dei portafogli non li usano: compaiono solo nelle annotazioni ('-> pd.DataFrame'),
che Python valuta quando la funzione viene DEFINITA. Basta quindi un oggetto
con l'attributo giusto perche' core.py si importi, e da li' _apri, _chiudi e
open_position diventano verificabili su una macchina senza pandas — cioe' su
questa, e sul Pi appena installato.

DUE TRAPPOLE, ENTRAMBE PAGATE

1. Registrare lo stub con sys.modules.setdefault() e' sbagliato: se pandas non
   e' ANCORA stato importato, setdefault non trova nulla e installa il finto
   sopra un pandas vero e perfettamente funzionante. installa() prova prima
   l'import reale, e si fa da parte se riesce.

2. Uno stub registrato resta in sys.modules per tutto il processo, quindi
   'import pandas' riesce anche nei test che pandas lo usano davvero.
   test_segnale.py si saltava da solo con un try/import; con lo stub in giro
   l'import riusciva e i test fallivano invece di saltarsi. Per questo lo stub
   porta una marca, ed e_finto() permette di riconoscerlo.
"""

import sys
import types

MARCA = "__tradebot_finto__"

# Solo cio' che serve a far valutare le annotazioni di core.py. Se un giorno
# servisse altro, il posto e' questo: uno stub che cresce in tre file diversi
# e' tre stub che divergono.
FINTI = (("numpy", {}), ("pandas", {"DataFrame": object}))


def installa_questi(elenco) -> list:
    """
    Registra i moduli finti dell'elenco, ma solo quelli davvero assenti.

    Restituisce i nomi sostituiti, cosi' un test puo' dire PERCHE' si sta
    saltando invece di limitarsi a saltarsi.
    """
    sostituiti = []
    for nome, attributi in elenco:
        if nome in sys.modules:
            continue
        try:
            __import__(nome)
            continue                  # quello vero c'e': non toccarlo
        except ImportError:
            pass
        m = types.ModuleType(nome)
        setattr(m, MARCA, True)
        for k, v in attributi.items():
            setattr(m, k, v)
        sys.modules[nome] = m
        sostituiti.append(nome)
    return sostituiti


def installa() -> list:
    """Registra pandas e numpy finti, se e solo se mancano."""
    return installa_questi(FINTI)


def e_finto(modulo) -> bool:
    """Vero se il modulo e' uno dei nostri stub, non la libreria vera."""
    return bool(getattr(modulo, MARCA, False))
