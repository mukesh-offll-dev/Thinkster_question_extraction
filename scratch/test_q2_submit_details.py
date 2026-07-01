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
            
            # --- Q1 ---
            options = driver.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option")
            visible_options = [o for o in options if o.is_displayed()]
            if visible_options:
                inp = visible_options[0].find_element(By.TAG_NAME, "input")
                driver.execute_script("arguments[0].click();", inp)
                time.sleep(1.0)
                
                submit_btn = None
                for btn in driver.find_elements(By.TAG_NAME, "button"):
                    if btn.is_displayed() and "submit" in btn.text.strip().lower():
                        submit_btn = btn
                        break
                if submit_btn:
                    safe_click(driver, submit_btn)
                    print("Q1 submitted.")
                    time.sleep(4.0)

            # --- Q2 ---
            options = driver.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option")
            visible_options = [o for o in options if o.is_displayed()]
            if visible_options:
                # Select Option A (incorrect)
                inp = visible_options[0].find_element(By.TAG_NAME, "input")
                driver.execute_script("arguments[0].click();", inp)
                time.sleep(1.0)
                
                submit_btn = None
                for btn in driver.find_elements(By.TAG_NAME, "button"):
                    if btn.is_displayed() and "submit" in btn.text.strip().lower():
                        submit_btn = btn
                        break
                
                if submit_btn:
                    print(f"Submitting Q2. Button is enabled: {submit_btn.is_enabled()}")
                    # Let's double check if button is disabled by attribute
                    print(f"Button class: {submit_btn.get_attribute('class')}")
                    print(f"Button disabled attr: {submit_btn.get_attribute('disabled')}")
                    
                    # Click it
                    safe_click(driver, submit_btn)
                    
                    # Capture screenshots at short intervals to watch transition
                    os.makedirs("screenshots/q2_flow", exist_ok=True)
                    for idx, delay in enumerate([0.5, 1.0, 1.5, 2.0]):
                        time.sleep(0.5)
                        driver.save_screenshot(f"screenshots/q2_flow/step_{idx}_{delay}s.png")
                        print(f"Saved step_{idx}_{delay}s.png")
                        # Print header text
                        try:
                            header = driver.find_element(By.TAG_NAME, "header")
                            text_clean = header.text.strip().replace('\n', ' ')
                            print(f"  Step {idx} Header: {text_clean}")
                        except Exception:
                            pass
                else:
                    print("Q2 Submit button not found")

    except Exception as e:
        print("Error:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
