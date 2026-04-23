"""
Final Ex-DAV pipeline orchestration.

This module executes the end-to-end flow and returns the final research output
schema for explainable drug authenticity verification.
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.mapping.ontology_mapper import map_validated_metadata_to_ontology
from src.ocr.metadata_validate import parse_metadata, validate_metadata
from src.ocr.ocr_extract import extract_text
from src.reasoning.reasoning_interface import reason_over_ontology_ready_input
from src.verdict.final_decision import decide_final_verdict


def _semantic_flags_list(reasoning_result: Dict[str, Any]) -> List[str]:
    """Convert reasoning flag dictionary into a list of active semantic flags."""
    flags = reasoning_result.get("flags", {}) or {}
    return [name for name, is_active in flags.items() if is_active]


def _build_explanation_list(
    metadata: Dict[str, Any],
    validation_result: Dict[str, Any],
    reasoning_result: Dict[str, Any],
    decision_result: Dict[str, Any],
) -> List[str]:
    """Build a concise explanation list for transparency and traceability."""
    extracted_fields = [
        field
        for field in ["drug_name", "batch_number", "expiry_date", "manufacturer"]
        if metadata.get(field) is not None
    ]
    validation_issues = validation_result.get("issues", [])
    triggered_rules = reasoning_result.get("reasons", [])

    explanation = [
        "Extracted fields: "
        + (", ".join(extracted_fields) if extracted_fields else "none"),
        "Validation failures: "
        + (
            ", ".join(issue.get("code", "UNKNOWN") for issue in validation_issues)
            if validation_issues
            else "none"
        ),
        "Triggered rules: "
        + ("; ".join(triggered_rules) if triggered_rules else "none"),
        "Final decision rationale: " + "; ".join(decision_result.get("explanation", [])),
    ]
    return explanation


def run_pipeline_from_ocr(ocr_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run validation / ontology / reasoning on a completed extract_text() result.

    Used to avoid a duplicate OCR pass on the first image when multiple images
    are processed (process_images already merged per-image OCR).
    """
    metadata = parse_metadata(
        ocr_result.get("text", ""),
        roi_text=ocr_result.get("roi_text", ""),
    )
    validation_result = validate_metadata(metadata)
    ontology_ready = map_validated_metadata_to_ontology(metadata)
    reasoning_result = reason_over_ontology_ready_input(ontology_ready)
    decision_result = decide_final_verdict(
        ocr_result=ocr_result,
        validation_result=validation_result,
        reasoning_result=reasoning_result,
    )

    return {
        "final_verdict": decision_result["final_verdict"],
        "confidence_level": decision_result["confidence_level"],
        "explanation": _build_explanation_list(
            metadata=metadata,
            validation_result=validation_result,
            reasoning_result=reasoning_result,
            decision_result=decision_result,
        ),
        "extracted_metadata": {
            "drug_name": metadata.get("drug_name"),
            "batch_number": metadata.get("batch_number"),
            "expiry_date": metadata.get("expiry_date"),
            "manufacturer": metadata.get("manufacturer"),
        },
        "validation_issues": validation_result.get("issues", []),
        "semantic_flags": _semantic_flags_list(reasoning_result),
        "ocr_text": ocr_result.get("text", ""),
        "ocr_success": bool(ocr_result.get("success")),
        "full_metadata": metadata,
        "completeness_score": float(validation_result.get("completeness_score", 0.0)),
    }


def run_pipeline(image_path: str) -> Dict[str, Any]:
    """
    Run the full Ex-DAV interim pipeline for one image.

    Args:
        image_path: Input drug packaging image path.

    Returns:
        dict: Final structured JSON-ready output.
    """
    ocr_result = extract_text(image_path)
    return run_pipeline_from_ocr(ocr_result)

