import time
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium.webdriver.common.by import By
import config
from login import launch_browser, login
from utils import safe_text

def main():
    config.HEADLESS = True
    driver = launch_browser()
    try:
        driver.get(config.BASE_URL)
        time.sleep(3.0)
        
        # Clear cookies to force log out
        print("Clearing session cookies...")
        driver.delete_all_cookies()
        driver.get(config.BASE_URL)
        time.sleep(3.0)
        
        # Now log in fresh
        login(driver)
        time.sleep(5.0)
        
        # Print page text
        body_text = driver.find_element(By.TAG_NAME, "body").text
        print("\n--- PROFILE PAGE TEXT ---")
        print(body_text)
        print("-------------------------\n")
        
        # Find all buttons
        buttons = driver.find_elements(By.TAG_NAME, "button")
        print(f"Buttons found: {len(buttons)}")
        for idx, btn in enumerate(buttons):
            try:
                print(f"Button [{idx}]: Text='{btn.text}' | Class='{btn.get_attribute('class')}'")
            except Exception:
                pass
                
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
