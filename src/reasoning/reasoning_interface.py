"""
Reasoning interface for Ex-DAV.

This module accepts ontology-ready mapped input and produces semantic flags.
The default implementation is a lightweight rule-based reasoner designed to be
easy to replace later with a full semantic backend (e.g., Protégé/Jena).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


REQUIRED_EVIDENCE_FIELDS = ["drugName", "batchNumber", "expiryDate"]


def _is_expired(expiry_value: str) -> bool:
    """Return True if the expiry month/year is strictly in the past relative to today."""
    if not expiry_value:
        return False
    if "/" in expiry_value:
        parts = expiry_value.split("/")
    elif "-" in expiry_value:
        parts = expiry_value.split("-")
    else:
        return False
    if len(parts) != 2:
        return False
    month_s, year_s = parts[0], parts[1]
    if not (month_s.isdigit() and year_s.isdigit()):
        return False
    month_i = int(month_s)
    if month_i < 1 or month_i > 12:
        return False
    year_i = 2000 + int(year_s) if len(year_s) == 2 else int(year_s)
    now = datetime.now()
    # Product is expired when the expiry month/year is before the current month
    return (year_i < now.year) or (year_i == now.year and month_i < now.month)


def reason_over_ontology_ready_input(mapped_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Produce interim semantic flags from ontology-ready mapping output.

    Args:
        mapped_payload: Output of ontology mapper containing at least:
            - properties: dict of ontology property values
            - missing_fields: list[str] (optional)
            - warnings: list[str] (optional)

    Returns:
        dict: Structured reasoning output:
            {
              "flags": {
                "suspicious": bool,
                "incomplete_evidence": bool,
                "metadata_conflict": bool,
                "likely_authentic": bool
              },
              "reasons": list[str],
              "engine": "rule_based_v1"
            }
    """
    properties = mapped_payload.get("properties", {}) or {}
    missing_fields = mapped_payload.get("missing_fields", []) or []
    reasons: List[str] = []

    missing_required = [
        field for field in REQUIRED_EVIDENCE_FIELDS if not properties.get(field)
    ]

    incomplete_evidence = bool(missing_required or missing_fields)
    if missing_required:
        reasons.append(
            "Missing required evidence fields: " + ", ".join(missing_required)
        )

    metadata_conflict = False
    expiry_value = properties.get("expiryDate")
    if expiry_value and _is_expired(expiry_value):
        metadata_conflict = True
        reasons.append("Expiry indicates product may be expired")

    suspicious = incomplete_evidence or metadata_conflict
    likely_authentic = not suspicious

    return {
        "flags": {
            "suspicious": suspicious,
            "incomplete_evidence": incomplete_evidence,
            "metadata_conflict": metadata_conflict,
            "likely_authentic": likely_authentic,
        },
        "reasons": reasons,
        "engine": "rule_based_v1",
    }

