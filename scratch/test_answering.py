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
from utils import safe_text, get_element_html, scroll_into_view, safe_click

def main():
    config.HEADLESS = True
    driver = launch_browser()
    try:
        login(driver)
        print("Logged in successfully.")
        select_student(driver)
        print("Selected student Thomas D.")
        click_start_learning(driver)
        print("Start learning clicked. Waiting for dashboard to load...")
        time.sleep(5)
        
        # Open Complex Numbers topic and locate the card for AQCMXAL214
        finder = TopicWorksheetFinder(driver)
        topic_el = finder._find_topic_element("Complex Numbers")
        if not topic_el:
            print("Topic 'Complex Numbers' not found")
            return
            
        # Expand sidebar topic
        scroll_into_view(driver, topic_el)
        safe_click(driver, topic_el)
        time.sleep(4)
        
        # Since it is a sidebar topic, collect cards from the body
        topic_container = driver.find_element(By.TAG_NAME, "body")
        cards = finder._collect_cards(topic_container)
        matching_card = None
        for card in cards:
            card_id, _ = finder.extract_worksheet_id_and_title(card)
            if card_id == "AQCMXAL214":
                matching_card = card
                break
                
        if not matching_card:
            print("Could not find card for AQCMXAL214")
            return
            
        print("Found card. Clicking Start/Resume...")
        success = finder._click_start(matching_card, "Complex Numbers", "Graphing complex numbers - Worksheet 2")
        if not success:
            print("Failed to open worksheet")
            return
            
        print("Waiting for worksheet to load...")
        time.sleep(5)
        
        # Print active question options before selection
        print("\nMCQ Options before selection:")
        options = driver.find_elements(By.CSS_SELECTOR, "[class*='mcq-option'], .lrn-mcq-option")
        for idx, opt in enumerate(options):
            try:
                if opt.is_displayed():
                    print(f"Option {idx} class: {opt.get_attribute('class')}")
            except Exception:
                pass
                
        # Question 1: Complex numbers z1 = 2 + 3i, z2 = -1 + i, z3 = 4 - 2i. Midpoint of z1 and z3.
        # Midpoint = (z1 + z3)/2 = (2+4)/2 + (3i-2i)/2 = 3 + 0.5i.
        # Option A is: 3 + 1/2 i. This is Option A.
        # Let's select Option A (which is index 0 or matches choice A)
        if options:
            print("Selecting Option A (index 0)...")
            scroll_into_view(driver, options[0])
            safe_click(driver, options[0])
            time.sleep(1.0)
            
        # Let's see if Submit Answer button is present
        submit_btn = None
        for tag in ["button", "input", "span"]:
            for btn in driver.find_elements(By.TAG_NAME, tag):
                try:
                    if btn.is_displayed() and "submit answer" in btn.text.strip().lower():
                        submit_btn = btn
                        break
                except Exception:
                    pass
            if submit_btn:
                break
                
        if submit_btn:
            print(f"Found Submit Answer button: '{submit_btn.text.strip()}'. Clicking...")
            scroll_into_view(driver, submit_btn)
            safe_click(driver, submit_btn)
            time.sleep(3.0)
        else:
            print("Could not find Submit Answer button")
            
        # Take screenshot of question after submit
        os.makedirs("screenshots", exist_ok=True)
        screenshot_path = "screenshots/q1_submitted.png"
        driver.save_screenshot(screenshot_path)
        print(f"Saved screenshot: {screenshot_path}")
        
        # Dump option HTML/classes after submission
        print("\nMCQ Options after submission:")
        options = driver.find_elements(By.CSS_SELECTOR, "[class*='mcq-option'], .lrn-mcq-option")
        for idx, opt in enumerate(options):
            try:
                if opt.is_displayed():
                    print(f"Option {idx} class: {opt.get_attribute('class')}")
                    # Print outerHTML snippet to see classes and attributes
                    print(f"HTML: {get_element_html(driver, opt)[:250]}")
            except Exception:
                pass
                
        # Let's also check for any feedback elements (correct/incorrect)
        print("\nChecking for correctness feedback elements:")
        feedback_elems = driver.find_elements(By.CSS_SELECTOR, "[class*='correct'], [class*='incorrect'], [class*='feedback'], [class*='check'], [class*='icon']")
        for idx, el in enumerate(feedback_elems):
            try:
                if el.is_displayed() and el.text.strip():
                    print(f"Feedback {idx}: Tag={el.tag_name} | Class={el.get_attribute('class')} | Text={el.text.strip()[:100]}")
            except Exception:
                pass

    except Exception as e:
        print("Error during test answering:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
