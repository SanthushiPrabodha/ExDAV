import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher, get_close_matches
from typing import Optional


# ---------------------------------------------------------------------------
# KNOWN DRUG / MANUFACTURER DICTIONARIES
# Used by the fuzzy-correction layer to recover noisy OCR tokens.
# ---------------------------------------------------------------------------

KNOWN_DRUG_NAMES = {
    # ── Generic names ────────────────────────────────────────────────────────
    "PARACETAMOL", "ACETAMINOPHEN", "IBUPROFEN", "ASPIRIN",
    "AMOXICILLIN", "AMOXICILLIN TRIHYDRATE", "AMOXICLAV",
    "CETIRIZINE", "CETIRIZINE DIHYDROCHLORIDE", "CETIRIZINE HYDROCHLORIDE",
    "LORATADINE", "CHLORPHENIRAMINE", "CHLORPHENAMINE",
    "METFORMIN", "METFORMIN HYDROCHLORIDE",
    "ATORVASTATIN", "SIMVASTATIN", "ROSUVASTATIN",
    "OMEPRAZOLE", "PANTOPRAZOLE", "LANSOPRAZOLE",
    "CIPROFLOXACIN", "AZITHROMYCIN", "CLARITHROMYCIN",
    "METRONIDAZOLE", "DOXYCYCLINE", "TETRACYCLINE",
    "FLUCLOXACILLIN", "CEFUROXIME", "CEFTRIAXONE", "COTRIMOXAZOLE",
    "DICLOFENAC", "NAPROXEN", "MEFENAMIC ACID",
    "CODEINE", "TRAMADOL", "MORPHINE",
    "SALBUTAMOL", "PREDNISOLONE", "DEXAMETHASONE", "HYDROCORTISONE",
    "AMLODIPINE", "LISINOPRIL", "ENALAPRIL", "LOSARTAN",
    "GLIBENCLAMIDE", "GLIPIZIDE",
    "FERROUS SULFATE", "FOLIC ACID", "VITAMIN C", "ASCORBIC ACID",
    "ZINC SULFATE", "CALCIUM CARBONATE",
    "INSULIN", "INSULIN GLARGINE", "INSULIN ASPART",
    "FLUCONAZOLE", "CLINDAMYCIN", "GENTAMICIN", "FUSIDIC ACID",
    "DOMPERIDONE", "RANITIDINE", "FAMOTIDINE", "BETAMETHASONE",
    "TERBINAFINE", "CELECOXIB", "MONTELUKAST", "FORMOTEROL",
    "BECLOVENT",
    "BECLATE",
    # Enzymes used as active ingredients (intentionally kept as generics,
    # not as brand-name candidates — see _fallback_drug_name logic)
    "CHYMOTRYPSIN", "TRYPSIN", "SERRATIOPEPTIDASE", "BROMELAIN",
    # ── Brand names (from real-world packaging in this dataset) ─────────────
    "ALPHINTERN",
    "ADOL", "PANADOL", "PARAMOL", "EZAMOL",
    "BRUFEN", "CATAFLAM", "DICLAC", "FLECTOR",
    "AUGMENTIN", "MEGAMOX", "FLUMOX", "HIBIOTIC", "AMRIZOLE",
    "FLAGYL", "CIPRODIAZOLE", "CIPROFAR", "FLOXABACT",
    "DIFLUCAN",
    "GLUCOPHAGE",
    "MOTILIUM",
    "BETADINE", "BETADERM",
    "LAMISIL", "LAMIFEN",
    "CELEBREX",
    "CLARITINE", "CLARINASE", "HISTAZINE", "CONGESTAL",
    "ZYRTEC", "CETALSINUS",
    "ZANTAC",
    "ANTOPRAL", "MUCOSTA",
    "FUCIDIN", "FUCICORT",
    "GARAMYCIN",
    "PREDSAL", "PREDSOL",
    "CEFTRIAXONE", "CEMICRESTO",
    "SALBUTAMOL", "AIROPLAST", "FARCOLIN", "ALLVENT",
    "JANUMET",
    "DAFLON",
    "DAVALINDI",
    "NEUROVIT", "MILGA",
    "OSTEOCARE", "FEROGLOBIN", "FERROFOL",
    "BRUFEN", "JUSPRIN",
    "TAREG", "CANDALKAN", "SELOKEN",
    "MIDODRINE",
    "LOVIR",
    # Topical / dermatology
    "ZENTA",
    # Antihistamine brands
    "CETRICON", "CETRINE", "CETIMAX",
}

# Brand names only — used in fallback so that active ingredient names
# (CHYMOTRYPSIN, TRYPSIN, etc.) are never mistaken for the product brand.
KNOWN_BRAND_NAMES: set = {
    "ALPHINTERN",
    "PANADOL", "ADOL", "PARAMOL", "EZAMOL",
    "BRUFEN", "CATAFLAM", "DICLAC",
    "AUGMENTIN", "MEGAMOX", "FLUMOX", "HIBIOTIC", "AMRIZOLE",
    "FLAGYL", "CIPROFAR", "FLOXABACT",
    "DIFLUCAN",
    "GLUCOPHAGE",
    "MOTILIUM",
    "BETADINE", "BETADERM",
    "LAMISIL", "LAMIFEN",
    "CELEBREX",
    "CLARITINE", "CLARINASE", "HISTAZINE", "CONGESTAL",
    "ZYRTEC", "CETALSINUS",
    "ZANTAC",
    "ANTOPRAL", "MUCOSTA",
    "FUCIDIN", "FUCICORT",
    "GARAMYCIN",
    "PREDSAL", "PREDSOL",
    "AIROPLAST", "FARCOLIN", "ALLVENT",
    "JANUMET",
    "DAFLON",
    "NEUROVIT", "MILGA",
    "OSTEOCARE", "FEROGLOBIN", "FERROFOL",
    "JUSPRIN",
    "TAREG", "CANDALKAN", "SELOKEN",
    "MIDODRINE",
    "LOVIR",
    "DAVALINDI",
    # Additional common brands users may upload
    "POLYBION",
    "CALPOL", "TYLENOL", "NUROFEN", "ADVIL",
    "AUGMENTIN", "AMOXIL",
    "AZITHRAL", "ZITHROMAX",
    "NORFLOX", "CIPLOX",
    "OMEZ", "NEXIUM", "PRILOSEC",
    "GLUCOPHAGE", "METPURE",
    "AMLOKIND", "STAMLO",
    "TELMA", "LOSAR",
    "NEBICARD", "METOLAR",
    "ASCORIL", "BENADRYL",
    "PHENERGAN", "AVIL",
    "VOLINI", "MOOV",
    "BETNESOL", "WYSOLONE",
    "FORTWIN", "KETOROL",
    "ACILOC", "PANTOCID",
    "COBADEX", "BECADEX",
    "FEOSOL", "SANGOBION",
    "CREMAFFIN", "SOFTOVAC",
    "GLYCOMET", "JANUVIA",
    "TENORMIN", "INDERAL",
    "STUGERON", "VERTIN",
    "METROGYL", "ORNIDAZOLE",
    # Topical / dermatology
    "ZENTA",
    # Antihistamine brands
    "CETRICON", "CETRINE", "CETIMAX", "CETCIP",
    "XYZAL",
    # Other common brands
    "CIPLA", "ZOCON", "ZOCEF",
    # Beclometasone inhaler brands (NMRA — common OCR: Belcovic / Belcovent)
    "BECLOVENT",
    "BECLATE",
}

