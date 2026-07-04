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
from answering import wait_for_loading, click_question_dot, wait_for_active_question, handle_text_inputs

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
                    
                    # ── TEST QUESTION 2 ──
                    print("\n--- TESTING Q2 ---")
                    click_question_dot(driver, 2)
                    wait_for_active_question(driver, 2)
                    time.sleep(2.0)
                    success_q2 = handle_text_inputs(driver, "1+2i")
                    print(f"Q2 Handled: {success_q2}")
                    os.makedirs("screenshots", exist_ok=True)
                    driver.save_screenshot("screenshots/real_test_q2_after.png")
                    print("Saved screenshots/real_test_q2_after.png")
                    
                    # ── TEST QUESTION 5 ──
                    print("\n--- TESTING Q5 ---")
                    click_question_dot(driver, 5)
                    wait_for_active_question(driver, 5)
                    time.sleep(2.0)
                    success_q5 = handle_text_inputs(driver, "\\sqrt{34}")
                    print(f"Q5 Handled: {success_q5}")
                    driver.save_screenshot("screenshots/real_test_q5_after.png")
                    print("Saved screenshots/real_test_q5_after.png")
                    
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
