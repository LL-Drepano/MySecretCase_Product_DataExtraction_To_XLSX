# MySecretCase_Product_DataExtraction_To_XLSX
An automated pipeline Demo I built for MySecretCase (famous sextoys italian company) that extracts structured product data from packaging dieline PDFs and maps it to a spreadsheet with **one row per pack and one column per field**, following the supplied 34-column reference mapping.

## The problem

The input looked straightforward: 50 PDF dielines, all following the same general layout, with one reference file showing the expected mapping.

The obvious solution would have been to extract the text directly from each PDF and map it into columns. That approach did not work.

Most of the useful content — product name, LOT information, dimensions, battery specifications, waterproof rating, material, feature icons, and warranty symbols — had been converted into **vector outlines** during the prepress process. To a normal PDF text parser, those values were not text anymore; they were drawing instructions.

Direct extraction still recovered a few residual elements, mainly recycling codes, but not enough to build the required dataset. The task therefore needed a hybrid pipeline: deterministic parsing wherever possible, and multimodal AI only for the semantic information embedded in the artwork.

---

## What I built

A four-part extraction system:

1. **Deterministic extraction** — the filename provides the EAN, box dimensions, and product reference; residual PDF text provides recycling codes; fixed company fields are populated from controlled constants.
2. **Vision-based extraction** — page one is rasterised and sent to Gemini with a strict JSON response schema to read the semantic and graphical fields.
3. **Validation and confidence scoring** — the EAN check digit, double AI reading, domain rules, missing-field checks, and field-level disagreements produce a confidence level and human-readable flags.
4. **Automatic batch orchestration** — the 50 PDFs are processed in groups of five, with pauses, retries, temporary outputs, and a final automatic merge into one spreadsheet.

**Stack:** Python · `pdfplumber` / `pypdf` · Poppler (`pdftoppm`) · Pillow · Gemini API · `requests` · OpenPyXL.

---

## How it works

### 0. The filename is treated as structured input

Each filename follows a pattern similar to:

```text
EAN_LxWxH_Product-name.pdf
```

A regular expression extracts:

* EAN-13;
* external box dimensions;
* product name or variant.

The EAN is then validated using its check digit. These fields do not require an LLM and are therefore deterministic, fast, and effectively free to process.

The same principle is applied to fields that are constant across the product line, such as manufacturer and importer details.

### 1. The PDF is inspected before using AI

The parser first attempts to recover live text and positional information.

This is still useful for the small amount of text that survived the outlining process, particularly recycling labels such as `PAP 21` and `CPE 07`. Those values are paired spatially and mapped deterministically to the correct packaging component.

The important design choice was not to force one extraction method onto every field. Fields that can be derived reliably remain outside the AI step.

### 2. The artwork becomes a vision input

The first page of each dieline is rasterised with Poppler and converted into an image suitable for a multimodal model.

Gemini then returns structured JSON containing fields such as:

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

The request uses `temperature = 0` and a response schema so that the output is predictable and machine-readable.

### 3. Every pack is read twice

Each image is sent to the model twice.

If both readings agree, the field is considered stable. If they disagree, the conflicting value is removed rather than guessed, and the row is marked for review.

Additional guards check for cases such as:

* invalid EAN check digit;
* missing LOT or product dimensions;
* an electronic product marked waterproof without an IPX code;
* expected battery or operating data missing from an electronic product;
* fields that are genuinely absent from the original dieline.

The output includes two service columns:

* **Confidence:** High, Medium, or Low;
* **Flags / Notes:** a readable explanation of what requires attention.

The system never invents a missing value just to complete the row.

### 4. The real scaling issue: four PDFs worked, fifty did not

The validation run on four PDFs completed correctly, but processing the full folder as one uninterrupted run caused the Gemini endpoint to become temporarily unavailable after repeated calls.

The reason is structural: every pack requires two model calls, so 50 packs produce approximately 100 requests. This is small in cost terms, but enough to encounter free-tier request limits or temporary throttling.

The solution was not to ask the operator to divide the work manually. I added `batch_run.py`, which handles the entire process automatically:

1. discovers all PDFs in the input folder;
2. splits them into batches of five;
3. runs the normal extraction pipeline on each batch;
4. waits 60 seconds before starting the next batch;
5. retries a failed batch after a longer cooldown;
6. stores each temporary workbook separately;
7. merges all rows into one final Excel file;
8. removes temporary PDF copies after completion.

The user still launches a single command. Batching is an internal rate-limit strategy, not a manual workflow.

### 5. The final workbook is converted to Google Sheets

The pipeline writes the 34 official columns in the same order as the reference mapping and adds a small number of grey service columns for provenance, confidence, flags, EAN, box dimensions, and product identification.

The resulting `.xlsx` file can be uploaded to Google Drive and opened with Google Sheets without changing the column structure.

---

## Accuracy and validation

The first validation set contained four deliberately different products. All four produced a complete 34-column mapping, with three classified as High confidence and one flagged because the source itself contained an ambiguous or absent value.

After processing the complete 50-pack dataset, I performed a stratified manual review of 15 rows:

* 5 High-confidence rows;
* 5 Medium-confidence rows;
* 5 Low-confidence rows.

