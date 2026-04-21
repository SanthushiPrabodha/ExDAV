# Ex-DAV Showcase Demo

This folder provides a quick, repeatable demo flow for supervisors and showcase visitors.

## 1) Install dependencies

From project root:

```bash
pip install -r requirements.txt
```

Install Tesseract OCR and set the executable path if needed:

```bash
# Windows PowerShell example
$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
```

## 2) Run CLI demo

```bash
python run_pipeline.py --image "path/to/your/demo_image.jpg" --save-json --save-html
```

This prints JSON and saves timestamped reports under `outputs/`.

## 3) Run upload UI demo

```bash
streamlit run streamlit_app.py
```

Then upload a drug package image and review:

- final verdict
- confidence
- explanation bullets
- extracted metadata
- validation issues
- semantic flags

## Notes

- If evidence is incomplete or OCR is poor, Ex-DAV is intentionally conservative and returns `Inconclusive`.
- Use clear, front-facing package images for the best demo OCR quality.
