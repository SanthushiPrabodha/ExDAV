import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional

# Repo root must be on sys.path before importing sibling backend modules / src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from backend.services.ocr_brand_fix import (
    coerce_metadata_drug_name,
    normalize_nmra_query_fragment,
)

logger = logging.getLogger("exdav.pipeline")

# Minimum 5 chars to reduce false positives from OCR noise.
# All entries are matched as whole words (see _detect_logos).
# ---------------------------------------------------------------------------
# NMRA / SPC / BNF REGULATORY KEYWORD SETS
# ---------------------------------------------------------------------------

# Regulatory-approval indicators that should appear on authentic packaging.
# Based on NMRA Guideline on Labelling of Medicines (nmra.gov.lk/pages/guidelines)
# and WHO model labelling requirements.
_NMRA_REG_KEYWORDS: List[str] = [
    "NMRA", "REGISTERED", "REGISTRATION", "REG NO", "REG. NO",
    "M.L.:", "ML:", "LICENCE NO", "LICENSE NO", "APPROVED",
    "MARKETING AUTHORISATION", "MARKETING AUTHORIZATION",
    "NDA", "IDA",                       # National / Indian Drug Authority
    "SCHEDULE H", "SCHEDULE G",         # Indian prescription-drug schedules
    "RX ONLY", "RX",
    "TRADE MARK", "TRADEMARK", "REGISTERED TRADE MARK",
]

LOGO_KEYWORDS = [
    "GLAXOSMITHKLINE", "GSK",
    "PFIZER",
    "NOVARTIS",
    "CIPLA",
    "ABBOTT",
    "SANOFI",
    "BAYER",
    "ASTRAZENECA",
    "RECKITT",
    "MERCK",
    "SANDOZ",
    "MYLAN",
    "ASPEN",
    "AMOUN",           # manufacturer of Alphintern
    "HIKMA",
    "JULPHAR",
    "SPIMACO",
    "MARCYRL",
    "EIPICO",
    "PHARCO",
    "EVA PHARMA",
    "MINAPHARM",
    "NEOPHARMA",
    "MEDIBIOS",
    "CARELINK",
    "PHARMATEC", "PHARMANOVA",
    "PROCTER",                   # Procter & Gamble (5 chars, word-boundary safe)
]


def _confidence_to_number(confidence_level: str) -> float:
    mapping = {"HIGH": 0.90, "MEDIUM": 0.65, "LOW": 0.35}
    return mapping.get((confidence_level or "").upper(), 0.40)


def _extract_dosage(metadata: Dict[str, Any], text: str) -> str:
    """Return dosage/strength: prefer the value already parsed by metadata_validate."""
    if metadata.get("strength"):
        return str(metadata["strength"]).strip()
    match = re.search(r"(?<![A-Z])(\d+(?:\.\d+)?\s?(?:MG|G|ML|MCG|IU|%))(?![A-Z0-9])", text.upper())
    return match.group(1).strip() if match else ""


def _build_nmra_search_text(
    drug_name: str,
    dosage: str,
    ocr_text: str,
    *,
    extra_brand_hints: str = "",
    maxlen: int = 520,
) -> str:
    """
    Combine product fields with a capped OCR snippet so NMRA matching can
    resolve brand tokens (e.g. BECLOVENT) and form words (INHALATION, CREAM)
    that are not always captured in drug_name alone.

    *extra_brand_hints* — ROI / fuzzy brand candidates prepended so they participate
    in brand-token scoring before generic stems (e.g. BECLATE vs BECLOMETASONE).
    """
    def _nmfrag(fragment: str) -> str:
        frag = (fragment or "").strip()
        if not frag:
            return ""
        try:
            from src.ocr.metadata_validate import normalize_text as _nmra_norm_fragment

            return _nmra_norm_fragment(frag)
        except Exception:
            return normalize_nmra_query_fragment(frag)

    parts: List[str] = []
    if extra_brand_hints and str(extra_brand_hints).strip():
        parts.append(_nmfrag(str(extra_brand_hints)))
    if drug_name and str(drug_name).strip():
        parts.append(_nmfrag(str(drug_name)))
    if dosage and str(dosage).strip():
        parts.append(_nmfrag(str(dosage)))
    if ocr_text:
        try:
            from src.ocr.metadata_validate import normalize_text as _nmra_norm_ocr

            snippet = _nmra_norm_ocr(ocr_text)
        except Exception:
            snippet = normalize_nmra_query_fragment(ocr_text or "")
        if len(snippet) > maxlen:
            snippet = snippet[:maxlen]
        if snippet:
            parts.append(snippet)
    return " ".join(parts).strip()


def _detect_logos(ocr_text: str) -> List[str]:
    """
    Return known pharma company/brand names detected in OCR text.

    Uses whole-word regex matching (\\b…\\b) to avoid false positives
    from short character sequences that appear inside OCR noise tokens.
    Only keywords >= 5 characters are included in LOGO_KEYWORDS.
    """
    text = (ocr_text or "").upper()
    found = []
    for logo in LOGO_KEYWORDS:
        if re.search(r"\b" + re.escape(logo) + r"\b", text):
            found.append(logo)
    return found


# ---------------------------------------------------------------------------
# SPC / WHO ADDITIONAL KEYWORD SETS
# ---------------------------------------------------------------------------

# SPC Section 6.4 – Special precautions for storage (EMA/CHMP guideline)
_STORAGE_KEYWORDS: List[str] = [
    "STORE", "STORAGE", "REFRIGERATE", "REFRIGERATED", "COOL PLACE",
    "BELOW", "NOT ABOVE", "PROTECT FROM LIGHT", "PROTECT FROM MOISTURE",
    "KEEP DRY", "TEMPERATURE", "DO NOT FREEZE", "ROOM TEMPERATURE",
    "2°C", "8°C", "25°C", "30°C",
]

# SPC Section 4.2 – Posology and method of administration
_ROUTE_KEYWORDS: List[str] = [
    "ORAL", "FOR ORAL USE", "BY MOUTH", "ORAL ADMINISTRATION",
    "TOPICAL", "EXTERNAL USE ONLY", "FOR EXTERNAL USE",
    "INJECTION", "INTRAVENOUS", "INTRAMUSCULAR", "SUBCUTANEOUS",
    "INTRANASAL", "SUBLINGUAL", "BUCCAL",
    "OPHTHALMIC", "OCULAR", "EAR DROPS", "NASAL SPRAY",
    "RECTAL", "VAGINAL", "TRANSDERMAL",
]

# WHO Model Labelling / NMRA – Patient safety warning
_SAFETY_WARNING_KEYWORDS: List[str] = [
    "KEEP OUT OF REACH", "REACH OF CHILDREN", "KEEP AWAY FROM CHILDREN",
    "NOT FOR CHILDREN", "CHILDREN UNDER",
]


