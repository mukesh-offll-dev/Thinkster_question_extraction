import csv
import os

csv_path = r"csv/algebra2-worksheets-report.csv"
output_path = r"worksheet_ids.txt"

print(f"Reading CSV from: {csv_path}")

unique_ids = []
seen = set()

with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        ws_num = row.get("thinkster_worksheet_number", "").strip()
        if ws_num and ws_num not in seen:
            seen.add(ws_num)
            unique_ids.append(ws_num)
            if len(unique_ids) == 50:
                break

print(f"Extracted {len(unique_ids)} unique non-empty worksheet IDs:")
for i, uid in enumerate(unique_ids, 1):
    print(f"  {i}. {uid}")

with open(output_path, "w", encoding="utf-8") as out:
    for uid in unique_ids:
        out.write(uid + "\n")

print(f"\nSaved IDs to: {os.path.abspath(output_path)}")
