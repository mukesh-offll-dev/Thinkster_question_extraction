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
                    
                    # Loop through 5 questions
                    for q_no in range(1, 6):
                        click_question_dot(driver, q_no)
                        wait_for_active_question(driver, q_no)
                        time.sleep(2.0)
                        
                        # Inspect MCQ options
                        options = driver.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option, [class*='mcq-option']")
                        visible_options = [o for o in options if o.is_displayed()]
                        
                        # Inspect math fields
                        math_fields = driver.find_elements(By.CSS_SELECTOR, ".mq-editable-field, .lrn-formula-input")
                        visible_math_fields = [f for f in math_fields if f.is_displayed()]
                        
                        print(f"Question {q_no}: MCQ Options={len(visible_options)} | Math Inputs={len(visible_math_fields)}")
                        
                        if visible_math_fields:
                            # Capture screenshot of the math input question
                            driver.save_screenshot(f"screenshots/math_q{q_no}.png")
                            print(f"  Saved screenshots/math_q{q_no}.png")
                            
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
