import json
import tempfile
from pathlib import Path

import streamlit as st

from src.pipeline.run_pipeline import run_pipeline


st.set_page_config(page_title="Ex-DAV Showcase", page_icon="💊", layout="wide")

st.title("Ex-DAV: Explainable Drug Authenticity Verification")

uploaded = st.file_uploader(
    "Upload a drug packaging image", type=["jpg", "jpeg", "png", "bmp", "webp"]
)

if uploaded is not None:
    st.image(uploaded, caption="Uploaded image", width="stretch")

    suffix = Path(uploaded.name).suffix or ".jpg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(uploaded.read())
        temp_path = temp_file.name

    result = run_pipeline(temp_path)

    c1, c2 = st.columns(2)
    c1.metric("Final Verdict", result["final_verdict"])
    c2.metric("Confidence", result["confidence_level"])

    st.subheader("Explanation")
    for item in result.get("explanation", []):
        st.write(f"- {item}")

    st.subheader("Extracted Metadata")
    st.json(result.get("extracted_metadata", {}))

    st.subheader("Validation Issues")
    st.json(result.get("validation_issues", []))

    st.subheader("Semantic Flags")
    st.json(result.get("semantic_flags", []))

    st.subheader("Raw JSON")
    st.code(json.dumps(result, indent=2), language="json")
else:
    st.info("Upload an image to run the Ex-DAV pipeline.")

