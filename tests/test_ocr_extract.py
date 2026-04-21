import unittest

from src.ocr.ocr_extract import extract_text


class TestOCRExtract(unittest.TestCase):
    def test_extract_text_returns_structured_error_for_missing_file(self):
        result = extract_text("this/path/does/not/exist.jpg")

        self.assertIsInstance(result, dict)
        self.assertIn("success", result)
        self.assertIn("text", result)
        self.assertIn("error", result)
        self.assertFalse(result["success"])
        self.assertEqual(result["text"], "")
        self.assertIsNotNone(result["error"])


if __name__ == "__main__":
    unittest.main()
