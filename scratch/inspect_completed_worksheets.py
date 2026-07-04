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
from utils import scroll_into_view, safe_click, js_click

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
            time.sleep(3.0)
            
            # Find Show All or Completed buttons inside the dashboard
            # Let's search by text
            buttons = driver.find_elements(By.TAG_NAME, "button") + driver.find_elements(By.TAG_NAME, "a") + driver.find_elements(By.TAG_NAME, "span")
            for b in buttons:
                try:
                    if b.is_displayed() and b.text.strip() in ("Show All", "Completed"):
                        print(f"Found filter button: '{b.text.strip()}' - Clicking it...")
                        js_click(driver, b)
                        time.sleep(2.0)
                except Exception:
                    pass
            
            # Now collect cards
            topic_container = driver.find_element(By.TAG_NAME, "body")
            cards = finder._collect_cards(topic_container)
            print(f"Total cards found after filter: {len(cards)}")
            for idx, card in enumerate(cards):
                card_id, title = finder.extract_worksheet_id_and_title(card)
                print(f"Card [{idx}]: ID='{card_id}' | Title='{title}'")
                if card_id == "AQCMXAL214":
                    print("Found AQCMXAL214!")
                    # Check what start/review button exists on it
                    buttons_on_card = card.find_elements(By.CSS_SELECTOR, "button, a")
                    for bdx, b in enumerate(buttons_on_card):
                        if b.is_displayed():
                            print(f"  Button [{bdx}]: Text='{b.text}' | Class='{b.get_attribute('class')}'")
                            
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
