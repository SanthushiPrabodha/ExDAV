"""
Backend-local OCR brand corrections (always importable from backend.services.*).

Safety net when src.ocr.metadata_validate is unavailable or when raw OCR still
contains Belcovic/Belcovent misreads after other passes.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

_BECLOVENT_REGEX: list[tuple[str, str]] = [
    (r"\b8elcovic\b", "BECLOVENT"),
    (r"\b8elcovent\b", "BECLOVENT"),
    (r"\bbelcovic\s+400\b", "BECLOVENT 400"),
    (r"\bbelcovent\s+400\b", "BECLOVENT 400"),
    (r"\bbeclovic\s+400\b", "BECLOVENT 400"),
    (r"\bbelcovic\b", "BECLOVENT"),
    (r"\bbelcovent\b", "BECLOVENT"),
    (r"\bbeclcovic\b", "BECLOVENT"),
    (r"\bbeclovic\b", "BECLOVENT"),
    (r"\bbelovent\b", "BECLOVENT"),
    (r"\bbeclcovent\b", "BECLOVENT"),
    (r"\bbelcovi\b", "BECLOVENT"),
    (r"\bbeclove\b", "BECLOVENT"),
]


def _fold_unicode(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "")


def fix_text_beclovent_family(text: str) -> str:
    """Apply Belcovic→BECLOVENT fixes to arbitrary OCR text."""
    if not text or not str(text).strip():
        return text or ""
    t = _fold_unicode(text)
    for pat, repl in _BECLOVENT_REGEX:
        t = re.sub(pat, repl, t, flags=re.IGNORECASE)
    return t


def _fuzzy_token_beclovent(word: str) -> Optional[str]:
    w2 = re.sub(r"[^A-Za-z0-9]", "", word.upper())
    if w2.startswith("8"):
        w2 = "B" + w2[1:]
    if not w2.startswith("B") or len(w2) < 6 or len(w2) > 14:
        return None
    if not ("COV" in w2 or "COVI" in w2 or "VENT" in w2 or "COVENT" in w2):
        return None
    if SequenceMatcher(None, w2, "BECLOVENT").ratio() >= 0.52:
        return "BECLOVENT"
    return None


def normalize_nmra_query_fragment(s: str) -> str:
    """Uppercase + Beclovent fixes for NMRA matching (backend-only fallback)."""
    if not s:
        return ""
    t = fix_text_beclovent_family(s)
    t = t.upper()
    t = re.sub(r"[^A-Z0-9\/\-\%\:\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    parts: list[str] = []
    for w in t.split():
        fz = _fuzzy_token_beclovent(w)
        parts.append(fz if fz else w)
    return " ".join(parts)


def fix_drug_name_display(drug_name: Optional[str]) -> str:
    """Canonical display: Beclovent / Beclovent 400 when OCR misread the brand."""
    if not drug_name or not str(drug_name).strip():
        return ""
    raw = str(drug_name).strip()
    fixed = fix_text_beclovent_family(raw)
    fixed = re.sub(r"(?i)\bBECLOVENT\s+400\b", "Beclovent 400", fixed)
    fixed = re.sub(r"(?i)\bBECLOVENT\b", "Beclovent", fixed)
    if re.search(r"(?i)belcovi", fixed) and "beclovent" not in fixed.lower():
        fixed = re.sub(r"(?i)belcovic|belcovent|beclovic|beclcovic", "Beclovent", fixed)
    return fixed


def coerce_metadata_drug_name(name: Optional[str]) -> str:
    """Pipeline: ensure metadata.drug_name never ships Belcovic to the client."""
    return fix_drug_name_display(name or "")
