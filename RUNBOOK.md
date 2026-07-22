# Runbook — From 50 PDFs to a Google Sheet

This procedure is intended to be run once for a complete batch.

## 1. Open the project

```bash
cd task2-fustelle-extraction
```

## 2. Create the Python environment

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows PowerShell

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Poppler must be installed separately because the pipeline uses `pdftoppm` to rasterize PDF pages.

Verify the installation:

```bash
pdftoppm -v
```

## 3. Configure the Gemini API key

Create an API key in Google AI Studio and store it in the current shell.

### macOS / Linux

```bash
export GEMINI_API_KEY="..."
```

### Windows PowerShell

```powershell
$env:GEMINI_API_KEY="..."
```

Never commit the key to the repository.

## 4. Select an available Flash model

Model IDs change over time. Query the API and choose a Flash model that supports `generateContent`.

### Windows PowerShell

```powershell
(Invoke-RestMethod "https://generativelanguage.googleapis.com/v1beta/models?key=$env:GEMINI_API_KEY").models |
Where-Object {
    $_.name -match "flash" -and
    $_.supportedGenerationMethods -contains "generateContent"
} |
Select-Object -ExpandProperty name
```

Then set the selected model without the `models/` prefix:

```powershell
$env:MODEL="<available-flash-model-id>"
```

### macOS / Linux

```bash
curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY" \
  | grep -o '"name": "models/[^"]*"' | grep -i flash

export MODEL="<available-flash-model-id>"
```

## 5. Prepare the folders

Place the four reference PDFs in:

```text
test/
```

Place all production PDFs in:

```text
fustelle/
```

The input PDFs are private data and should not be committed.

## 6. Validate the model on the reference set

### Windows PowerShell

```powershell
python validate.py .\test --model $env:MODEL
```

### macOS / Linux

```bash
python validate.py ./test --model "$MODEL"
```

Review any mismatches against the original PDF. A textual difference is not necessarily an extraction error when the model has captured the source more accurately than the stored fixture.

## 7. Process the complete folder

Use the automatic batch runner for a long run.

### Windows PowerShell

```powershell
python batch_run.py .\fustelle \
  --model $env:MODEL \
  --out output\Dati_Pack.xlsx \
  --batch-size 5 \
  --pause 60 \
  --retries 4 \
  --retry-wait 120
```

In PowerShell, use backticks instead of backslashes for a multiline command, or run the short form:

```powershell
python batch_run.py .\fustelle --model $env:MODEL --out output\Dati_Pack.xlsx
```

### macOS / Linux

```bash
python batch_run.py ./fustelle \
  --model "$MODEL" \
  --out output/Dati_Pack.xlsx \
  --batch-size 5 \
  --pause 60 \
  --retries 4 \
  --retry-wait 120
```

The runner:

1. discovers all PDFs in the input folder;
2. creates temporary groups of 5;
3. invokes `run.py` for each group;
4. waits between groups;
5. retries failed groups;
6. merges the partial workbooks into one final file.

## 8. Review the result

At the end of each group, the CLI prints:

- processed pack count;
- High-confidence rows;
- Medium-confidence rows;
- Low-confidence or review rows;
- detailed flags.

Review all non-High-confidence rows and a representative sample of High-confidence rows.

A `NEEDS_REVIEW` flag may correctly indicate that the source PDF itself does not contain a readable value.

## 9. Convert the workbook to Google Sheets

1. Upload `output/Dati_Pack.xlsx` to Google Drive.
2. Right-click the file.
3. Select **Open with → Google Sheets**.

The coloured columns are the official mapped fields. Grey columns on the right contain operational metadata and may be removed before delivery.

## 10. Common errors

| Symptom | Action |
|---|---|
| `404 model not found` | Query the model list again and use an exact available ID |
| `429`, `500`, or `503` | Let the automatic retry and batching logic handle the temporary API failure |
| `Gemini unreachable after 4 attempts` on a long run | Use `batch_run.py` rather than invoking `run.py` on the full folder |
| `pdftoppm: command not found` | Install Poppler and ensure it is available on the system path |
| Unexpected unreadable fields | Review the source PDF; if necessary, increase rasterization resolution or add a targeted crop |

## Output

The final local output is:

```text
output/Dati_Pack.xlsx
```

Do not commit this file if it contains company or product data.
