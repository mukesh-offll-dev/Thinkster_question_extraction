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
    print("Waiting for worksheet to load fully...")
    start_time = time.time()
    while time.time() - start_time < 45:
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            if "Loading worksheet..." not in body_text and "Loading" not in body_text:
                print("Worksheet loaded fully!")
                return True
        except Exception:
            pass
        time.sleep(1)
    print("Timed out waiting for worksheet to load.")
    return False

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
            
            # Wait for load
            if not wait_for_loading(driver):
                return
            time.sleep(3)
            
            # --- Q1 ---
            options = driver.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option")
            visible_options = [o for o in options if o.is_displayed()]
            print(f"Q1: Found {len(visible_options)} visible options.")
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
                    driver.execute_script("arguments[0].click();", submit_btn)
                    print("Q1 submitted via JS click.")
                    time.sleep(4.0)

            # --- Q2 ---
            options = driver.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option")
            visible_options = [o for o in options if o.is_displayed()]
            print(f"Q2: Found {len(visible_options)} visible options.")
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
                    print("Submitting Q2 via JS click...")
                    driver.execute_script("arguments[0].click();", submit_btn)
                    time.sleep(4.0)
                else:
                    print("Q2 Submit button not found")

            # Take screenshot after Q2 submission
            os.makedirs("screenshots", exist_ok=True)
            screenshot_path = "screenshots/q2_consec_submitted.png"
            driver.save_screenshot(screenshot_path)
            print(f"Saved screenshot: {screenshot_path}")

            # Print navigation dots info
            print("\nNavigation dots info:")
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                try:
                    text = btn.text.strip()
                    if text.isdigit():
                        print(f"Dot {text}: class='{btn.get_attribute('class')}'")
                except Exception:
                    pass

            # Print header text
            try:
                # Try finding elements near Exit button
                exit_btn = driver.find_element(By.XPATH, "//*[contains(text(), 'Exit') or contains(text(), 'exit')]")
                parent = exit_btn.find_element(By.XPATH, "..")
                text_clean = parent.text.strip().replace('\n', ' ')
                print(f"Stats parent text: {text_clean}")
            except Exception as e:
                print("Error getting header stats:", e)

    except Exception as e:
        print("Error:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
