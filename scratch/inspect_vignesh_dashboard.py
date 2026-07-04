import time
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium.webdriver.common.by import By
import config
from login import launch_browser, login
from dashboard import select_student, click_start_learning
from utils import scroll_into_view, safe_click, js_click

def main():
    config.HEADLESS = True
    driver = launch_browser()
    try:
        driver.get(config.BASE_URL)
        time.sleep(3.0)
        
        # Clear cookies to force student select
        driver.delete_all_cookies()
        driver.get(config.BASE_URL)
        time.sleep(3.0)
        
        login(driver)
        time.sleep(5.0)
        
        # Select Vignesh LastName instead of Thomas D
        # Find Vignesh LastName card and click Select button
        cards = driver.find_elements(By.XPATH, "//*[contains(text(), 'Vignesh')]")
        if cards:
            print("Found Vignesh LastName profile card")
            # Find the Select button inside or after it
            # The select buttons are index-aligned: 
            # Thomas D is button [2], Vignesh is button [3]
            buttons = driver.find_elements(By.TAG_NAME, "button")
            # Click button [3]
            print("Clicking Select button for Vignesh LastName...")
            js_click(driver, buttons[3])
            time.sleep(3.0)
            
            # Click Start Learning if on dashboard entry page
            click_start_learning(driver)
            time.sleep(5.0)
            
            # Print page body text
            body_text = driver.find_element(By.TAG_NAME, "body").text
            print("\n--- VIGNESH DASHBOARD TOPICS ---")
            print(body_text[:1500])
            print("---------------------------------\n")
            
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