# Generics that should NEVER be returned as the drug brand name in fallback
# (they are active ingredient names that often appear on side labels)
_ACTIVE_INGREDIENT_NAMES: frozenset = frozenset({
    "CHYMOTRYPSIN", "TRYPSIN", "SERRATIOPEPTIDASE", "BROMELAIN",
    "LYSOZYME", "PAPAIN", "FICIN", "NATTOKINASE",
    "CHYMOTRYPSINE", "TRYPSINE",
})

# Month abbreviations for dot-matrix labels: EXP : MAR 2027, MFG : APR 2024
_MONTH_ABBR: dict = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}
_MONTH_NAMES_RE = "|".join(_MONTH_ABBR)


def _coerce_year_token(y: str) -> Optional[int]:
    """
    Recover 4-digit year from noisy dot-matrix OCR (e.g. 227 → 2027, 20240 → 2024).
    """
    y = (y or "").strip()
    if not y.isdigit():
        return None
    if len(y) == 5 and y.startswith("202") and y.endswith("0"):
        return int(y[:-1])
    if len(y) == 3 and y.startswith("22"):
        return 2000 + int(y[1:])
    if len(y) == 4 and 2000 <= int(y) <= 2099:
        return int(y)
    if len(y) == 2:
        return 2000 + int(y)
    return None


def _fix_pharma_brand_typos(norm: str) -> str:
    """
    Correct recurring Tesseract misreads on brand names (uppercase text).

    Common on inhalers: BELCOVIC / BELCOVENT / BECLOVIC → BECLOVENT (v↔n, c↔e).
    """
    if not norm:
        return norm
    t = norm
    # Longer phrases first
    pairs = [
        #(r"\b8ELCOVIC\b", "BECLOVENT"),
        (r"\b8ELCOVENT\b", "BECLOVENT"),
        #(r"\bBELCOVIC\s+400\b", "BECLOVENT 400"),
        (r"\bBELCOVENT\s+400\b", "BECLOVENT 400"),
        #(r"\bBECLOVIC\s+400\b", "BECLOVENT 400"),
        #(r"\bBELCOVIC\b", "BECLOVENT"),
        (r"\bBELCOVENT\b", "BECLOVENT"),
        #(r"\bBECLCOVIC\b", "BECLOVENT"),
        #(r"\bBECLOVIC\b", "BECLOVENT"),
        (r"\bBELOVENT\b", "BECLOVENT"),
        (r"\bBECLCOVENT\b", "BECLOVENT"),
        # Truncated / merged tokens
        #(r"\bBELCOVI\b", "BECLOVENT"),
        (r"\bBECLOVE\b", "BECLOVENT"),
    ]
    for pat, repl in pairs:
        t = re.sub(pat, repl, t, flags=re.IGNORECASE)
    t = _fuzzy_beclovent_tokens(t)
    return t


def _fuzzy_beclovent_tokens(norm: str) -> str:
    """
    Catch OCR variants that regex misses (spacing, odd chars) but are still
    clearly 'Beclovent' (COV/COVI/VENT) — do not map toward BECLATE.
    """
    if not norm:
        return norm
    out: list[str] = []
    for w in norm.split():
        w2 = re.sub(r"[^A-Z0-9]", "", w.upper())
        if (
            w2
            and w2[0] in ("B", "8")
            and 6 <= len(w2) <= 13
            and ("COV" in w2 or "COVI" in w2 or "VENT" in w2 or "COVENT" in w2)
        ):
            if w2[0] == "8":
                w2 = "B" + w2[1:]
            if SequenceMatcher(None, w2, "BECLOVENT").ratio() >= 0.52:
                out.append("BECLOVENT")
                continue
        out.append(w)
    return " ".join(out)


def _normalize_display_brand_name(name: str) -> str:
    """Apply canonical spelling for display when OCR matched a known typo."""
    if not name or not str(name).strip():
        return name
    s = str(name).strip()
    # Single source of truth: same normalize_text() as NMRA / registry matching
    try:
        n = normalize_text(s)
        parts = n.split()
        if parts and parts[0] == "BECLOVENT":
            tail = " ".join(s.split()[1:]) if len(s.split()) > 1 else ""
            return f"Beclovent {tail}".strip() if tail else "Beclovent"
        if parts and parts[0] == "BECLATE":
            tail = " ".join(s.split()[1:]) if len(s.split()) > 1 else ""
            return f"Beclate {tail}".strip() if tail else "Beclate"
    except Exception:
        pass
    compact = re.sub(r"[^A-Z0-9]", "", s.upper())
    if compact in ("BELCOVIC", "BELCOVENT", "BECLCOVIC", "BECLOVIC", "BELOVENT", "BECLCOVENT"):
        return "Beclovent"
    if compact in ("BELCOVIC400", "BELCOVENT400", "BECLOVIC400"):
        return "Beclovent 400"
    toks = s.split()
    if toks and re.sub(r"[^A-Z0-9]", "", toks[0].upper()) in (
        #"BELCOVIC",
        "BELCOVENT",
        #"BECLCOVIC",
        #"BECLOVIC",
        "BELOVENT",
    ):
        if len(toks) == 1:
            return "Beclovent"
        if len(toks) == 2 and toks[1].upper() in ("400", "200", "100", "250"):
            return f"Beclovent {toks[1]}"
        return "Beclovent " + " ".join(toks[1:])
    return name


def _expand_dot_matrix_typos(norm: str) -> str:
    """Fix common Tesseract substitutions on dotted / thermal label fonts."""
    n = norm
    n = re.sub(r"\bMEG\s+", "MFG ", n)
    n = re.sub(r"\bMPG\s*:", "MFG:", n)
    n = re.sub(r"\bEXE\s*", "EXP ", n)
    # Dot-matrix often mis-reads these month abbreviations
    n = re.sub(r"\bAPK\b", "APR", n)
    n = re.sub(r"\bHAR\b", "MAR", n)
    # "Bach" misread of "Batch" on dotted fonts
    n = re.sub(r"\bBACH\s+(\d)", r"BATCH \1", n)
    # EXP line misread as "FAR IG SPR" on some dot-matrix labels
    n = re.sub(r"\bFAR\s+IG\s+SPR\s+(20\d{2})\b", r"EXP MAR \1", n)
    return n


def _coerce_month_abbrev(tok: str) -> Optional[str]:
    """Map a noisy 3-letter token to JAN..DEC when possible."""
    if not tok:
        return None
    t = re.sub(r"[^A-Z]", "", tok.upper())[:3]
    if t in _MONTH_ABBR:
        return t
    # Common dot-matrix / low-DPI substitutions
    aliases = {"APK": "APR", "HAR": "MAR", "FAR": "MAR"}
    if t in aliases:
        return aliases[t]
    # "SPR" collides with SEP vs MAR; prefer MAR when paired with late 2020s (typical kit expiry)
    if t == "SPR":
        return "MAR"
    hits = get_close_matches(t, list(_MONTH_ABBR.keys()), n=1, cutoff=0.55)
    return hits[0] if hits else None


