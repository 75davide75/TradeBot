#!/usr/bin/env python3
"""
Il livello IA: spiega e propone, non decide da solo.

DUE COMPITI, TENUTI SEPARATI DI PROPOSITO

1. riassunto()  — legge stato, journal e metriche e scrive in italiano cosa e'
   successo e cosa e' anomalo. E' un compito di sintesi, dove i modelli
   linguistici sono davvero bravi, e ha rischio zero perche' non tocca nessuna
   decisione. Finisce nel messaggio delle 9.

2. universo_proposto() — sceglie i mercati per il TERZO portafoglio, quello
   sperimentale. Non tocca il portafoglio vero ne' l'ombra.

PERCHE' LA SCELTA DEI MERCATI STA SOLO NEL PORTAFOGLIO SPERIMENTALE

Un modello linguistico non e' verificabile in anticipo come lo e' un segnale
numerico: e' addestrato su testo storico e lo ricorda, quindi qualunque
backtest e' contaminato (correlazioni fino al 100% su rendimenti annuali
dell'S&P 500 sono documentate). Non si puo' sapere se funziona prima di
usarlo. E risponde sempre: chiedigli quali mercati sembrano promettenti e
otterrai una lista motivata ogni singolo giorno, anche quando la risposta
onesta e' "non lo so".

Quindi si misura in avanti, in parallelo, con soldi finti — che e' esattamente
il motivo per cui esiste l'infrastruttura dei portafogli affiancati.

DEGRADA IN SILENZIO

Senza chiave API o senza la libreria 'anthropic' installata, ogni funzione
qui restituisce None e il resto del sistema continua identico. L'IA e' un
accessorio: se manca, il bot funziona uguale.
"""

import json
import os

MODELLO = "claude-opus-5"


def _cliente(cfg: dict):
    """Restituisce un client, o None se non e' configurabile."""
    chiave = cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not chiave:
        return None
    try:
        import anthropic
    except ImportError:
        print("[ia] libreria 'anthropic' non installata: salto "
              "(pip3 install anthropic)")
        return None
    return anthropic.Anthropic(api_key=chiave)


def _testo(risposta) -> str:
    """Estrae il testo, saltando i blocchi di ragionamento."""
    return "".join(b.text for b in risposta.content if b.type == "text").strip()


# --------------------------------------------------------------------------
# 1. RIASSUNTO — spiega, non decide
# --------------------------------------------------------------------------
ISTRUZIONI_RIASSUNTO = """\
Sei l'assistente di un bot di trading in PAPER (nessun capitale reale).
Ricevi lo stato del sistema e devi scrivere un riassunto in italiano per il
proprietario, che legge il messaggio la mattina.

Il tuo compito e' spiegare cosa e' successo e segnalare cosa e' anomalo.
NON dai consigli di investimento, NON suggerisci di cambiare la strategia,
NON prevedi i prezzi. Se i dati non bastano per dire qualcosa, dillo.

Cose che vale la pena segnalare: zero operazioni per molti giorni quando il
segnale dovrebbe averne prodotte, uno scostamento grande fra portafoglio
reale e portafoglio ombra, un funding molto fuori scala, un mercato escluso
dal filtro di negoziabilita', un drawdown che si avvicina al kill switch.

Cose che NON sono anomalie: zero operazioni quando nessun trend si e'
invertito (il segnale e' un momentum a 60 giorni, cambia in media una volta
ogni 18 giorni per mercato), oscillazioni di pochi centesimi.

Massimo 6 righe. Niente elenchi puntati, niente emoji, niente preamboli.
Scrivi in modo diretto: se non c'e' niente di notevole, dillo in una riga."""


