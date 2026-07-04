import time
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
import config
from login import launch_browser, login
from dashboard import select_student, click_start_learning
from topic_worksheet_finder import TopicWorksheetFinder
from utils import scroll_into_view, safe_click, get_element_html
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
        topic_el = finder._find_topic_element("Complex Numbers")
        if topic_el:
            scroll_into_view(driver, topic_el)
            safe_click(driver, topic_el)
            time.sleep(4.0)
            topic_container = driver.find_element(By.TAG_NAME, "body")
            cards = finder._collect_cards(topic_container)
            
            matching_card = None
            for card in cards:
                card_id, _ = finder.extract_worksheet_id_and_title(card)
                if card_id == "AQCMXAL211":
                    matching_card = card
                    break
            
            if matching_card:
                card_id, ws_title = finder.extract_worksheet_id_and_title(matching_card)
                finder._click_start(matching_card, "Complex Numbers", ws_title)
                
                if wait_for_loading(driver):
                    time.sleep(3.0)
                    
                    click_question_dot(driver, 5)
                    wait_for_active_question(driver, 5)
                    time.sleep(2.0)
                    
                    inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea, .mq-editable-field, .lrn-formula-input")
                    visible_inputs = [i for i in inputs if i.is_displayed()]
                    if visible_inputs:
                        print("Focusing math input...")
                        driver.execute_script("arguments[0].click();", visible_inputs[0])
                        time.sleep(1.0)
                        
                        # Find all toggles and option buttons
                        toggles = driver.find_elements(By.XPATH, "//div[contains(@class, 'lrn-formula-keyboard-menu-groups')]//button[contains(@class, 'lrn_dropdown_toggle')]")
                        print(f"Total toggles found in menu-groups: {len(toggles)}")
                        for idx, t in enumerate(toggles):
                            print(f"Toggle [{idx}]: Displayed={t.is_displayed()} | Class='{t.get_attribute('class')}'")
                            
                        options = driver.find_elements(By.XPATH, "//div[contains(@class, 'lrn-formula-keyboard-menu-groups')]//button[contains(@class, 'lrn_dropdown_option')]")
                        print(f"Total options found in menu-groups: {len(options)}")
                        for idx, o in enumerate(options):
                            print(f"Option [{idx}]: Displayed={o.is_displayed()} | Title='{o.get_attribute('title')}' | Aria-label='{o.get_attribute('aria-label')}' | Class='{o.get_attribute('class')}'")
                            
                        # Let's try switching to Keyboard layout
                        # Click the visible toggle
                        visible_toggle = None
                        for t in toggles:
                            if t.is_displayed():
                                visible_toggle = t
                                break
                                
                        if visible_toggle:
                            print("Clicking visible toggle button...")
                            # Try native click
                            try:
                                visible_toggle.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", visible_toggle)
                            time.sleep(1.0)
                            
                            # Check visibility of options after click
                            print("Options visibility after toggle click:")
                            for idx, o in enumerate(options):
                                print(f"Option [{idx}]: Displayed={o.is_displayed()} | Title='{o.get_attribute('title')}' | Class='{o.get_attribute('class')}'")
                                
                            # Click the Keyboard option
                            keyboard_opt = None
                            for o in options:
                                title = o.get_attribute("title") or o.get_attribute("aria-label") or ""
                                if "keyboard" in title.lower():
                                    keyboard_opt = o
                                    break
                                    
                            if keyboard_opt:
                                print("Clicking Keyboard option...")
                                try:
                                    keyboard_opt.click()
                                except Exception:
                                    driver.execute_script("arguments[0].click();", keyboard_opt)
                                time.sleep(1.0)
                                
                                # Take screenshot
                                driver.save_screenshot("screenshots/test_keypad_switch_detail.png")
                                print("Saved screenshots/test_keypad_switch_detail.png")
                                
                                # Verify layout
                                print("Keyboard option classes after selection:")
                                print(f"Class: '{keyboard_opt.get_attribute('class')}'")
                            else:
                                print("Keyboard option not found!")
                        else:
                            print("No visible toggle found!")
                            
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
