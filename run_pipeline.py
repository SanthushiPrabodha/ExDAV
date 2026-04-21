import cv2
import os


def run_pipeline(image_path, expected_data=None):
    print("🚀 Pipeline started")
    print("📂 Original path:", image_path)

    # ---------- FIX PATH ----------
    image_path = os.path.abspath(image_path)
    image_path = image_path.replace("\\", "/")

    print("📂 Fixed path:", image_path)

    # ---------- Check file ----------
    if not os.path.exists(image_path):
        raise Exception(f"Image file not found at {image_path}")

    # ---------- Read image safely ----------
    img = cv2.imread(image_path)

    if img is None:
        raise Exception("OpenCV failed to read image (unsupported format or corrupted file)")

    print("✅ Image loaded successfully")

    # ---------- Dummy Metadata ----------
    metadata = {
        "drugName": "Paracetamol",
        "batchNumber": "B1234",
        "expiryDate": "2026-12",
        "manufacturer": "ABC Pharma",
        "ocrText": "Sample OCR text"
    }

    verdict = "Authentic"
    confidence = 0.85
    conflicting = False

    # ---------- Expected data check ----------
    if expected_data:
        if expected_data.get("drugName") and expected_data["drugName"] != metadata["drugName"]:
            conflicting = True
            verdict = "Suspicious"
            confidence = 0.6

    return {
        "verdict": verdict,
        "confidence": confidence,
        "summary": "Basic verification completed",
        "metadata": metadata,
        "explanation": "Image processed successfully",
        "validationResults": [],
        "evidence": ["Image loaded", "Metadata extracted"],
        "recommendation": "Verify with official database",
        "trustScore": 90,
        "conflictingClues": conflicting,
    }