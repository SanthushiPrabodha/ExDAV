"""
Ontology mapping layer for Ex-DAV.

This module converts validated metadata into ontology-ready structured data.
It is intentionally independent from OCR extraction and validation logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _normalize_text(value: Any) -> Optional[str]:
    """
    Normalize a metadata value into a clean string.

    Returns None when the value is missing or empty after cleanup.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def map_validated_metadata_to_ontology(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map validated metadata into ontology-ready structured payload.

    Args:
        metadata: A dictionary containing validated metadata fields such as
            drug_name, dosage_form, strength, package_size, batch_number,
            expiry_date, and manufacturer.

    Returns:
        dict: A mapping payload with:
            - properties: ontology property values ready for assignment
            - missing_fields: metadata fields missing after normalization
            - warnings: non-fatal mapping notes

    Notes:
        - The mapper is conservative and does not invent values.
        - It keeps values as strings to avoid unit-lossy coercion
          (e.g., "30g", "125ml", "5cm x 5yd").
    """
    properties = {
        "drugName": _normalize_text(metadata.get("drug_name")),
        "dosageForm": _normalize_text(metadata.get("dosage_form")),
        "strength": _normalize_text(metadata.get("strength")),
        "packageSize": _normalize_text(metadata.get("package_size")),
        "batchNumber": _normalize_text(metadata.get("batch_number")),
        "expiryDate": _normalize_text(metadata.get("expiry_date")),
        "manufacturer": _normalize_text(metadata.get("manufacturer")),
    }

    missing_fields: List[str] = [
        field_name for field_name, value in properties.items() if value is None
    ]
    warnings: List[str] = []

    if missing_fields:
        warnings.append(
            "Some metadata fields are missing and will not be asserted: "
            + ", ".join(missing_fields)
        )

    return {
        "properties": properties,
        "missing_fields": missing_fields,
        "warnings": warnings,
    }

