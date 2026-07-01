import time
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium.webdriver.common.by import By
import config
from login import launch_browser, login
from dashboard import select_student, click_start_learning

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
        time.sleep(6)
        
        print("\n=== URL ===")
        print(driver.current_url)
        
        print("\n=== PAGE TITLE ===")
        print(driver.title)
        
        # Print headings (h1, h2, h3, h4)
        print("\n=== HEADINGS ===")
        for tag in ["h1", "h2", "h3", "h4", "h5"]:
            elems = driver.find_elements(By.TAG_NAME, tag)
            for el in elems:
                if el.is_displayed():
                    print(f"<{tag}>: {el.text.strip()}")
                    
        # Let's find any buttons, or elements with text "Complex" or "Numbers"
        print("\n=== ELEMENTS CONTAINING 'COMPLEX' OR 'NUMBERS' ===")
        elems = driver.find_elements(By.XPATH, "//*[contains(text(), 'Complex') or contains(text(), 'Numbers') or contains(text(), 'Worksheet')]")
        for el in elems:
            try:
                if el.is_displayed() and el.text.strip():
                    print(f"Tag={el.tag_name} | Class={el.get_attribute('class')} | Text={el.text.strip()[:100]}")
            except Exception:
                pass

        # Let's dump all text of the body to see what's on the screen
        print("\n=== BODY TEXT SCRIPT ===")
        body_text = driver.find_element(By.TAG_NAME, "body").text
        print(body_text[:1000])

    except Exception as e:
        print("Error:", e)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
