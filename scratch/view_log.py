import sys

# Ensure UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

log_path = r"C:\Users\ELCOT\.gemini\antigravity-ide\brain\23dd03a0-e322-4c43-ab88-a890e0107e26\.system_generated\tasks\task-388.log"

with open(log_path, "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

print("--- Instance 1 Exit Status Check ---")
for idx, line in enumerate(lines):
    if "Instance 1" in line and ("exit" in line.lower() or "summary" in line.lower() or "completed" in line.lower()):
        print(f"Line {idx}: {line.strip()}")
    elif "exited with code" in line:
        print(f"Line {idx}: {line.strip()}")
