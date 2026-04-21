import pandas as pd

INPUT_PATH = "dataset/metadata/drug list.xlsx"
OUTPUT_PATH = "dataset/metadata/drug_list.csv"

df = pd.read_excel(INPUT_PATH)

# Clean column names
df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

# Add drug_id if not exists
if "drug_id" not in df.columns:
    df.insert(0, "drug_id", [f"D{str(i+1).zfill(3)}" for i in range(len(df))])

df.to_csv(OUTPUT_PATH, index=False)
print("drug_list.csv created successfully")
