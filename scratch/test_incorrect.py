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
            print(f"Q1: Found {len(visible_options)} visible options.")
            if visible_options:
                print("Selecting correct option (index 0)...")
                inp = visible_options[0].find_element(By.TAG_NAME, "input")
                driver.execute_script("arguments[0].click();", inp)
                time.sleep(1.0)
                
                submit_btn = None
                for btn in driver.find_elements(By.TAG_NAME, "button"):
                    if btn.is_displayed() and "submit answer" in btn.text.strip().lower():
                        submit_btn = btn
                        break
                if submit_btn:
                    safe_click(driver, submit_btn)
                    print("Q1 submitted.")
                    time.sleep(3.0)

            # --- Q2 ---
            # Wait for Q2 options to be visible
            options = driver.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option")
            visible_options = [o for o in options if o.is_displayed()]
            print(f"Q2: Found {len(visible_options)} visible options.")
            if visible_options:
                # Option A is incorrect. Let's select Option A (index 0 of visible options)
                print("Selecting incorrect option (index 0)...")
                inp = visible_options[0].find_element(By.TAG_NAME, "input")
                driver.execute_script("arguments[0].click();", inp)
                time.sleep(1.0)
                
                submit_btn = None
                for btn in driver.find_elements(By.TAG_NAME, "button"):
                    if btn.is_displayed() and "submit answer" in btn.text.strip().lower():
                        submit_btn = btn
                        break
                if submit_btn:
                    safe_click(driver, submit_btn)
                    print("Q2 submitted.")
                    time.sleep(3.0)

            # Take screenshot of Q3 (after Q2 submission)
            os.makedirs("screenshots", exist_ok=True)
            screenshot_path = "screenshots/q2_graded_incorrect.png"
            driver.save_screenshot(screenshot_path)
            print(f"Saved screenshot: {screenshot_path}")

            # Let's inspect the dots at the top to see their classes and status
            print("\nNavigation dots info:")
            # Dots are usually inside some pagination/navigation container
            # We can find them by looking for buttons/links containing numbers 1, 2, 3, etc.
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                try:
                    text = btn.text.strip()
                    if text.isdigit():
                        print(f"Dot {text}: class='{btn.get_attribute('class')}' | parent_class='{btn.find_element(By.XPATH, '..').get_attribute('class')}'")
                except Exception:
                    pass

            # Let's also inspect header counters (green/purple/orange dots)
            print("\nHeader text stats:")
            try:
                # Usually in the top header
                header = driver.find_element(By.TAG_NAME, "header")
                print(f"Header Text: {header.text.strip()}")
            except Exception:
                try:
                    # Try finding elements near Exit button
                    exit_btn = driver.find_element(By.XPATH, "//*[contains(text(), 'Exit') or contains(text(), 'exit')]")
                    parent = exit_btn.find_element(By.XPATH, "..")
                    print(f"Parent of Exit Text: {parent.text.strip()}")
                except Exception as e:
                    print("Error getting header stats:", e)

    except Exception as e:
        print("Error during incorrect test answering:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
