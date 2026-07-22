"""
Controllo di correttezza PRIMA di lanciare i 50.

Esegue Gemini *dal vivo* sui pack di test presenti nella cartella e confronta
campo per campo con i valori gia' verificati (i fixture in run.py). Se coincidono,
ci si puo' fidare della lettura automatica sui 50.

  export GEMINI_API_KEY=...
  python validate.py /percorso/4-pack-di-test --model <id-modello-da-AI-Studio>
"""
import argparse, os, sys
from extract_pack import parse_filename, rasterize_page1
from gemini_vision import GeminiVisionExtractor
from run import FIXTURES

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--model", default="gemini-2.5-flash")
    a = ap.parse_args()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY non impostata")
    gem = GeminiVisionExtractor(key, model=a.model)

    tot_ok = tot_cmp = 0
    for name in sorted(os.listdir(a.folder)):
        if not name.lower().endswith((".pdf", ".ai")):
            continue
        fn = parse_filename(name)
        if not fn or fn["ean"] not in FIXTURES:
            continue
        truth = FIXTURES[fn["ean"]]
        img = rasterize_page1(os.path.join(a.folder, name))
        got, disagree = gem.extract(img, {"ean": fn["ean"], "product": fn["product"]})
        print(f"\n=== {fn['product']}  (EAN {fn['ean']}) ===")
        if disagree:
            print(f"  ! doppia lettura incoerente su: {', '.join(disagree)}")
        for field in sorted(truth):
            exp, act = truth[field], got.get(field, "<mancante>")
            ok = str(exp).strip().lower() == str(act).strip().lower()
            tot_cmp += 1; tot_ok += ok
            if not ok:
                print(f"  MISMATCH  {field:<20} atteso='{exp}'  ottenuto='{act}'")
        print("  (tutti i campi coincidono)" if all(
            str(truth[f]).strip().lower() == str(got.get(f, "")).strip().lower()
            for f in truth) else "")
    print(f"\n--- Campi coincidenti: {tot_ok}/{tot_cmp} "
          f"({100*tot_ok/tot_cmp:.0f}%) ---" if tot_cmp else "Nessun pack di test trovato.")

if __name__ == "__main__":
    main()
