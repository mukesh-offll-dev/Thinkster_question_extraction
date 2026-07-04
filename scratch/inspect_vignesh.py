import time
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium.webdriver.common.by import By
import config
from login import launch_browser, login
from utils import js_click

def main():
    config.HEADLESS = True
    driver = launch_browser()
    try:
        driver.get(config.BASE_URL)
        time.sleep(3.0)
        
        # Clear cookies
        driver.delete_all_cookies()
        driver.get(config.BASE_URL)
        time.sleep(3.0)
        
        login(driver)
        time.sleep(5.0)
        
        buttons = driver.find_elements(By.TAG_NAME, "button")
        if len(buttons) > 3:
            print("Clicking Select button for Vignesh LastName...")
            js_click(driver, buttons[3])
            time.sleep(6.0)
            
            os.makedirs("screenshots", exist_ok=True)
            driver.save_screenshot("screenshots/vignesh_after_select.png")
            print("Saved screenshots/vignesh_after_select.png")
            
            print(f"Current URL: {driver.current_url}")
            body_text = driver.find_element(By.TAG_NAME, "body").text
            print("\n--- PAGE TEXT ---")
            print(body_text[:1200])
            print("-----------------\n")
            
            # Click any Start Learning button if visible
            for tag in ["button", "a"]:
                for el in driver.find_elements(By.TAG_NAME, tag):
                    try:
                        if el.is_displayed() and "learning" in el.text.lower():
                            print(f"Found clickable element with learning: '{el.text}' - Clicking it...")
                            js_click(driver, el)
                            time.sleep(5.0)
                            print(f"New URL: {driver.current_url}")
                            body_text2 = driver.find_element(By.TAG_NAME, "body").text
                            print("\n--- NEW PAGE TEXT ---")
                            print(body_text2[:1200])
                            print("---------------------\n")
                            driver.save_screenshot("screenshots/vignesh_dashboard.png")
                            print("Saved screenshots/vignesh_dashboard.png")
                            break
                    except Exception:
                        pass
                        
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
