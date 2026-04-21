import unittest
from unittest.mock import patch

from src.pipeline.run_interim_pipeline import run_interim_pipeline


class TestRunInterimPipeline(unittest.TestCase):
    @patch("src.pipeline.run_interim_pipeline.extract_text")
    def test_pipeline_returns_structured_output(self, mock_extract_text):
        mock_extract_text.return_value = {
            "success": True,
            "text": (
                "DRUG NAME: ZYRTEC ORAL DROPS "
                "BATCH: AB-1234 EXP DATE: 11/2027 MFG BY: UCB PHARMA LTD"
            ),
            "error": None,
            "image_path": "dummy.jpg",
        }

        result = run_interim_pipeline("dummy.jpg")

        self.assertIn("ocr", result)
        self.assertIn("metadata", result)
        self.assertIn("validation", result)
        self.assertIn("ontology_ready", result)
        self.assertIn("reasoning", result)
        self.assertIn("final_verdict", result)
        self.assertIn("trust_level", result)
        self.assertIn("explanation", result)
        self.assertEqual(result["final_verdict"], "Authentic")
        self.assertEqual(result["trust_level"], "High")


if __name__ == "__main__":
    unittest.main()
