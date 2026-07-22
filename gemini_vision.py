"""
Estrazione dei campi *visuali* dalla fustella (Path B: testo vettorializzato).

Il pack ha il testo convertito in tracciati, quindi pdfplumber e' cieco: i campi
semantici (LOT, batteria, materiale, IPX, dimensioni prodotto, conteggi feature,
presenza icone) vanno letti dall'immagine con un LLM multimodale.

Scelta d'ingegneria (stessa della invoice-pipeline):
- niente nodo pre-costruito: chiamata REST diretta per poter forzare temperature=0
  -> pack identici devono restituire dati identici (determinismo);
- responseSchema per output strutturato -> nessun parsing fragile di testo libero;
- doppia lettura a temp 0: se un campo diverge tra le due letture, non entra nel
  foglio come valore "sicuro" ma viene marcato per revisione.
"""
from __future__ import annotations
import base64, json, os, time
import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# --- responseSchema: sottoinsieme OpenAPI accettato da Gemini ------------------
# Stringhe = testo verbatim ("" se assente).  Boolean = simbolo presente sul pack.
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "lot":                 {"type": "STRING"},   # es. "LOT: 531"  ("" se illeggibile)
        "product_dimensions":  {"type": "STRING"},   # es. "19cm x Ø2,8cm"
        "material":            {"type": "STRING"},   # es. "Silicone/ABS"
        "waterproof":          {"type": "STRING"},   # es. "IPX6" oppure "Impermeabile"
        "charge_mode":         {"type": "STRING"},   # es. "Ricarica minijack"
        "battery":             {"type": "STRING"},   # es. "500mAh / 3.7V"
        "vibration":           {"type": "STRING"},   # es. "10 + 10 vibrazioni"
        "speed":               {"type": "STRING"},   # es. "4 velocità"
        "suction":             {"type": "STRING"},
        "tapping":             {"type": "STRING"},
        "rotation":            {"type": "STRING"},
        "sexy_ideas":          {"type": "STRING"},   # testo del box, "" se assente
        "triman_content":      {"type": "STRING"},   # es. "scatola + sacchetto"
        "other_features_seen": {"type": "STRING"},   # feature con icona ma senza colonna (CSV)
        "ce":               {"type": "BOOLEAN"},
        "raee":             {"type": "BOOLEAN"},
        "ukca":             {"type": "BOOLEAN"},
        "triman":           {"type": "BOOLEAN"},
        "spanish_disposal": {"type": "BOOLEAN"},
        "junker_qr":        {"type": "BOOLEAN"},
        "warranty_2y":      {"type": "BOOLEAN"},
        "booklet":          {"type": "BOOLEAN"},
        "strap_on":         {"type": "BOOLEAN"},
        "heating":          {"type": "BOOLEAN"},
    },
    "required": ["lot", "product_dimensions", "material", "waterproof",
                 "ce", "raee", "ukca", "triman", "warranty_2y", "booklet"],
}

# Prompt fisso (l'unico input variabile e' l'immagine -> assembly injection-safe).
PROMPT = (
    "Questa e' la pagina 1 della fustella (die-cut) di un pack prodotto MySecretCase. "
    "Estrai SOLO cio' che e' effettivamente stampato e visibile. Non dedurre, non inventare, "
    "non completare valori mancanti. Regole:\n"
    "- Per i campi testuali riporta il testo verbatim (dimensioni, LOT, mAh, ecc.); "
    "stringa vuota se il campo non compare.\n"
    "- Per i simboli/icone (ce, raee, ukca, triman, spanish_disposal, junker_qr, "
    "warranty_2y, booklet) rispondi true/false se il simbolo e' presente.\n"
    "- 'waterproof': se c'e' un codice IPX riportalo (es. IPX6); se c'e' solo la dicitura "
    "'Impermeabile' senza codice, scrivi 'Impermeabile'.\n"
    "- 'other_features_seen': elenca (CSV) eventuali feature con icona+etichetta che non "
    "rientrano tra vibrazioni/velocita'/suzione/tapping/rotazione/strap-on/riscaldante "
    "(es. 'Telecomandato').\n"
    "Rispondi esclusivamente con il JSON conforme allo schema."
)

BOOL_KEYS = {"ce","raee","ukca","triman","spanish_disposal","junker_qr",
             "warranty_2y","booklet","strap_on","heating"}


class VisionExtractor:
    def extract(self, image_bytes: bytes, context: dict) -> tuple[dict, list[str]]:
        raise NotImplementedError


class GeminiVisionExtractor(VisionExtractor):
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", retries: int = 4):
        self.api_key, self.model, self.retries = api_key, model, retries

    def _call_once(self, image_bytes: bytes) -> dict:
        body = {
            "contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": "image/jpeg",
                                 "data": base64.b64encode(image_bytes).decode()}},
                {"text": PROMPT},
            ]}],
            "generationConfig": {
                "temperature": 0,
                "response_mime_type": "application/json",
                "response_schema": RESPONSE_SCHEMA,
            },
        }
        url = GEMINI_URL.format(model=self.model)
        delay = 1.0
        for attempt in range(self.retries):                 # backoff su 429/5xx
            r = requests.post(url, params={"key": self.api_key}, json=body, timeout=60)
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(txt)
            if r.status_code in (429, 500, 503):
                time.sleep(delay); delay *= 2; continue
            r.raise_for_status()
        raise RuntimeError(f"Gemini non raggiungibile dopo {self.retries} tentativi")

    def extract(self, image_bytes, context):
        a = self._call_once(image_bytes)
        b = self._call_once(image_bytes)               # doppia lettura a temp 0
        disagree = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
        merged = dict(a)
        for k in disagree:                             # in caso di conflitto: svuota il campo
            merged[k] = False if k in BOOL_KEYS else ""
        return merged, disagree


class FixtureVisionExtractor(VisionExtractor):
    """Esecuzione OFFLINE: restituisce i valori vision gia' letti sui 4 pack di test.
    Serve a far girare l'intera pipeline (parse -> validate -> raster -> guard ->
    scrittura) senza rete. In produzione si usa GeminiVisionExtractor."""
    def __init__(self, table: dict): self.table = table
    def extract(self, image_bytes, context):
        return dict(self.table[context["ean"]]), []      # nessun conflitto sui fixture
