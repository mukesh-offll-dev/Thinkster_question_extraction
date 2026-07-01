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
            if not options:
                print("No MCQ options found!")
                return
                
            opt = options[0]
            print("Trying Strategy 1: JS Click on the input element inside option...")
            try:
                inp = opt.find_element(By.TAG_NAME, "input")
                driver.execute_script("arguments[0].click();", inp)
                print("JS Click on input done.")
            except Exception as e:
                print("Strategy 1 error:", e)
            
            time.sleep(1.0)
            driver.save_screenshot("screenshots/click_strategy_1.png")
            
            print("Trying Strategy 2: Clicking the label inside option...")
            try:
                lbl = opt.find_element(By.TAG_NAME, "label")
                driver.execute_script("arguments[0].click();", lbl)
                print("JS Click on label done.")
            except Exception as e:
                try:
                    lbl = opt.find_element(By.TAG_NAME, "label")
                    lbl.click()
                    print("Standard Click on label done.")
                except Exception as e2:
                    print("Strategy 2 error:", e2)
            
            time.sleep(1.0)
            driver.save_screenshot("screenshots/click_strategy_2.png")

            print("Trying Strategy 3: Standard click on the li block...")
            try:
                opt.click()
                print("Standard click on li done.")
            except Exception as e:
                print("Strategy 3 error:", e)
                
            time.sleep(1.0)
            driver.save_screenshot("screenshots/click_strategy_3.png")

            # Let's check if option has checked status
            try:
                inp = opt.find_element(By.TAG_NAME, "input")
                is_checked = driver.execute_script("return arguments[0].checked;", inp)
                print(f"Radio input checked status: {is_checked}")
            except Exception as e:
                print("Error checking input status:", e)

    except Exception as e:
        print("Error:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
