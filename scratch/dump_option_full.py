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
from utils import get_element_html, scroll_into_view, safe_click

def main():
    config.HEADLESS = True
    driver = launch_browser()
    try:
        login(driver)
        select_student(driver)
        click_start_learning(driver)
        time.sleep(5)
        
        finder = TopicWorksheetFinder(driver)
        topic_el = finder._find_topic_element("Complex Numbers")
        if topic_el:
            scroll_into_view(driver, topic_el)
            safe_click(driver, topic_el)
            time.sleep(4)
            topic_container = driver.find_element(By.TAG_NAME, "body")
            cards = finder._collect_cards(topic_container)
            for card in cards:
                card_id, _ = finder.extract_worksheet_id_and_title(card)
                if card_id == "AQCMXAL214":
                    finder._click_start(card, "Complex Numbers", "Graphing complex numbers")
                    break
            time.sleep(5)
            
            # Print the entire HTML of option 0
            options = driver.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option")
            if options:
                print("OPTION 0 HTML:")
                print(get_element_html(driver, options[0]))
                
                # Check for child elements of option 0
                children = options[0].find_elements(By.XPATH, ".//*")
                print(f"\nChildren of option 0 ({len(children)}):")
                for idx, c in enumerate(children):
                    print(f"  Child {idx}: tag={c.tag_name} | class={c.get_attribute('class')} | text='{c.text.strip()}'")

    except Exception as e:
        print("Error:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
