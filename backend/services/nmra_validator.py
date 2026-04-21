"""
NMRA Drug Registry Validator
=============================
Loads the Sri Lanka NMRA Registered Medicines Excel file once at module
import time and exposes two public methods:

    match_drug(drug_name)          → NMRAMatchResult
    match_manufacturer(mfr, entry) → ManufacturerMatchResult

Column mapping (from the supplied spreadsheet):
    GENERIC NAME, BRAND, DOSAGE, PACK SIZE, PACK TYPE, MANUFACTURE,
    COUNTRY, AGENT, REG.DATE, REG.NO., SHEDULE, VALIDATION, DOSSIER NO.

All stored fields are uppercase stripped for matching; display uses the same.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher, get_close_matches
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("exdav.nmra")

# Bundled copy of the NMRA Excel (copied from the source spreadsheet)
_NMRA_XLSX = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "nmra_registered.xlsx")
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class NMRAEntry:
    generic_name: str = ""
    brand_name: str = ""
    manufacturer: str = ""
    reg_no: str = ""
    validation_status: str = ""
    dosage: str = ""
    country: str = ""
    pack_size: str = ""
    pack_type: str = ""
    agent: str = ""
    reg_date: str = ""
    schedule: str = ""
    dossier_no: str = ""

    def to_display_dict(self) -> Dict[str, str]:
        """Human-readable NMRA record for API / UI."""
        return {
            "generic_name": self.generic_name,
            "brand": self.brand_name,
            "dosage": self.dosage,
            "pack_size": self.pack_size,
            "pack_type": self.pack_type,
            "manufacturer": self.manufacturer,
            "country": self.country,
            "agent": self.agent,
            "reg_date": _format_reg_date_display(self.reg_date),
            "reg_no": self.reg_no,
            "schedule": self.schedule,
            "validation_status": self.validation_status,
            "dossier_no": self.dossier_no,
        }


@dataclass
class NMRAMatchResult:
    status: str = "Not Found"            # "Registered" | "Not Found" | "Unavailable"
    matched_name: Optional[str] = None   # The name that was matched
    match_type: Optional[str] = None     # "exact_brand" | "exact_generic" | "fuzzy"
    score: float = 0.0
    entry: Optional[NMRAEntry] = None    # Full NMRA entry if matched
    reg_no: Optional[str] = None
    validation_status: Optional[str] = None
    brand_match: Optional[bool] = None     # extracted vs NMRA brand
    dosage_match: Optional[bool] = None  # extracted vs NMRA dosage


@dataclass
class ManufacturerMatchResult:
    match: bool = False
    nmra_manufacturer: Optional[str] = None
    score: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(text: Any) -> str:
    """Uppercase, collapse whitespace, strip."""
    return re.sub(r"\s+", " ", str(text or "").strip()).upper()


def _format_reg_date_display(raw: Any) -> str:
    """Strip Excel/datetime time-of-day for UI (e.g. 2025-09-25 00:00:00 → 2025-09-25)."""
    s = str(raw or "").strip()
    if not s or s.lower() == "nan":
        return ""
    # ISO date with midnight time from pandas/Excel
    m = re.match(r"(\d{4}-\d{2}-\d{2})\s+00:00:00", s)
    if m:
        return m.group(1)
    if re.match(r"\d{4}-\d{2}-\d{2}$", s):
        return s[:10]
    return s


def _first_word(text: str) -> str:
    """Return the first alphabetic token of a string (≥ 4 chars)."""
    words = re.findall(r"[A-Z]{4,}", text)
    return words[0] if words else ""


def _row_field(row: Dict[str, Any], name: str) -> str:
    """Read column *name* from a row dict (headers already uppercased for pandas)."""
    v = row.get(name)
    if v is None or (isinstance(v, float) and str(v) == "nan"):
        return ""
    return str(v).strip()


def compare_extracted_brand_to_nmra(extracted_drug: str, entry: NMRAEntry) -> bool:
    """True if extracted text aligns with the NMRA brand name."""
    q = _norm(extracted_drug)
    b = entry.brand_name
    if not q or not b:
        return False
    if q == b:
        return True
    if q in b or b in q:
        return True
    r = SequenceMatcher(None, q, b).ratio()
    if r >= 0.72:
        return True
    # First significant token (e.g. BECLOVENT from BECLOVENT 400)
    qfw = _first_word(q)
    if qfw and qfw in b.split():
        return True
    return False


def _significant_numbers(text: str) -> set:
    """Decimal numbers as strings (e.g. 400, 0.025) from normalized text."""
    return set(re.findall(r"\d+(?:\.\d+)?", _norm(text)))


def _query_blob(
    query_norm: str,
    extracted_dosage: Optional[str],
    extracted_mfr: Optional[str],
) -> str:
    """Combined text used to disambiguate among many NMRA rows."""
    parts = [query_norm]
    if extracted_dosage:
        parts.append(_norm(extracted_dosage))
    if extracted_mfr:
        parts.append(_norm(extracted_mfr))
    return " ".join(p for p in parts if p).strip()


def _topical_markers(text: str) -> bool:
    t = _norm(text)
    return any(
        k in t
        for k in (
            "CREAM",
            "OINTMENT",
            "GEL",
            "LOTION",
            "% W/W",
            "W/W",
            "TOPICAL",
        )
    )


def _inhalation_markers(text: str) -> bool:
    t = _norm(text)
    return any(
        k in t
        for k in (
            "INHALATION",
            "INHALER",
            "CAPSULE",
            "CAPSULES",
            "POWDER",
            "AEROSOL",
            "PRESSURISED",
            "PRESSURIZED",
            "PUFF",
            "MTD",
            "DRY POWDER",
        )
    )


def _form_alignment_adjustment(query_blob: str, entry: NMRAEntry) -> float:
    """
    Penalise contradictory dosage forms (e.g. cream vs inhalation) between
    query context and NMRA generic/dosage lines.
    """
    qb = _norm(query_blob)
    combined = " ".join([entry.generic_name, entry.dosage, entry.brand_name])
    q_top = _topical_markers(qb)
    q_inh = _inhalation_markers(qb)
    e_top = _topical_markers(combined)
    e_inh = _inhalation_markers(combined)
    adj = 0.0
    if q_inh and e_top and not e_inh:
        adj -= 4.5
    if q_top and e_inh and not e_top:
        adj -= 4.5
    return adj


# Tokens so common in generic names that they do not disambiguate between SKUs.
_DISCRIM_TOKEN_SKIP = frozenset(
    {
        "BECLOMETASONE",
        "BECLOMETHASONE",  # occasional NMRA typo
        "PARACETAMOL",
        "ACETAMINOPHEN",
        "IBUPROFEN",
        "AMOXICILLIN",
        "METFORMIN",
        "OMEPRAZOLE",
        "ATORVASTATIN",
    }
)


def _blob_token_overlap_bonus(blob: str, entry: NMRAEntry) -> float:
    """
    Reward NMRA rows whose brand/generic/dosage contain distinctive words or
    strengths also present in the full OCR search string (e.g. BECLATE vs BECLOVENT).
    """
    b = _norm(blob)
    if not b:
        return 0.0
    combined = " ".join([entry.brand_name, entry.generic_name, entry.dosage, entry.manufacturer])
    bonus = 0.0
    for tok in re.findall(r"[A-Z]{4,}", b):
        if tok in _DISCRIM_TOKEN_SKIP:
            continue
        if len(tok) >= 5 and tok in combined:
            bonus += 0.62
        elif len(tok) == 4 and tok in combined:
            bonus += 0.22
    for tok in re.findall(r"\d{3,}", b):
        if tok in combined:
            bonus += 0.48
    return min(bonus, 4.0)


def _numeric_strength_adjustment(query_blob: str, entry: NMRAEntry) -> float:
    """When both query and registry line contain strengths, prefer consistent numbers."""
    qb = _significant_numbers(query_blob)
    if not qb:
        return 0.0
    combined = " ".join([entry.generic_name, entry.dosage, entry.brand_name])
    eb = _significant_numbers(combined)
    if not eb:
        return 0.0
    if qb & eb:
        return 0.6 * len(qb & eb)
    # Same molecule, different strengths — strong penalty
    return -3.5


def compare_extracted_dosage_to_nmra(extracted_dosage: str, entry: NMRAEntry) -> Optional[bool]:
    """True/False if comparable; None if insufficient data to compare."""
    ex = _norm(extracted_dosage or "")
    nm = entry.dosage
    if not ex or not nm:
        return None
    if nm in ex or ex in nm:
        return True
    nums_ex = set(re.findall(r"\d+(?:\.\d+)?", ex))
    nums_nm = set(re.findall(r"\d+(?:\.\d+)?", nm))
    if nums_ex & nums_nm:
        return True
    return SequenceMatcher(None, ex, nm).ratio() >= 0.55


# ---------------------------------------------------------------------------
# Validator class
# ---------------------------------------------------------------------------

class NMRAValidator:
    """
    Singleton validator backed by the NMRA registered medicines Excel.

    Loads the spreadsheet once; subsequent calls are in-memory lookups.
    If the Excel file is unavailable, all queries return status="Unavailable".
    """

    def __init__(self, xlsx_path: str = _NMRA_XLSX) -> None:
        self._loaded = False
        self._entries: List[NMRAEntry] = []

        # Lookup structures
        # exact brand → entry index list
        self._brand_idx: Dict[str, List[int]] = {}
        # exact generic first-word → entry index list
        self._generic_idx: Dict[str, List[int]] = {}
        # flat sorted list of ALL searchable names (for fuzzy matching)
        self._all_names: List[str] = []

        self._load(xlsx_path)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self, path: str) -> None:
        if not os.path.exists(path):
            logger.warning("NMRA Excel not found at %s — registry validation disabled", path)
            return
        try:
            rows = self._read_excel(path)
        except Exception as exc:
            logger.warning("Failed to load NMRA Excel: %s", exc)
            return

        for row in rows:
            generic = _norm(_row_field(row, "GENERIC NAME"))
            brand = _norm(_row_field(row, "BRAND"))
            mfr = _norm(_row_field(row, "MANUFACTURE"))
            reg_no = _row_field(row, "REG.NO.")
            val = _row_field(row, "VALIDATION")
            dosage = _norm(_row_field(row, "DOSAGE"))
            country = _norm(_row_field(row, "COUNTRY"))
            pack_size = _norm(_row_field(row, "PACK SIZE"))
            pack_type = _norm(_row_field(row, "PACK TYPE"))
            agent = _norm(_row_field(row, "AGENT"))
            reg_date = _row_field(row, "REG.DATE")
            schedule = _norm(_row_field(row, "SHEDULE"))
            dossier_no = _row_field(row, "DOSSIER NO.")

            entry = NMRAEntry(
                generic_name=generic,
                brand_name=brand,
                manufacturer=mfr,
                reg_no=reg_no,
                validation_status=val,
                dosage=dosage,
                country=country,
                pack_size=pack_size,
                pack_type=pack_type,
                agent=agent,
                reg_date=reg_date,
                schedule=schedule,
                dossier_no=dossier_no,
            )
            i = len(self._entries)
            self._entries.append(entry)

            for key in self._brand_keys(brand):
                self._brand_idx.setdefault(key, []).append(i)

            gw = _first_word(generic)
            if gw:
                self._generic_idx.setdefault(gw, []).append(i)

        name_set = set(self._brand_idx) | set(self._generic_idx)
        self._all_names = sorted(name_set)
        self._loaded = True
        logger.info(
            "NMRA registry loaded: %d entries, %d searchable names",
            len(self._entries), len(self._all_names),
        )

    @staticmethod
    def _read_excel(path: str) -> List[Dict[str, Any]]:
        """
        Load the NMRA data into a list of dicts.

        Loading priority (fastest / most reliable first):
          1. JSON sidecar file  — zero dependencies, always works
          2. pandas read_excel  — fast but requires compatible NumPy
          3. openpyxl           — no NumPy, but slower on large files

        The JSON sidecar is pre-built by running:
            python -c "import openpyxl, json; ..."
        and committed alongside the Excel file.
        """
        # ── Attempt 1: JSON sidecar (zero-dependency fast path) ───────
        json_path = os.path.splitext(path)[0] + ".json"
        if os.path.exists(json_path):
            try:
                import json as _json
                with open(json_path, encoding="utf-8") as fh:
                    records = _json.load(fh)
                logger.debug("NMRA loaded from JSON sidecar (%d rows)", len(records))
                return records
            except Exception as json_exc:
                logger.debug("JSON sidecar failed (%s), trying Excel", json_exc)

        # ── Attempt 2: pandas ─────────────────────────────────────────
        try:
            import pandas as pd
            df = pd.read_excel(path, dtype=str)
            df.columns = [c.strip().upper() for c in df.columns]
            return df.to_dict(orient="records")
        except Exception as pandas_exc:
            logger.debug("pandas unavailable (%s), trying openpyxl", pandas_exc)

        # ── Attempt 3: openpyxl (no numpy dependency) ─────────────────
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers = [str(h or "").strip().upper() for h in next(rows_iter)]
        records = []
        for row in rows_iter:
            records.append({
                headers[i]: (str(v) if v is not None else "")
                for i, v in enumerate(row)
                if i < len(headers)
            })
        wb.close()
        return records

    @staticmethod
    def _brand_keys(brand: str) -> List[str]:
        """Return indexing keys for a brand string."""
        if not brand:
            return []
        keys = [brand]
        # First word (e.g. "POLYBION" from "POLYBION SF SYRUP")
        fw = _first_word(brand)
        if fw and fw != brand:
            keys.append(fw)
        return keys

    def _pick_best_entry_index_with_score(
        self,
        indices: List[int],
        query_norm: str,
        extracted_mfr: Optional[str],
        extracted_dosage: Optional[str],
    ) -> Tuple[int, float]:
        """Pick best row among *indices*; return (index, score) for tie-breaking across keys."""
        if len(indices) == 1:
            i0 = indices[0]
            blob = _query_blob(query_norm, extracted_dosage, extracted_mfr)
            s0 = self._score_candidate_row(i0, query_norm, blob, extracted_mfr, extracted_dosage)
            return i0, s0
        blob = _query_blob(query_norm, extracted_dosage, extracted_mfr)
        best_i, best_s = indices[0], -1e9
        for i in indices:
            s = self._score_candidate_row(i, query_norm, blob, extracted_mfr, extracted_dosage)
            if s > best_s:
                best_s, best_i = s, i
        return best_i, best_s

    def _score_candidate_row(
        self,
        i: int,
        query_norm: str,
        blob: str,
        extracted_mfr: Optional[str],
        extracted_dosage: Optional[str],
    ) -> float:
        """Composite score for disambiguating duplicate index keys."""
        e = self._entries[i]
        s = 0.0
        short_query = len(query_norm) < 36
        gen_weight = 0.14 if short_query else 0.35
        if e.brand_name:
            s += SequenceMatcher(None, blob, e.brand_name).ratio()
            s += 0.35 * SequenceMatcher(None, query_norm, e.brand_name).ratio()
        if e.generic_name:
            s += gen_weight * SequenceMatcher(None, query_norm, e.generic_name).ratio()
            s += 0.25 * SequenceMatcher(None, blob, e.generic_name).ratio()
            if short_query:
                s += 0.002 * min(len(e.generic_name), 400)
        if e.brand_name and re.search(r"\d{3,}", e.brand_name):
            s += 0.28
        if extracted_mfr:
            mr = self.match_manufacturer(extracted_mfr, e)
            if mr.match:
                # Strong signal: pack MAH often matches exactly one NMRA registration line.
                s += 1.35 + 0.35 * (mr.score or 0.0)
            elif len(_norm(extracted_mfr)) >= 8:
                s -= 0.55
        if extracted_dosage and e.dosage:
            dm = compare_extracted_dosage_to_nmra(extracted_dosage, e)
            if dm is True:
                s += 0.35
            elif dm is False:
                s -= 0.4
        s += _numeric_strength_adjustment(blob, e)
        s += _form_alignment_adjustment(blob, e)
        s += _blob_token_overlap_bonus(blob, e)
        return s

    def _pick_best_entry_index(
        self,
        indices: List[int],
        query_norm: str,
        extracted_mfr: Optional[str],
        extracted_dosage: Optional[str],
    ) -> int:
        """When several NMRA rows share the same index key, pick the best-scoring row."""
        return self._pick_best_entry_index_with_score(
            indices, query_norm, extracted_mfr, extracted_dosage
        )[0]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def match_drug(
        self,
        drug_name: str,
        fuzzy_cutoff: float = 0.85,
        extracted_manufacturer: Optional[str] = None,
        extracted_dosage: Optional[str] = None,
    ) -> NMRAMatchResult:
        """
        Match *drug_name* (extracted from image) against the NMRA registry.

        Priority:
          1. Exact brand match (full brand string)
          2. Exact brand first-word match
          3. Word scan (≥4 chars): try every brand key in the query before generic
          4. Exact generic first-word match
          5. Word scan for generic keys not handled above
          6. Fuzzy match (SequenceMatcher ≥ fuzzy_cutoff)

        Optional *extracted_manufacturer* / *extracted_dosage* disambiguate
        multiple NMRA rows and populate brand/dosage match flags.

        Returns NMRAMatchResult with status="Registered" or "Not Found".
        """
        if not self._loaded:
            return NMRAMatchResult(status="Unavailable")
        if not drug_name:
            return NMRAMatchResult(status="Not Found")

        raw_drug = str(drug_name).strip()
        # Use same OCR normalization as metadata (Belcovic→BECLOVENT, unicode fold, etc.)
        try:
            from src.ocr.metadata_validate import normalize_text as _nmra_query_norm

            query = _nmra_query_norm(raw_drug)
        except Exception:
            try:
                from backend.services.ocr_brand_fix import normalize_nmra_query_fragment

                query = normalize_nmra_query_fragment(raw_drug)
            except Exception:
                query = _norm(raw_drug)
        qfw = _first_word(query) or query  # first alphabetic token

        # 1. Exact full brand
        if query in self._brand_idx:
            return self._result_from_brand(
                query, "exact_brand", 1.0, query, raw_drug,
                extracted_manufacturer, extracted_dosage,
            )

        # 2. First word of query matches a brand key
        if qfw and qfw in self._brand_idx:
            return self._result_from_brand(
                qfw, "exact_brand", 0.95, query, raw_drug,
                extracted_manufacturer, extracted_dosage,
            )

        # 3. Any token in the query matches a brand key (before generic stem).
        # Score each key's best row — do not use max(len): a long spurious token can
        # beat the true trade name (e.g. manufacturer words vs BECLOVENT).
        words = sorted(set(re.findall(r"[A-Z]{4,}", query)), key=len, reverse=True)
        brand_hits = [w for w in words if w in self._brand_idx]
        if brand_hits:
            best_key = None
            best_bi = -1
            best_sc = -1e9
            for key in brand_hits:
                indices = self._brand_idx[key]
                bi, sc = self._pick_best_entry_index_with_score(
                    indices, query, extracted_manufacturer, extracted_dosage
                )
                if sc > best_sc:
                    best_sc, best_bi, best_key = sc, bi, key
            return self._result_from_brand_at(
                best_bi,
                best_key or "",
                "word_brand",
                0.92,
                query,
                raw_drug,
                extracted_manufacturer,
                extracted_dosage,
            )

        # 4. Exact generic first-word
        if qfw and qfw in self._generic_idx:
            return self._result_from_generic(
                qfw, "exact_generic", 0.95, query, raw_drug,
                extracted_manufacturer, extracted_dosage,
            )

        # 5. Word-by-word scan (generic keys)
        for word in words:
            if word in self._generic_idx:
                return self._result_from_generic(
                    word, "word_generic", 0.90, query, raw_drug,
                    extracted_manufacturer, extracted_dosage,
                )

        # 6. Fuzzy — search both query and first-word
        for q in sorted({query, qfw}, key=len, reverse=True):
            if not q:
                continue
            hits = get_close_matches(q, self._all_names, n=1, cutoff=fuzzy_cutoff)
            if hits:
                matched = hits[0]
                score = round(SequenceMatcher(None, q, matched).ratio(), 3)
                if matched in self._brand_idx:
                    return self._result_from_brand(
                        matched, "fuzzy", score, query, raw_drug,
                        extracted_manufacturer, extracted_dosage,
                    )
                if matched in self._generic_idx:
                    return self._result_from_generic(
                        matched, "fuzzy", score, query, raw_drug,
                        extracted_manufacturer, extracted_dosage,
                    )

        return NMRAMatchResult(status="Not Found")

    def match_manufacturer(
        self,
        extracted: str,
        entry: Optional[NMRAEntry],
        fuzzy_cutoff: float = 0.72,
    ) -> ManufacturerMatchResult:
        """
        Compare *extracted* manufacturer against the NMRA-registered one.

        Accepts partial containment (e.g. "PROCTER" in "PROCTER & GAMBLE HEALTH LTD")
        and fuzzy similarity above *fuzzy_cutoff*.
        """
        if not extracted or entry is None:
            return ManufacturerMatchResult(match=False)

        ext = _norm(extracted)
        nmra_mfr = entry.manufacturer

        if not nmra_mfr:
            return ManufacturerMatchResult(match=False, nmra_manufacturer=None)

        # Exact
        if ext == nmra_mfr:
            return ManufacturerMatchResult(match=True, nmra_manufacturer=nmra_mfr, score=1.0)

        # Partial containment (either direction)
        if ext in nmra_mfr or nmra_mfr in ext:
            score = round(SequenceMatcher(None, ext, nmra_mfr).ratio(), 3)
            return ManufacturerMatchResult(match=True, nmra_manufacturer=nmra_mfr, score=score)

        # Any significant word from the extracted name present in NMRA manufacturer
        sig_words = [w for w in ext.split() if len(w) >= 5]
        if any(w in nmra_mfr for w in sig_words):
            score = round(SequenceMatcher(None, ext, nmra_mfr).ratio(), 3)
            return ManufacturerMatchResult(match=True, nmra_manufacturer=nmra_mfr, score=score)

        # Reverse direction: distinctive tokens from the registry name appear in OCR text
        # (handles noisy leading tokens like licence fragments before the company name).
        nmra_sig = [w for w in nmra_mfr.split() if len(w) >= 4]
        if any(w in ext for w in nmra_sig):
            score = round(SequenceMatcher(None, ext, nmra_mfr).ratio(), 3)
            return ManufacturerMatchResult(match=True, nmra_manufacturer=nmra_mfr, score=score)

        # Fuzzy fallback
        score = round(SequenceMatcher(None, ext, nmra_mfr).ratio(), 3)
        if score >= fuzzy_cutoff:
            return ManufacturerMatchResult(match=True, nmra_manufacturer=nmra_mfr, score=score)

        return ManufacturerMatchResult(match=False, nmra_manufacturer=nmra_mfr, score=score)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _result_from_brand_at(
        self,
        bi: int,
        key: str,
        match_type: str,
        score: float,
        query_norm: str,
        extracted_drug: str,
        extracted_mfr: Optional[str] = None,
        extracted_dosage: Optional[str] = None,
    ) -> NMRAMatchResult:
        entry = self._entries[bi]
        bm = compare_extracted_brand_to_nmra(extracted_drug, entry)
        dm = (
            compare_extracted_dosage_to_nmra(extracted_dosage, entry)
            if extracted_dosage
            else None
        )
        return NMRAMatchResult(
            status="Registered",
            matched_name=entry.brand_name or key,
            match_type=match_type,
            score=score,
            entry=entry,
            reg_no=entry.reg_no,
            validation_status=entry.validation_status,
            brand_match=bm,
            dosage_match=dm,
        )

    def _result_from_brand(
        self,
        key: str,
        match_type: str,
        score: float,
        query_norm: str,
        extracted_drug: str,
        extracted_mfr: Optional[str] = None,
        extracted_dosage: Optional[str] = None,
    ) -> NMRAMatchResult:
        indices = self._brand_idx.get(key, [])
        if not indices:
            return NMRAMatchResult(status="Not Found")
        bi = self._pick_best_entry_index(indices, query_norm, extracted_mfr, extracted_dosage)
        return self._result_from_brand_at(
            bi,
            key,
            match_type,
            score,
            query_norm,
            extracted_drug,
            extracted_mfr,
            extracted_dosage,
        )

    def _result_from_generic(
        self,
        key: str,
        match_type: str,
        score: float,
        query_norm: str,
        extracted_drug: str,
        extracted_mfr: Optional[str] = None,
        extracted_dosage: Optional[str] = None,
    ) -> NMRAMatchResult:
        indices = self._generic_idx.get(key, [])
        if not indices:
            return NMRAMatchResult(status="Not Found")
        bi = self._pick_best_entry_index(indices, query_norm, extracted_mfr, extracted_dosage)
        entry = self._entries[bi]
        bm = compare_extracted_brand_to_nmra(extracted_drug, entry)
        dm = (
            compare_extracted_dosage_to_nmra(extracted_dosage, entry)
            if extracted_dosage
            else None
        )
        return NMRAMatchResult(
            status="Registered",
            matched_name=entry.generic_name or key,
            match_type=match_type,
            score=score,
            entry=entry,
            reg_no=entry.reg_no,
            validation_status=entry.validation_status,
            brand_match=bm,
            dosage_match=dm,
        )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_INSTANCE: Optional[NMRAValidator] = None
_DATA_LOAD_MTIME: float = 0.0


def _nmra_data_mtime() -> float:
    """Latest mtime of NMRA JSON sidecar or Excel (whichever exists)."""
    try:
        json_path = os.path.splitext(_NMRA_XLSX)[0] + ".json"
        if os.path.exists(json_path):
            return os.path.getmtime(json_path)
        if os.path.exists(_NMRA_XLSX):
            return os.path.getmtime(_NMRA_XLSX)
    except OSError:
        pass
    return 0.0


def get_nmra_validator() -> NMRAValidator:
    """
    Return the registry singleton. Reloads automatically when the NMRA data file
    on disk changes (so Excel/JSON updates apply without a full server restart).
    """
    global _INSTANCE, _DATA_LOAD_MTIME
    mt = _nmra_data_mtime()
    if _INSTANCE is None or (mt > 0 and mt > _DATA_LOAD_MTIME):
        _INSTANCE = NMRAValidator()
        _DATA_LOAD_MTIME = mt
    return _INSTANCE
