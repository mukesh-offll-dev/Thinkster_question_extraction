import time
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium.webdriver.common.by import By
import config
from login import launch_browser, login
from dashboard import select_student, click_start_learning
from topic_worksheet_finder import TopicWorksheetFinder

def main():
    config.HEADLESS = True
    driver = launch_browser()
    try:
        login(driver)
        select_student(driver)
        click_start_learning(driver)
        time.sleep(5)
        
        finder = TopicWorksheetFinder(driver)
        # Find all elements that look like topics
        print("\n--- Scanning for Topic Elements ---")
        # In Thinkster Elevate, topics are in elements with classes like .lrn-topic, or text in accordion headers
        # Let's search for headings or buttons containing topic names
        elements = driver.find_elements(By.CSS_SELECTOR, "h1, h2, h3, h4, h5, button, span, a")
        topics = set()
        for el in elements:
            try:
                if el.is_displayed():
                    text = el.text.strip()
                    if text and len(text) > 3 and len(text) < 50:
                        topics.add(text)
            except Exception:
                pass
                
        print(f"Found {len(topics)} text elements:")
        for t in sorted(list(topics)):
            print(f" - {t}")
            
    except Exception as e:
        print("Error:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
