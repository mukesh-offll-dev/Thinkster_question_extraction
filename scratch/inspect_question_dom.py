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
from utils import safe_text, get_element_html, scroll_into_view, safe_click

def main():
    # Run in headless mode so it is fast and backgrounded, or set config.HEADLESS = False if we want to debug
    config.HEADLESS = True
    driver = launch_browser()
    try:
        login(driver)
        print("Logged in successfully.")
        select_student(driver)
        print("Selected student Thomas D.")
        click_start_learning(driver)
        print("Start learning clicked.")
        time.sleep(4)
        
        # Search topic and worksheet
        print("Searching worksheet AQCMXAL214 under Complex Numbers...")
        found = find_worksheet_in_topic(driver, "Complex Numbers", "AQCMXAL214")
        if not found:
            print("Failed to locate worksheet AQCMXAL214")
            return
            
        print("Waiting for worksheet loading screen to disappear...")
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text
                if "Loading worksheet..." not in body_text and "Loading" not in body_text:
                    print("Worksheet loaded!")
                    break
            except Exception:
                pass
            time.sleep(1)
        time.sleep(3)

        # Let's inspect multiple questions: Q1 (MCQ), Q3 (Input Box), Q4 (True/False Table)
        for q_no in [1, 3, 4]:
            print(f"\n=====================================")
            print(f"   INSPECTING QUESTION {q_no}")
            print(f"=====================================")
            
            # Click question dot
            dot_clicked = False
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                try:
                    if btn.is_displayed() and btn.text.strip() == str(q_no):
                        scroll_into_view(driver, btn)
                        safe_click(driver, btn)
                        dot_clicked = True
                        break
                except Exception:
                    continue
            
            if not dot_clicked:
                print(f"Could not click question dot {q_no}")
                continue
                
            time.sleep(2.5) # wait for question to render
            
            # 1. Look for input boxes
            inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea")
            print(f"Inputs found ({len(inputs)}):")
            for idx, inp in enumerate(inputs):
                try:
                    if inp.is_displayed():
                        print(f"  [{idx}] type='{inp.get_attribute('type')}' | id='{inp.get_attribute('id')}' | class='{inp.get_attribute('class')}' | placeholder='{inp.get_attribute('placeholder')}'")
                except Exception:
                    pass

            # 2. Look for MCQ options
            mcq_options = driver.find_elements(By.CSS_SELECTOR, "[class*='mcq-option'], [class*='option'], [class*='choice']")
            print(f"Choice options found ({len(mcq_options)}):")
            for idx, opt in enumerate(mcq_options):
                try:
                    if opt.is_displayed():
                        text = opt.text.strip().replace('\n', ' ')
                        print(f"  [{idx}] class='{opt.get_attribute('class')}' | text='{text[:100]}'")
                except Exception:
                    pass

            # 3. Look for table matrix elements (e.g. True/False table)
            matrix_rows = driver.find_elements(By.CSS_SELECTOR, "tr")
            print(f"Table rows found ({len(matrix_rows)}):")
            for idx, row in enumerate(matrix_rows):
                try:
                    if row.is_displayed():
                        text = row.text.strip().replace('\n', ' ')
                        print(f"  [{idx}] text='{text[:150]}'")
                        # Print radio/checkbox inputs inside this row
                        row_inputs = row.find_elements(By.CSS_SELECTOR, "input, [role='radio'], [role='checkbox'], button")
                        for ri_idx, ri in enumerate(row_inputs):
                            print(f"    - RowInput [{ri_idx}] tag={ri.tag_name} | type={ri.get_attribute('type')} | role={ri.get_attribute('role')} | class={ri.get_attribute('class')}")
                except Exception:
                    pass
            
            # 4. Check for keypad / formula editor
            keypad_container = driver.find_elements(By.CSS_SELECTOR, "[class*='keypad'], [class*='keyboard'], [class*='palette']")
            print(f"Keypad containers found: {len(keypad_container)}")
            for idx, kc in enumerate(keypad_container):
                try:
                    if kc.is_displayed():
                        print(f"  [{idx}] class='{kc.get_attribute('class')}'")
                except Exception:
                    pass

    except Exception as e:
        print("Inspection Error:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
