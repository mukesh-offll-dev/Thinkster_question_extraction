import json

transcript_path = r"C:\Users\ELCOT\.gemini\antigravity-ide\brain\23dd03a0-e322-4c43-ab88-a890e0107e26\.system_generated\logs\transcript_full.jsonl"

with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("step_index") == 26 or data.get("type") == "BROWSER_SUBAGENT":
                content = data.get("content", "")
                
                step_pos = content.find("### Step 80: capture_browser_screenshot")
                if step_pos != -1:
                    print("Found Step 80 at position:", step_pos)
                    # Print the next 4000 to 10000 chars of step 80
                    snippet = content[step_pos+4000:step_pos+10000]
                    print(snippet)
        except Exception as e:
            print("Error parsing line:", e)
