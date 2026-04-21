"""
Ex-DAV Evaluation Framework
============================
Quantitative evaluation of the Ex-DAV pipeline against a ground-truth
manifest.  Produces per-field extraction metrics (Precision, Recall, F1)
and verdict classification accuracy — the core empirical results for MSc
AI research reporting.

Usage
-----
1. Create a manifest file (see MANIFEST FORMAT below).
2. Activate the project virtual environment.
3. Run:
       python evaluate.py --manifest eval_manifest.json --report eval_report.json

Manifest Format
---------------
A JSON array where each entry represents one test image:

  [
    {
      "image": "dataset/alphintern_cn_31.jpg",
      "ground_truth": {
        "drug_name":    "Alphintern",
        "batch_number": "AL2023001",
        "expiry_date":  "06-2025",
        "manufacturer": "Amoun Pharmaceutical",
        "verdict":      "Authentic"
      }
    },
    ...
  ]

Fields in ground_truth are optional; omit a field to skip it in metrics.
`verdict` must be one of: Authentic | Suspicious | Inconclusive | Counterfeit

Output
------
Prints a formatted table to stdout and writes a JSON report to --report.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------------------------
# Path bootstrap — allow running from project root without installation
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# Lazy import: pipeline only loaded when evaluate() is called so that
# importing this module (e.g. in tests) does not require all heavy deps.
_pipeline = None

def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from backend.services.pipeline_service import process_image
        _pipeline = process_image
    return _pipeline


# ---------------------------------------------------------------------------
# FIELD MATCHING HELPERS
# ---------------------------------------------------------------------------

def _normalise(value: Optional[str]) -> str:
    """Lower-case, strip, collapse whitespace for fair comparison."""
    return " ".join((value or "").lower().split())


def _field_match(predicted: Optional[str], ground_truth: Optional[str],
                 fuzzy_threshold: float = 0.80) -> Tuple[bool, float]:
    """
    Returns (exact_match, similarity_score).

    Exact match: normalised strings are identical.
    Similarity : SequenceMatcher ratio — used for fuzzy partial credit.

    The fuzzy_threshold is intentionally generous (0.80) to account for
    OCR noise that slightly corrupts a correctly extracted value.
    """
    p = _normalise(predicted)
    g = _normalise(ground_truth)
    if not g:
        return True, 1.0   # no ground truth → skip (treated as N/A)
    if not p:
        return False, 0.0
    exact = p == g
    similarity = SequenceMatcher(None, p, g).ratio()
    return exact, similarity


# ---------------------------------------------------------------------------
# PER-FIELD METRIC ACCUMULATOR
# ---------------------------------------------------------------------------

@dataclass
class FieldMetrics:
    field: str
    tp: int = 0       # true positive  (extracted AND correct)
    fp: int = 0       # false positive  (extracted BUT wrong)
    fn: int = 0       # false negative  (not extracted, had ground truth)
    na: int = 0       # not applicable  (no ground truth for this image)
    similarity_sum: float = 0.0
    similarity_count: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def mean_similarity(self) -> float:
        return self.similarity_sum / self.similarity_count if self.similarity_count else 0.0

    def update(self, predicted: Optional[str], ground_truth: Optional[str],
               fuzzy_threshold: float = 0.80) -> None:
        if not ground_truth:
            self.na += 1
            return
        exact, sim = _field_match(predicted, ground_truth, fuzzy_threshold)
        if predicted:
            if exact or sim >= fuzzy_threshold:
                self.tp += 1
            else:
                self.fp += 1
            self.similarity_sum += sim
            self.similarity_count += 1
        else:
            self.fn += 1


# ---------------------------------------------------------------------------
# VERDICT METRICS
# ---------------------------------------------------------------------------

@dataclass
class VerdictMetrics:
    correct: int = 0
    total: int = 0
    per_class: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def update(self, predicted: str, ground_truth: str) -> None:
        if not ground_truth:
            return
        self.total += 1
        if predicted.lower() == ground_truth.lower():
            self.correct += 1
        gt = ground_truth.lower()
        pr = predicted.lower()
        if gt not in self.per_class:
            self.per_class[gt] = {"tp": 0, "fp_other": 0, "fn": 0}
        if pr == gt:
            self.per_class[gt]["tp"] += 1
        else:
            self.per_class[gt]["fn"] += 1
            if pr not in self.per_class:
                self.per_class[pr] = {"tp": 0, "fp_other": 0, "fn": 0}
            self.per_class[pr]["fp_other"] += 1

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


# ---------------------------------------------------------------------------
# EVALUATION ENGINE
# ---------------------------------------------------------------------------

FIELDS = ["drug_name", "batch_number", "expiry_date", "manufacturer"]


def evaluate(manifest_path: str, fuzzy_threshold: float = 0.80,
             abort_on_error: bool = False) -> dict:
    """
    Run the Ex-DAV pipeline on every image in the manifest and compute metrics.

    Parameters
    ----------
    manifest_path    : path to JSON manifest file
    fuzzy_threshold  : similarity ratio for a fuzzy-correct extraction (0–1)
    abort_on_error   : if True, raise on first pipeline failure

    Returns
    -------
    dict with keys: field_metrics, verdict_metrics, per_image_results, summary
    """
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    process_image = _get_pipeline()

    field_acc: Dict[str, FieldMetrics] = {f: FieldMetrics(field=f) for f in FIELDS}
    verdict_acc = VerdictMetrics()
    per_image: List[dict] = []

    for idx, entry in enumerate(manifest):
        img_path = os.path.join(ROOT, entry["image"])
        gt = entry.get("ground_truth", {})

        print(f"[{idx+1}/{len(manifest)}] {entry['image']} ...", end=" ", flush=True)
        t0 = time.time()

        try:
            result = process_image(img_path)
            elapsed = time.time() - t0
        except Exception as exc:
            print(f"ERROR: {exc}")
            if abort_on_error:
                raise
            per_image.append({
                "image": entry["image"],
                "error": str(exc),
                "elapsed_s": round(time.time() - t0, 2),
            })
            continue

        predicted_meta = result.get("metadata", {})
        predicted_verdict = result.get("verdict", "")

        # Per-field metrics
        field_results = {}
        for f in FIELDS:
            pred = predicted_meta.get(f)
            truth = gt.get(f)
            field_acc[f].update(pred, truth, fuzzy_threshold)
            _, sim = _field_match(pred, truth, fuzzy_threshold)
            field_results[f] = {
                "predicted": pred or "",
                "ground_truth": truth or "",
                "similarity": round(sim, 3),
                "match": (not truth) or sim >= fuzzy_threshold,
            }

        # Verdict metrics
        gt_verdict = gt.get("verdict", "")
        verdict_acc.update(predicted_verdict, gt_verdict)

        print(
            f"verdict={predicted_verdict!r:14s} "
            f"gt={gt_verdict!r:14s} "
            f"elapsed={elapsed:.1f}s"
        )

        per_image.append({
            "image": entry["image"],
            "predicted_verdict": predicted_verdict,
            "ground_truth_verdict": gt_verdict,
            "verdict_correct": predicted_verdict.lower() == gt_verdict.lower() if gt_verdict else None,
            "fields": field_results,
            "trust_score": result.get("trustScore"),
            "confidence": result.get("confidence"),
            "elapsed_s": round(elapsed, 2),
        })

    # Compile final report
    field_report = {}
    for f, m in field_acc.items():
        field_report[f] = {
            "precision": round(m.precision, 3),
            "recall": round(m.recall, 3),
            "f1": round(m.f1, 3),
            "mean_similarity": round(m.mean_similarity, 3),
            "tp": m.tp, "fp": m.fp, "fn": m.fn, "na": m.na,
        }

    summary = {
        "images_evaluated": len(manifest),
        "images_with_errors": sum(1 for r in per_image if "error" in r),
        "verdict_accuracy": round(verdict_acc.accuracy, 3),
        "verdict_total": verdict_acc.total,
        "verdict_correct": verdict_acc.correct,
        "mean_f1_across_fields": round(
            sum(field_report[f]["f1"] for f in FIELDS) / len(FIELDS), 3
        ),
        "fuzzy_threshold_used": fuzzy_threshold,
    }

    return {
        "summary": summary,
        "field_metrics": field_report,
        "verdict_metrics": {
            "accuracy": round(verdict_acc.accuracy, 3),
            "per_class": verdict_acc.per_class,
        },
        "per_image_results": per_image,
    }


# ---------------------------------------------------------------------------
# PRETTY-PRINT TABLE
# ---------------------------------------------------------------------------

def _print_report(report: dict) -> None:
    s = report["summary"]
    fm = report["field_metrics"]

    print("\n" + "=" * 68)
    print("  Ex-DAV EVALUATION REPORT")
    print("=" * 68)
    print(f"  Images evaluated  : {s['images_evaluated']}")
    print(f"  Errors            : {s['images_with_errors']}")
    print(f"  Verdict accuracy  : {s['verdict_accuracy']:.1%}  "
          f"({s['verdict_correct']}/{s['verdict_total']})")
    print(f"  Mean field F1     : {s['mean_f1_across_fields']:.3f}")
    print(f"  Fuzzy threshold   : {s['fuzzy_threshold_used']}")
    print("-" * 68)
    print(f"  {'Field':<20} {'P':>6} {'R':>6} {'F1':>6} {'Sim':>6}  TP  FP  FN  NA")
    print("-" * 68)
    for f in FIELDS:
        m = fm[f]
        print(
            f"  {f:<20} {m['precision']:>6.3f} {m['recall']:>6.3f} "
            f"{m['f1']:>6.3f} {m['mean_similarity']:>6.3f}"
            f"  {m['tp']:>2}  {m['fp']:>2}  {m['fn']:>2}  {m['na']:>2}"
        )
    print("=" * 68 + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate the Ex-DAV pipeline against a ground-truth manifest."
    )
    parser.add_argument("--manifest", required=True,
                        help="Path to JSON manifest file")
    parser.add_argument("--report", default="eval_report.json",
                        help="Output path for JSON report (default: eval_report.json)")
    parser.add_argument("--fuzzy", type=float, default=0.80,
                        help="Fuzzy similarity threshold 0–1 (default: 0.80)")
    parser.add_argument("--abort-on-error", action="store_true",
                        help="Stop on first pipeline failure")
    args = parser.parse_args()

    report = evaluate(
        manifest_path=args.manifest,
        fuzzy_threshold=args.fuzzy,
        abort_on_error=args.abort_on_error,
    )
    _print_report(report)

    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"Full report saved to: {args.report}\n")
