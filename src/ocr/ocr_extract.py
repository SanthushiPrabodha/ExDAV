import os
import shutil
import re

import cv2
import pytesseract


# -------------------------------
# TESSERACT PATH FIX
# -------------------------------
def _resolve_tesseract_cmd():
    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd:
        return env_cmd

    discovered = shutil.which("tesseract")
    if discovered:
        return discovered

    return r"C:\Program Files\Tesseract-OCR\tesseract.exe"


pytesseract.pytesseract.tesseract_cmd = _resolve_tesseract_cmd()


def _apply_brand_post_fix(t: str) -> str:
    """
    Fix common brand OCR misreads before metadata parsing (e.g. Belcovic→BecLovent path).
    Uses backend helper when the API package is importable; otherwise no-op.
    """
    if not t or not str(t).strip():
        return t
    try:
        from backend.services.ocr_brand_fix import fix_text_beclovent_family

        return fix_text_beclovent_family(t)
    except Exception:
        return t


def _dot_matrix_supplement_ocr(gray_roi) -> str:
    """
    Second-pass OCR for small dot-matrix printed lines (batch / MFG / EXP).

    The main full-frame threshold paths often produce unusable noise on
    dotted fonts; a tight bottom crop + superscale recovers lines like
    "MFG : APR 2024" and "EXP : MAR 2027" that regex matchers need.
    """
    if gray_roi is None or gray_roi.size == 0:
        return ""

    gh, _gw = gray_roi.shape[:2]
    chunks: list[str] = []
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    config = r"--oem 3 --psm 6 -l eng"

    for y0_frac, y1_frac, scale in (
        (0.22, 0.48, 4.0),  # upper part of batch/MFG/EXP block (batch often above MFG)
        (0.32, 0.52, 4.0),  # band that often contains batch + MFG + EXP together
        (0.35, 1.0, 3.0),   # lower label block
    ):
        y0 = int(gh * y0_frac)
        y1 = int(gh * y1_frac)
        if y1 <= y0 + 10:
            continue
        sub = gray_roi[y0:y1, :]
        sub = cv2.resize(
            sub, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )
        sub = clahe.apply(sub)
        _, bin_img = cv2.threshold(
            sub, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        if cv2.countNonZero(bin_img) / max(bin_img.size, 1) < 0.5:
            bin_img = cv2.bitwise_not(bin_img)
        raw = pytesseract.image_to_string(bin_img, config=config)
        if raw.strip():
            chunks.append(raw.strip())

    # De-duplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for c in chunks:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return "\n".join(out)


# -------------------------------
# OCR FUNCTION
# -------------------------------
def extract_text(image_path):

    result = {
        "success": False,
        "text": "",
        "error": None,
        "image_path": image_path,
    }

    if not image_path:
        result["error"] = "Empty image path provided"
        return result

    if not os.path.exists(image_path):
        result["error"] = f"Image not found: {image_path}"
        return result

    image = cv2.imread(image_path)
    if image is None:
        result["error"] = f"Unable to read image: {image_path}"
        return result

    try:
        # -----------------------------------------------
        # ROI CROP – focus on the main label area
        # Keep a reference to the original for side-strip
        # rotation passes further below.
        # -----------------------------------------------
        orig_h, orig_w = image.shape[:2]
        image_orig = image                           # reference, no copy needed
        h, w = image.shape[:2]
        roi = image[int(h * 0.15):int(h * 0.85), int(w * 0.05):int(w * 0.95)]
        image = roi

        # -----------------------------------------------
        # GRAYSCALE + RESIZE (cubic gives crisper edges)
        # Cap at MAX_DIM on the longer side BEFORE the
        # bilateral filter to keep runtimes reasonable.
        # High-res phone photos (12–40 MP) otherwise cause
        # multi-minute processing times.
        # -----------------------------------------------
        MAX_DIM = 2000
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gh, gw = gray.shape
        natural_scale = 2.0
        # Never scale up beyond the point where the longer
        # side exceeds MAX_DIM; downscale if already large.
        capped_scale = min(natural_scale, MAX_DIM / max(gh, gw, 1))
        gray = cv2.resize(gray, None, fx=capped_scale, fy=capped_scale,
                          interpolation=cv2.INTER_CUBIC)

        # -----------------------------------------------
        # CONTRAST ENHANCEMENT  (CLAHE)
        # Save output before bilateral so Path C can use it.
        # -----------------------------------------------
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_clahe = clahe.apply(gray)

        # -----------------------------------------------
        # EDGE-PRESERVING DENOISING (bilateral filter)
        # -----------------------------------------------
        gray = cv2.bilateralFilter(gray_clahe, 9, 75, 75)

        # Morphological opening kernel (shared across all paths)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))

        # -----------------------------------------------
        # THREE THRESHOLD PATHS – pick the richest result
        #
        # Path A: global Otsu       (uniform/clean backgrounds)
        # Path B: adaptive Gaussian (uneven/gradient lighting)
        # Path C: morphological black-hat
        #         Highlights dark text against ANY background
        #         including repetitive wave/gradient patterns
        #         (e.g. Cetricon blue-wave box, Polybion foil).
        #         black-hat = closing(img, K) − img
        #         With a kernel >> text stroke width, closing
        #         returns a smooth "background estimate"; the
        #         difference isolates dark foreground blobs.
        # -----------------------------------------------
        _, gray_otsu = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        gray_adaptive = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31, 2,
        )

        # Path C: black-hat applied on CLAHE output (pre-bilateral),
        # because bilateral can soften the text-background contrast
        # that black-hat depends on.
        bh_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (45, 45))
        gray_bh_raw = cv2.morphologyEx(gray_clahe, cv2.MORPH_BLACKHAT, bh_kernel)
        gray_bh_raw = cv2.normalize(gray_bh_raw, None, 0, 255, cv2.NORM_MINMAX)
        _, gray_blackhat = cv2.threshold(
            gray_bh_raw, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        gray_otsu    = cv2.morphologyEx(gray_otsu,    cv2.MORPH_OPEN, kernel)
        gray_adaptive = cv2.morphologyEx(gray_adaptive, cv2.MORPH_OPEN, kernel)
        gray_blackhat = cv2.morphologyEx(gray_blackhat, cv2.MORPH_OPEN, kernel)

        # -----------------------------------------------
        # OCR – PSM 6 (single uniform block) tends to
        # extract label text more completely than PSM 4
        # -----------------------------------------------
        config = r"--oem 3 --psm 6 -l eng"
        text_a = pytesseract.image_to_string(gray_otsu,    config=config)
        text_b = pytesseract.image_to_string(gray_adaptive, config=config)
        text_c = pytesseract.image_to_string(gray_blackhat, config=config)

        # Choose the path that produced the most text content
        candidates = [
            (text_a, gray_otsu),
            (text_b, gray_adaptive),
            (text_c, gray_blackhat),
        ]
        text, best_gray = max(candidates, key=lambda x: len(x[0].strip()))

        # -----------------------------------------------
        # TEXT CLEANING
        # Keep . : / - % , which are used in label fields
        # (dates, dosage units, label separators)
        # -----------------------------------------------
        def _clean(raw: str) -> str:
            # Strip non-label characters first so the letter-spacing
            # merge works on a cleaner token stream.
            raw = re.sub(r"[^A-Za-z0-9%\-/\s\.:,&]", " ", raw)

            # ── Merge letter-spaced characters ──────────────────────
            # Pharmaceutical labels often typeset brand names with
            # extra space between each character, e.g.:
            #   "C E T R I C O N"  →  "CETRICON"
            #   "Z E N T A"        →  "ZENTA"
            # Require ≥ 4 consecutive single-alpha tokens to avoid
            # merging genuine two/three-letter abbreviations (IV, BD).
            raw = re.sub(
                r'\b([A-Za-z])(?:\s+([A-Za-z])){3,}\b',
                lambda m: re.sub(r'\s+', '', m.group(0)),
                raw,
            )

            # ── Digit-in-word OCR corrections ────────────────────────
            # Replace common digit/letter confusion only when the digit
            # is flanked by letters, so batch numbers and dates are safe.
            #   0 → O  ("C0RTAL"  → "CORTAL")
            #   1 → I  ("ALPH1NE" → "ALPHINE")
            #   8 → B  ("AL8UMIN" → "ALBUMIN")
            raw = re.sub(r'(?<=[A-Za-z])0(?=[A-Za-z])', 'O', raw)
            raw = re.sub(r'(?<=[A-Za-z])1(?=[A-Za-z])', 'I', raw)
            raw = re.sub(r'(?<=[A-Za-z])8(?=[A-Za-z])', 'B', raw)

            return re.sub(r"\s+", " ", raw).strip()

        text = _clean(text)

        # -----------------------------------------------
        # DOT-MATRIX SUPPLEMENT — recover batch/MFG/EXP lines
        # that the main pass misses on dotted fonts.
        # -----------------------------------------------
        try:
            dm_raw = _dot_matrix_supplement_ocr(gray)
            if dm_raw:
                text = text + "\n" + _clean(dm_raw)
        except Exception:
            pass

        # -----------------------------------------------
        # SIDE-STRIP ROTATION PASSES
        # Brand names are often printed vertically on the
        # left/right side panels of drug packaging (e.g.
        # "Alphintern" on the Alphintern box left panel).
        #
        # Pipeline per strip:
        #   1. Crop the side strip from the original image.
        #   2. Scale it so each character ends up ~35 px tall
        #      after rotation — Tesseract's sweet spot for
        #      word segmentation.  Scaling down also speeds
        #      up the OCR significantly.
        #   3. Apply CLAHE + slight Gaussian blur to enhance
        #      contrast and soften letter-spacing gaps that
        #      cause individual characters to be tokenised
        #      separately.
        #   4. Rotate so vertical text reads left-to-right.
        #   5. Otsu threshold; auto-invert if text is white
        #      on a dark background (common on side panels).
        #   6. Horizontal dilation closes the residual gaps
        #      between letter-spaced characters so Tesseract
        #      groups them as whole words.
        # -----------------------------------------------
        clahe_strip = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))

        for (x0_frac, x1_frac), rotate_code in (
            ((0.0, 0.38), cv2.ROTATE_90_CLOCKWISE),          # left panel
            ((0.62, 1.0), cv2.ROTATE_90_COUNTERCLOCKWISE),   # right panel
        ):
            x0 = int(orig_w * x0_frac)
            x1 = int(orig_w * x1_frac)
            strip = image_orig[int(orig_h * 0.05):int(orig_h * 0.95), x0:x1]
            strip_gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)

            # 2× upscale (same as main OCR) — gives Tesseract crisper
            # edges; avoids the blurring caused by aggressive downscaling.
            strip_gray = cv2.resize(
                strip_gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC
            )

            # Contrast enhancement
            strip_gray = clahe_strip.apply(strip_gray)

            # Gaussian blur — kernel 7×7 softens the ~20–40 px letter-
            # spacing gaps found on large-font brand-name text; this
            # causes adjacent character blobs to touch so Tesseract
            # groups them as one word instead of individual tokens.
            strip_gray = cv2.GaussianBlur(strip_gray, (7, 7), 0)

            # Rotate to make vertical text horizontal
            strip_gray = cv2.rotate(strip_gray, rotate_code)

            # Threshold
            _, strip_bin = cv2.threshold(
                strip_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )

            # Auto-invert: white text on dark background → invert to
            # black-on-white (Tesseract's preferred polarity)
            white_ratio = cv2.countNonZero(strip_bin) / max(strip_bin.size, 1)
            if white_ratio < 0.4:
                strip_bin = cv2.bitwise_not(strip_bin)

            # Extra horizontal dilation (25 px) to bridge residual gaps
            # between letter-spaced characters after blur-threshold.
            h_kern = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
            strip_bin = cv2.dilate(strip_bin, h_kern)

            strip_raw = pytesseract.image_to_string(strip_bin, config=config)
            strip_clean = _clean(strip_raw)
            if strip_clean:
                text = text + "\n" + strip_clean

        # -----------------------------------------------
        # 180° ROTATION FALLBACK
        # When the full package is photographed upside-down
        # (common when holding a phone over a flat box) the
        # main 0° pass produces very few alpha tokens.
        # We detect this by counting 4+-letter alpha words
        # in the cleaned text.  If fewer than 5 are found,
        # we retry with a 180° rotation of the processed ROI
        # and keep whichever pass produced more readable text.
        # Cost: one additional Tesseract call, only triggered
        # when main quality is already very low.
        # -----------------------------------------------
        alpha_count = sum(
            1 for t in text.split() if re.match(r"^[A-Za-z]{4,}$", t)
        )
        if alpha_count < 5:
            rot180 = cv2.rotate(best_gray, cv2.ROTATE_180)
            raw180 = pytesseract.image_to_string(rot180, config=config)
            clean180 = _clean(raw180)
            alpha_count_180 = sum(
                1 for t in clean180.split() if re.match(r"^[A-Za-z]{4,}$", t)
            )
            if alpha_count_180 > alpha_count:
                # 180° is clearly better — use it as the primary text
                text = clean180 + ("\n" + text if text else "")
            elif clean180:
                # marginal gain — append for completeness
                text = text + "\n" + clean180

        # -----------------------------------------------
        # BRAND ROI PASS
        # The product brand name is almost always printed
        # in the central-upper portion of the primary face:
        #   x: 15 – 85 % of original width
        #   y: 20 – 55 % of original height
        # Running a dedicated OCR pass on this tightly
        # cropped region reduces background noise and
        # gives the extraction layer a high-confidence
        # candidate that takes priority over fuzzy matches
        # from the full OCR text.
        # -----------------------------------------------
        try:
            bx0 = int(orig_w * 0.15)
            bx1 = int(orig_w * 0.85)
            by0 = int(orig_h * 0.20)
            by1 = int(orig_h * 0.55)
            brand_crop = image_orig[by0:by1, bx0:bx1]

            if brand_crop.size > 0:
                b_gray = cv2.cvtColor(brand_crop, cv2.COLOR_BGR2GRAY)
                b_scale = min(2.0, 2000 / max(b_gray.shape[0], b_gray.shape[1], 1))
                b_gray = cv2.resize(b_gray, None, fx=b_scale, fy=b_scale,
                                    interpolation=cv2.INTER_CUBIC)
                b_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                b_gray = b_clahe.apply(b_gray)
                b_gray = cv2.bilateralFilter(b_gray, 9, 75, 75)

                # Try all three threshold paths used in the main pass
                _, b_otsu = cv2.threshold(
                    b_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                )
                bh_kern = cv2.getStructuringElement(cv2.MORPH_RECT, (45, 45))
                b_bh_raw = cv2.morphologyEx(b_gray, cv2.MORPH_BLACKHAT, bh_kern)
                b_bh_raw = cv2.normalize(b_bh_raw, None, 0, 255, cv2.NORM_MINMAX)
                _, b_bh = cv2.threshold(
                    b_bh_raw, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
                )

                roi_a = pytesseract.image_to_string(b_otsu, config=config)
                roi_b = pytesseract.image_to_string(b_bh, config=config)
                roi_raw = roi_a if len(roi_a.strip()) >= len(roi_b.strip()) else roi_b
                roi_text = _clean(roi_raw)
            else:
                roi_text = ""
        except Exception:
            roi_text = ""

        # -------------------------------
        result["success"] = True
        result["text"] = _apply_brand_post_fix(text)
        result["roi_text"] = _apply_brand_post_fix(roi_text)
        return result

    except Exception as exc:
        result["error"] = f"OCR failed: {exc}"
        return result