import json
import re

transcript_path = r"C:\Users\ELCOT\.gemini\antigravity-ide\brain\23dd03a0-e322-4c43-ab88-a890e0107e26\.system_generated\logs\transcript_full.jsonl"

with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        if "Current Assessment" in line or "Current Assignment" in line or "Manage worksheet" in line:
            print("Found match in line!")
            # Print the context of match
            matches = re.findall(r"(.{0,150}(?:Current Assessment|Current Assignment|Manage worksheet).{0,150})", line, re.IGNORECASE)
            for m in matches[:10]:
                print("Match:", m.strip())
            print("-" * 50)
