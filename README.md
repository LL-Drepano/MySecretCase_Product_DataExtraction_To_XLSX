# MySecretCase_Product_DataExtraction_To_XLSX

An automated pipeline demo I built for a **MySecretCase selection task**, designed to extract structured product data from packaging dieline PDFs and map it to a spreadsheet with **one row per pack and one column per field**, following the supplied 34-column reference mapping.

## The problem

The input was a folder of 50 PDF dielines, all following the same general layout, plus one reference file showing the expected spreadsheet mapping.

The first idea was to extract the text directly from each PDF and map it into columns. That did not work.

Most of the useful content — product name, LOT information, dimensions, battery specifications, waterproof rating, material, feature icons, and warranty symbols — had been converted into **vector outlines** during the prepress process. To a normal PDF text parser, those values were not text anymore.

Direct extraction still recovered a few residual elements, mainly recycling codes, but not enough to build the dataset.

The resulting pipeline therefore uses deterministic extraction where the source allows it and vision-based extraction for information embedded in the artwork.

---

## Highlights

* **50 packaging PDFs → one structured 34-column dataset.** The full folder is processed automatically and merged into a single Excel workbook.
* **Hybrid extraction.** EAN, box dimensions, recycling codes, filenames, and fixed fields are handled deterministically; Gemini Vision is used only for information that cannot be recovered as text.
* **Two-pass extraction with review flags.** Every pack is sent to the model twice. Disagreements, missing values, and failed validation rules are surfaced instead of silently accepted.
* **Automatic rate-limit handling.** The initial pipeline worked on four PDFs but became unreliable across all 50. A batch runner was added to handle cooldowns, retries, temporary outputs, and final consolidation.
* **Manual validation on 510 fields.** I reviewed all 34 mapped fields across a stratified sample of 15 packs and found no extraction mismatches in the reviewed sample.

**Stack:** Python · `pdfplumber` / `pypdf` · Poppler (`pdftoppm`) · Pillow · Gemini API · `requests` · OpenPyXL.

---

## How it works

### 1. Structured information from the filename

Each filename follows a pattern similar to:

```text
EAN_LxWxH_Product-name.pdf
```

A regular expression extracts:

* EAN-13;
* external box dimensions;
* product name or variant.

The EAN is also validated using its check digit.

Fields that are constant across the product line, such as manufacturer and importer information, are populated from controlled values rather than extracted repeatedly.

### 2. PDF inspection

The parser first attempts to recover any remaining live text and positional information.

This is useful for the small amount of text that survived the outlining process, particularly recycling labels such as `PAP 21` and `CPE 07`.

Those values are paired spatially and mapped to the corresponding packaging component.

### 3. Vision extraction

The first page of each dieline is rasterised with Poppler and converted into an image.

Gemini returns structured JSON containing fields such as:

* serial or LOT information;
* CE, WEEE, UKCA, TRIMAN, warranty, manual, and QR symbols;
* battery capacity and voltage;
* charging method;
* waterproof rating;
* material;
* product dimensions;
* vibration, speed, suction, tapping, and rotation counts;
* strap-on compatibility;
* heating functionality;
* TRIMAN disposal content;
* presence of “Sexy Ideas”.

The request uses a defined response schema and `temperature = 0` to keep the output format consistent.

### 4. Two-pass extraction and validation

Each pack is processed through **two separate model calls**.

If the two results agree, the value is kept. If they disagree, the conflicting field is cleared and flagged for review rather than guessed.

Additional checks cover cases such as:

* invalid EAN check digit;
* missing LOT or product dimensions;
* waterproof products without an IPX value;
* expected battery or operating data missing from electronic products;
* information genuinely absent from the source dieline.

The output contains two additional service columns:

* **Confidence:** High, Medium, or Low;
* **Flags / Notes:** explanation of fields that may require review.

The confidence value is a **model-generated heuristic label**, not a calibrated probability of correctness. It is used together with deterministic validation rules and disagreement flags to prioritise manual review.

Missing information remains missing rather than being filled with plausible-looking values.

---

## Scaling from 4 PDFs to 50

The first validation run on four PDFs completed correctly.

Processing all 50 packs in one uninterrupted run caused temporary Gemini failures after repeated requests. Since every pack requires two model calls, the complete dataset requires roughly 100 vision requests.

To handle this, `batch_run.py`:

1. discovers all PDFs in the input folder;
2. splits them into batches of five;
3. processes each batch through the standard extraction pipeline;
4. waits between batches;
5. retries failed batches after a longer cooldown;
6. stores temporary workbooks separately;
7. merges all rows into the final Excel file;
8. removes temporary PDF copies after completion.

The operator still launches one command; the batching happens internally.

---

## Accuracy and validation

The initial validation set contained four deliberately different products. All four produced a complete 34-column mapping, with three classified as High confidence and one flagged because the source contained an ambiguous or missing value.

After processing the complete 50-pack dataset, I manually reviewed a stratified sample of 15 rows:

* 5 High-confidence rows;
* 5 Medium-confidence rows;
* 5 Low-confidence rows.

For each selected row, I compared **all 34 mapped fields** against the corresponding source PDF.

That produced:

```text
15 rows × 34 fields = 510 manual comparisons
```

No extraction mismatches were found in those 510 comparisons.

The reviewed `NEEDS_REVIEW` cases were not extraction errors: flags such as “LOT unreadable” or “dimensions missing” matched information that was actually absent or unreadable in the source.

Validation summary:

* complete dataset: **50 packs**;
* rows manually reviewed: **15 of 50**;
* fields reviewed per row: **34**;
* total manual comparisons: **510**;
* extraction mismatches found: **0**;
* failed rows found in the reviewed sample: **0**;
* false-positive review flags found in the reviewed sample: **0**.

This is a **sample-based validation**, not a claim that every cell across all 50 rows was manually audited.

---

## Error handling

| Situation                  | Behaviour                                |
| -------------------------- | ---------------------------------------- |
| Invalid EAN check digit    | Row flagged                              |
| LOT or dimensions absent   | Empty / missing value and review flag    |
| Two Gemini calls disagree  | Conflicting field cleared and flagged    |
| Temporary Gemini failure   | Automatic request retry with backoff     |
| Whole batch fails          | Batch-level retry after longer cooldown  |
| Free-tier throttling       | Five-file batching and inter-batch pause |
| Non-conforming filename    | Row retained, identifying fields flagged |
| Missing source information | Reported as missing, never fabricated    |

If the configured retry budget is exhausted, the process stops with an explicit error rather than silently dropping a batch.

---

## Output

The pipeline writes the 34 requested columns in the same order as the reference mapping.

Additional service columns contain information such as:

* provenance;
* confidence;
* review flags;
* EAN;
* box dimensions;
* product identification.

The final `.xlsx` can be uploaded directly to Google Drive and opened with Google Sheets without changing the original column structure.

---

## Cost per pack

The deterministic part has no per-pack API cost.

The vision stage sends one rasterised page twice for validation.

With a Flash-class Gemini model, estimated paid usage is approximately:

```text
€0.002–€0.005 per pack
```

The actual test run used the free tier, so the direct API cost was zero.

At this scale, the main practical constraint was request throttling rather than inference cost.

Pricing and quotas change over time, so this estimate should be recalculated against the selected Gemini model before production use.

---

## Processing time

With 50 files and a batch size of five:

```text
10 batches
9 forced pauses
60 seconds per pause
≈ 9 minutes minimum deliberate throttling
```

Total runtime also includes rasterisation, Gemini response time, local processing, and possible retries.

With higher API quotas, the pauses could be reduced or removed and requests could be processed with controlled concurrency.

---

## Limitations and possible improvements

* **ASIN is not printed on the dieline.** It requires an external catalogue or PIM joined through the EAN.
* **Source ambiguity cannot always be solved.** Information genuinely absent from the artwork remains unavailable.
* **Layout drift detection.** Dielines that differ substantially from the expected visual structure could be detected before extraction.
* **Barcode cross-check.** `pyzbar` could compare the barcode against both the printed EAN and filename.
* **Targeted re-reading.** Ambiguous regions could be cropped and processed again at higher resolution instead of repeating the complete page.
* **Direct Google Sheets output.** `gspread` and a service account could remove the intermediate Excel upload.
* **Cloud orchestration.** A Drive trigger in Make.com or n8n could start processing automatically when new PDFs arrive.
* **Human-review queue.** Flagged rows could be copied automatically into a separate review sheet.

---

## Running the project

### Prerequisites

* Python 3;
* Poppler available on the system path;
* a Gemini API key;
* a Gemini Flash model available to the account.

Install the dependencies:

```bash
python -m venv .venv
pip install -r requirements.txt
```

Set the API key and model.

PowerShell:

```powershell
$env:GEMINI_API_KEY="your-api-key"
$env:MODEL="your-available-flash-model"
```

macOS / Linux:

```bash
export GEMINI_API_KEY="your-api-key"
export MODEL="your-available-flash-model"
```

Validate on the reference set:

```powershell
python validate.py .\test --model $env:MODEL
```

Process the complete folder:

```powershell
python batch_run.py .\fustelle --model $env:MODEL --out output\Dati_Pack.xlsx
```

Optional tuning:

```powershell
python batch_run.py .\fustelle `
  --model $env:MODEL `
  --out output\Dati_Pack.xlsx `
  --batch-size 5 `
  --pause 60 `
  --retries 4 `
  --retry-wait 120
```

Final output:

```text
output/Dati_Pack.xlsx
```

---

## Repository structure

```text
task2-fustelle-extraction/
├── README.md
├── RUNBOOK.md
├── requirements.txt
├── run.py
├── batch_run.py
├── extract_pack.py
├── gemini_vision.py
├── validate.py
├── .gitignore
└── output/
```

Generated outputs, source PDFs, local environments, temporary batches, and API secrets are excluded from version control.