def _has_regulatory_indicator(ocr_text: str) -> bool:
    """Return True if the OCR text contains any recognised regulatory indicator."""
    text_upper = (ocr_text or "").upper()
    return any(kw.upper() in text_upper for kw in _NMRA_REG_KEYWORDS)


def _ocr_contains_any(ocr_text: str, keywords: List[str]) -> bool:
    """Case-insensitive substring check for any keyword in OCR text."""
    text_upper = (ocr_text or "").upper()
    return any(kw.upper() in text_upper for kw in keywords)


def _extract_evidence_snippet(ocr_text: str, patterns: List[str], window: int = 70) -> Optional[str]:
    """
    Return a short OCR text snippet around the first pattern match.

    Used to ground each validation finding in the actual label text,
    supporting the explainability requirement for XAI research.

    Parameters
    ----------
    ocr_text : raw OCR string
    patterns : list of regex patterns to search for
    window   : characters to include after the match start
    """
    for pat in patterns:
        m = re.search(pat, ocr_text, re.IGNORECASE)
        if m:
            start = max(0, m.start() - 15)
            end = min(len(ocr_text), m.start() + window)
            snippet = " ".join(ocr_text[start:end].split())  # collapse whitespace
            return f'"{snippet}"'
    return None


def _extra_regulatory_checks(
    metadata: Dict[str, Any],
    ocr_text: str,
    ocr_success: bool,
) -> List[Dict[str, str]]:
    """
    Additional guideline checks beyond mandatory-field presence.

    Checks:
      A. Drug name clarity/visibility
      B. Brand / manufacturer logo presence
      C. NMRA regulatory approval indication

    Returns a list of ValidationResult-style dicts ready to merge into the
    main validation_results list.

    References:
      • NMRA Guideline on Labelling of Medicines (GL-XXX)
        https://www.nmra.gov.lk/pages/guidelines
      • SPC Section 1 (Name of the medicinal product)
      • WHO Model Labelling for Pharmaceuticals
    """
    results: List[Dict[str, str]] = []

    # ── A. Drug name clarity ─────────────────────────────────────────────
    if not metadata.get("drug_name"):
        results.append({
            "guideline": "NMRA / SPC",
            "rule": "Product name must be clearly identifiable on primary packaging",
            "status": "failed",
            "detail": (
                "The product name (brand or generic) could not be reliably identified "
                "from the packaging image. Per the NMRA Guideline on Labelling of Medicines "
                "and SPC Section 1, the non-proprietary name and, where applicable, the brand "
                "name must be prominently displayed on the primary and secondary packaging. "
                "Absence or illegibility of the product name prevents verification against "
                "registered product records and is a significant labelling non-conformance."
            ),
            "severity": "error",
        })
    else:
        results.append({
            "guideline": "NMRA / SPC",
            "rule": "Product name must be clearly identifiable on primary packaging",
            "status": "passed",
            "detail": (
                f"The product name '{metadata['drug_name']}' was identified from the packaging. "
                "This satisfies NMRA labelling requirements for product name visibility."
            ),
            "severity": "info",
        })

    # ── B. Brand / manufacturer logo ─────────────────────────────────────
    if not metadata.get("detected_logos"):
        results.append({
            "guideline": "NMRA / WHO",
            "rule": "Manufacturer or brand identification should be visible on packaging",
            "status": "failed",
            "detail": (
                "No recognised manufacturer logo or brand identifier was detected in the "
                "label text. Per NMRA labelling guidelines and WHO model labelling requirements, "
                "the name and address of the manufacturer or marketing authorisation holder must "
                "appear on the label. The absence of a recognisable brand indicator reduces "
                "confidence in the verified identity of the product source."
            ),
            "severity": "warning",
        })

    # ── C. NMRA regulatory approval indication ───────────────────────────
    if ocr_success and not _has_regulatory_indicator(ocr_text):
        results.append({
            "guideline": "NMRA",
            "rule": "Regulatory approval / registration marking required on packaging",
            "status": "failed",
            "detail": (
                "This packaging does not display any recognisable regulatory approval "
                "information (e.g. NMRA registration number, 'Registered', 'M.L.:', "
                "marketing authorisation number). According to the NMRA Guideline on "
                "Labelling of Medicines (nmra.gov.lk/pages/guidelines), every registered "
                "medicinal product must bear its registration/licence number on the label. "
                "The absence of such markings is a strong indicator of non-compliance or "
                "possible counterfeiting."
            ),
            "severity": "warning",
        })

    # ── D. Storage conditions (SPC Section 6.4 / WHO Model Labelling) ────
    if ocr_success:
        if _ocr_contains_any(ocr_text, _STORAGE_KEYWORDS):
            snippet = _extract_evidence_snippet(ocr_text, _STORAGE_KEYWORDS)
            detail = (
                "Storage condition instructions were detected on the packaging"
                + (f" (evidence: {snippet})" if snippet else "") + ". "
                "This satisfies SPC Section 6.4 (Special precautions for storage) "
                "and WHO Model Labelling requirements."
            )
            results.append({
                "guideline": "SPC 6.4 / WHO",
                "rule": "Storage conditions must be stated on the label",
                "status": "passed",
                "detail": detail,
                "severity": "info",
            })
        else:
            results.append({
                "guideline": "SPC 6.4 / WHO",
                "rule": "Storage conditions must be stated on the label",
                "status": "failed",
                "detail": (
                    "No storage condition instructions (e.g. 'Store below 25°C', "
                    "'Protect from light', 'Keep refrigerated') were detected. "
                    "SPC Section 6.4 and WHO Model Labelling guidelines require that "
                    "storage conditions be clearly stated on the primary and secondary "
                    "packaging to ensure product stability and patient safety."
                ),
                "severity": "warning",
            })

    # ── E. Route of administration (SPC Section 4.2) ──────────────────────
    if ocr_success:
        if _ocr_contains_any(ocr_text, _ROUTE_KEYWORDS):
            snippet = _extract_evidence_snippet(ocr_text, _ROUTE_KEYWORDS)
            detail = (
                "Route of administration was identified on the packaging"
                + (f" (evidence: {snippet})" if snippet else "") + ". "
                "This is consistent with SPC Section 4.2 (Posology and method of "
                "administration) requirements."
            )
            results.append({
                "guideline": "SPC 4.2",
                "rule": "Route/method of administration must be stated",
                "status": "passed",
                "detail": detail,
                "severity": "info",
            })
        else:
            results.append({
                "guideline": "SPC 4.2",
                "rule": "Route/method of administration must be stated",
                "status": "failed",
                "detail": (
                    "The route or method of administration (e.g. 'For oral use', "
                    "'For external use only', 'Topical') was not detected on the label. "
                    "SPC Section 4.2 and NMRA labelling guidelines require the route of "
                    "administration to be unambiguously stated on the packaging to prevent "
                    "medication errors."
                ),
                "severity": "warning",
            })

    # ── F. Patient safety warning (WHO / NMRA / ICH Q10) ─────────────────
    if ocr_success:
        if _ocr_contains_any(ocr_text, _SAFETY_WARNING_KEYWORDS):
            results.append({
                "guideline": "WHO / NMRA",
                "rule": "Patient safety warning (keep out of reach of children) must be present",
                "status": "passed",
                "detail": (
                    "A 'Keep out of reach of children' or equivalent patient safety warning "
                    "was detected on the packaging, satisfying WHO Model Labelling and NMRA "
                    "labelling requirements."
                ),
                "severity": "info",
            })
        else:
            results.append({
                "guideline": "WHO / NMRA",
                "rule": "Patient safety warning (keep out of reach of children) must be present",
                "status": "failed",
                "detail": (
                    "No patient safety warning ('Keep out of reach of children' or equivalent) "
                    "was detected on the packaging. WHO Model Labelling guidelines and NMRA "
                    "requirements mandate this warning on all medicinal products to reduce the "
                    "risk of accidental paediatric ingestion."
                ),
                "severity": "warning",
            })

    return results


