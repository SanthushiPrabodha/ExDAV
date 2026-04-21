import unittest
from unittest.mock import patch

from src.pipeline.run_pipeline import run_pipeline


class TestRunPipelineOutputContract(unittest.TestCase):
    @patch("src.pipeline.run_pipeline.extract_text")
    def test_returns_required_json_schema(self, mock_extract_text):
        mock_extract_text.return_value = {
            "success": True,
            "text": "DRUG NAME: ZYRTEC BATCH: AB-1234 EXP DATE: 11/2027 MFG BY: UCB",
            "error": None,
            "image_path": "dummy.jpg",
        }

        result = run_pipeline("dummy.jpg")

        self.assertIn("final_verdict", result)
        self.assertIn("confidence_level", result)
        self.assertIn("explanation", result)
        self.assertIn("extracted_metadata", result)
        self.assertIn("validation_issues", result)
        self.assertIn("semantic_flags", result)
        self.assertIn(result["final_verdict"], ["Authentic", "Counterfeit", "Suspicious", "Inconclusive"])
        self.assertIn(result["confidence_level"], ["High", "Medium", "Low"])
        self.assertIsInstance(result["explanation"], list)
        self.assertIsInstance(result["validation_issues"], list)
        self.assertIsInstance(result["semantic_flags"], list)

    @patch("src.pipeline.run_pipeline.extract_text")
    def test_incomplete_evidence_prefers_inconclusive(self, mock_extract_text):
        mock_extract_text.return_value = {
            "success": True,
            "text": "RANDOM NOISY TEXT",
            "error": None,
            "image_path": "dummy.jpg",
        }

        result = run_pipeline("dummy.jpg")
        self.assertEqual(result["final_verdict"], "Inconclusive")
        self.assertEqual(result["confidence_level"], "Low")


if __name__ == "__main__":
    unittest.main()
