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
from utils import scroll_into_view, safe_click

def main():
    config.HEADLESS = True
    driver = launch_browser()
    try:
        login(driver)
        select_student(driver)
        click_start_learning(driver)
        time.sleep(5)
        
        # We find all sidebar/accordion buttons for topics
        # First, find the container or elements
        # Usually they are button elements or links
        buttons = driver.find_elements(By.CSS_SELECTOR, "button, [role='button'], [class*='topic'], [class*='accordion']")
        print(f"Total candidate elements: {len(buttons)}")
        
        finder = TopicWorksheetFinder(driver)
        
        # Let's inspect the page body text to see what topics are visible
        body_text = driver.find_element(By.TAG_NAME, "body").text
        print("\n--- BODY TEXT PREVIEW ---")
        print(body_text[:1000])
        print("-------------------------\n")
        
        # We can find all elements with class containing 'item', 'card', 'topic', 'group'
        elements = driver.find_elements(By.XPATH, "//*[contains(@class, 'topic') or contains(@class, 'accordion') or contains(@class, 'skill')]")
        print(f"Elements with class containing topic/accordion/skill: {len(elements)}")
        for idx, el in enumerate(elements[:20]):
            try:
                if el.is_displayed():
                    text = el.text.strip().split('\n')[0]
                    print(f"Element [{idx}]: Tag={el.tag_name} | Class='{el.get_attribute('class')}' | Text='{text}'")
            except Exception:
                pass
                
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