KNOWN_MANUFACTURERS = {
    "GLAXOSMITHKLINE", "GSK",
    "PFIZER", "PFIZER INC",
    "NOVARTIS", "NOVARTIS PHARMA",
    "CIPLA", "CIPLA LIMITED",
    "ABBOTT", "ABBOTT LABORATORIES",
    "SANOFI", "SANOFI AVENTIS",
    "BAYER", "BAYER AG",
    "RECKITT BENCKISER",
    "JOHNSON AND JOHNSON",
    "MERCK", "MERCK KGA",
    "ASTRAZENECA",
    "ELI LILLY",
    "ROCHE",
    "BRISTOL MYERS SQUIBB",
    "TAKEDA",
    "BOEHRINGER INGELHEIM",
    "TEVA", "TEVA PHARMACEUTICAL",
    "SANDOZ",
    "MYLAN",
    "SUN PHARMA", "SUN PHARMACEUTICAL",
    "DR REDDYS", "DR REDDYS LABORATORIES",
    "ASPEN",
    "INDOCO REMEDIES",
    "HETERO LABS",
    "EMCURE PHARMACEUTICALS",
    "COSMAS",
    "PROCTER AND GAMBLE", "PROCTER GAMBLE", "PROCTER GAMBLE HEALTH",
    "AMOUN", "AMOUN PHARMACEUTICAL",
    "SAVERA PHARMACEUTICALS",
    "HIMALAYA", "HIMALAYA DRUG",
    "DABUR", "DABUR INDIA",
    "MANKIND PHARMA", "ALKEM LABORATORIES",
    "TORRENT PHARMACEUTICALS", "LUPIN LIMITED",
    "ZYDUS CADILA", "CADILA HEALTHCARE",
    "IPCA LABORATORIES", "WOCKHARDT",
    "GLENMARK PHARMACEUTICALS",
    "MEDIBIOS", "MEDIBIOS PHARMACEUTICALS",
    "CARELINK", "CARE LINK",
    "PHARMATEC", "PHARMANOVA", "PHARMALAB",
    "LINA MANUFACTURING (PVT) LTD", "LINA",
}


# ---------------------------------------------------------------------------
# FUZZY CORRECTION
# Uses stdlib difflib – no external dependencies.
# Conservative cutoff (0.72) avoids over-correction on short tokens.
# ---------------------------------------------------------------------------

def _fuzzy_correct(value: str, known_set: set, cutoff: float = 0.72) -> Optional[str]:
    """Return the closest known name if similarity >= cutoff, else None."""
    if not value:
        return None
    upper = value.upper().strip()
    if upper in known_set:
        return upper.title()
    matches = get_close_matches(upper, known_set, n=1, cutoff=cutoff)
    return matches[0].title() if matches else None


# ---------------------------------------------------------------------------
# OCR RECONSTRUCTION
#
# Applied BEFORE normalization so every downstream extractor — whether
# the drug is known or unknown — sees clean, properly-formed words.
#
# Two common OCR failure modes are corrected here:
#
#   1. Letter-spacing: printers typeset brand names with extra spacing
#      between each character.  Tesseract then tokenises each character
#      individually → "C E T R I C O N".  We detect runs of ≥ 4
#      space-separated single alpha chars and collapse the spaces.
#      Threshold of 4 avoids merging genuine two-letter abbreviations
#      (e.g. "IV", "BD") while catching any drug name of 4+ chars.
#
#   2. Digit-in-word substitution: common Tesseract confusion:
#        0 ↔ O  (zero / oh)
#        1 ↔ I  (one / eye)
#        8 ↔ B  (eight / bee)
#      Corrected only when the digit is surrounded by letters on both
#      sides (look-ahead + look-behind) so batch numbers and dates are
#      never modified.
# ---------------------------------------------------------------------------

def reconstruct_ocr_words(text: str) -> str:
    """
    Repair common OCR tokenisation failures so extractors work on any image,
    whether the drug is in the known-brand list or not.

    Idempotent: safe to call multiple times on the same string.
    """
    if not text:
        return text

    # ── 1. Merge letter-spaced characters ──────────────────────────────
    # Matches: single-alpha  (space  single-alpha){3,}
    # e.g. "C E T R I C O N" (8 chars, 7 spaces) → "CETRICON"
    #      "Z E N T A"       (5 chars, 4 spaces) → "ZENTA"
    #      "A D O L"         (4 chars, 3 spaces) → "ADOL"
    text = re.sub(
        r'\b([A-Za-z])(?:\s+([A-Za-z])){3,}\b',
        lambda m: re.sub(r'\s+', '', m.group(0)),
        text,
    )

    # ── 2. Digit-in-word corrections ────────────────────────────────────
    # Only when flanked by letters — leaves batch/date digits untouched.
    text = re.sub(r'(?<=[A-Za-z])0(?=[A-Za-z])', 'O', text)
    text = re.sub(r'(?<=[A-Za-z])1(?=[A-Za-z])', 'I', text)
    text = re.sub(r'(?<=[A-Za-z])8(?=[A-Za-z])', 'B', text)

    return text


# ---------------------------------------------------------------------------
# TEXT NORMALIZATION
# Preserves / and - so date and batch separators survive into regex matching.
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    # Reconstruct fragmented OCR words first, then normalise.
    text = reconstruct_ocr_words(text)
    # Fold unicode homoglyphs (e.g. Cyrillic letters) before stripping
    text = unicodedata.normalize("NFKC", text)
    text = text.upper()
    # Preserve characters used in dates (/), batch IDs (-), dosage (%), and
    # label separators (:) before stripping everything else.
    text = re.sub(r"[^A-Z0-9\/\-\%\:\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = _expand_dot_matrix_typos(text)
    text = _fix_pharma_brand_typos(text)
    return text.strip()


# ---------------------------------------------------------------------------
# INDIVIDUAL FIELD EXTRACTORS
# ---------------------------------------------------------------------------

def _extract_drug_name(raw_text: str) -> Optional[str]:
    patterns = [
        r"\b(?:DRUG\s*NAME|GENERIC\s*NAME|PRODUCT\s*NAME)\s*[:\-]\s*([A-Z][A-Z0-9\s\-]{1,60})",
        r"\bNAME\s*[:\-]\s*([A-Z][A-Z0-9\s\-]{1,60})",
        r"\bPRODUCT\s*[:\-]\s*([A-Z][A-Z0-9\s\-]{1,60})",
        r"\bACTIVE\s*INGREDIENT\s*[:\-]\s*([A-Z][A-Z0-9\s\-]{1,60})",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_text)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" -:")
            # Strip trailing noise words (dosage units that bled into name)
            value = re.sub(r"\s+\d+\s*(?:MG|G|ML|MCG|IU|%).*$", "", value).strip()
            if len(value) >= 3:
                return value
    return None


