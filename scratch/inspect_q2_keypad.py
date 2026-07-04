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
                    
                    click_question_dot(driver, 2)
                    wait_for_active_question(driver, 2)
                    time.sleep(2.0)
                    
                    inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea, .mq-editable-field, .lrn-formula-input")
                    visible_inputs = [i for i in inputs if i.is_displayed()]
                    if visible_inputs:
                        print("Clicking input in Q2...")
                        driver.execute_script("arguments[0].click();", visible_inputs[0])
                        time.sleep(2.0)
                        
                        # Find all buttons
                        buttons = driver.find_elements(By.TAG_NAME, "button")
                        print(f"Total buttons found: {len(buttons)}")
                        
                        keypad_btns = []
                        for idx, btn in enumerate(buttons):
                            try:
                                is_disp = btn.is_displayed()
                                cls = btn.get_attribute("class") or ""
                                text = btn.text.strip().split('\n')[0]
                                if is_disp and ("lrn" in cls or "key" in cls or "grid" in cls or btn.get_attribute("data-mq-value")):
                                    print(f"Button [{idx}]: text='{text}' | class='{cls}' | data-mq-value='{btn.get_attribute('data-mq-value')}' | displayed={is_disp}")
                                    keypad_btns.append(btn)
                            except Exception:
                                pass
                                
                        print(f"Detected keypad buttons count: {len(keypad_btns)}")
                        
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
