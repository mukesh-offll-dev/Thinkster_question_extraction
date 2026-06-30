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
from topic_worksheet_finder import find_worksheet_in_topic
from question_extractor import analyze_worksheet_questions

def main():
    driver = launch_browser()
    try:
        login(driver)
        print("Logged in successfully.")
        select_student(driver)
        print("Selected student Thomas D.")
        click_start_learning(driver)
        print("Start learning clicked.")
        time.sleep(3)
        
        # Search topic and worksheet
        print("Searching worksheet AQCMXAL209 under Complex Numbers...")
        found = find_worksheet_in_topic(driver, "Complex Numbers", "AQCMXAL209")
        if not found:
            print("Failed to locate worksheet AQCMXAL209")
            return
            
        print("Worksheet opened. Running extractor...")
        total = analyze_worksheet_questions(driver, "AQCMXAL209")
        print(f"Extraction and solving completed. Total questions processed: {total}")
        
    except Exception as e:
        print("Error during worksheet run:", e)
    finally:
        print("Closing browser in 5 seconds...")
        time.sleep(5)
        driver.quit()

if __name__ == "__main__":
    main()
