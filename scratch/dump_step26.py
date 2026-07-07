import json

transcript_path = r"C:\Users\ELCOT\.gemini\antigravity-ide\brain\23dd03a0-e322-4c43-ab88-a890e0107e26\.system_generated\logs\transcript_full.jsonl"
out_path = r"c:\Users\ELCOT\Documents\Thinkster_question_extraction\scratch\subagent_output.txt"

with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("step_index") == 26 or data.get("type") == "BROWSER_SUBAGENT":
                with open(out_path, "w", encoding="utf-8") as out_f:
                    out_f.write(data.get("content", ""))
                print("Dumped subagent output to", out_path)
                break
        except Exception as e:
            print("Error parsing line:", e)
