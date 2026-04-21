# Ex-DAV (Explainable Drug Authenticity Verification)

Modular research pipeline: drug packaging image → OCR → metadata parsing → validation → ontology-ready mapping → rule-based reasoning → final verdict with explainability.

## Requirements

- Python 3 with project dependencies installed (see existing `venv` / `exdav_env` if you use them).
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed.
- Optional environment variable for Tesseract executable:
  - PowerShell: `$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run the full pipeline (CLI)

From the repository root (`ExDAV`):

```bash
python run_pipeline.py --image "path/to/packaging.jpg"
```

### Output format

- **Pretty JSON** (default): indented
- **Compact JSON**: single-line

```bash
python run_pipeline.py --image "path/to/packaging.jpg" --format compact
```

### Save JSON report

- **Auto path** (timestamped file under `outputs/`):

```bash
python run_pipeline.py --image "path/to/packaging.jpg" --save-json
```

- **Explicit file**:

```bash
python run_pipeline.py --image "path/to/packaging.jpg" --save-json "reports/run1.json"
```

- **Directory** (timestamped filename inside that folder):

```bash
python run_pipeline.py --image "path/to/packaging.jpg" --save-json "reports"
```

### Save HTML report (demo-friendly)

- **Auto path** (timestamped file under `outputs/`):

```bash
python run_pipeline.py --image "path/to/packaging.jpg" --save-html
```

- **Explicit file**:

```bash
python run_pipeline.py --image "path/to/packaging.jpg" --save-html "reports/run1.html"
```

### Save both JSON + HTML

```bash
python run_pipeline.py --image "path/to/packaging.jpg" --save-json --save-html
```

## Upload-based showcase UI

Run the Streamlit demo:

```bash
streamlit run streamlit_app.py
```

The UI lets users upload a packaging image and view verdict, confidence, explainability, metadata, and full JSON.

## Expected JSON output shape

The pipeline prints (and optionally saves) JSON with roughly this structure:

```json
{
  "final_verdict": "Authentic | Counterfeit | Suspicious | Inconclusive",
  "confidence_level": "High | Medium | Low",
  "explanation": [
    "Extracted fields: ...",
    "Validation failures: ...",
    "Triggered rules: ...",
    "Final decision rationale: ..."
  ],
  "extracted_metadata": {
    "drug_name": null,
    "batch_number": null,
    "expiry_date": null,
    "manufacturer": null
  },
  "validation_issues": [
    {
      "field": "expiry_date",
      "code": "MISSING_REQUIRED_FIELD",
      "severity": "error",
      "message": "..."
    }
  ],
  "semantic_flags": [
    "suspicious",
    "incomplete_evidence",
    "metadata_conflict",
    "likely_authentic"
  ]
}
```

**Notes**

- `semantic_flags` lists **only active** flags from the reasoning layer (boolean `true` in the internal engine).
- Missing or noisy OCR and incomplete required metadata favor **`Inconclusive`** with **low** confidence where appropriate.
- Validation `code` values include (non-exhaustive): `MISSING_REQUIRED_FIELD`, `INVALID_EXPIRY_FORMAT`, `EXPIRED_PRODUCT`, `INCONSISTENT_VALUE`.

## Main modules (overview)

| Area | Path |
|------|------|
| CLI | `run_pipeline.py` |
| Upload UI | `streamlit_app.py` |
| Pipeline | `src/pipeline/run_pipeline.py` |
| HTML report renderer | `src/pipeline/html_report.py` |
| OCR | `src/ocr/ocr_extract.py` |
| Parse + validate | `src/ocr/metadata_validate.py` |
| Ontology-ready mapping | `src/mapping/ontology_mapper.py` |
| Reasoning (rule-based, swappable) | `src/reasoning/reasoning_interface.py` |
| Final decision | `src/verdict/final_decision.py` |

## Demo folder

See `demo/README.md` for a quick showcase runbook and `demo/run_demo.py` for a minimal scripted demo command.

## Tests

From repository root:

```bash
python -m unittest discover -s tests -p "test_*.py"
```
