import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def explore():
    options = Options()
    # Run in headful mode so we can debug, or headless if preferred.
    # Since we want to check things, we can use headless but configure window size.
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1366,768")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    try:
        # Step 1: Login
        print("Navigating to login page...")
        driver.get("https://tutor4.0.hellothinkster.com/login")
        time.sleep(3)
        
        # Look for login form elements
        print("Current URL:", driver.current_url)
        email_input = driver.find_element(By.CSS_SELECTOR, "input[type='email'], #email")
        password_input = driver.find_element(By.CSS_SELECTOR, "input[type='password'], #password")
        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        
        print(f"Logging in with intern@hellothinkster.com...")
        email_input.send_keys("intern@hellothinkster.com")
        password_input.send_keys("Password")
        submit_btn.click()
        
        time.sleep(5)
        print("Current URL post-login:", driver.current_url)
        
        # Step 2: Navigate to the student page
        student_url = "https://tutor4.0.hellothinkster.com/students/626b0368-19b9-4c31-843d-7113872324b9"
        print(f"Navigating to student URL: {student_url}")
        driver.get(student_url)
        time.sleep(5)
        print("Current URL at student page:", driver.current_url)
        
        # Let's inspect all tabs/buttons on the student page
        print("\n--- Visible Buttons/Tabs on Student Page ---")
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for idx, btn in enumerate(buttons):
            text = btn.text.strip()
            if text:
                print(f"Button {idx}: '{text}' (class: {btn.get_attribute('class')})")
                
        anchors = driver.find_elements(By.TAG_NAME, "a")
        for idx, a in enumerate(anchors):
            text = a.text.strip()
            if text:
                print(f"Anchor {idx}: '{text}' (href: {a.get_attribute('href')}, class: {a.get_attribute('class')})")
                
        # Find element containing "Current Assignment" or "Current Assessment"
        print("\nSearching for tabs...")
        for tag in ["button", "a", "div", "span"]:
            elements = driver.find_elements(By.TAG_NAME, tag)
            for el in elements:
                try:
                    txt = el.text.strip()
                    if txt and ("assessment" in txt.lower() or "assignment" in txt.lower() or "current" in txt.lower()):
                        print(f"Found element <{tag}> with text '{txt}' (class: {el.get_attribute('class')})")
                except:
                    pass

        # Switch to the tab (let's find the tab with text matching current assignment / current assessment)
        tab_el = None
        for tag in ["button", "a"]:
            elements = driver.find_elements(By.TAG_NAME, tag)
            for el in elements:
                try:
                    txt = el.text.strip().lower()
                    if "current assessment" in txt or "current assignment" in txt or txt == "assignments" or txt == "current assessment":
                        tab_el = el
                        break
                except:
                    pass
            if tab_el:
                break
                
        if tab_el:
            print(f"Clicking tab: '{tab_el.text}'")
            driver.execute_script("arguments[0].click();", tab_el)
            time.sleep(4)
            print("Switched tab.")
        else:
            print("Tab not found via exact text, trying coordinates or clicking button index...")
            # Let's try finding element by xpath
            try:
                # Common xpath for tabs
                current_ass = driver.find_element(By.XPATH, "//*[contains(text(), 'Current Assessment') or contains(text(), 'Current Assignments')]")
                print("Found tab by XPath:", current_ass.text)
                driver.execute_script("arguments[0].click();", current_ass)
                time.sleep(4)
            except Exception as e:
                print("XPath find tab failed:", e)
                
        # Let's list the visible text on the page now
        print("\n--- Page Body Snippet after Tab click ---")
        body_text = driver.find_element(By.TAG_NAME, "body").text
        print(body_text[:1500])
        
        # Let's look for "Manage Worksheet" buttons
        print("\n--- Searching for Manage Worksheet elements ---")
        for tag in ["button", "a"]:
            elements = driver.find_elements(By.TAG_NAME, tag)
            for el in elements:
                try:
                    txt = el.text.strip()
                    if txt and ("manage" in txt.lower() or "worksheet" in txt.lower()):
                        print(f"Element <{tag}>: '{txt}' (class: {el.get_attribute('class')})")
                except:
                    pass
                    
        # Let's try to locate the specific "Manage worksheet" of Algebra 2
        # Let's print out text of parents / cards
        print("\n--- Card Elements ---")
        cards = driver.find_elements(By.XPATH, "//*[contains(text(), 'Algebra 2') or contains(text(), 'Algebra II')]")
        for idx, card in enumerate(cards):
            try:
                print(f"Card {idx}: Tag: {card.tag_name}, Text: {card.text[:200]}")
            except:
                pass
                
    finally:
        driver.quit()

if __name__ == "__main__":
    explore()