Every checked field matched the information actually visible in the corresponding PDF, giving an **observed accuracy of 100% on the reviewed sample**.

The `NEEDS_REVIEW` cases were not extraction errors. In the reviewed rows, flags such as “LOT unreadable” or “dimensions missing” correctly reflected information that was genuinely absent or unreadable in the original dieline.

Validation result:

* rows manually reviewed: **15 of 50**;
* observed field accuracy on the sample: **100%**;
* extraction errors found in the sample: **0**;
* failed rows found in the sample: **0**;
* false-positive review flags found in the sample: **0**.

This is a stratified sample-based validation, not a claim that every cell in all 50 rows was manually audited.

---

## Error handling

| Situation                    | Behaviour                                          |
| ---------------------------- | -------------------------------------------------- |
| Invalid EAN check digit      | Row flagged and confidence reduced                 |
| LOT or dimensions absent     | `❌` / empty value, `NEEDS_REVIEW`, Low confidence  |
| Two Gemini readings disagree | Conflicting field cleared and flagged              |
| Temporary Gemini failure     | Automatic request retry with backoff               |
| Whole batch fails            | Batch-level retry after a longer cooldown          |
| Free-tier throttling         | Automatic five-file batching and inter-batch pause |
| Non-conforming filename      | Row retained, but identifying fields are flagged   |
| Missing source information   | Reported as missing; never fabricated              |

A failed batch does not silently disappear. The process stops with an explicit error if the configured retry budget is exhausted.

---

## Design decisions

* **Hybrid extraction instead of AI-only extraction.** Reliable fields stay deterministic, reducing cost and avoiding unnecessary model variance.
* **Double reading at temperature zero.** Agreement between two independent calls is used as a practical stability check.
* **Clear separation between extraction and orchestration.** `run.py` processes one folder; `batch_run.py` adds batching, cooldowns, retries, and final consolidation.
* **Five-pack batches.** Small enough to operate reliably within constrained API quotas while keeping the process fully automatic.
* **Missing means missing.** The pipeline flags unsupported values instead of generating plausible-looking data.
* **Service columns outside the official mapping.** Confidence and traceability are added without modifying the required 34-column structure.
* **Excel as an interchangeable output layer.** OpenPyXL creates a file that can be opened directly in Google Sheets, while direct Sheets writing remains an easy future extension.

---

## Cost per pack

The deterministic part has no per-pack API cost.

The vision stage sends one rasterised page twice for validation. With a Flash-class Gemini model, the estimated paid usage is approximately:

```text
€0.002–€0.005 per pack
```

The test run used the free tier, so the direct API cost was zero. At this scale, the main operational constraint is request throttling rather than model cost.

Pricing and quotas change over time, so the estimate should be recalculated against the selected Gemini model before production use.

---

## Processing time

Local parsing and rasterisation take only a small fraction of the total runtime. Model latency, cooldowns, and retries dominate.

With 50 files and a batch size of five:

* total batches: 10;
* forced pauses between batches: 9 × 60 seconds;
* minimum deliberate throttling time: approximately 9 minutes;
* total runtime: throttling time plus rasterisation, Gemini latency, and any retries.

A paid deployment with higher quotas could reduce or remove the pauses and process batches concurrently with controlled parallelism.

---

## Limitations and possible improvements

* **ASIN is not printed on the dieline.** It requires an external catalogue or PIM joined through the EAN.
* **Source-level ambiguity remains real.** A vision model cannot recover information that is genuinely absent from the artwork.
* **Layout drift detection.** A structural check could reject dielines whose icon grid or visual hierarchy differs materially from the expected template.
* **Barcode cross-check.** `pyzbar` could compare the decoded barcode with the EAN in the filename and the printed digits.
* **Targeted re-reading.** Low-confidence regions could be cropped and reprocessed at higher resolution instead of repeating the full page.
* **Direct Google Sheets output.** `gspread` and a service account could replace the intermediate Excel upload.
* **Cloud orchestration.** A Drive trigger in Make.com or n8n could start the pipeline automatically when new PDFs arrive.
* **Human-review queue.** Medium- and Low-confidence rows could be copied into a separate “Needs Review” sheet.

---

## Running the project

### Prerequisites

* Python 3;
* Poppler available on the system path;
* a Gemini API key;
* a Gemini Flash model available to the account.

Install the Python dependencies:

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

Validate the model on the reference set:

```powershell
python validate.py .\test --model $env:MODEL
```

Process the full folder with automatic batching:

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

At the end of the run, the final workbook is available at:

```text
output/Dati_Pack.xlsx
```

Upload it to Google Drive and choose **Open with → Google Sheets**.

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

---

## What this project demonstrates

* Building a production-oriented extraction pipeline rather than a one-off prompt.
* Choosing between deterministic parsing and AI based on the actual source format.
* Working with multimodal structured output and validation schemas.
* Designing confidence scoring and review flags around source uncertainty.
* Debugging a workflow that succeeds on a small test but fails under batch load.
* Handling API rate limits without introducing manual processing.
* Preserving the client's required schema while adding operational traceability.
  ::: 
