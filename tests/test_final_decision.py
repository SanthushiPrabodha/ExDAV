import unittest

from src.verdict.final_decision import decide_final_verdict


class TestFinalDecision(unittest.TestCase):
    def test_inconclusive_when_evidence_incomplete(self):
        ocr_result = {"success": True, "text": "partial", "error": None}
        validation_result = {
            "issues": [
                {
                    "field": "expiry_date",
                    "code": "MISSING_REQUIRED_FIELD",
                    "severity": "error",
                    "message": "expiry_date is required but missing",
                }
            ],
            "completeness_score": 66.67,
        }
        reasoning_result = {
            "flags": {
                "suspicious": True,
                "incomplete_evidence": True,
                "metadata_conflict": False,
                "likely_authentic": False,
            },
            "reasons": ["Missing required evidence fields: expiryDate"],
            "engine": "rule_based_v1",
        }

        result = decide_final_verdict(ocr_result, validation_result, reasoning_result)
        self.assertEqual(result["final_verdict"], "Inconclusive")
        self.assertEqual(result["confidence_level"], "Low")
        self.assertIsInstance(result["explanation"], list)

    def test_likely_authentic_requires_complete_consistent_evidence(self):
        ocr_result = {"success": True, "text": "good", "error": None}
        validation_result = {"issues": [], "completeness_score": 100.0}
        reasoning_result = {
            "flags": {
                "suspicious": False,
                "incomplete_evidence": False,
                "metadata_conflict": False,
                "likely_authentic": True,
            },
            "reasons": [],
            "engine": "rule_based_v1",
        }

        result = decide_final_verdict(ocr_result, validation_result, reasoning_result)
        self.assertEqual(result["final_verdict"], "Authentic")
        self.assertEqual(result["confidence_level"], "High")

    def test_ocr_failure_forces_inconclusive(self):
        ocr_result = {"success": False, "text": "", "error": "Image not found"}
        validation_result = {"issues": [], "completeness_score": 100.0}
        reasoning_result = {
            "flags": {
                "suspicious": False,
                "incomplete_evidence": False,
                "metadata_conflict": False,
                "likely_authentic": True,
            },
            "reasons": [],
            "engine": "rule_based_v1",
        }

        result = decide_final_verdict(ocr_result, validation_result, reasoning_result)
        self.assertEqual(result["final_verdict"], "Inconclusive")
        self.assertEqual(result["confidence_level"], "Low")


if __name__ == "__main__":
    unittest.main()
