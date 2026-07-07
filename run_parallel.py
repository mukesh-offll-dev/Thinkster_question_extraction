import csv
import os
import sys
import time
import subprocess
import threading
from dotenv import load_dotenv

# Ensure UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

csv_path = r"csv/algebra2-worksheets-report.csv"
student_url = "https://tutor4.0.hellothinkster.com/students/626b0368-19b9-4c31-843d-7113872324b9"
subject = "Algebra 2"
email = "intern@hellothinkster.com"
password = "Password"

print(f"Reading worksheets from: {csv_path}")

target_courses = {"Math: Conic Sections", "Math: Complex Numbers"}
unique_ids = []
seen = set()

with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        course = row.get("course", "").strip()
        if course in target_courses:
            ws_num = row.get("thinkster_worksheet_number", "").strip()
            if ws_num and ws_num not in seen:
                seen.add(ws_num)
                unique_ids.append(ws_num)

total_count = len(unique_ids)
print(f"Found {total_count} unique worksheets for courses: {', '.join(target_courses)}")

if total_count == 0:
    print("No worksheets found. Exiting.")
    sys.exit(0)

# Split IDs list into 3 parts
num_instances = 3
chunk_size = (total_count + num_instances - 1) // num_instances
chunks = [unique_ids[i:i + chunk_size] for i in range(0, total_count, chunk_size)]

# Ensure we have exactly num_instances chunks
while len(chunks) < num_instances:
    chunks.append([])

print(f"\nDividing worksheets into {num_instances} chunks:")
for i, chunk in enumerate(chunks, 1):
    print(f"  Instance {i}: {len(chunk)} worksheets (e.g. {', '.join(chunk[:3])}...)")

os.makedirs("logs", exist_ok=True)

# Spawning helper
def log_stream(stream, prefix, log_filename):
    with open(log_filename, "w", encoding="utf-8") as lf:
        for line in iter(stream.readline, ""):
            if not line:
                break
            clean_line = line.strip()
            # Print prefixed to main console
            print(f"{prefix}: {clean_line}")
            # Write to file
            lf.write(line)

processes = []
threads = []

print("\nStarting parallel worksheet addition...")
for idx in range(num_instances):
    instance_num = idx + 1
    chunk_ids = chunks[idx]
    
    if not chunk_ids:
        print(f"Instance {instance_num} has no worksheets to process. Skipping.")
        continue
        
    cmd = [
        sys.executable,
        "-u",
        "add_worksheets.py",
        "--student-url", student_url,
        "--subject", subject,
        "--worksheet-ids", ",".join(chunk_ids),
        "--profile-suffix", str(instance_num),
        "--email", email,
        "--password", password
    ]
    
    log_file = f"logs/parallel_run_{instance_num}.log"
    print(f"Spawning Instance {instance_num} (Worksheets: {len(chunk_ids)})... Logs saved to {log_file}")
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # Line buffered
        encoding="utf-8",
        errors="replace"
    )
    processes.append(proc)
    
    # Start logging thread
    prefix = f"[Instance {instance_num}]"
    t = threading.Thread(target=log_stream, args=(proc.stdout, prefix, log_file))
    t.daemon = True
    t.start()
    threads.append(t)
    
    # Stagger startups by 15 seconds to prevent concurrent login/CDP locks
    if idx < num_instances - 1:
        print("Staggering startup: sleeping 15 seconds before launching next instance...")
        time.sleep(15)

print("\nAll instances spawned. Monitoring execution...\n")

# Wait for all processes to complete
for idx, proc in enumerate(processes, 1):
    exit_code = proc.wait()
    print(f"Instance {idx} exited with code {exit_code}.")

# Wait for all logging threads to complete reading
for t in threads:
    t.join()

print("\n============================================================")
print("             PARALLEL RUN COMPLETED SUCCESSFULY")
print("============================================================")
