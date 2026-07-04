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
        # Search under Complex Numbers for AQCMXAL214
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
                if card_id == "AQCMXAL214":
                    matching_card = card
                    break
            
            if matching_card:
                card_id, ws_title = finder.extract_worksheet_id_and_title(matching_card)
                finder._click_start(matching_card, "Complex Numbers", ws_title)
                
                if wait_for_loading(driver):
                    time.sleep(3.0)
                    
                    print("Navigating to Q4...", flush=True)
                    click_question_dot(driver, 4)
                    wait_for_active_question(driver, 4)
                    time.sleep(2.0)
                    
                    os.makedirs("screenshots", exist_ok=True)
                    driver.save_screenshot("screenshots/matrix_q4.png")
                    print("Saved screenshots/matrix_q4.png", flush=True)
                    
                    # Inspect active question area
                    # Find all inputs/rows
                    rows = driver.find_elements(By.CSS_SELECTOR, "tr")
                    print(f"Total tr rows: {len(rows)}")
                    for idx, r in enumerate(rows):
                        if r.is_displayed():
                            inputs = r.find_elements(By.CSS_SELECTOR, "input[type='radio'], [role='radio']")
                            text = r.text.strip().replace("\n", " | ")
                            print(f"Row [{idx}]: text='{text}' | inputs={len(inputs)}")
                            for jdx, inp in enumerate(inputs):
                                print(f"  Input [{jdx}]: Tag={inp.tag_name} | Class='{inp.get_attribute('class')}' | HTML='{inp.get_attribute('outerHTML')}'")
            else:
                print("Could not find AQCMXAL214 card")
        else:
            print("Could not find Complex Numbers topic")
                            
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
