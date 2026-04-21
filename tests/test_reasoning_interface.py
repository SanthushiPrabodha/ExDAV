import unittest

from src.reasoning.reasoning_interface import reason_over_ontology_ready_input


class TestReasoningInterface(unittest.TestCase):
    def test_likely_authentic_when_required_evidence_is_present(self):
        payload = {
            "properties": {
                "drugName": "ZYRTEC",
                "batchNumber": "AB-1234",
                "expiryDate": "11/2027",
                "manufacturer": "UCB",
            },
            "missing_fields": [],
            "warnings": [],
        }
        result = reason_over_ontology_ready_input(payload)

        self.assertFalse(result["flags"]["suspicious"])
        self.assertFalse(result["flags"]["incomplete_evidence"])
        self.assertFalse(result["flags"]["metadata_conflict"])
        self.assertTrue(result["flags"]["likely_authentic"])

    def test_incomplete_evidence_flag_when_required_fields_missing(self):
        payload = {
            "properties": {
                "drugName": "ZYRTEC",
                "batchNumber": None,
                "expiryDate": None,
            },
            "missing_fields": ["batchNumber", "expiryDate"],
            "warnings": ["missing"],
        }
        result = reason_over_ontology_ready_input(payload)

        self.assertTrue(result["flags"]["incomplete_evidence"])
        self.assertTrue(result["flags"]["suspicious"])
        self.assertFalse(result["flags"]["likely_authentic"])

    def test_metadata_conflict_flag_for_expired_metadata(self):
        payload = {
            "properties": {
                "drugName": "ZYRTEC",
                "batchNumber": "AB-1234",
                "expiryDate": "01/2020",
            },
            "missing_fields": [],
            "warnings": [],
        }
        result = reason_over_ontology_ready_input(payload)

        self.assertTrue(result["flags"]["metadata_conflict"])
        self.assertTrue(result["flags"]["suspicious"])
        self.assertFalse(result["flags"]["likely_authentic"])


if __name__ == "__main__":
    unittest.main()
