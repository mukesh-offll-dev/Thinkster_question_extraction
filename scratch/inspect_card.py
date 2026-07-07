import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def inspect():
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
        
        # Find and click Current Assignments tab
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
            print("Switched to tab successfully.")
        
        # Locate the card containing "Algebra 2"
        h3_el = driver.find_element(By.XPATH, "//h3[text()='Algebra 2' or contains(text(), 'Algebra 2')]")
        # Go up the ancestor chain to find the card container
        card_el = h3_el
        for _ in range(5):
            card_el = driver.execute_script("return arguments[0].parentElement;", card_el)
            
        print("Algebra 2 card innerHTML:")
        card_html = driver.execute_script("return arguments[0].innerHTML;", card_el)
        print(card_html[:3000]) # Print first 3000 chars of HTML
        
        # Let's find all buttons or interactive elements in this card
        print("\n--- Buttons in Algebra 2 card ---")
        sub_buttons = card_el.find_elements(By.TAG_NAME, "button")
        for idx, btn in enumerate(sub_buttons):
            print(f"Button {idx}: Text='{btn.text}', Class='{btn.get_attribute('class')}', ID='{btn.get_attribute('id')}'")
            
        sub_anchors = card_el.find_elements(By.TAG_NAME, "a")
        for idx, a in enumerate(sub_anchors):
            print(f"Anchor {idx}: Text='{a.text}', Class='{a.get_attribute('class')}', href='{a.get_attribute('href')}'")
            
        # Let's inspect divs inside the card that might be acting as buttons
        sub_divs = card_el.find_elements(By.TAG_NAME, "div")
        for idx, d in enumerate(sub_divs):
            role = d.get_attribute("role")
            title = d.get_attribute("title")
            txt = d.text.strip()
            if role or title or "manage" in txt.lower():
                print(f"Div {idx}: Text='{txt}', Class='{d.get_attribute('class')}', Role='{role}', Title='{title}'")

    finally:
        driver.quit()

if __name__ == "__main__":
    inspect()
