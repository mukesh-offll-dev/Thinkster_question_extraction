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
            
            options = driver.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option")
            if options:
                print("Selecting Option A (index 0) via input JS click...")
                inp = options[0].find_element(By.TAG_NAME, "input")
                driver.execute_script("arguments[0].click();", inp)
                time.sleep(1.0)
                
                # Find Submit Answer
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
                    time.sleep(4.0)
                else:
                    print("Submit Answer button not found")
                    
                # Take screenshot
                os.makedirs("screenshots", exist_ok=True)
                screenshot_path = "screenshots/q1_graded.png"
                driver.save_screenshot(screenshot_path)
                print(f"Saved screenshot: {screenshot_path}")
                
                # Check option classes now
                print("\nOption classes after grading:")
                options = driver.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option")
                for idx, opt in enumerate(options):
                    print(f"Option {idx}: class='{opt.get_attribute('class')}'")
                    # Check for child elements with correct/incorrect
                    sub_elems = opt.find_elements(By.XPATH, ".//*")
                    for se in sub_elems:
                        se_class = se.get_attribute("class") or ""
                        if "correct" in se_class.lower() or "incorrect" in se_class.lower() or "icon" in se_class.lower():
                            print(f"  - Child tag={se.tag_name} | class='{se_class}' | text='{se.text.strip()}'")
                            
                # Check for global feedback on page
                print("\nChecking for correctness feedback elements on page:")
                feedback_elems = driver.find_elements(By.CSS_SELECTOR, "[class*='correct'], [class*='incorrect'], [class*='feedback'], [class*='check'], [class*='icon']")
                for idx, el in enumerate(feedback_elems):
                    try:
                        if el.is_displayed() and el.text.strip():
                            print(f"Feedback {idx}: Tag={el.tag_name} | Class={el.get_attribute('class')} | Text={el.text.strip()[:100]}")
                    except Exception:
                        pass
                        
    except Exception as e:
        print("Error:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
