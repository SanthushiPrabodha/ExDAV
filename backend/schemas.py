from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Metadata(BaseModel):
    drug_name: Optional[str] = None
    dosage: Optional[str] = None
    manufacturer: Optional[str] = None
    batch_number: Optional[str] = None
    manufactured_date: Optional[str] = None
    expiry_date: Optional[str] = None
    detected_logos: List[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    guideline: str
    rule: str
    status: str
    detail: str
    severity: str


class AnalysisResponse(BaseModel):
    verdict: str
    confidence: float
    explanation: List[str]
    metadata: Metadata
    validationResults: List[ValidationResult]
    trustScore: float
    conflictingClues: bool
    ocr_raw_text: Optional[str] = ""
    featureImportances: Optional[Dict[str, float]] = Field(default_factory=dict)
    # ── New fields (NMRA & multi-image) ──────────────────────────────
    nmra_status: Optional[str] = "Not Found"
    manufacturer_match: Optional[bool] = False
    number_of_images_processed: Optional[int] = 1
    # Full NMRA integration payload (record, validation flags, narrative)
    nmra: Optional[Dict[str, Any]] = None