_NMRA_FIELD_RULES = {
    "drug_name": (
        "Product name must be clearly displayed on the primary and secondary packaging",
        "The product name (generic and/or brand) is absent from the packaging. "
        "Per NMRA Gazette Extraordinary No. 1862/2 (Labelling of Medicinal Products), "
        "the non-proprietary name must appear prominently. "
        "Absence of the drug name is indicative of a non-compliant or substandard product.",
    ),
    "batch_number": (
        "Batch/lot number must be present for post-market traceability",
        "No valid batch or lot number was identified on the packaging. "
        "NMRA Good Manufacturing Practice (GMP) Regulations require each production unit to carry "
        "a unique batch identifier to enable recall and traceability. "
        "Absence of this identifier is a significant labelling non-compliance.",
    ),
    "expiry_date": (
        "Expiry date must be printed on primary packaging",
        "The expiry date is absent from the extracted label text. "
        "Under NMRA Labelling Requirements and the BNF dispensing guidelines, "
        "a valid expiry date is mandatory on all registered medicinal products. "
        "Products without a discernible expiry date cannot be assessed for safety or efficacy.",
    ),
    "manufacturer": (
        "Manufacturer identity must be declared on the packaging",
        "The manufacturer or licence holder could not be identified from the packaging text. "
        "NMRA registration requirements mandate that the name and address of the manufacturer "
        "or marketing authorisation holder appear on the label. "
        "This omission prevents verification against registered product records.",
    ),
}


def _guideline_validation(
    metadata: Dict[str, Any],
    validation_issues: List[Dict[str, Any]],
    expected_data: Dict[str, Any],
) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    issue_codes = {issue.get("code", "") for issue in validation_issues}

    for field, (rule_text, detail_text) in _NMRA_FIELD_RULES.items():
        if not metadata.get(field):
            results.append(
                {
                    "guideline": "NMRA",
                    "rule": rule_text,
                    "status": "failed",
                    "detail": detail_text,
                    "severity": "error",
                }
            )

    if "EXPIRED_PRODUCT" in issue_codes:
        results.append(
            {
                "guideline": "BNF / NMRA",
                "rule": "Expired medicine must not be dispensed or supplied",
                "status": "failed",
                "detail": (
                    "The expiry date extracted from the packaging indicates this product has passed "
                    "its shelf-life endpoint. Per BNF dispensing guidance and NMRA post-market "
                    "surveillance regulations, dispensing an expired medicinal product is prohibited "
                    "and may constitute adulteration. The product is classified as potentially unsafe."
                ),
                "severity": "error",
            }
        )

    if "INVALID_EXPIRY_FORMAT" in issue_codes:
        results.append(
            {
                "guideline": "SPC / NMRA",
                "rule": "Expiry date must follow a standardised format (MM/YYYY or MM-YYYY)",
                "status": "failed",
                "detail": (
                    "The expiry date detected on the packaging does not conform to the "
                    "internationally recognised format (MM/YYYY). "
                    "SPC (Summary of Product Characteristics) and NMRA label specifications require "
                    "an unambiguous date format to prevent misinterpretation by dispensers and patients."
                ),
                "severity": "warning",
            }
        )

    batch_number = metadata.get("batch_number", "")
    if batch_number and not re.match(r"^[A-Z0-9\-]{3,30}$", str(batch_number).upper()):
        results.append(
            {
                "guideline": "SPC / GMP",
                "rule": "Batch/lot identifier must conform to alphanumeric traceability format",
                "status": "failed",
                "detail": (
                    "The detected batch number contains characters or formatting inconsistent "
                    "with SPC batch-coding conventions and GMP traceability requirements. "
                    "A non-standard batch code impairs supply-chain verification and may indicate "
                    "substandard manufacture or label tampering."
                ),
                "severity": "warning",
            }
        )

    expected_manufacturer = (expected_data or {}).get("manufacturer") or ""
    actual_manufacturer = metadata.get("manufacturer") or ""
    if expected_manufacturer and actual_manufacturer:
        if expected_manufacturer.strip().lower() != actual_manufacturer.strip().lower():
            results.append(
                {
                    "guideline": "NMRA",
                    "rule": "Declared manufacturer must match the registered marketing authorisation holder",
                    "status": "failed",
                    "detail": (
                        f"The manufacturer identified on the packaging ('{actual_manufacturer}') "
                        f"does not match the expected authorised entity ('{expected_manufacturer}'). "
                        "Per NMRA product registration requirements, any discrepancy between the "
                        "declared and registered manufacturer is a strong indicator of a counterfeit "
                        "or diverted product and must be investigated."
                    ),
                    "severity": "error",
                }
            )

    if not results:
        results.append(
            {
                "guideline": "NMRA / SPC / BNF",
                "rule": "Core labelling and safety requirements",
                "status": "passed",
                "detail": (
                    "All extractable labelling fields satisfy NMRA, SPC, and BNF core requirements. "
                    "No mandatory field omissions, expiry violations, or traceability issues were detected."
                ),
                "severity": "info",
            }
        )

    return results


