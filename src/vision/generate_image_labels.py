import os
import csv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMAGE_DIR = os.path.join(BASE_DIR, "dataset", "images")
OUTPUT_CSV = os.path.join(BASE_DIR, "dataset", "metadata", "image_labels.csv")

rows = []

for label in ["genuine", "counterfeit"]:
    folder = os.path.join(IMAGE_DIR, label)
    if not os.path.exists(folder):
        continue

    for img in os.listdir(folder):
        if img.lower().endswith((".jpg", ".png", ".jpeg")):
            drug_id = img.split("_")[0]   # D001 from D001_01.jpg
            rows.append([img, drug_id, label])

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["image_name", "drug_id", "visual_label"])
    writer.writerows(rows)

print(f"✅ image_labels.csv created with {len(rows)} entries")