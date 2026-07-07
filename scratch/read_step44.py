import json
import re

transcript_path = r"C:\Users\ELCOT\.gemini\antigravity-ide\brain\23dd03a0-e322-4c43-ab88-a890e0107e26\.system_generated\logs\transcript_full.jsonl"

with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("step_index") == 26 or data.get("type") == "BROWSER_SUBAGENT":
                content = data.get("content", "")
                
                # Let's find "Step 44: browser_get_dom" and its Status or results
                step_pos = content.find("### Step 44: browser_get_dom")
                if step_pos != -1:
                    print("Found Step 44 at position:", step_pos)
                    # Print the next 2000 chars of step 44 to see what it returned or did
                    snippet = content[step_pos:step_pos+3000]
                    print(snippet)
        except Exception as e:
            print("Error parsing line:", e)
