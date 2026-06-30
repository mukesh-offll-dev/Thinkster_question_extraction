import time
import os
import sys

# Windows terminal: ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
import config
from login import launch_browser, login
from dashboard import select_student, click_start_learning
from topic_worksheet_finder import find_worksheet_in_topic
from utils import safe_text, wait_for_page_load

def main():
    driver = launch_browser()
    try:
        login(driver)
        print("Logged in successfully.")
        select_student(driver)
        print("Selected student Thomas D.")
        click_start_learning(driver)
        print("Start learning clicked.")
        time.sleep(3)
        
        # Open Complex Numbers - AQCMXAL209
        print("Opening worksheet...")
        found = find_worksheet_in_topic(driver, "Complex Numbers", "AQCMXAL209")
        if not found:
            print("Failed to open worksheet AQCMXAL209")
            return
            
        print("Waiting for worksheet to load fully...")
        start_time = time.time()
        while time.time() - start_time < 45:
            try:
                # Find elements with text "Loading worksheet"
                body_text = driver.find_element(By.TAG_NAME, "body").text
                if "Loading worksheet..." not in body_text and "Loading" not in body_text:
                    print("Worksheet loaded fully (loading text disappeared)!")
                    break
            except Exception:
                pass
            time.sleep(1)
        
        time.sleep(3) # Wait extra for stability
        
        # Take a screenshot
        os.makedirs("screenshots", exist_ok=True)
        driver.save_screenshot("screenshots/worksheet_loaded.png")
        print("Saved screenshots/worksheet_loaded.png")
        
        # Dump candidate question dots elements
        print("\n=== SCANNING FOR QUESTION NAVIGATION ===")
        # Find elements that contain status-dot or look like a pagination dot or step
        # Learnosity usually uses classes like .lrn-item-status-dot, button.lrn-assess-step, etc.
        dots = driver.find_elements(By.XPATH, "//*[contains(@class, 'dot') or contains(@class, 'circle') or contains(@class, 'step') or contains(@class, 'nav') or @role='navigation']")
        print(f"Found {len(dots)} navigation/dot elements.")
        
        for d in dots:
            try:
                if d.is_displayed():
                    text = safe_text(d).strip()
                    classes = d.get_attribute("class") or ""
                    tag = d.tag_name
                    print(f"Dot element: tag={tag} | text='{text}' | class='{classes}' | loc={d.location} | size={d.size}")
            except Exception:
                pass
                
        # Let's search for buttons or spans containing numbers 1, 2, 3...
        print("\n=== SCANNING FOR NUMBERED BUTTONS OR SPANS ===")
        for el in driver.find_elements(By.XPATH, "//button | //span | //a | //div"):
            try:
                if el.is_displayed():
                    text = safe_text(el).strip()
                    if text.isdigit() and len(text) <= 2:
                        classes = el.get_attribute("class") or ""
                        print(f"Numbered element: tag={el.tag_name} | text='{text}' | class='{classes}' | loc={el.location}")
            except Exception:
                pass

        # Print keypad buttons too
        print("\n=== KEYPAD BUTTONS ===")
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            try:
                if btn.is_displayed():
                    text = safe_text(btn).strip()
                    classes = btn.get_attribute("class") or ""
                    aria = btn.get_attribute("aria-label") or ""
                    print(f"Button: text='{text}' | aria='{aria}' | class='{classes}' | loc={btn.location}")
            except Exception:
                pass
                
    except Exception as e:
        print("Error during dots inspection:", e)
    finally:
        print("Closing driver.")
        driver.quit()

if __name__ == "__main__":
    main()
