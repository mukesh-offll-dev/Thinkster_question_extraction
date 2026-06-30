import time
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from selenium.webdriver.common.by import By
import config
from login import launch_browser, login
from dashboard import select_student, click_start_learning
from topic_worksheet_finder import find_worksheet_in_topic
from utils import scroll_into_view, safe_click, get_element_html

def main():
    config.HEADLESS = True  # Run headlessly so we don't need a UI display
    driver = launch_browser()
    try:
        login(driver)
        print("Logged in successfully.")
        select_student(driver)
        print("Selected student Thomas D.")
        click_start_learning(driver)
        print("Start learning clicked.")
        time.sleep(3)
        
        # Search topic and worksheet
        print("Searching worksheet AQCMXAL209 under Complex Numbers...")
        found = find_worksheet_in_topic(driver, "Complex Numbers", "AQCMXAL209")
        if not found:
            print("Failed to locate worksheet AQCMXAL209")
            return
            
        # Wait up to 30 seconds for loading screen to disappear
        print("Waiting for loading screen to disappear...")
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text
                if "Loading worksheet..." not in body_text and "Loading" not in body_text:
                    print("Worksheet loading screen gone.")
                    break
            except Exception:
                pass
            time.sleep(1)
        time.sleep(3) # Wait extra for stability

        # Print all buttons to see how they look
        print("\nAll buttons on page:")
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            try:
                if btn.is_displayed():
                    print(f"Button: text='{btn.text.strip()}' | loc={btn.location} | size={btn.size} | class='{btn.get_attribute('class')}'")
            except Exception:
                pass

        # We want to check Question 3 (index 3) and Question 5 (index 5)
        for q_no in [3, 5]:
            print(f"\n--- NAVIGATING TO QUESTION {q_no} ---")
            dot_btn = None
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                try:
                    if btn.is_displayed():
                        text = btn.text.strip()
                        # Loosen the y coordinate constraint
                        if text == str(q_no):
                            dot_btn = btn
                            break
                except Exception:
                    continue


            if dot_btn:
                scroll_into_view(driver, dot_btn)
                safe_click(driver, dot_btn)
                time.sleep(4.0)  # Wait for transition
            else:
                print(f"Could not find button dot for Question {q_no}")
                continue
                
            # Now let's find the active question stimulus/text elements
            # and dump their HTML
            print(f"Dumping HTML of active question text elements for Question {q_no}:")
            
            # Find the active item container first if possible
            # Learnosity active item usually has class .lrn-active, or we can check the visible elements matching _QUESTION_TEXT_SELECTORS
            from extractor import _QUESTION_TEXT_SELECTORS, find_active_question_elements
            for sel in _QUESTION_TEXT_SELECTORS:
                elements = find_active_question_elements(driver, sel)
                for idx, el in enumerate(elements):
                    print(f"Selector: {sel} | Index: {idx}")
                    print(get_element_html(driver, el))
                    print("-" * 50)
                    
            # Let's also search for all elements with class starting with lrn-math or containing math
            math_elements = driver.find_elements(By.CSS_SELECTOR, "[class*='math'], [class*='Math']")
            visible_math = [m for m in math_elements if m.is_displayed()]
            print(f"Found {len(visible_math)} visible math elements on the page:")
            for idx, m in enumerate(visible_math):
                # Only dump if it is active (e.g. rect.x is within screen)
                rect = driver.execute_script(
                    "let r = arguments[0].getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: r.height};",
                    m
                )
                if rect['x'] >= -100:
                    print(f"Math Element {idx} | Class: {m.get_attribute('class')} | Rect: {rect}")
                    print(get_element_html(driver, m))
                    print("-" * 50)

    except Exception as e:
        print("Error during inspection:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
