import sys
import os

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from login import launch_browser

if __name__ == "__main__":
    print("Testing browser launch...")
    try:
        driver = launch_browser()
        print("Launch SUCCESS!")
        driver.quit()
    except Exception as e:
        print("Launch FAILED:", e)
        import traceback
        traceback.print_exc()
