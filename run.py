"""
CLI: cartella di fustelle -> Google Sheet compilato.

  # produzione (una chiave Gemini):
  export GEMINI_API_KEY=...
  python run.py /percorso/fustelle --out output/Dati_Pack.xlsx

  # demo offline sui 4 pack di test (nessuna rete): usa i valori vision gia' letti
  python run.py /percorso/fustelle --fixtures --out output/Dati_Pack_COMPILATO.xlsx
"""
import argparse, os, sys
from extract_pack import process_folder, write_xlsx
from gemini_vision import GeminiVisionExtractor, FixtureVisionExtractor

# Valori vision letti manualmente sui 4 pack forniti (chiave = EAN).
# In produzione questi vengono da Gemini; qui servono solo per l'esecuzione offline.
FIXTURES = {
    "8055712770439": {  # Coniglietto Schizzetto — Vibratore rabbit
        "lot":"LOT: 531","product_dimensions":"19cm x Ø2,8cm","material":"Silicone/ABS",
        "waterproof":"IPX6","charge_mode":"Ricarica minijack","battery":"500mAh / 3.7V",
        "vibration":"10 + 10 vibrazioni","speed":"","suction":"","tapping":"","rotation":"",
        "sexy_ideas":"Videochiamalǝ e chiedilǝ se vuolǝ vederti godere...",
        "triman_content":"scatola + sacchetto","other_features_seen":"",
        "ce":True,"raee":True,"ukca":True,"triman":True,"spanish_disposal":True,
        "junker_qr":True,"warranty_2y":True,"booklet":True,"strap_on":False,"heating":False},
    "8055712770125": {  # Clitofono — Vibratore clitoride
        "lot":"LOT: 470","product_dimensions":"9,5cm x Ø2,9cm","material":"Silicone/ABS",
        "waterproof":"IPX5","charge_mode":"Ricarica magnetica","battery":"180mAh / 3.7V",
        "vibration":"7 vibrazioni","speed":"","suction":"","tapping":"","rotation":"",
        "sexy_ideas":"Piccolo e compatto, tienilo tra due dita...",
        "triman_content":"scatola + sacchetto","other_features_seen":"Telecomandato",
        "ce":True,"raee":True,"ukca":True,"triman":True,"spanish_disposal":True,
        "junker_qr":True,"warranty_2y":True,"booklet":True,"strap_on":False,"heating":False},
    "8055712770316": {  # Confetto Pornetto — Ovetto vibrante
        "lot":"LOT: 431","product_dimensions":"7cm x Ø2,8cm","material":"Silicone/ABS",
        "waterproof":"IPX5","charge_mode":"Ricarica minijack","battery":"120mAh / 3.7V",
        "vibration":"7 vibrazioni","speed":"4 velocità","suction":"","tapping":"","rotation":"",
        "sexy_ideas":"","triman_content":"scatola + sacchetto","other_features_seen":"Telecomandata",
        "ce":True,"raee":True,"ukca":True,"triman":True,"spanish_disposal":True,
        "junker_qr":True,"warranty_2y":True,"booklet":True,"strap_on":False,"heating":False},
    "8058045165750": {  # Godolo (Cazzoni Animati) — Dildo realistico (non elettronico)
        "lot":"LOT: 553","product_dimensions":"20cm x Ø4,3cm","material":"Silicone",
        "waterproof":"Impermeabile","charge_mode":"","battery":"",
        "vibration":"","speed":"","suction":"","tapping":"","rotation":"",
        "sexy_ideas":"Cavalcalo come se fosse il tuo preferito... / Usalo in bagno... / Attacca il dildo...",
        "triman_content":"scatola + sacchetto","other_features_seen":"",
        "ce":True,"raee":True,"ukca":True,"triman":True,"spanish_disposal":True,
        "junker_qr":True,"warranty_2y":True,"booklet":True,"strap_on":True,"heating":False},
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--out", default="output/Dati_Pack.xlsx")
    ap.add_argument("--fixtures", action="store_true", help="esecuzione offline sui pack di test")
    ap.add_argument("--model", default="gemini-2.5-flash")
    a = ap.parse_args()

    if a.fixtures:
        extractor = FixtureVisionExtractor(FIXTURES)
    else:
        key = os.environ.get("GEMINI_API_KEY")
        if not key: sys.exit("GEMINI_API_KEY non impostata (usa --fixtures per la demo offline)")
        extractor = GeminiVisionExtractor(key, model=a.model)

    rows = process_folder(a.folder, extractor)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    write_xlsx(rows, a.out)

    perfetti = sum(1 for r in rows if r.get("_CONF") == "Alta")
    parziali = sum(1 for r in rows if r.get("_CONF") == "Media")
    falliti  = sum(1 for r in rows if r.get("_CONF") == "Bassa")
    print(f"Pack processati : {len(rows)}")
    print(f"  Alta conf.    : {perfetti}")
    print(f"  Media (flag)  : {parziali}")
    print(f"  Bassa/review  : {falliti}")
    print(f"Output          : {a.out}")
    for r in rows:
        if r.get("_FLAG","—") != "—":
            print(f"  ⚑ {r.get('_PROD','?')[:38]:<40} {r['_FLAG']}")

if __name__ == "__main__":
    main()
