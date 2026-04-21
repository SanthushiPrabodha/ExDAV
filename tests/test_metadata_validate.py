import unittest

from src.ocr.metadata_validate import parse_metadata, validate_metadata


class TestMetadataParsingNoisyOCR(unittest.TestCase):
    def test_noisy_text_extracts_expected_fields(self):
        ocr_text = """
        ### DRUG N@ME: ZYRTEC ORAL DROPS
        BATCH N0: AB-1234
        EXP DATE: 11/2027
        MFG BY: UCB PHARMA LTD
        """

        result = parse_metadata(ocr_text)

        self.assertEqual(result["drug_name"], "ZYRTEC ORAL DROPS")
        self.assertEqual(result["batch_number"], "AB-1234")
        self.assertEqual(result["expiry_date"], "11/2027")
        self.assertEqual(result["manufacturer"], "UCB PHARMA LTD")
        self.assertEqual(result["warnings"], [])

    def test_uncertain_fields_return_null_with_warnings(self):
        ocr_text = """
        RANDOM LABEL TEXT
        PRINTED CODE 88XTT
        SOME DATE 2027 BUT NO EXP TAG
        """

        result = parse_metadata(ocr_text)

        self.assertIsNone(result["drug_name"])
        self.assertIsNone(result["batch_number"])
        self.assertIsNone(result["expiry_date"])
        self.assertIsNone(result["manufacturer"])
        self.assertGreaterEqual(len(result["warnings"]), 4)


class TestDotMatrixLabelPatterns(unittest.TestCase):
    """Batch / MFG / EXP as on dot-matrix printed panels (e.g. BATCH : 84-0775)."""

    def test_batch_mfg_exp_month_names(self):
        ocr_text = """
        BATCH : 84-0775
        MFG : APR 2024
        EXP : MAR 2027
        """
        result = parse_metadata(ocr_text)
        self.assertEqual(result["batch_number"], "84-0775")
        self.assertEqual(result["expiry_date"], "03-2027")
        self.assertEqual(result["manufactured_date"], "04/2024")

    def test_ocr_8_for_b_in_batch(self):
        from src.ocr.metadata_validate import _extract_batch_number, normalize_text

        norm = normalize_text("8ATCH : 84-0775")
        self.assertEqual(_extract_batch_number(norm), "84-0775")

    def test_far_ig_spr_dot_matrix_exp_line(self):
        """EXP line sometimes OCRs as 'FAR IG SPR' on dotted fonts."""
        ocr = "MFG : APR 2024 BACH BETES: FAR ig SPR 2027"
        result = parse_metadata(ocr)
        self.assertEqual(result["expiry_date"], "03-2027")


class TestMetadataValidation(unittest.TestCase):
    def test_invalid_expiry_format_is_flagged(self):
        metadata = {
            "drug_name": "ZYRTEC ORAL DROPS",
            "batch_number": "AB-1234",
            "expiry_date": "2027/11",
        }
        result = validate_metadata(metadata)
        codes = [issue["code"] for issue in result["issues"]]

        self.assertIn("INVALID_EXPIRY_FORMAT", codes)
        self.assertEqual(result["completeness_score"], 100.0)

    def test_expired_date_is_flagged(self):
        metadata = {
            "drug_name": "ZYRTEC ORAL DROPS",
            "batch_number": "AB-1234",
            "expiry_date": "01/2020",
        }
        result = validate_metadata(metadata)
        codes = [issue["code"] for issue in result["issues"]]

        self.assertIn("EXPIRED_PRODUCT", codes)

    def test_missing_required_fields_and_completeness_score(self):
        metadata = {
            "drug_name": None,
            "batch_number": "AB-1234",
            "expiry_date": None,
        }
        result = validate_metadata(metadata)
        missing_issues = [
            issue
            for issue in result["issues"]
            if issue["code"] == "MISSING_REQUIRED_FIELD"
        ]

        self.assertEqual(len(missing_issues), 2)
        self.assertEqual(result["completeness_score"], 33.33)


if __name__ == "__main__":
    unittest.main()
