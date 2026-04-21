import unittest

from src.mapping.ontology_mapper import map_validated_metadata_to_ontology


class TestOntologyMapper(unittest.TestCase):
    def test_maps_values_and_preserves_units(self):
        metadata = {
            "drug_name": "Zyrtec",
            "dosage_form": "Oral Drops",
            "strength": "10mg",
            "package_size": "30g",
            "batch_number": "AB-1234",
            "expiry_date": "11/2027",
            "manufacturer": "UCB PHARMA LTD",
        }

        result = map_validated_metadata_to_ontology(metadata)
        props = result["properties"]

        self.assertEqual(props["drugName"], "Zyrtec")
        self.assertEqual(props["dosageForm"], "Oral Drops")
        self.assertEqual(props["strength"], "10mg")
        self.assertEqual(props["packageSize"], "30g")
        self.assertEqual(props["batchNumber"], "AB-1234")
        self.assertEqual(props["expiryDate"], "11/2027")
        self.assertEqual(props["manufacturer"], "UCB PHARMA LTD")
        self.assertEqual(result["missing_fields"], [])
        self.assertEqual(result["warnings"], [])

    def test_normalizes_empty_like_values_and_warns(self):
        metadata = {
            "drug_name": "  ",
            "dosage_form": None,
            "strength": "nan",
            "package_size": "125ml",
            "batch_number": "",
            "expiry_date": None,
            "manufacturer": "MFG LAB",
        }

        result = map_validated_metadata_to_ontology(metadata)
        props = result["properties"]

        self.assertIsNone(props["drugName"])
        self.assertIsNone(props["dosageForm"])
        self.assertIsNone(props["strength"])
        self.assertEqual(props["packageSize"], "125ml")
        self.assertIsNone(props["batchNumber"])
        self.assertIsNone(props["expiryDate"])
        self.assertEqual(props["manufacturer"], "MFG LAB")

        self.assertGreater(len(result["missing_fields"]), 0)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("missing", result["warnings"][0].lower())


if __name__ == "__main__":
    unittest.main()
