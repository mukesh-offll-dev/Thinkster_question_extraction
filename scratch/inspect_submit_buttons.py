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

def wait_for_loading(driver):
    start_time = time.time()
    while time.time() - start_time < 45:
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            if "Loading worksheet..." not in body_text and "Loading" not in body_text:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def print_submit_buttons(driver, label):
    print(f"\n--- {label}: Submit Buttons on Page ---")
    buttons = driver.find_elements(By.TAG_NAME, "button")
    submit_btns = [b for b in buttons if "submit" in b.text.strip().lower()]
    print(f"Total submit buttons found: {len(submit_btns)}")
    for idx, btn in enumerate(submit_btns):
        try:
            print(f"[{idx}] Text='{btn.text.strip()}' | Displayed={btn.is_displayed()} | Enabled={btn.is_enabled()}")
            print(f"HTML: {get_element_html(driver, btn)}")
        except Exception as e:
            print(f"[{idx}] Error: {e}")

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
            
            if not wait_for_loading(driver):
                return
            time.sleep(3)
            
            # Print buttons before Q1 submission
            print_submit_buttons(driver, "Before Q1 Submission")
            
            # Submit Q1
            options = driver.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option")
            visible_options = [o for o in options if o.is_displayed()]
            if visible_options:
                inp = visible_options[0].find_element(By.TAG_NAME, "input")
                driver.execute_script("arguments[0].click();", inp)
                time.sleep(1.0)
                
                # Click first visible submit button
                buttons = driver.find_elements(By.TAG_NAME, "button")
                submit_btn = [b for b in buttons if b.is_displayed() and "submit" in b.text.strip().lower()][0]
                driver.execute_script("arguments[0].click();", submit_btn)
                print("Q1 submitted.")
                time.sleep(4.0)
                
            # Print buttons after Q1 submission (Q2 active)
            print_submit_buttons(driver, "After Q1 Submission (Q2 Active)")

    except Exception as e:
        print("Error:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
