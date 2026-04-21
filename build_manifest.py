"""
build_manifest.py
=================
Auto-generate an evaluation manifest (eval_manifest.json) from the
existing dataset structure and drug_list.csv metadata.

The dataset layout is:
    dataset/images/<DrugName_Strength_Form>/<genuine|counterfeit>/img_NNN.jpg

This script:
1. Reads dataset/metadata/drug_list.csv  →  drug_name, strength, dosage_form
2. Walks dataset/images/                 →  one entry per image file
3. Infers `verdict` from the subfolder name:
       genuine      → Authentic
       counterfeit  → Counterfeit
       suspicious   → Suspicious
       (anything else → Inconclusive)
4. Writes the ground-truth fields it KNOWS from the CSV;
   leaves batch_number / expiry_date / manufacturer empty
   (these require manual labelling).
5. Saves eval_manifest.json ready for use with evaluate.py.

Usage
-----
    python build_manifest.py [--limit N] [--output eval_manifest.json]

Options
-------
--limit   : max images per drug/label combination (default: 5)
--output  : output manifest path (default: eval_manifest.json)
--all     : include all images (overrides --limit)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random

ROOT = os.path.dirname(os.path.abspath(__file__))
DATASET_IMAGES = os.path.join(ROOT, "dataset", "images")
DRUG_LIST_CSV = os.path.join(ROOT, "dataset", "metadata", "drug_list.csv")

_VERDICT_MAP = {
    "genuine": "Authentic",
    "authentic": "Authentic",
    "counterfeit": "Counterfeit",
    "fake": "Counterfeit",
    "suspicious": "Suspicious",
    "suspect": "Suspicious",
}

_IMG_EXTS = {".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"}


def _load_drug_meta() -> dict:
    """Return {normalised_prefix → {drug_name, strength, dosage_form}}."""
    meta = {}
    if not os.path.exists(DRUG_LIST_CSV):
        return meta
    with open(DRUG_LIST_CSV, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = row.get("drug_name", "").strip()
            strength = row.get("strength", "").strip()
            form = row.get("dosage_form", "").strip()
            # Build a normalised key matching the folder name prefix
            key = name.lower().replace(" ", "_")
            meta[key] = {"drug_name": name, "strength": strength, "dosage_form": form}
    return meta


def _folder_verdict(path_parts: list) -> str:
    """Infer verdict from any path component that matches the verdict map."""
    for part in path_parts:
        v = _VERDICT_MAP.get(part.lower())
        if v:
            return v
    return "Inconclusive"


def _match_drug(folder_name: str, drug_meta: dict) -> dict:
    """Match a dataset folder name to the closest drug in drug_list.csv."""
    lower = folder_name.lower()
    for key, info in drug_meta.items():
        if lower.startswith(key):
            return info
    # Fallback: first word of folder
    first = lower.split("_")[0]
    for key, info in drug_meta.items():
        if first == key or first in key:
            return info
    return {}


def build_manifest(limit: int = 5, output: str = "eval_manifest.json",
                   include_all: bool = False) -> None:
    drug_meta = _load_drug_meta()
    entries = []

    if not os.path.isdir(DATASET_IMAGES):
        print(f"Dataset images directory not found: {DATASET_IMAGES}")
        return

    for drug_folder in sorted(os.listdir(DATASET_IMAGES)):
        drug_dir = os.path.join(DATASET_IMAGES, drug_folder)
        if not os.path.isdir(drug_dir):
            continue
        meta = _match_drug(drug_folder, drug_meta)

        # Walk sub-directories (genuine / counterfeit / or flat)
        sublabels = [
            d for d in os.listdir(drug_dir)
            if os.path.isdir(os.path.join(drug_dir, d))
        ]
        if not sublabels:
            sublabels = [""]  # flat layout: images directly in drug_dir

        for sublabel in sublabels:
            img_dir = os.path.join(drug_dir, sublabel) if sublabel else drug_dir
            images = [
                f for f in os.listdir(img_dir)
                if os.path.splitext(f)[1] in _IMG_EXTS
            ]
            if not include_all and limit:
                random.seed(42)
                images = random.sample(images, min(limit, len(images)))

            path_parts = [drug_folder, sublabel]
            verdict = _folder_verdict(path_parts)

            for img_name in sorted(images):
                rel_path = os.path.relpath(
                    os.path.join(img_dir, img_name), ROOT
                ).replace("\\", "/")
                entry = {
                    "image": rel_path,
                    "ground_truth": {
                        "drug_name":    meta.get("drug_name", ""),
                        "batch_number": "",   # fill manually for full eval
                        "expiry_date":  "",   # fill manually for full eval
                        "manufacturer": "",   # fill manually for full eval
                        "verdict":      verdict,
                    },
                }
                entries.append(entry)

    out_path = os.path.join(ROOT, output)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2)

    print(f"Manifest written: {out_path}  ({len(entries)} entries)")
    verdict_counts: dict = {}
    for e in entries:
        v = e["ground_truth"]["verdict"]
        verdict_counts[v] = verdict_counts.get(v, 0) + 1
    for v, c in sorted(verdict_counts.items()):
        print(f"  {v:<15}: {c}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Ex-DAV evaluation manifest")
    parser.add_argument("--limit", type=int, default=5,
                        help="Max images per drug/label combination (default: 5)")
    parser.add_argument("--output", default="eval_manifest.json",
                        help="Output path (default: eval_manifest.json)")
    parser.add_argument("--all", action="store_true",
                        help="Include all images (overrides --limit)")
    args = parser.parse_args()
    build_manifest(limit=args.limit, output=args.output, include_all=args.all)
