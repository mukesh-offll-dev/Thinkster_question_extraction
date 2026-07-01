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
                    finder._click_start(card, "Circles", "Circles - Worksheet 2")
                    break
            
            if not wait_for_loading(driver):
                return
            time.sleep(3)
            
            # Go to Q5
            click_question_dot(driver, 5)
            wait_for_active_question(driver, 5)
            time.sleep(3.0)
            
            # Inspect inputs
            inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea, [class*='mq-textarea'] textarea")
            print(f"\n--- Question 5 Inputs ({len(inputs)}) ---")
            for idx, inp in enumerate(inputs):
                if inp.is_displayed():
                    print(f"Input [{idx}] Tag={inp.tag_name} | ID='{inp.get_attribute('id')}' | Class='{inp.get_attribute('class')}' | Displayed={inp.is_displayed()}")
                    
            # Click the first visible input to trigger the keypad
            visible_inputs = [i for i in inputs if i.is_displayed()]
            if visible_inputs:
                print("Clicking input to show keypad...")
                driver.execute_script("arguments[0].click();", visible_inputs[0])
                time.sleep(2.0)
                
            # Inspect keypad buttons
            buttons = driver.find_elements(By.TAG_NAME, "button")
            print(f"\n--- Buttons on page after input click ({len(buttons)}) ---")
            keypad_btns = []
            for btn in buttons:
                try:
                    if btn.is_displayed():
                        text = btn.text.strip()
                        classes = btn.get_attribute("class") or ""
                        # Check if inside a keypad container
                        parent_classes = ""
                        try:
                            parent = btn.find_element(By.XPATH, "..")
                            parent_classes = parent.get_attribute("class") or ""
                            # Also check grandparents
                            gp = parent.find_element(By.XPATH, "..")
                            parent_classes += " " + (gp.get_attribute("class") or "")
                        except Exception:
                            pass
                        
                        if any(k in (classes + " " + parent_classes).lower() for k in ["keypad", "keyboard", "palette", "formula", "math"]):
                            keypad_btns.append(btn)
                except Exception:
                    pass
                    
            print(f"Found {len(keypad_btns)} displayed keypad buttons:")
            for idx, btn in enumerate(keypad_btns):
                try:
                    print(f"Key [{idx}] Text='{btn.text.strip()}' | Class='{btn.get_attribute('class')}'")
                except Exception as e:
                    print(f"Key [{idx}] Error: {e}")

    except Exception as e:
        print("Error:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
