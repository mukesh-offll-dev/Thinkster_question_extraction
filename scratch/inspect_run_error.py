import sys

# Ensure UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

log_path = r"C:\Users\ELCOT\.gemini\antigravity-ide\brain\23dd03a0-e322-4c43-ab88-a890e0107e26\.system_generated\tasks\task-228.log"

with open(log_path, "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

# Find the LAST match of AQTRGRAL202 (not the one in the header listing all IDs)
for idx in range(len(lines) - 1, -1, -1):
    line = lines[idx]
    if "AQTRGRAL202" in line and "Processing" not in line and "Searching" in line:
        print(f"--- Line {idx} ---")
        start = max(0, idx - 10)
        end = min(len(lines), idx + 40)
        for j in range(start, end):
            print(f"{j}: {lines[j].strip()}")
        break
