import time
import os
import sys

# Windows terminal: ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from selenium.webdriver.common.by import By
import config
from login import launch_browser, login
from dashboard import select_student, click_start_learning
from index_builder import IndexBuilder

def main():
    driver = launch_browser()
    try:
        login(driver)
        print("Logged in successfully.")
        select_student(driver)
        print("Selected student Thomas D.")
        click_start_learning(driver)
        print("Start learning clicked.")
        time.sleep(5)
        
        # Capture dashboard screenshot
        os.makedirs("screenshots", exist_ok=True)
        driver.save_screenshot("screenshots/dashboard.png")
        print("Captured screenshots/dashboard.png")
        
        # List topics
        builder = IndexBuilder(driver)
        topics = builder.get_all_topics()
        print(f"Discovered {len(topics)} topics:")
        for t in topics:
            print(f" - {t.name}")
            
    except Exception as e:
        print("Error during inspection:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
