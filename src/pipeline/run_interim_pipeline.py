"""
Interim Ex-DAV pipeline orchestrator.

Pipeline:
Image -> OCR -> metadata parsing -> validation -> ontology-ready mapping
-> reasoning -> final verdict -> explanation
"""

from __future__ import annotations

from typing import Any, Dict

from src.mapping.ontology_mapper import map_validated_metadata_to_ontology
from src.ocr.metadata_validate import parse_metadata, validate_metadata
from src.ocr.ocr_extract import extract_text
from src.reasoning.reasoning_interface import reason_over_ontology_ready_input
from src.verdict.final_decision import decide_final_verdict


def run_interim_pipeline(image_path: str) -> Dict[str, Any]:
    """
    Execute the interim Ex-DAV pipeline for a single image path.

    Args:
        image_path: Path to the input image.

    Returns:
        dict: Structured stage-by-stage output plus final verdict/explanation.
    """
    ocr_result = extract_text(image_path)
    metadata = parse_metadata(ocr_result.get("text", ""))
    validation_result = validate_metadata(metadata)
    ontology_ready = map_validated_metadata_to_ontology(metadata)
    reasoning_result = reason_over_ontology_ready_input(ontology_ready)
    final_decision = decide_final_verdict(
        ocr_result=ocr_result,
        validation_result=validation_result,
        reasoning_result=reasoning_result,
    )

    return {
        "image_path": image_path,
        "ocr": ocr_result,
        "metadata": metadata,
        "validation": validation_result,
        "ontology_ready": ontology_ready,
        "reasoning": reasoning_result,
        "final_verdict": final_decision["final_verdict"],
        "trust_level": final_decision["confidence_level"],
        "explanation": final_decision["explanation"],
    }