def _compute_trust_score(
    confidence: float,
    completeness_score: float,
    validation_results: List[Dict[str, str]],
    conflicting_clues: bool,
    nmra_registered: bool = False,
    manufacturer_match: bool = False,
    missing_field_count: int = 0,
) -> float:
    """
    Trust score (0–100).

    Base:
      confidence × completeness (both normalised to 0–1) → 0–100

    Bonuses (NMRA-based):
      +30  drug found in NMRA registered medicines list
      +20  extracted manufacturer matches NMRA record

    Penalties:
      -10  per missing mandatory field (batch, expiry, manufacturer, drug name)
      -20  per "error"-severity guideline failure
      -8   per "warning"-severity guideline failure
      -5   conflicting evidence detected
    """
    base = confidence * (completeness_score / 100.0) * 100.0
    bonus = 0.0
    if nmra_registered:
        bonus += 30.0
    if manufacturer_match:
        bonus += 20.0

    penalty = 0.0
    penalty += missing_field_count * 10.0
    for item in validation_results:
        if item["status"] == "failed":
            if item["severity"] == "error":
                penalty += 20.0
            elif item["severity"] == "warning":
                penalty += 8.0
    if conflicting_clues:
        penalty += 5.0

    return round(max(0.0, min(100.0, base + bonus - penalty)), 2)


def _merge_ocr_for_images(image_paths: List[str]) -> Dict[str, Any]:
    """
    Run OCR on every supplied image path and merge the results into a
    single combined text + best ROI text.

    The individual OCR texts are concatenated with a separator so that
    the downstream parse_metadata call sees all available label text.
    The ROI text with the most content is selected as the authoritative
    brand-name source.

    Returns:
        {
          "combined_text": str,   — all OCR texts joined
          "roi_text":      str,   — ROI text from the best image
          "any_success":   bool,  — True if at least one OCR pass succeeded
          "per_image":     list,  — raw result per image for logging
        }
    """
    from src.ocr.ocr_extract import extract_text  # deferred — heavy import

    per_image = []
    texts: List[str] = []
    roi_texts: List[str] = []

    for path in image_paths:
        try:
            result = extract_text(path)
            per_image.append(result)
            if result.get("text"):
                texts.append(result["text"])
            roi_texts.append(result.get("roi_text", "") or "")
        except Exception as exc:
            logger.warning("OCR failed for %s: %s", path, exc)
            per_image.append({"success": False, "text": "", "roi_text": "", "error": str(exc)})
            roi_texts.append("")

    combined_text = "\n--- IMAGE BREAK ---\n".join(t for t in texts if t.strip())
    best_roi = max(roi_texts, key=len, default="")
    any_success = any(r.get("success") for r in per_image)

    return {
        "combined_text": combined_text,
        "roi_text": best_roi,
        "any_success": any_success,
        "per_image": per_image,
    }


def _compose_nmra_summary_text(
    metadata: Dict[str, Any],
    nmra_match: Any,
    manufacturer_match: bool,
) -> str:
    """Narrative paragraph for NMRA integration (shown in System Explanation)."""
    drug = (metadata.get("drug_name") or "").strip() or "the product"
    parts: List[str] = [f"This drug is identified as {drug}."]
    if nmra_match.entry:
        parts.append(
            f"NMRA registration {nmra_match.entry.reg_no or 'N/A'} "
            f"— validation status: {nmra_match.entry.validation_status or 'unknown'}."
        )
    if nmra_match.brand_match is True:
        parts.append("The brand matches the NMRA registered record.")
    elif nmra_match.brand_match is False:
        parts.append(
            "The extracted product name does not match the registered brand name closely "
            "(generic listing or alternate wording may apply)."
        )
    if nmra_match.dosage_match is True:
        parts.append("The extracted dosage matches the NMRA record.")
    elif nmra_match.dosage_match is False:
        parts.append(
            "There is a mismatch between the detected dosage and the NMRA registered dosage."
        )
    if manufacturer_match:
        parts.append(
            "The manufacturer is consistent with the NMRA registered marketing authorisation holder."
        )
    else:
        parts.append(
            "There is a mismatch between the detected manufacturer and the NMRA registered "
            "manufacturer. This may indicate repackaging or a counterfeit risk."
        )
    return " ".join(parts)


