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

# Il modello si puo' cambiare da config.json con "anthropic_model".
# Vale la pena saperlo: le due chiamate giornaliere su Opus 5 costano intorno
# ai 4 USD al mese, cioe' piu' di quanto un conto da 200 EUR possa
# ragionevolmente rendere. Su un conto in paper e' il prezzo di un
# esperimento, non un costo operativo — ma va guardato per quello che e'.
MODELLO = "claude-opus-5"


def _modello(cfg: dict) -> str:
    return cfg.get("anthropic_model") or os.environ.get(
        "ANTHROPIC_MODEL") or MODELLO


UNIVERSO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "docs", "ia_universo.json")
SCELTE_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "docs", "ia_scelte.jsonl")

# Oltre questa eta' la scelta su file viene ignorata. Serve perche' il task
# schedulato gira solo con l'app aperta: se resta spenta per giorni, il
# portafoglio deve smettere di seguire una decisione vecchia invece di
# congelarsi su di essa fingendo che sia attuale.
ETA_MASSIMA_ORE = 36


def universo_da_file(cfg: dict, candidati: dict, quanti: int):
    """
    Legge la scelta prodotta da un'istanza schedulata, se c'e' ed e' fresca.

    Perche' esiste: un'istanza schedulata di Claude fa lo stesso lavoro di una
    chiamata API — parte senza memoria, vede solo i dati che le passi — ma non
    costa niente. Su un conto da 200 EUR la differenza non e' estetica: 12 EUR
    l'anno di API sono il 6% del capitale, e falserebbero il confronto fra i
    portafogli.

    La convalida e' la stessa della via API: simboli inventati vengono scartati.
    """
    import json as _json
    from datetime import datetime as _dt, timezone as _tz
    try:
        with open(UNIVERSO_FILE) as f:
            d = _json.load(f)
    except Exception:
        return None

    try:
        quando = _dt.fromisoformat(str(d.get("scelto_il", "")).replace("Z", "+00:00"))
        ore = (_dt.now(_tz.utc) - quando).total_seconds() / 3600
    except Exception:
        print("[ia] file universo senza data valida: ignorato")
        return None
    if ore > ETA_MASSIMA_ORE:
        print(f"[ia] scelta su file vecchia di {ore:.0f} ore: ignorata")
        return None

    validi = [m for m in d.get("mercati", []) if m in candidati]
    scartati = [m for m in d.get("mercati", []) if m not in candidati]
    if scartati:
        print(f"[ia] file: simboli non negoziabili ignorati: {scartati}")
    if not validi:
        print("[ia] file: nessun simbolo valido")
        return None

    return {"mercati": validi[:quanti],
            "motivazione": d.get("motivazione", ""),
            "fiducia": d.get("fiducia", "media"),
            "origine": "istanza schedulata"}


def stato_ia(cfg: dict) -> tuple:
    """
    (attiva, motivo) — perche' il livello IA gira o non gira.

    Esiste perche' l'assenza silenziosa e' costata due giorni di indagine:
    il terzo portafoglio non partiva, non lasciava traccia nei log, e dal di
    fuori era indistinguibile da un guasto. La differenza fra "spento per
    scelta" e "rotto" deve essere DICHIARATA, non dedotta.
    """
    if cfg.get("portafoglio_ia") is False:
        return False, "disattivato per scelta in config.json"

    # Il file prodotto da un'istanza schedulata vale quanto una chiave API,
    # e costa zero. Se e' fresco, il livello e' attivo anche senza credenziali.
    try:
        import json as _json
        from datetime import datetime as _dt, timezone as _tz
        with open(UNIVERSO_FILE) as f:
            d = _json.load(f)
        q = _dt.fromisoformat(str(d["scelto_il"]).replace("Z", "+00:00"))
        ore = (_dt.now(_tz.utc) - q).total_seconds() / 3600
        if ore <= ETA_MASSIMA_ORE:
            return True, f"attivo via istanza schedulata (scelta di {ore:.0f}h fa)"
        motivo_file = f"ultima scelta su file vecchia di {ore:.0f} ore"
    except Exception:
        motivo_file = "nessuna scelta su file"

    if not (cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")):
        return False, f"{motivo_file}, e nessuna chiave API configurata"
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False, "libreria 'anthropic' non installata (pip3 install anthropic)"
    return True, f"attivo, modello {_modello(cfg)}"


def _cliente(cfg: dict):
    """Restituisce un client, o None se non e' configurabile."""
    attiva, motivo = stato_ia(cfg)
    if not attiva:
        print(f"[ia] livello disattivato: {motivo}")
        return None
    import anthropic
    chiave = cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
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
            model=_modello(cfg),
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
    if not candidati:
        return None

    # Prima si guarda il file: se un'istanza schedulata ha gia' scelto oggi,
    # quella scelta vale e non si paga nessuna chiamata API.
    da_file = universo_da_file(cfg, candidati, quanti)
    if da_file:
        return da_file

    c = _cliente(cfg)
    if c is None:
        return None
    try:
        r = c.messages.create(
            model=_modello(cfg),
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
