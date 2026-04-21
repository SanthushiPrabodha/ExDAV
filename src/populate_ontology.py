import os
import re
import pandas as pd
from owlready2 import get_ontology
from mapping.ontology_mapper import map_validated_metadata_to_ontology

# ===============================
# PATH SETUP (WINDOWS SAFE)
# ===============================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ONTO_PATH = os.path.join(BASE_DIR, "ontology", "exdav.rdf")
CSV_PATH = os.path.join(BASE_DIR, "dataset", "metadata", "drug_list.csv")
OUT_PATH = os.path.join(BASE_DIR, "ontology", "exdav_populated.rdf")


# ===============================
# UTILITY: SAFE INDIVIDUAL NAME
# ===============================
def safe_name(text: str) -> str:
    text = str(text).strip()
    text = re.sub(r"[^\w]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = "Unnamed"
    if text[0].isdigit():
        text = f"D_{text}"
    return text


# ===============================
# MAIN FUNCTION
# ===============================
def main():
    print("🔹 Loading ontology...")
    onto = get_ontology(ONTO_PATH)
    onto.load()
    print("✔ Ontology loaded successfully")

    Drug = onto.search_one(iri="*Drug")
    if Drug is None:
        raise ValueError("Class 'Drug' not found in ontology.")

    df = pd.read_csv(CSV_PATH, encoding="utf-8")
    print(f"✔ CSV loaded: {len(df)} records")

    created = 0
    updated = 0

    with onto:
        for _, row in df.iterrows():
            # Individual name from drug_id
            ind_name = safe_name(row["drug_id"])
            d = onto.search_one(iri=f"*{ind_name}")

            if d is None:
                d = Drug(ind_name)
                created += 1
            else:
                updated += 1

            # -----------------------
            # DATA PROPERTIES
            # -----------------------
            mapped = map_validated_metadata_to_ontology(row.to_dict())
            props = mapped["properties"]

            if hasattr(onto, "drugName") and props["drugName"] is not None:
                d.drugName = [props["drugName"]]

            if hasattr(onto, "dosageForm") and props["dosageForm"] is not None:
                d.dosageForm = [props["dosageForm"]]

            if hasattr(onto, "strength") and props["strength"] is not None:
                d.strength = [props["strength"]]

            if hasattr(onto, "packageSize") and props["packageSize"] is not None:
                d.packageSize = [props["packageSize"]]

    onto.save(file=OUT_PATH, format="rdfxml")

    print("✅ Ontology population completed")
    print(f"   Created: {created}")
    print(f"   Updated: {updated}")
    print(f"   Saved to: {OUT_PATH}")


if __name__ == "__main__":
    main()