def _build_nmra_ui_payload(
    nmra_status: str,
    nmra_match: Any,
    manufacturer_match: bool,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """Structured NMRA block for API / React (full record + validation flags)."""
    mt = getattr(nmra_match, "match_type", None) or ""
    bm = getattr(nmra_match, "brand_match", None)
    ext_mfr = (metadata.get("manufacturer") or "").strip()
    nmra_mfr = ""
    if nmra_status == "Registered" and nmra_match and nmra_match.entry:
        nmra_mfr = (nmra_match.entry.manufacturer or "").strip()

    out: Dict[str, Any] = {
        "status": nmra_status,
        "match_type": mt or None,
        "match_score": float(getattr(nmra_match, "score", 0.0) or 0.0),
        "registered_name": getattr(nmra_match, "matched_name", None),
        "record": None,
        "extracted_manufacturer": ext_mfr,
        "nmra_manufacturer": nmra_mfr,
        "validation": {
            "manufacturer_match": manufacturer_match,
            "brand_match": bm,
            "dosage_match": getattr(nmra_match, "dosage_match", None),
        },
        "display_status": "",
        "summary_text": "",
        # Clarifies that exact_generic ≠ trade name verification
        "match_note": "",
    }
    if nmra_status == "Registered" and nmra_match and nmra_match.entry:
        out["display_status"] = "APPROVED"
        out["record"] = nmra_match.entry.to_display_dict()
        out["summary_text"] = _compose_nmra_summary_text(
            metadata, nmra_match, manufacturer_match
        )
        if "generic" in (mt or "").lower() and bm is False:
            out["match_note"] = (
                "Match is on the generic ingredient (not necessarily the exact trade name on "
                "your pack). Confirm the brand and manufacturer on the label match this line."
            )
    elif nmra_status == "Not Found":
        out["display_status"] = "NOT FOUND"
        out["summary_text"] = (
            "This drug is not found in the NMRA registered database."
        )
    else:
        out["display_status"] = "UNAVAILABLE"
        out["summary_text"] = (
            "NMRA registry could not be loaded; registration status could not be verified."
        )
    return out


def process_image(image_path: str, expected_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Thin wrapper — delegates to process_images for a single image."""
    return process_images([image_path], expected_data)


def process_images(
    image_paths: List[str],
    expected_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    expected_data = expected_data or {}
    n_images = len(image_paths)

    # ── Validate paths ────────────────────────────────────────────────
    valid_paths = [p for p in image_paths if p and os.path.exists(p)]
    if not valid_paths:
        logger.warning("process_images called with no valid paths: %r", image_paths)
        _empty_meta = {
            "drug_name": "", "dosage": "", "manufacturer": "",
            "batch_number": "", "manufactured_date": "", "expiry_date": "",
            "detected_logos": [],
        }
        return {
            "verdict": "Inconclusive", "confidence": 0.0,
            "explanation": ["No valid image was provided. Analysis cannot proceed."],
            "metadata": _empty_meta,
            "validationResults": [{
                "guideline": "NMRA", "rule": "Image evidence required",
                "status": "failed",
                "detail": "No valid image was provided for assessment.",
                "severity": "error",
            }],
            "trustScore": 0.0, "conflictingClues": True, "ocr_raw_text": "",
            "nmra_status": "Unavailable", "manufacturer_match": False,
            "number_of_images_processed": 0, "featureImportances": {},
            "nmra": {
                "status": "Unavailable",
                "display_status": "UNAVAILABLE",
                "record": None,
                "extracted_manufacturer": "",
                "nmra_manufacturer": "",
                "validation": {
                    "manufacturer_match": False,
                    "brand_match": None,
                    "dosage_match": None,
                },
                "summary_text": "Analysis could not run; NMRA data was not consulted.",
            },
        }

    try:
        from src.pipeline.run_pipeline import run_pipeline
        from src.ocr.metadata_validate import (
            extract_expiry_date_from_text,
            extract_manufactured_date_from_text,
            parse_metadata,
        )
    except Exception as exc:
        logger.error("Pipeline import failed: %s", exc)
        _empty_meta = {
            "drug_name": "", "dosage": "", "manufacturer": "",
            "batch_number": "", "manufactured_date": "", "expiry_date": "",
            "detected_logos": [],
        }
        return {
            "verdict": "Inconclusive", "confidence": 0.0,
            "explanation": ["Pipeline dependencies failed to load.", f"Dependency error: {exc}"],
            "metadata": _empty_meta,
            "validationResults": [{
                "guideline": "System", "rule": "Dependency availability",
                "status": "failed",
                "detail": "OCR/reasoning dependencies are not available in the runtime environment.",
                "severity": "error",
            }],
            "trustScore": 0.0, "conflictingClues": True, "ocr_raw_text": "",
            "nmra_status": "Unavailable", "manufacturer_match": False,
            "number_of_images_processed": 0, "featureImportances": {},
            "nmra": {
                "status": "Unavailable",
                "display_status": "UNAVAILABLE",
                "record": None,
                "extracted_manufacturer": "",
                "nmra_manufacturer": "",
                "validation": {
                    "manufacturer_match": False,
                    "brand_match": None,
                    "dosage_match": None,
                },
                "summary_text": "Pipeline unavailable; NMRA data was not consulted.",
            },
        }

    # ── Multi-image OCR ───────────────────────────────────────────────
    # For a single image, run the full run_pipeline (OCR + parse + validate
    # + ontology + reasoning).  For multiple images, we OCR every image,
    # merge the texts, and re-parse combined metadata; then run the rest of
    # the pipeline (validation / ontology / reasoning) on the merged result.
    if n_images == 1:
        base_result = run_pipeline(image_path=valid_paths[0])
        ocr_text: str = base_result.get("ocr_text", "") or ""
        ocr_success: bool = base_result.get("ocr_success", False)
        parsed_metadata: Dict[str, Any] = base_result.get("full_metadata") or {}
        validation_issues: List[Dict[str, Any]] = base_result.get("validation_issues") or []
        completeness: float = base_result.get("completeness_score", 0.0)
    else:
        # Multi-image: merge OCR texts, then re-parse and run pipeline on
        # best image (used for reasoning/verdict), supplementing with merged metadata
        merged_ocr = _merge_ocr_for_images(valid_paths)
        ocr_text = merged_ocr["combined_text"]
        ocr_success = merged_ocr["any_success"]
        roi_text = merged_ocr["roi_text"]

        # Run the full pipeline on the FIRST valid image for reasoning/verdict
        base_result = run_pipeline(image_path=valid_paths[0])

        # Re-parse metadata using ALL combined OCR to fill in fields that
        # might only appear on other images (batch from side panel etc.)
        merged_parsed = parse_metadata(ocr_text, roi_text=roi_text)

        # Merge: combined OCR is authoritative for traceability fields (batch /
        # dates often appear only on a side panel, while image 1 may wrongly
        # pick a plain MM-YYYY as "expiry" from noise).
        base_meta = dict(base_result.get("full_metadata") or {})
        for field in ("batch_number", "expiry_date", "manufactured_date"):
            if merged_parsed.get(field):
                base_meta[field] = merged_parsed[field]
        for field in ("drug_name", "manufacturer", "strength"):
            if not base_meta.get(field) and merged_parsed.get(field):
                base_meta[field] = merged_parsed[field]
        # Always prefer drug_name from the image with higher confidence
        base_conf = base_meta.get("drug_name_confidence", 0)
        merge_conf = merged_parsed.get("drug_name_confidence", 0)
        if merge_conf > base_conf and merged_parsed.get("drug_name"):
            for k in ("drug_name", "drug_name_source", "drug_name_confidence",
                      "drug_name_roi_candidate", "drug_name_fuzzy_candidate"):
                base_meta[k] = merged_parsed.get(k)

        parsed_metadata = base_meta
        validation_issues = base_result.get("validation_issues") or []
        completeness = base_result.get("completeness_score", 0.0)

    logger.info(
        "OCR result: success=%s, text_length=%d chars",
        ocr_success,
        len(ocr_text),
    )
    logger.info(
        "Extracted metadata: drug_name=%r, batch=%r, expiry=%r, manufacturer=%r, strength=%r",
        parsed_metadata.get("drug_name"),
        parsed_metadata.get("batch_number"),
        parsed_metadata.get("expiry_date"),
        parsed_metadata.get("manufacturer"),
        parsed_metadata.get("strength"),
    )

    verdict = base_result.get("final_verdict", "Inconclusive")
    confidence = _confidence_to_number(base_result.get("confidence_level", "Low"))
    conflicting_clues = verdict in {"Suspicious", "Counterfeit", "Inconclusive"} or bool(
        validation_issues
    )

    logger.info(
        "Reasoning & verdict: verdict=%s, confidence_level=%s, conflicting=%s",
        verdict,
        base_result.get("confidence_level"),
        conflicting_clues,
    )

    metadata = {
        "drug_name": coerce_metadata_drug_name(parsed_metadata.get("drug_name")),
        "dosage": _extract_dosage(parsed_metadata, ocr_text),
        "manufacturer": parsed_metadata.get("manufacturer") or "",
        "batch_number": parsed_metadata.get("batch_number") or "",
        "manufactured_date": (
            (parsed_metadata.get("manufactured_date") or "").strip()
            or (extract_manufactured_date_from_text(ocr_text) or "")
        ),
        "expiry_date": (
            (parsed_metadata.get("expiry_date") or "").strip()
            or (extract_expiry_date_from_text(ocr_text) or "")
        ),
        "detected_logos": _detect_logos(ocr_text),
    }

    validation_results = _guideline_validation(
        metadata=metadata,
        validation_issues=validation_issues,
        expected_data=expected_data,
    )

    # Merge the extra regulatory checks (drug name visibility, logo, NMRA reg)
    extra_checks = _extra_regulatory_checks(metadata, ocr_text, ocr_success)
    existing_rules = {v["rule"] for v in validation_results}
    for check in extra_checks:
        if check["rule"] not in existing_rules:
            validation_results.append(check)

    # ──────────────────────────────────────────────────────────────────────
    # NMRA REGISTRY VALIDATION
    # Match the extracted drug name and manufacturer against the official
    # Sri Lanka NMRA Registered Medicines list.
    # ──────────────────────────────────────────────────────────────────────
    nmra_match = None
    nmra_status = "Not Found"
    mfr_match_result = None
    manufacturer_match = False
    nmra_ui: Dict[str, Any] = {}

    try:
        from backend.services.nmra_validator import get_nmra_validator
        validator = get_nmra_validator()

        _nmra_hints = " ".join(
            x
            for x in (
                (parsed_metadata.get("drug_name_roi_candidate") or "").strip(),
                (parsed_metadata.get("drug_name_fuzzy_candidate") or "").strip(),
            )
            if x
        )
        drug_name_for_nmra = _build_nmra_search_text(
            metadata.get("drug_name") or "",
            metadata.get("dosage") or "",
            ocr_text,
            extra_brand_hints=_nmra_hints,
        )
        nmra_match = validator.match_drug(
            drug_name_for_nmra,
            extracted_manufacturer=metadata.get("manufacturer") or "",
            extracted_dosage=metadata.get("dosage") or "",
        )
        nmra_status = nmra_match.status

        if nmra_match.status == "Registered" and nmra_match.entry:
            mfr_match_result = validator.match_manufacturer(
                metadata.get("manufacturer") or "", nmra_match.entry
            )
            manufacturer_match = mfr_match_result.match

        # Add NMRA match result as a validation rule
        if nmra_status == "Registered":
            nmra_detail = (
                f"Drug name '{metadata.get('drug_name')}' matched NMRA registered "
                f"medicine '{nmra_match.matched_name}' "
                f"(Reg. No. {nmra_match.reg_no or 'N/A'}, "
                f"Validation: {nmra_match.validation_status or 'N/A'}, "
                f"match type: {nmra_match.match_type}, score: {nmra_match.score:.2f})."
            )
            validation_results.append({
                "guideline": "NMRA",
                "rule": "Drug registration status",
                "status": "passed",
                "detail": nmra_detail,
                "severity": "info",
            })
        elif nmra_status == "Not Found":
            validation_results.append({
                "guideline": "NMRA",
                "rule": "Drug registration status",
                "status": "failed",
                "detail": (
                    f"Drug name '{metadata.get('drug_name') or 'Not detected'}' "
                    "was not found in the NMRA registered medicines list. "
                    "Per NMRA regulations, all pharmaceutical products marketed "
                    "in Sri Lanka must be registered with the NMRA "
                    "(nmra.gov.lk). Unregistered products may be counterfeit, "
                    "substandard, or illegally imported."
                ),
                "severity": "error",
            })
        else:
            # "Unavailable" — registry could not be loaded
            validation_results.append({
                "guideline": "NMRA",
                "rule": "Drug registration status",
                "status": "failed",
                "detail": "NMRA registry is temporarily unavailable. Drug registration status could not be verified.",
                "severity": "warning",
            })

        # Manufacturer validation result
        if mfr_match_result is not None:
            if manufacturer_match:
                validation_results.append({
                    "guideline": "NMRA",
                    "rule": "Manufacturer consistency",
                    "status": "passed",
                    "detail": (
                        f"Extracted manufacturer '{metadata.get('manufacturer')}' "
                        f"is consistent with the NMRA-registered manufacturer "
                        f"'{mfr_match_result.nmra_manufacturer}' "
                        f"(similarity score: {mfr_match_result.score:.2f})."
                    ),
                    "severity": "info",
                })
            else:
                validation_results.append({
                    "guideline": "NMRA",
                    "rule": "Manufacturer consistency",
                    "status": "failed",
                    "detail": (
                        f"Extracted manufacturer '{metadata.get('manufacturer') or 'Not detected'}' "
                        f"does not match the NMRA-registered manufacturer "
                        f"'{mfr_match_result.nmra_manufacturer or 'N/A'}' "
                        f"(similarity score: {mfr_match_result.score:.2f}). "
                        "A manufacturer mismatch is a potential indicator of counterfeiting."
                    ),
                    "severity": "warning",
                })

        # Brand / dosage cross-checks against the selected NMRA row
        if nmra_match.status == "Registered" and nmra_match.entry:
            if nmra_match.brand_match is False:
                validation_results.append({
                    "guideline": "NMRA",
                    "rule": "Brand consistency",
                    "status": "failed",
                    "detail": (
                        "Extracted product name does not align with the NMRA registered brand "
                        "for this record (generic or alternate wording may apply)."
                    ),
                    "severity": "warning",
                })
            elif nmra_match.brand_match is True:
                validation_results.append({
                    "guideline": "NMRA",
                    "rule": "Brand consistency",
                    "status": "passed",
                    "detail": "Extracted name is consistent with the NMRA brand entry.",
                    "severity": "info",
                })
            if nmra_match.dosage_match is False:
                validation_results.append({
                    "guideline": "NMRA",
                    "rule": "Dosage consistency",
                    "status": "failed",
                    "detail": (
                        "Extracted strength does not match the NMRA dosage for this registration."
                    ),
                    "severity": "warning",
                })
            elif nmra_match.dosage_match is True:
                validation_results.append({
                    "guideline": "NMRA",
                    "rule": "Dosage consistency",
                    "status": "passed",
                    "detail": "Extracted dosage is consistent with the NMRA record.",
                    "severity": "info",
                })

        nmra_ui = _build_nmra_ui_payload(nmra_status, nmra_match, manufacturer_match, metadata)
    except Exception as exc:
        logger.warning("NMRA validation error: %s", exc)
        nmra_status = "Unavailable"
        nmra_ui = _build_nmra_ui_payload("Unavailable", nmra_match, manufacturer_match, metadata)

    logger.info("NMRA validation: status=%s, manufacturer_match=%s", nmra_status, manufacturer_match)

    # ──────────────────────────────────────────────────────────────────────
    # NMRA-INFORMED VERDICT UPGRADE
    #
    # The base pipeline verdict (from reasoning_interface + decide_final_verdict)
    # only knows about extracted fields.  It does not know whether the drug is
    # officially registered.  NMRA registration is the single strongest signal
    # of authenticity: a drug that exists in the official SL registry cannot
    # reasonably be labelled "Inconclusive" just because some fields are hard
    # to OCR.
    #
    # Rules:
    #   NMRA Registered + all key fields visible          → Authentic
    #   NMRA Registered + batch OR expiry missing         → Suspicious
    #   NMRA Registered + drug name only (other missing)  → Suspicious
    #   NMRA Not Found (no match at all)                  → keep/downgrade
    # ──────────────────────────────────────────────────────────────────────
    if nmra_status == "Registered":
        has_drug   = bool(metadata.get("drug_name"))
        has_batch  = bool(metadata.get("batch_number"))
        has_expiry = bool(metadata.get("expiry_date"))
        has_mfr    = bool(metadata.get("manufacturer"))

        all_key_fields = has_drug and has_batch and has_expiry
        some_key_fields = has_drug and (has_batch or has_expiry)

        if verdict == "Inconclusive":
            if all_key_fields:
                verdict = "Authentic"
                logger.info("Verdict upgraded: Inconclusive → Authentic (NMRA registered, all key fields present)")
            elif some_key_fields:
                verdict = "Suspicious"
                logger.info("Verdict upgraded: Inconclusive → Suspicious (NMRA registered, partial fields)")
            else:
                # Drug name matched NMRA but very little else visible
                verdict = "Suspicious"
                logger.info("Verdict upgraded: Inconclusive → Suspicious (NMRA registered)")
        elif verdict == "Suspicious" and all_key_fields and manufacturer_match:
            verdict = "Authentic"
            logger.info("Verdict upgraded: Suspicious → Authentic (NMRA registered, all fields, mfr matched)")

    elif nmra_status == "Not Found" and verdict == "Authentic":
        # Drug not in NMRA but pipeline called it Authentic — downgrade
        verdict = "Suspicious"
        logger.info("Verdict downgraded: Authentic → Suspicious (drug not in NMRA registry)")

    # ------------------------------------------------------------------
    # BUILD STRUCTURED EXPLANATION
    # ------------------------------------------------------------------
    explanation: List[str] = []

    # ── SECTION 0: Multi-image notice ─────────────────────────────────
    if n_images > 1:
        explanation.append(
            f"Analysis performed on {n_images} image(s). "
            "OCR text from all images was combined to maximise field coverage. "
            "The most confident value for each field was selected across all images."
        )

    # ── SECTION 1: Image / OCR quality ──────────────────────────────────
    is_low_quality = not ocr_success or len(ocr_text) < 150
    if is_low_quality:
        explanation.append(
            "The provided image has limited readability due to image angle, lighting "
            "conditions, or resolution. As a result, some required regulatory labelling "
            "elements could not be reliably detected. A definitive authenticity "
            "determination requires a clearer, well-oriented image of the packaging."
        )

    # ── SECTION 2: Summary of detected elements ──────────────────────────
    detected_items: List[str] = []
    if metadata.get("drug_name"):
        detected_items.append(f"product name ('{metadata['drug_name']}')")
    if metadata.get("batch_number"):
        detected_items.append(f"batch/lot number ('{metadata['batch_number']}')")
    if metadata.get("expiry_date"):
        detected_items.append(f"expiry date ('{metadata['expiry_date']}')")
    if metadata.get("manufacturer"):
        detected_items.append(f"manufacturer ('{metadata['manufacturer']}')")
    if metadata.get("detected_logos"):
        detected_items.append(
            "brand indicators (" + ", ".join(metadata["detected_logos"]) + ")"
        )

    if detected_items:
        explanation.append(
            "The following regulatory labelling elements were successfully identified "
            "from the packaging image: " + "; ".join(detected_items) + "."
        )

    # ── SECTION 2b: NMRA status ──────────────────────────────────────────
    if nmra_status == "Registered" and nmra_match:
        nmra_sentence = (
            f"The drug name '{metadata.get('drug_name')}' was matched against the "
            f"NMRA Registered Medicines list (Reg. No. {nmra_match.reg_no or 'N/A'}). "
        )
        if manufacturer_match and mfr_match_result:
            nmra_sentence += (
                f"The detected manufacturer '{metadata.get('manufacturer')}' is "
                f"consistent with the NMRA record "
                f"('{mfr_match_result.nmra_manufacturer}')."
            )
        elif mfr_match_result:
            nmra_sentence += (
                f"However, the detected manufacturer '{metadata.get('manufacturer') or 'not detected'}' "
                f"does not match the NMRA record "
                f"('{mfr_match_result.nmra_manufacturer}'), which warrants further investigation."
            )
        explanation.append(nmra_sentence)
    elif nmra_status == "Not Found":
        explanation.append(
            f"The drug name '{metadata.get('drug_name') or 'could not be identified'}' "
            "was not found in the NMRA Registered Medicines list. "
            "All pharmaceutical products marketed in Sri Lanka must be registered with "
            "the NMRA (nmra.gov.lk/pages/guidelines). "
            "An unregistered product is a significant authenticity concern."
        )

    # ── SECTION 2c: Drug-name confidence notice ───────────────────────────
    # parse_metadata flags when drug name was inferred rather than read from
    # a labelled field.  Surface this as a dedicated explanation sentence so
    # reviewers are aware of the reduced certainty.
    drug_name_source = parsed_metadata.get("drug_name_source", "labelled")
    if drug_name_source in ("roi_visible", "prominent_word", "fallback_verified") and metadata.get("drug_name"):
        explanation.append(
            f"The drug name '{metadata['drug_name']}' was identified from the "
            "visually prominent brand area of the packaging rather than an "
            "explicitly labelled field. "
            "While the extraction is based on visual evidence, "
            "manual verification is recommended for high-stakes decisions."
        )
    elif drug_name_source == "rejected_no_evidence":
        explanation.append(
            "Drug name could not be reliably identified. "
            "A fuzzy-match candidate was found but had no visual evidence in the "
            "OCR text and was rejected to prevent misidentification."
        )

    # ── SECTION 3: Pipeline reasoning ────────────────────────────────────
    pipeline_reasons = base_result.get("explanation", [])
    if pipeline_reasons:
        explanation.extend(pipeline_reasons)

    # ── SECTION 4: Evidence-mapped guideline violation details ─────────────
    # For each failed check, append the detail text.
    # Where the relevant OCR evidence snippet can be extracted, it is cited
    # inline so that the explanation is grounded in actual label text.
    # This satisfies the XAI requirement for evidence-backed decisions.
    for item in validation_results:
        if item["status"] == "failed":
            explanation.append(item["detail"])

    # ── SECTION 5: Missing fields summary ────────────────────────────────
    _FIELD_LABELS = {
        "drug_name": "product name",
        "batch_number": "batch/lot number",
        "expiry_date": "expiry date",
        "manufacturer": "manufacturer identity",
    }
    missing_fields = [lbl for f, lbl in _FIELD_LABELS.items() if not metadata.get(f)]
    if missing_fields and not is_low_quality:
        explanation.append(
            "The following mandatory labelling elements could not be extracted: "
            + ", ".join(missing_fields) + ". "
            "Per the NMRA Guideline on Labelling of Medicines "
            "(nmra.gov.lk/pages/guidelines), all registered pharmaceutical products "
            "must display complete labelling including product name, batch number, "
            "expiry date, and manufacturer identity on the primary packaging. "
            "Incomplete labelling constitutes a significant regulatory non-conformance."
        )

    # ── SECTION 5b: OCR evidence anchors ─────────────────────────────────
    # Cite specific OCR text fragments that grounded the analysis.
    # This provides a transparent evidence trail (XAI / explainability).
    evidence_lines: List[str] = []
    if metadata.get("expiry_date"):
        snip = _extract_evidence_snippet(
            ocr_text, [r"exp[iry\.]*\s*[:\-]?\s*\d", r"use before", r"best before"],
        )
        if snip:
            evidence_lines.append(f"Expiry date evidence: {snip}")
    if metadata.get("batch_number"):
        snip = _extract_evidence_snippet(
            ocr_text, [r"batch\s*[:\-\.]?\s*\w", r"\bLot\b\s*[:\-]?\s*\w", r"\bB\.?\s*No"],
        )
        if snip:
            evidence_lines.append(f"Batch number evidence: {snip}")
    if metadata.get("manufacturer"):
        snip = _extract_evidence_snippet(
            ocr_text, [r"manufactured\s+by", r"mfd\s+by", r"marketed\s+by", r"dist(?:ributed)?\s+by"],
        )
        if snip:
            evidence_lines.append(f"Manufacturer evidence: {snip}")
    if _ocr_contains_any(ocr_text, _STORAGE_KEYWORDS):
        snip = _extract_evidence_snippet(ocr_text, [r"store\b", r"refriger", r"protect\s+from"])
        if snip:
            evidence_lines.append(f"Storage evidence: {snip}")

    if evidence_lines:
        explanation.append(
            "OCR evidence anchors — extracted directly from the label text: "
            + "; ".join(evidence_lines) + "."
        )

    # ── SECTION 6: Closing verdict reasoning ──────────────────────────────
    if verdict == "Authentic":
        nmra_note = (
            " The product is confirmed in the NMRA Registered Medicines list."
            if nmra_status == "Registered" else ""
        )
        explanation.append(
            f"Based on this comprehensive analysis, the product is classified as '{verdict}'.{nmra_note} "
            "All extractable labelling elements are consistent with the standards expected "
            "of an authentic, registered medicinal product. No critical regulatory "
            "non-conformances were identified."
        )
    elif verdict == "Suspicious":
        if nmra_status == "Registered":
            explanation.append(
                f"The product is classified as '{verdict}'. "
                "The drug name is confirmed in the NMRA Registered Medicines list, "
                "which is a strong indicator of authenticity. However, one or more "
                "mandatory labelling elements (batch number, expiry date, or manufacturer) "
                "could not be fully verified from the provided images. "
                "Physical inspection of the packaging is recommended to confirm "
                "the remaining details."
            )
        else:
            explanation.append(
                f"Based on this analysis, the product is classified as '{verdict}'. "
                "Some labelling elements raised concerns or could not be verified. "
                "Further physical verification or regulatory enquiry is recommended."
            )
    else:
        explanation.append(
            f"Based on this analysis, the product is classified as '{verdict}'. "
            "The incomplete or unverifiable labelling elements observed are inconsistent "
            "with the standards expected of authenticated and registered medicinal products. "
            "Further physical verification or regulatory enquiry is recommended before "
            "dispensing or supply."
        )

    # ── LEARNED SCORING LAYER ──────────────────────────────────────────────
    # The scoring model extracts a structured feature vector and computes a
    # calibrated confidence via a weighted linear model + Platt sigmoid.
    # This makes the authenticity score a proper probability estimate rather
    # than an ad-hoc weighted sum, and provides per-feature importances that
    # ground the XAI explainability claim in the research paper.
    has_critical = any(
        v.get("severity") == "error" and v.get("status") == "failed"
        for v in validation_results
    )
    try:
        from backend.services.scoring_model import get_model
        scoring = get_model().score(
            metadata=metadata,
            validation_results=validation_results,
            completeness_score=completeness,
            has_critical_failure=has_critical,
        )
        learned_confidence = scoring.confidence
        learned_verdict = scoring.verdict
        # Append the scoring model's evidence snippet to the explanation
        explanation.append(scoring.explanation_snippet)
        # Use the learned confidence if it differs meaningfully from the
        # rule-based one (gives the ML layer authority over the final output).
        final_confidence = round(
            0.5 * confidence + 0.5 * learned_confidence, 2
        )
        feature_importances = scoring.feature_importances
    except Exception as exc:
        logger.warning("Scoring model unavailable: %s", exc)
        learned_verdict = verdict
        final_confidence = round(confidence, 2)
        feature_importances = {}

    if nmra_ui.get("summary_text"):
        explanation.append(nmra_ui["summary_text"])

    _FIELD_LABELS_TRUST = ["drug_name", "batch_number", "expiry_date", "manufacturer"]
    missing_count = sum(1 for f in _FIELD_LABELS_TRUST if not metadata.get(f))

    return {
        "verdict": verdict,
        "confidence": final_confidence,
        "explanation": explanation,
        "metadata": metadata,
        "validationResults": validation_results,
        "trustScore": _compute_trust_score(
            final_confidence,
            completeness,
            validation_results,
            conflicting_clues,
            nmra_registered=(nmra_status == "Registered"),
            manufacturer_match=manufacturer_match,
            missing_field_count=missing_count,
        ),
        "conflictingClues": conflicting_clues,
        "ocr_raw_text": ocr_text,
        "featureImportances": feature_importances,
        # ── New fields ────────────────────────────────────────────────
        "nmra_status": nmra_status,
        "manufacturer_match": manufacturer_match,
        "number_of_images_processed": n_images,
        "nmra": nmra_ui,
    }