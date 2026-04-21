import sys
import os
sys.path.append(os.path.dirname(__file__))

from ocr_extract import extract_text
from metadata_validate import parse_metadata, validate_metadata


import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

image_path = os.path.join(BASE_DIR, "dataset", "images", "Zyrtec_OralDrops", "img_008.jpg")

print("🔍 Running OCR...")
ocr_result = extract_text(image_path)
ocr_text = ocr_result["text"]

print("\n====== OCR TEXT ======")
print(ocr_text if ocr_text else "[NO RELIABLE TEXT DETECTED]")
if not ocr_result["success"] and ocr_result["error"]:
    print(f"OCR error: {ocr_result['error']}")

metadata = parse_metadata(ocr_text)

print("\n====== PARSED METADATA ======")
for k, v in metadata.items():
    print(f"{k}: {v}")

issues = validate_metadata(metadata)

print("\n====== VALIDATION RESULT ======")
if issues["issues"]:
    for issue in issues["issues"]:
        print(f"❌ [{issue['code']}] {issue['message']}")
else:
    print("✅ No issues detected")
print(f"Completeness score: {issues['completeness_score']}%")
