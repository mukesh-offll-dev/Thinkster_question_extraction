import sys
import time

# Ensure UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys

def set_react_input_value(driver, element, value):
    js_code = """
    var input = arguments[0];
    var value = arguments[1];
    var lastValue = input.value;
    input.value = value;
    var event = new Event('input', { bubbles: true });
    var tracker = input._valueTracker;
    if (tracker) {
        tracker.setValue(lastValue);
    }
    input.dispatchEvent(event);
    """
    driver.execute_script(js_code, element, value)

def test_click():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1366,768")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    try:
        # Login
        driver.get("https://tutor4.0.hellothinkster.com/login")
        time.sleep(2)
        driver.find_element(By.CSS_SELECTOR, "input[type='email'], #email").send_keys("intern@hellothinkster.com")
        driver.find_element(By.CSS_SELECTOR, "input[type='password'], #password").send_keys("Password")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(3)
        
        # Navigate to student
        driver.get("https://tutor4.0.hellothinkster.com/students/626b0368-19b9-4c31-843d-7113872324b9")
        time.sleep(3)
        
        # Click Current Assignments
        tab_el = None
        for tag in ["button", "a", "span", "div"]:
            elements = driver.find_elements(By.TAG_NAME, tag)
            for el in elements:
                try:
                    txt = el.text.strip().lower()
                    if "current assignment" in txt or "current assessment" in txt:
                        tab_el = el
                        break
                except:
                    pass
            if tab_el:
                break
        if tab_el:
            driver.execute_script("arguments[0].click();", tab_el)
            time.sleep(3)
            
        # Click Manage Worksheets button of Algebra 2
        h3_el = driver.find_element(By.XPATH, "//h3[text()='Algebra 2' or contains(text(), 'Algebra 2')]")
        card_el = h3_el
        for _ in range(5):
            card_el = driver.execute_script("return arguments[0].parentElement;", card_el)
        manage_btn = card_el.find_element(By.XPATH, ".//button[@title='Manage worksheets']")
        driver.execute_script("arguments[0].click();", manage_btn)
        time.sleep(3)
        
        # Click Search Worksheets tab
        search_tab = driver.find_element(By.XPATH, "//button[contains(text(), 'Search Worksheets')]")
        driver.execute_script("arguments[0].click();", search_tab)
        time.sleep(2)
        
        # Focus search input and clear/set it using React helper
        search_input = driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Search by worksheet ID')]")
        
        print("Setting React input value to: AQCONAL211")
        set_react_input_value(driver, search_input, "AQCONAL211")
        time.sleep(3)
        
        # Check results
        parent = search_input.find_element(By.XPATH, "./..")
        results_container = driver.execute_script("return arguments[0].nextElementSibling;", parent)
        
        print("Results container innerText:")
        print(results_container.text)
        
        # Check for .border-2 element inside results container
        card_els = results_container.find_elements(By.CSS_SELECTOR, ".border-2")
        if card_els:
            print("Found card using .border-2 class!")
            print("Card text:", card_els[0].text)
            print("Card class before click:", card_els[0].get_attribute("class"))
            # Click card
            driver.execute_script("arguments[0].click();", card_els[0])
            time.sleep(2)
            print("Clicked card.")
            print("Card class after click:", card_els[0].get_attribute("class"))
            
            # Find Save Changes button
            save_btn = driver.find_element(By.XPATH, "//button[text()='Save Changes']")
            print("Save Changes button text:", save_btn.text)
            print("Save Changes button enabled:", save_btn.is_enabled())
            # Click Save Changes
            driver.execute_script("arguments[0].click();", save_btn)
            time.sleep(3)
            print("Clicked Save Changes.")
        else:
            print("Card not found via .border-2 class.")
            
    finally:
        driver.quit()

if __name__ == "__main__":
    test_click()