def riassunto(cfg: dict, dati: dict):
    """Riassunto in italiano dello stato. None se l'IA non e' disponibile."""
    c = _cliente(cfg)
    if c is None:
        return None
    try:
        r = c.messages.create(
            model=MODELLO,
            max_tokens=1500,
            system=ISTRUZIONI_RIASSUNTO,
            thinking={"type": "adaptive"},
            output_config={"effort": "low"},
            messages=[{"role": "user",
                       "content": json.dumps(dati, ensure_ascii=False, default=str)}],
        )
        if r.stop_reason == "refusal":
            print("[ia] riassunto rifiutato dai filtri di sicurezza")
            return None
        return _testo(r) or None
    except Exception as e:
        print(f"[ia] riassunto non riuscito: {e}")
        return None


# --------------------------------------------------------------------------
# 2. UNIVERSO PROPOSTO — solo per il portafoglio sperimentale
# --------------------------------------------------------------------------
ISTRUZIONI_UNIVERSO = """\
Scegli su quali mercati perpetui far operare un portafoglio SPERIMENTALE in
paper trading (nessun capitale reale). La tua scelta non tocca il portafoglio
principale: serve a misurare, in avanti e per mesi, se una selezione ragionata
batte una lista fissa.

Ricevi i mercati disponibili con spread, volume 24h, funding rate annualizzato
e variazione a 24 ore. Sono gli unici dati che hai: non hai notizie, non hai
accesso al web, e non devi fingere di averli.

Criteri che contano, in ordine:
- costo: spread stretto e volume alto, perche' il costo per giro e' l'unica
  quantita' certa dell'operazione
- diversificazione: mercati che non si muovono tutti insieme
- funding: valori estremi indicano posizionamento affollato

Scegli ESATTAMENTE il numero di mercati richiesto. Se non hai una ragione
migliore del caso per preferirne uno, dillo nella motivazione invece di
inventarne una: una motivazione onesta e' piu' utile di una plausibile."""

SCHEMA_UNIVERSO = {
    "type": "object",
    "properties": {
        "mercati": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Simboli scelti, esattamente come ricevuti",
        },
        "motivazione": {
            "type": "string",
            "description": "Due o tre frasi sul perche' di questa selezione",
        },
        "fiducia": {
            "type": "string",
            "enum": ["bassa", "media", "alta"],
            "description": "Quanta fiducia hai che questa scelta batta una lista fissa",
        },
    },
    "required": ["mercati", "motivazione", "fiducia"],
    "additionalProperties": False,
}


def universo_proposto(cfg: dict, candidati: dict, quanti: int):
    """
    Chiede all'IA quali mercati usare nel portafoglio sperimentale.

    Restituisce {"mercati": [...], "motivazione": str, "fiducia": str}
    oppure None. I simboli restituiti sono sempre validati contro i candidati:
    un modello che inventa un mercato non deve poter far aprire una posizione.
    """
    c = _cliente(cfg)
    if c is None or not candidati:
        return None
    try:
        r = c.messages.create(
            model=MODELLO,
            max_tokens=4000,
            system=ISTRUZIONI_UNIVERSO,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium",
                           "format": {"type": "json_schema", "schema": SCHEMA_UNIVERSO}},
            messages=[{"role": "user", "content": json.dumps(
                {"scegline": quanti, "mercati_disponibili": candidati},
                ensure_ascii=False)}],
        )
        if r.stop_reason == "refusal":
            print("[ia] scelta dell'universo rifiutata dai filtri di sicurezza")
            return None
        scelta = json.loads(_testo(r))
    except Exception as e:
        print(f"[ia] scelta dell'universo non riuscita: {e}")
        return None

    # Convalida: tengo solo simboli che esistono davvero fra i candidati.
    # Un modello che allucina un mercato non deve poter aprire una posizione.
    validi = [m for m in scelta.get("mercati", []) if m in candidati]
    scartati = [m for m in scelta.get("mercati", []) if m not in candidati]
    if scartati:
        print(f"[ia] simboli inesistenti ignorati: {scartati}")
    if not validi:
        print("[ia] nessun simbolo valido nella risposta")
        return None
    scelta["mercati"] = validi[:quanti]
    return scelta
