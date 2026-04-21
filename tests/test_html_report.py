import unittest

from src.pipeline.html_report import render_html_report


class TestHtmlReport(unittest.TestCase):
    def test_render_html_report_contains_key_sections(self):
        sample = {
            "final_verdict": "Suspicious",
            "confidence_level": "Medium",
            "explanation": ["Extracted fields: drug_name", "Validation failures: none"],
            "extracted_metadata": {"drug_name": "ZYRTEC"},
            "validation_issues": [],
            "semantic_flags": ["suspicious"],
        }
        html = render_html_report(sample)
        self.assertIn("Ex-DAV Showcase Report", html)
        self.assertIn("Suspicious", html)
        self.assertIn("Medium", html)
        self.assertIn("Extracted Metadata", html)


if __name__ == "__main__":
    unittest.main()
