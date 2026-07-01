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
from answering import wait_for_loading, click_question_dot, wait_for_active_question

def main():
    config.HEADLESS = True
    driver = launch_browser()
    try:
        login(driver)
        select_student(driver)
        click_start_learning(driver)
        time.sleep(5)
        
        finder = TopicWorksheetFinder(driver)
        topic_el = finder._find_topic_element("Conic Sections")
        if topic_el:
            scroll_into_view(driver, topic_el)
            safe_click(driver, topic_el)
            time.sleep(4)
            topic_container = driver.find_element(By.TAG_NAME, "body")
            cards = finder._collect_cards(topic_container)
            for card in cards:
                card_id, _ = finder.extract_worksheet_id_and_title(card)
                if card_id == "AQCONAL202":
                    finder._click_start(card, "Conic Sections", "Circles - Worksheet 2")
                    break
            
            if not wait_for_loading(driver):
                return
            time.sleep(3)
            
            # Go to Q5
            click_question_dot(driver, 5)
            wait_for_active_question(driver, 5)
            time.sleep(3.0)
            
            # Find editable math fields
            math_fields = driver.find_elements(By.CSS_SELECTOR, ".lrn-formula-input, .mq-editable-field, .mq-root-block")
            visible_fields = [f for f in math_fields if f.is_displayed()]
            print(f"Found {len(visible_fields)} visible math fields.")
            
            if visible_fields:
                target_field = visible_fields[0]
                print(f"Clicking math field to focus: {get_element_html(driver, target_field)[:200]}")
                driver.execute_script("arguments[0].click();", target_field)
                time.sleep(2.0)
                
                # Check for keypad buttons
                buttons = driver.find_elements(By.TAG_NAME, "button")
                visible_buttons = [b for b in buttons if b.is_displayed()]
                print(f"Total visible buttons on page: {len(visible_buttons)}")
                
                # Try clicking "4"
                clicked = False
                for btn in visible_buttons:
                    text = btn.text.strip().lower()
                    if text == "4":
                        print(f"Found button '4'. Clicking via JS...")
                        driver.execute_script("arguments[0].click();", btn)
                        clicked = True
                        break
                        
                if not clicked:
                    print("Could not find button for '4'")
                
                time.sleep(2.0)
                
                # Take screenshot to verify input
                os.makedirs("screenshots", exist_ok=True)
                screenshot_path = "screenshots/q5_keypad_input_test.png"
                driver.save_screenshot(screenshot_path)
                print(f"Saved screenshot to {screenshot_path}")

    except Exception as e:
        print("Error:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
