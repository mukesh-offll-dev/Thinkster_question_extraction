import subprocess
import json
import sys
import os

def kill_zombie_chromes():
    print("Searching for Chrome processes using our workspace profile...")
    
    # Run Get-CimInstance via PowerShell to retrieve JSON details of all chrome.exe processes
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-CimInstance -ClassName Win32_Process -Filter \"Name = 'chrome.exe'\" | Select-Object ProcessId, CommandLine | ConvertTo-Json"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout.strip()
        if not output:
            print("No chrome.exe processes found.")
            return
            
        # Parse output. If there is only one process, it might not be a JSON array, so handle both.
        try:
            data = json.loads(output)
        except Exception as e:
            print("Failed to parse JSON. Raw output:")
            print(output)
            return

        if isinstance(data, dict):
            processes = [data]
        elif isinstance(data, list):
            processes = data
        else:
            processes = []

        killed_count = 0
        for p in processes:
            pid = p.get("ProcessId")
            cmdline = p.get("CommandLine") or ""
            
            # Check if this process uses our chrome_profile directory
            if "chrome_profile" in cmdline:
                print(f"Found zombie Chrome process {pid} using chrome_profile. Terminating...")
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                    killed_count += 1
                except Exception as ex:
                    print(f"Failed to kill process {pid}: {ex}")
        
        print(f"Cleaned up {killed_count} zombie Chrome processes.")
    except Exception as e:
        print("Error during cleanup:", e)

if __name__ == "__main__":
    kill_zombie_chromes()