def _extract_batch_number(raw_text: str) -> Optional[str]:
    patterns = [
        # Standard: BATCH NO / LOT NO (also BATCH N0 — common OCR)
        r"\b(?:BATCH\s*(?:NO|N0|NUMBER)|LOT\s*(?:NO|N0|NUMBER)|LOT)\s*[:\-\/]?\s*([A-Z0-9][A-Z0-9\-]{2,29})\b",

        # OCR often reads the first letter of "BATCH" as 8 → "8ATCH"
        r"\b(?:B|8)ATCH\s*[:\-]?\s*([A-Z0-9]{1,5}(?:\s*-\s*|[\-])[A-Z0-9]{2,20})\b",

        # "Batch : 84-0775" / "Batch : 84 - 0775" (spaces around hyphen)
        r"\bBATCH\s*[:\-]?\s*([A-Z0-9]{1,5}(?:\s*-\s*|[\-])[A-Z0-9]{2,20})\b",

        # "Batch : B4-0775" / "Batch : B4 - 0775" (spaces around hyphen)
        r"\bBATCH\s*[:\-]?\s*([A-Z]{1,5}(?:\s*-\s*|[\-])[A-Z]{2,20})\b",

        # Abbreviated: BNO, B/N, B.N.
        r"\b(?:B\s*NO|BNO|B\s*[\/\.]\s*N)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-]{2,29})\b",

        # Short: B1234 / B-1234
        r"\bB\s*[\-:]?\s*([0-9][A-Z0-9\-]{2,14})\b",

        # Lot prefix: L-1234
        r"\bL\s*[\-:]?\s*([0-9][A-Z0-9\-]{2,14})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_text)
        if match:
            value = match.group(1).strip().upper()
            value = re.sub(r"\s*-\s*", "-", value)
            value = re.sub(r"\s+", "", value)
            if re.match(r"^[A-Z0-9\-]{3,30}$", value):
                return value

    # Last resort: hyphenated codes like 84-0775 (reject MM-YYYY look-alikes 04-2024)
    if re.search(r"\b(?:B|8)ATCH\b|\bBATCH\b", raw_text):
        for m in re.finditer(r"\b(\d{2})-(\d{4})\b", raw_text):
            a, b = int(m.group(1)), int(m.group(2))
            if 1 <= a <= 12 and 2000 <= b <= 2099:
                continue
            cand = f"{m.group(1)}-{m.group(2)}"
            if re.match(r"^[A-Z0-9\-]{3,30}$", cand):
                return cand
    return None


def _extract_expiry_date(raw_text: str) -> Optional[str]:
    """
    Recognises all common expiry date formats found on pharmaceutical packaging:
      MM/YYYY  MM-YYYY  MM/YY  MM-YY
      YYYY-MM  YYYY/MM
      DD/YYYY  (treated as day-ignored, month inferred from context)
      EXP MM YYYY  |  EXP: MM/YYYY  |  BEST BEFORE MM/YYYY
      EXP : MAR 2027  (month *name* — common on dot-matrix prints)
      EXP.\nDATE : MM/YYYY  (multiline label layout)
    Returns normalised form MM-YYYY or MM-YY.
    """
    # All recognised expiry label keywords (case-insensitive in caller)
    keyword = (
        r"(?:EXP(?:IRY|I(?:RY)?)?\.?\s*DATE?|EXP\.?\s*DT"
        r"|BEST\s*BEFORE|USE\s*BEFORE|USE\s*BY|BB|EXPIRY)"
        r"\s*[:\-\.]?\s*"
    )

    # ── Month-name dates (must run before bare MM/YYYY to avoid ambiguity) ──
    # Year capture allows 20xx, 3-digit fragments (227), or 5-digit noise (20240).
    _y = r"(\d{2,5})"
    month_name_patterns = [
        keyword + rf"({_MONTH_NAMES_RE})\s+{_y}\b",
        r"\bEXP\s*[:\-\.]?\s*(" + _MONTH_NAMES_RE + r")\s+" + _y + r"\b",
    ]
    for pattern in month_name_patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            mon = _coerce_month_abbrev(match.group(1))
            year_str = match.group(2)
            if mon and mon in _MONTH_ABBR:
                year = _coerce_year_token(year_str)
                if year is not None:
                    try:
                        month = int(_MONTH_ABBR[mon])
                        if 1 <= month <= 12:
                            return f"{month:02d}-{year:04d}"
                    except ValueError:
                        pass

    patterns_with_sep = [
        # Labelled: EXP: 04/2025  EXP: 04-2025  EXP: 04/25
        keyword + r"(\d{1,2})[\/\-](\d{2,4})",
        # Labelled YYYY-MM or YYYY/MM
        keyword + r"(20\d{2})[\/\-](\d{1,2})",
        # Plain MM/YYYY or MM-YYYY (not preceded by another digit)
        r"(?<!\d)(\d{1,2})[\/\-](20\d{2})(?!\d)",
        # DD/YYYY where DD ≤ 31 — treat the first part as month guess;
        # _normalise_date_parts will reject invalid months automatically
        r"(?<!\d)(\d{2})[\/\-](20\d{2})(?!\d)",
        # Plain YYYY-MM bare
        r"(?<!\d)(20\d{2})[\/\-](\d{1,2})(?!\d)",
    ]

    space_patterns = [
        # EXP 04 2025 or EXP 2025 04
        keyword + r"(\d{1,2})\s+(20\d{2})",
        keyword + r"(20\d{2})\s+(\d{1,2})",
    ]

    for pattern in patterns_with_sep:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            g1, g2 = match.group(1), match.group(2)
            result = _normalise_date_parts(g1, g2)
            if result:
                return result

    for pattern in space_patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            g1, g2 = match.group(1), match.group(2)
            result = _normalise_date_parts(g1, g2)
            if result:
                return result

    # Loose: EXP ... (noise) ... (MON) YEAR anywhere in the same string (dot-matrix garbage between)
    loose = re.search(
        r"\bEXP\b.{0,160}?([A-Z]{3})\s+(\d{2,5})\b",
        raw_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if loose:
        mon = _coerce_month_abbrev(loose.group(1))
        year = _coerce_year_token(loose.group(2))
        if mon and year is not None:
            try:
                mi = int(_MONTH_ABBR[mon])
                return f"{mi:02d}-{year:04d}"
            except (ValueError, KeyError):
                pass

    return None


def _normalise_date_parts(a: str, b: str) -> Optional[str]:
    """Given two numeric strings, return MM-YYYY (or MM-YY) if they form a valid month/year pair."""
    if len(a) == 4 and a.startswith("20"):
        # YYYY-MM → swap
        year_str, month_str = a, b
    else:
        month_str, year_str = a, b

    try:
        month = int(month_str)
        year = int(year_str)
        if len(year_str) == 2:
            year += 2000
        if not (1 <= month <= 12 and 2000 <= year <= 2099):
            return None
        return f"{month:02d}-{year:04d}"
    except ValueError:
        return None


def extract_manufactured_date_from_text(text: str) -> str:
    """
    Extract manufacturing date from raw OCR text (same rules as pipeline_service).

    Handles numeric and month-name forms: MFG : 04/2024, MFG : APR 2024, etc.
    Returns a string like "04/2024" or "04/2027"; empty if not found.
    """
    if not text or not text.strip():
        return ""
    upper = text.upper()

    numeric_patterns = [
        r"\b(?:MFD|MFG|MANUFACTURED)\s*(?:DATE|DT|DATE\s*OF\s*MFG)?\s*[:\-\.]?\s*(\d{1,2}[\/\-]\d{2,4})\b",
        r"\b(?:MFD|MFG|MANUFACTURED)\s*(?:DATE|DT)?\s*[:\-\.]?\s*(\d{1,2}\s+\d{4})\b",
    ]
    for pattern in numeric_patterns:
        match = re.search(pattern, upper)
        if match:
            return re.sub(r"\s+", "/", match.group(1).strip())

    month_pattern = (
        rf"\b(?:MFD|MFG|MEG|MANUFACTURED)\s*(?:DATE|DT)?\s*[:\-\.]?\s*"
        rf"({_MONTH_NAMES_RE})\s+(\d{{2,5}})\b"
    )
    m = re.search(month_pattern, upper)
    if m:
        mon = m.group(1).upper()[:3]
        if mon in _MONTH_ABBR:
            y = _coerce_year_token(m.group(2))
            if y is not None:
                return f"{_MONTH_ABBR[mon]}/{y}"

    return ""


def extract_expiry_date_from_text(text: str) -> str:
    """
    Extract expiry as MM-YYYY from raw OCR (same rules as parse_metadata).

    Exposed for pipeline_service parity with extract_manufactured_date_from_text.
    """
    if not text or not text.strip():
        return ""
    v = _extract_expiry_date(normalize_text(text))
    return v if v else ""


def _extract_manufacturer(raw_text: str) -> Optional[str]:
    """
    Extract manufacturer / marketing-authorisation holder from OCR text.

    Handles three layout styles:
      (a) "Manufactured by: Procter & Gamble Health Ltd."  (inline)
      (b) "Manufactured by:\nProcter & Gamble Health Ltd." (newline between)
      (c) Direct P&G / PROCTER keyword when no 'by' phrase is present

    The `re.DOTALL` flag is NOT used so that `.*` does not swallow newlines;
    instead `[^\n]{2,80}` matches a single line after the keyword.
    """
    # Allow optional whitespace/newline between keyword and company name.
    _KEYWORD = (
        r"(?:MANUFACTURED\s*BY|MFG\.?\s*BY|MFD\.?\s*BY"
        r"|MARKETED\s*BY|DISTRIBUTED\s*BY|DIST\.?\s*BY"
        r"|IMPORTED\s*BY|MANUFACTURER|MFR)"
    )
    patterns = [
        # (a)+(b): keyword followed by optional whitespace (including newline) then company
        rf"\b{_KEYWORD}\s*[:\-]?\s*\n?\s*([A-Z][A-Z0-9 \.\-&]{{2,80}})",
        # Fallback: look for P&G / PROCTER directly (normalised text has no &)
        r"\b(PROCTER(?:\s+(?:AND|&))?\s+GAMBLE[A-Z0-9 \.\-]{0,40})",
        r"\b(GLAXOSMITHKLINE[A-Z0-9 \.\-]{0,40})",
    ]

    for pattern in patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" -:")

            # Truncate at address indicators / next metadata keyword
            value = re.split(
                r"\s+(?:BATCH|LOT|EXP|MFD|STORE|REG|PLOT|ROAD|STREET"
                r"|AT\s*:|PVT|INDIA|PLOT|SURVEY|VILLAGE|DISTRICT|PIN)",
                value,
                flags=re.IGNORECASE,
            )[0].strip()

            # Also stop after common company-suffix words
            for suffix in ("LIMITED", " LTD", " INC", " LLC", " CORP", " HEALTH", " PHARMA"):
                idx = value.upper().find(suffix)
                if idx >= 0:
                    value = value[: idx + len(suffix)].strip()
                    break

            if len(value) >= 3:
                return value

    return None


def _extract_dosage(raw_text: str) -> Optional[str]:
    """Extract strength / dosage (500mg, 1%, 5ml, 10IU, etc.)."""
    labeled = r"\b(?:STRENGTH|DOSAGE|DOSE|EACH\s+(?:TABLET|CAPSULE|ML|TAB|CAP))\s*[:\-]?\s*(\d+(?:\.\d+)?\s?(?:MG|G|ML|MCG|IU|%))"
    match = re.search(labeled, raw_text)
    if match:
        return match.group(1).strip()
    # Unlabeled: bare value like "500MG", "1%", "5ML"
    bare = r"(?<![A-Z])(\d+(?:\.\d+)?\s?(?:MG|G|ML|MCG|IU|%))(?![A-Z0-9])"
    match = re.search(bare, raw_text)
    return match.group(1).strip() if match else None


# ---------------------------------------------------------------------------
# DESCRIPTOR WORD FILTER
# Words that sound like drug names but are actually descriptions, dosage
# forms, instructions, or common English.  Excluded from fallback picking.
# ---------------------------------------------------------------------------
_DESCRIPTOR_WORDS: frozenset = frozenset({
    # Dosage forms
    "TABLETS", "TABLET", "CAPSULES", "CAPSULE", "CAPLETS", "CAPLET",
    "SOLUTION", "SYRUP", "CREAM", "LOTION", "GEL", "OINTMENT", "PASTE",
    "SPRAY", "DROPS", "INJECTION", "INFUSION", "SUSPENSION", "POWDER",
    "ELIXIR", "TINCTURE", "PATCH", "SACHET", "SACHETS", "SUPPOSITORY",
    "EFFERVESCENT", "CHEWABLE", "DISPERSIBLE", "ENTERIC", "COATED",
    "EXTENDED", "RETARD", "REPEAT", "REPETABS",
    # Pharmacological / nutritional category words
    "ANTI", "ANTIBIOTIC", "ANTIHISTAMINE", "ANTIFUNGAL", "ANTIVIRAL",
    "ANALGESIC", "ANTIPYRETIC", "ANTACID", "ANTIDIARRHEAL", "ANTISPASMODIC",
    "INFLAMMATORY", "EDEMATOUS", "ANTIINFLAMMATORY", "ANTIEDEMATOUS",
    "ANTISEPTIC", "ANTIBACTERIAL", "ANTHELMINTIC",
    "VITAMIN", "VITAMINS", "MINERAL", "MINERALS",
    "COMPLEX", "SUPPLEMENT", "NUTRITIONAL",
    # Instruction / label words
    "INDICATIONS", "DOSAGE", "CONTRAINDICATIONS", "WARNINGS", "PRECAUTIONS",
    "STORE", "KEEP", "PROTECT", "LIGHT", "MOISTURE", "CHILDREN", "ADULTS",
    "EACH", "CONTAINS", "ACTIVE", "INGREDIENT", "EXCIPIENT",
    "INDICATION", "LEAFLET", "ENCLOSED", "TEMPERATURE",
    # Manufacturer / company words
    "MANUFACTURED", "MANUFACTURER", "MANUFACTURING",
    "PHARMACEUTICAL", "PHARMACEUTICALS", "PHARMA",
    "LABORATORY", "LABORATORIES",
    "CORPORATION", "COMPANY", "LIMITED", "PRIVATE", "INDUSTRIES",
    "REGISTERED", "TRADEMARK", "REGISTRATION",
    "HEALTH", "HEALTHCARE", "MEDICAL",
    # Common English filler words long enough to fool the fallback
    "WITH", "FROM", "THIS", "THAT", "THESE", "THOSE", "HAVE", "BEEN",
    "WILL", "SHOULD", "BEFORE", "AFTER", "DURING", "BETWEEN",
    "PRODUCT", "MEDICINAL", "MEDICINE",
    "FORMULA", "STRENGTH", "COMPOSITION",
    "ULTRA", "EXTRA", "SUPER", "RAPID", "SWIFT",
    # Person / company surnames that appear in manufacturer address blocks
    # and must never be mistaken for a drug brand name
    "PINGITORE", "PATEL", "SHARMA", "MEHTA", "GUPTA", "SINGH",
})


# ---------------------------------------------------------------------------
# PROMINENT-WORD EXTRACTOR (position-aware, original-case)
#
# Many clean drug labels (e.g. Polybion, Augmentin, Panadol) display the
# brand name as a large TitleCase word near the TOP of the label, BEFORE
# the Batch/Mfg/Exp section.  Scanning the original (non-normalised) OCR
# text for this structure avoids the case-folding loss of the normalised
# pipeline and naturally excludes address/manufacturer text which appears
# after the metadata fields.
# ---------------------------------------------------------------------------

_LABEL_BOUNDARY_RE = re.compile(
    r'\b(?:batch|lot|b\.?\s*no|mfg\.?|manufactured|exp\.?|expiry|date|m\.l\.)\b',
    re.IGNORECASE,
)


def _extract_first_prominent_word(original_text: str) -> Optional[str]:
    """
    Return the first TitleCase word that appears BEFORE any batch-number /
    date / manufacturer boundary keyword in the OCR text.

    No hard length gate is applied — drug brand names can be as short as
    4 characters ("Adol") or as long as 17+ ("Serratiopeptidase").  The
    real discriminators are:
      • TitleCase capitalisation  (brand name, not ALL-CAPS descriptor)
      • Not in _DESCRIPTOR_WORDS  (dosage forms, instruction words, etc.)
      • Not in _ACTIVE_INGREDIENT_NAMES  (enzyme / INN generics)
      • ≥ 2 distinct vowels       (pronounceable word, not OCR garbage)
      • Appears BEFORE the metadata boundary  (positional prominence)

    A minimal floor of 3 characters is kept only to skip OCR artifacts
    like "Ab", "Rr", "XZ".
    """
    if not original_text:
        return None

    # Reconstruct letter-spaced/fragmented OCR tokens before scanning
    # so "C E T R I C O N" → "CETRICON" before the regex runs.
    original_text = reconstruct_ocr_words(original_text)

    boundary = _LABEL_BOUNDARY_RE.search(original_text)
    region = original_text[: boundary.start()].strip() if boundary else original_text

    # Words explicitly excluded beyond _DESCRIPTOR_WORDS.
    # These are product category descriptors that often appear before
    # the brand name (e.g. "Vitamin B-Complex Syrup" precedes "Polybion").
    _IGNORE_WORDS: frozenset = frozenset({
        "VITAMIN", "VITAMINS", "COMPLEX", "SYRUP", "TABLETS", "CAPSULES",
        "LIQUID", "MIXTURE", "FORTE", "JUNIOR", "SENIOR",
        "SUGAR", "COATED", "ULTRA", "FAST", "SLOW", "RAPID",
        "REGISTERED", "TRADEMARK", "TRADE",
    })

    def _is_valid_brand_word(word: str) -> bool:
        """
        Return True when a word is a plausible drug brand name.

        Criteria (all must pass):
          • len ≥ 5          — rules out short noise like ADGA (4), ADA (3)
          • unique chars > 2 — rules out repeated-letter artifacts
          • ≥ 2 vowels       — pronounceable, not random consonants
          • not a descriptor / active-ingredient / ignore word
        """
        upper = re.sub(r'[^A-Z]', '', word.upper())
        return (
            len(upper) >= 5
            and len(set(upper)) > 2
            and sum(1 for ch in upper if ch in "AEIOU") >= 2
            and upper not in _DESCRIPTOR_WORDS
            and upper not in _ACTIVE_INGREDIENT_NAMES
            and upper not in _IGNORE_WORDS
        )

    # ── PHASE 1: Top-6 lines only (highest positional priority) ──────────
    # The brand name appears near the top of the label, well above the
    # metadata section.  Scanning only the first 6 lines of the region
    # before the metadata boundary maximises precision.
    top_lines = "\n".join(region.splitlines()[:6])
    for word in re.findall(r'\b([A-Z][a-zA-Z]{2,})\b', top_lines):
        if _is_valid_brand_word(word):
            return word  # preserve original capitalisation

    # ── PHASE 2: Full region (handles labels with longer preambles) ───────
    for word in re.findall(r'\b([A-Z][a-zA-Z]{2,})\b', region):
        if _is_valid_brand_word(word):
            return word

    return None


def _extract_brand_from_roi(roi_text: str) -> Optional[str]:
    """
    Extract the drug brand name from the central brand ROI OCR result.

    The brand ROI (x: 15-85 %, y: 20-55 % of original image) is a tight crop
    focused on the area where the brand name is printed in large font.
    Text from this region has the highest visual evidence value and must NOT
    be overridden by fuzzy matching against the known-brand dictionary.

    Rules:
      • Prefer TitleCase (mixed-case) words — strong indicator of brand name
      • Require len ≥ 5, unique chars > 2, ≥ 2 vowels
      • Exclude descriptors / active ingredients
      • ALL-CAPS words are also accepted if they pass quality gates
        (handles labels printed in all-caps)
    """
    if not roi_text:
        return None

    roi_text = reconstruct_ocr_words(roi_text)

    _IGNORE = _DESCRIPTOR_WORDS | frozenset({
        "VITAMIN", "VITAMINS", "COMPLEX", "SYRUP", "TABLETS", "CAPSULES",
        "LIQUID", "MIXTURE", "FORTE", "JUNIOR", "SENIOR",
        "SUGAR", "COATED", "ULTRA", "FAST", "SLOW", "RAPID",
        "REGISTERED", "TRADEMARK", "TRADE",
    })

    def _roi_quality(upper: str) -> bool:
        return (
            len(upper) >= 5
            and len(set(upper)) > 2
            and sum(1 for ch in upper if ch in "AEIOU") >= 2
            and upper not in _IGNORE
            and upper not in _ACTIVE_INGREDIENT_NAMES
        )

    # Phase A: TitleCase (highest confidence — brand font)
    for word in re.findall(r'\b([A-Z][a-z]{2,}[A-Za-z]*)\b', roi_text):
        upper = re.sub(r'[^A-Z]', '', word.upper())
        if _roi_quality(upper):
            return word  # original capitalisation

    # Phase B: ALL-CAPS (some labels set brand in all-caps)
    for word in re.findall(r'\b([A-Z]{5,})\b', roi_text):
        if _roi_quality(word):
            return word.title()

    return None


def _fallback_drug_name(raw_text: str, original_text: str = "") -> Optional[str]:
    """
    Best-effort drug name when no labelled keyword was found.

    Strategy (in priority order):
      0. Scan top-6 OCR lines for a TitleCase word meeting quality criteria
         (len≥5, unique chars>2, ≥2 vowels, not descriptor/ingredient).
         TitleCase is a strong signal: printers set brand names in mixed case,
         while descriptor text is typically ALL-CAPS or sentence-case.
      1. Direct lookup of the full candidate set against KNOWN_BRAND_NAMES.
      2. Fuzzy match against KNOWN_BRAND_NAMES (cutoff 0.75).
      3. Fuzzy match against full KNOWN_DRUG_NAMES (cutoff 0.75).
      4. Quality-gated longest plausible word:
           len ≥ 5, unique chars > 2, ≥ 2 vowels,
           clean OCR → allow single-occurrence; noisy OCR → require ≥ 2.
      Return None when no candidate passes.
    """
    if not raw_text:
        return None

    _VOWELS = frozenset("AEIOU")
    _IGNORE = _DESCRIPTOR_WORDS | frozenset({
        "VITAMIN", "VITAMINS", "COMPLEX", "SYRUP", "TABLETS", "CAPSULES",
        "REGISTERED", "TRADEMARK", "TRADE",
    })

    def _brand_quality(word: str) -> bool:
        """Return True when word passes all brand-name quality gates."""
        upper = re.sub(r'[^A-Z]', '', word.upper())
        return (
            len(upper) >= 5
            and len(set(upper)) > 2
            and sum(1 for ch in upper if ch in _VOWELS) >= 2
            and upper not in _IGNORE
            and upper not in _ACTIVE_INGREDIENT_NAMES
        )

    # ── Step 0: TitleCase scan of top-6 lines of the ORIGINAL text ────
    # `raw_text` is the normalised (uppercase) text — TitleCase words are
    # gone there.  We use `original_text` (passed by parse_metadata) for
    # this scan so capitalisation signals are preserved.
    scan_src = reconstruct_ocr_words(original_text) if original_text else ""
    top_lines = "\n".join(scan_src.splitlines()[:6])
    for word in re.findall(r'\b([A-Z][a-z]{2,}[A-Za-z]*)\b', top_lines):
        if _brand_quality(word):
            return word  # preserve original capitalisation

    # Build de-duplicated candidate list, preserving first-occurrence order.
    seen: set = set()
    candidates = []
    for word in raw_text.split():
        upper = re.sub(r"[^A-Z]", "", word.upper())
        if len(upper) >= 3 and upper not in _DESCRIPTOR_WORDS and upper not in seen:
            seen.add(upper)
            candidates.append(upper)

    if not candidates:
        return None

    filtered = [c for c in candidates if c not in _ACTIVE_INGREDIENT_NAMES]
    if not filtered:
        filtered = candidates

    # ── Step 1: O(|KNOWN_BRAND_NAMES|) direct lookup ──────────────────
    candidate_set = set(filtered)
    found_brands = [b for b in KNOWN_BRAND_NAMES if b in candidate_set]
    if found_brands:
        return max(found_brands, key=len).title()

    # ── Step 2: fuzzy match against BRAND names (first 300 candidates) ─
    for candidate in filtered[:300]:
        match = _fuzzy_correct(candidate, KNOWN_BRAND_NAMES, cutoff=0.75)
        if match:
            return match

    # ── Step 3: fuzzy match against full known-drugs set ───────────────
    for candidate in filtered[:300]:
        match = _fuzzy_correct(candidate, KNOWN_DRUG_NAMES, cutoff=0.75)
        if match:
            return match

    # ── Step 4: quality-gated most-plausible word ─────────────────────
    # Now apply strict quality gates: len≥5, unique chars>2, ≥2 vowels.
    # This explicitly blocks short noise tokens like "ADGA" (4 chars) that
    # come from license numbers (e.g. "AD/116A") or address fragments.
    all_toks = raw_text.split()
    alpha_toks = [t for t in all_toks if re.match(r'^[A-Z]{3,}$', t)]
    ocr_quality = len(alpha_toks) / max(len(all_toks), 1)

    plausible = [
        c for c in filtered
        if len(c) >= 5
        and len(set(c)) > 2
        and c not in _ACTIVE_INGREDIENT_NAMES
    ]
    for candidate in sorted(plausible, key=len, reverse=True):
        vowel_count = sum(1 for ch in candidate if ch in _VOWELS)
        occurrences = raw_text.count(candidate)
        if vowel_count >= 2 and (ocr_quality >= 0.35 or occurrences >= 2):
            return candidate.title()

    return None


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def parse_metadata(ocr_text: str, roi_text: str = "") -> dict:
    """
    Parse all metadata fields from OCR text.

    Parameters
    ----------
    ocr_text  : full OCR output from the image (all passes combined)
    roi_text  : OCR output from the central brand ROI (x:15-85%, y:20-55%).
                When provided this acts as the highest-priority source for
                drug name extraction and cannot be overridden by fuzzy matching.
    """
    if not ocr_text or not ocr_text.strip():
        return {
            "drug_name": None,
            "drug_name_source": "none",
            "drug_name_confidence": 0.0,
            "drug_name_roi_candidate": None,
            "drug_name_fuzzy_candidate": None,
            "dosage_form": None,
            "strength": None,
            "expiry_date": None,
            "batch_number": None,
            "manufactured_date": None,
            "manufacturer": None,
            "warnings": ["OCR text is empty; no metadata could be extracted"],
        }

    norm = normalize_text(ocr_text)

    # Drug name resolved later with explicit priority chain
    drug_name = None
    batch_number = _extract_batch_number(norm)
    expiry_date = _extract_expiry_date(norm)
    manufacturer = _extract_manufacturer(norm)
    strength = _extract_dosage(norm)
    manufactured_date = extract_manufactured_date_from_text(ocr_text) or None

    # ================================================================
    # DRUG NAME PRIORITY CHAIN
    # Order (highest → lowest confidence):
    #   1. Exact known-brand match from brand ROI text
    #   2. Clean visible TitleCase/ALLCAPS candidate from brand ROI
    #   3. Labelled keyword ("DRUG NAME:") from full OCR
    #   4. TitleCase prominent word from full OCR (before boundary)
    #   5. Fuzzy/fallback from full OCR (lowest confidence)
    #
    # SAFETY RULE: if a candidate was found in the ROI (steps 1-2),
    # fuzzy matching CANNOT override it.  This prevents garbled OCR
    # fragments from matching e.g. "Losar" when "Polybion" is clearly
    # visible in the brand area of the image.
    # ================================================================
    drug_name_source = "none"
    drug_name_confidence = 0.0
    roi_candidate: Optional[str] = None
    fuzzy_candidate: Optional[str] = None

    # ── Step 1: ROI exact known-brand lookup ──────────────────────────
    if roi_text:
        roi_norm = normalize_text(roi_text)
        roi_words = set(re.findall(r'\b[A-Z]{4,}\b', roi_norm))
        found_roi_brands = [b for b in KNOWN_BRAND_NAMES if b in roi_words]
        if found_roi_brands:
            drug_name = max(found_roi_brands, key=len).title()
            drug_name_source = "roi_exact"
            drug_name_confidence = 0.98

    # ── Step 2: ROI clean visible candidate ───────────────────────────
    if drug_name is None and roi_text:
        roi_candidate = _extract_brand_from_roi(roi_text)
        if roi_candidate:
            drug_name = roi_candidate
            drug_name_source = "roi_visible"
            drug_name_confidence = 0.90

    # ── Step 3: Labelled keyword from full OCR ────────────────────────
    if drug_name is None:
        labeled = _extract_drug_name(norm)
        if labeled:
            drug_name = labeled
            drug_name_source = "labelled"
            drug_name_confidence = 0.95

    # ── Step 4: TitleCase prominent word from full OCR ────────────────
    if drug_name is None:
        prominent = _extract_first_prominent_word(ocr_text)
        if prominent:
            drug_name = prominent
            drug_name_source = "prominent_word"
            drug_name_confidence = 0.75

    # ── Step 5: Fuzzy / fallback (full OCR) ──────────────────────────
    # Only allowed when no ROI or prominent candidate was found.
    # Also compute the fuzzy candidate for debug purposes.
    fuzzy_candidate = _fallback_drug_name(norm, original_text=ocr_text)

    if drug_name is None:
        # No visual evidence found — apply fuzzy only if confidence is
        # high (the result appears verbatim in the OCR text).
        if fuzzy_candidate:
            fuzzy_upper = re.sub(r"[^A-Z]", "", fuzzy_candidate.upper())
            visual_evidence = fuzzy_upper in norm.replace(" ", "")
            if visual_evidence:
                drug_name = fuzzy_candidate
                drug_name_source = "fallback_verified"
                drug_name_confidence = 0.55
            else:
                # Fuzzy match has no visual anchor — reject to avoid
                # hallucinating a drug name that is not on the label.
                drug_name = None
                drug_name_source = "rejected_no_evidence"
                drug_name_confidence = 0.0

    # ---- Fuzzy correction of drug name ----
    # Allowed ONLY when source is NOT roi_* — fuzzy must never override
    # a word that was physically visible in the brand ROI.
    if drug_name and drug_name_source not in ("roi_exact", "roi_visible"):
        fuzzy_result = _fuzzy_correct(drug_name.upper(), KNOWN_DRUG_NAMES)
        if fuzzy_result:
            fuzzy_candidate = fuzzy_result
            # Only apply if the fuzzy result is actually present in the OCR
            fuzzy_upper = re.sub(r"[^A-Z]", "", fuzzy_result.upper())
            if fuzzy_upper in norm.replace(" ", ""):
                drug_name = fuzzy_result
                drug_name_source = "fuzzy_corrected"

    if manufacturer:
        # First try: find a known manufacturer name as a SUBSTRING of the
        # captured text (handles noisy captures that include address text).
        mfr_upper = manufacturer.upper()
        best_known = max(
            (km for km in KNOWN_MANUFACTURERS if km in mfr_upper),
            key=len,
            default=None,
        )
        if best_known:
            manufacturer = best_known.title()
        else:
            corrected = _fuzzy_correct(manufacturer, KNOWN_MANUFACTURERS)
            if corrected:
                manufacturer = corrected

    # ---- Prefer future expiry date ----
    # If the extracted expiry_date is already in the past (a common OCR
    # confusion between Mfg Date and Exp Date), scan the normalised text
    # for any date that is still in the future and use that instead.
    if expiry_date:
        try:
            parts = re.split(r"[/\-]", expiry_date)
            if len(parts) == 2:
                em, ey = int(parts[0]), int(parts[1])
                if ey < 100:
                    ey += 2000
                now = datetime.now()
                if ey < now.year or (ey == now.year and em < now.month):
                    # Current hit is in the past — search for a future date
                    for fm, fy in re.findall(
                        r"(?<!\d)(\d{1,2})[\/\-](20[3-9]\d|202[6-9])(?!\d)", norm
                    ):
                        fi, mi = int(fy), int(fm)
                        if (
                            1 <= mi <= 12
                            and (fi > now.year or (fi == now.year and mi >= now.month))
                        ):
                            expiry_date = f"{mi:02d}-{fi:04d}"
                            break
        except Exception:
            pass

    # ---- Prominent-word extraction (position-aware, original case) ----
    # Tries to find the brand name as a TitleCase word appearing BEFORE
    # the batch/date/manufacturer section in the ORIGINAL OCR text.
    # This handles clean label images (Polybion, Augmentin, etc.) where
    # no explicit "DRUG NAME:" label keyword is present.
    drug_name_source = "labelled"
    if drug_name is None:
        drug_name = _extract_first_prominent_word(ocr_text)
        if drug_name:
            drug_name_source = "prominent_word"
            corrected = _fuzzy_correct(drug_name.upper(), KNOWN_DRUG_NAMES)
            if corrected:
                drug_name = corrected

    # ---- Normalised-text fallback ----
    if drug_name is None:
        drug_name = _fallback_drug_name(norm)
        if drug_name:
            drug_name_source = "fallback"

    warnings = []
    if batch_number is None:
        warnings.append("Batch number is missing or uncertain")
    if expiry_date is None:
        warnings.append("Expiry date is missing or uncertain")
    if manufacturer is None:
        warnings.append("Manufacturer is missing or uncertain")

    # Confidence notice feeds into pipeline_service.py explanation builder
    if drug_name_source in ("prominent_word", "fallback_verified"):
        warnings.append(
            "The drug name was inferred from prominent packaging text. "
            "However, due to OCR noise or unlabelled layout, the result "
            "may have limited confidence. Manual verification is recommended."
        )
    if drug_name_source == "rejected_no_evidence":
        warnings.append(
            "Drug name could not be reliably identified. "
            "Fuzzy match produced a candidate with no visual evidence "
            "in the OCR text and was rejected to prevent misidentification."
        )

    if roi_candidate:
        roi_candidate = _normalize_display_brand_name(roi_candidate)
    if fuzzy_candidate:
        fuzzy_candidate = _normalize_display_brand_name(fuzzy_candidate)
    if drug_name:
        drug_name = _normalize_display_brand_name(drug_name)

    return {
        "drug_name": drug_name,
        # ── Debug fields (not shown in UI, used for research/testing) ──
        "drug_name_source": drug_name_source,
        "drug_name_confidence": round(drug_name_confidence, 2),
        "drug_name_roi_candidate": roi_candidate,
        "drug_name_fuzzy_candidate": fuzzy_candidate,
        # ────────────────────────────────────────────────────────────────
        "dosage_form": None,
        "strength": strength,
        "expiry_date": expiry_date,
        "batch_number": batch_number,
        "manufactured_date": manufactured_date,
        "manufacturer": manufacturer,
        "warnings": warnings,
    }


def validate_metadata(metadata):
    required_fields = ["drug_name", "batch_number", "expiry_date"]
    issues = []

    for field in required_fields:
        if not metadata.get(field):
            issues.append(
                {
                    "field": field,
                    "code": "MISSING_REQUIRED_FIELD",
                    "severity": "error",
                    "message": f"{field} is required but missing",
                }
            )

    expiry_value = metadata.get("expiry_date")
    expiry_format = r"^\d{2}[\/\-](\d{2}|\d{4})$"

    if expiry_value:
        if not re.match(expiry_format, expiry_value):
            issues.append(
                {
                    "field": "expiry_date",
                    "code": "INVALID_EXPIRY_FORMAT",
                    "severity": "error",
                    "message": "expiry_date must match MM/YY, MM-YY, MM/YYYY, or MM-YYYY",
                }
            )
        else:
            try:
                month_str, year_str = re.split(r"[\/\-]", expiry_value)
                month = int(month_str)
                year = int(year_str)
                if len(year_str) == 2:
                    year += 2000

                if month < 1 or month > 12:
                    raise ValueError("Month out of range")

                now = datetime.now()
                current_month_index = now.year * 12 + now.month
                expiry_month_index = year * 12 + month
                if expiry_month_index < current_month_index:
                    issues.append(
                        {
                            "field": "expiry_date",
                            "code": "EXPIRED_PRODUCT",
                            "severity": "error",
                            "message": "expiry_date is in the past",
                        }
                    )
            except Exception:
                issues.append(
                    {
                        "field": "expiry_date",
                        "code": "INVALID_EXPIRY_FORMAT",
                        "severity": "error",
                        "message": "expiry_date is invalid or unparsable",
                    }
                )

    # Lightweight inconsistency checks (conservative; no guessing)
    drug_name = metadata.get("drug_name")
    if drug_name and not re.search(r"[A-Z]", str(drug_name).upper()):
        issues.append(
            {
                "field": "drug_name",
                "code": "INCONSISTENT_VALUE",
                "severity": "error",
                "message": "drug_name appears inconsistent (no alphabetic characters)",
            }
        )

    batch_number = metadata.get("batch_number")
    if batch_number and not re.match(r"^[A-Z0-9\-]{3,30}$", str(batch_number).upper()):
        issues.append(
            {
                "field": "batch_number",
                "code": "INCONSISTENT_VALUE",
                "severity": "error",
                "message": "batch_number has invalid characters or format",
            }
        )

    present_required = sum(1 for field in required_fields if metadata.get(field))
    completeness_score = round((present_required / len(required_fields)) * 100, 2)

    return {
        "issues": issues,
        "completeness_score": completeness_score,
    }
