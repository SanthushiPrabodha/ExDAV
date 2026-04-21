"""
Final decision module for Ex-DAV.

Combines OCR status, metadata validation output, and semantic reasoning flags
into a conservative final verdict with trust level and plain explanation.
"""

from __future__ import annotations

from typing import Any, Dict, List


def decide_final_verdict(
    ocr_result: Dict[str, Any],
    validation_result: Dict[str, Any],
    reasoning_result: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build final decision from OCR, validation, and reasoning signals.

    Returns:
        dict: {
            "final_verdict": "Authentic" | "Counterfeit" | "Suspicious" | "Inconclusive",
            "confidence_level": "High" | "Medium" | "Low",
            "explanation": list[str]
        }
    """
    flags = reasoning_result.get("flags", {}) or {}
    issues = validation_result.get("issues", []) or []
    completeness = float(validation_result.get("completeness_score", 0))
    ocr_success = bool(ocr_result.get("success"))

    issue_codes = {issue.get("code") for issue in issues if isinstance(issue, dict)}
    has_errors = any(issue.get("severity") == "error" for issue in issues if isinstance(issue, dict))

    reasons: List[str] = []
    if not ocr_success:
        reasons.append("OCR extraction failed")
    if has_errors:
        reasons.append(f"Validation returned {len(issues)} issue(s)")
    if flags.get("metadata_conflict"):
        reasons.append("Semantic reasoning detected metadata conflict")
    if flags.get("incomplete_evidence"):
        reasons.append("Semantic reasoning indicates incomplete evidence")

    if not ocr_success or flags.get("incomplete_evidence") or completeness < 100:
        verdict = "Inconclusive"
        confidence_level = "Low"
    elif flags.get("metadata_conflict") and completeness >= 100 and ocr_success:
        verdict = "Counterfeit"
        confidence_level = "High"
    elif flags.get("suspicious") or has_errors or "EXPIRED_PRODUCT" in issue_codes:
        verdict = "Suspicious"
        confidence_level = "Medium" if completeness >= 66 else "Low"
    elif (
        flags.get("likely_authentic")
        and not has_errors
        and "EXPIRED_PRODUCT" not in issue_codes
        and completeness >= 100
    ):
        verdict = "Authentic"
        confidence_level = "High"
    else:
        verdict = "Inconclusive"
        confidence_level = "Low"

    if not reasons:
        reasons = [
            "Evidence is complete and consistent across OCR, validation, and reasoning."
        ]

    return {
        "final_verdict": verdict,
        "confidence_level": confidence_level,
        "explanation": reasons,
    }

