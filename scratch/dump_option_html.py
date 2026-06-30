import time
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium.webdriver.common.by import By
import config
from login import launch_browser, login
from dashboard import select_student, click_start_learning
from topic_worksheet_finder import find_worksheet_in_topic
from utils import scroll_into_view, safe_click, get_element_html

def main():
    config.HEADLESS = True
    driver = launch_browser()
    try:
        login(driver)
        select_student(driver)
        click_start_learning(driver)
        time.sleep(3)
        find_worksheet_in_topic(driver, "Complex Numbers", "AQCMXAL209")
        
        # Wait for loading screen to disappear
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text
                if "Loading worksheet..." not in body_text and "Loading" not in body_text:
                    break
            except Exception:
                pass
            time.sleep(1)
        time.sleep(3)

        # Print options of Question 1
        print("Question 1 Options HTML:")
        options = driver.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option")
        for idx, opt in enumerate(options):
            print(f"Option {idx}:")
            print(get_element_html(driver, opt))
            print("-" * 50)
            
    except Exception as e:
        print("Error:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
