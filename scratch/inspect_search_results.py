import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def inspect_search():
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
        
        # Type worksheet ID
        search_input = driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Search by worksheet ID')]")
        search_input.send_keys("AQFFNAL219")
        time.sleep(3)
        
        # Let's inspect the results container
        # Sibling of the parent of the input
        parent = search_input.find_element(By.XPATH, "./..")
        results_container = driver.execute_script("return arguments[0].nextElementSibling;", parent)
        
        print("Results container innerHTML:")
        print(driver.execute_script("return arguments[0].innerHTML;", results_container)[:3000])
        
        # Print children that are div or button
        print("\n--- Children Elements in Results ---")
        items = results_container.find_elements(By.XPATH, ".//*")
        for idx, item in enumerate(items[:30]):
            txt = item.text.strip()
            if txt:
                print(f"Item {idx}: Tag='{item.tag_name}', Class='{item.get_attribute('class')}', Text='{txt[:100]}'")

    finally:
        driver.quit()

if __name__ == "__main__":
    inspect_search()
