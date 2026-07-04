import time
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from answering import handle_matrix

def main():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    try:
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        mock_file = os.path.join(curr_dir, "test_matrix.html")
        mock_uri = f"file:///{mock_file.replace(os.sep, '/')}"
        print(f"Loading mock page: {mock_uri}")
        driver.get(mock_uri)
        time.sleep(1.0)
        
        answers = ["True", "False", "True"]
        print(f"Submitting answers: {answers}")
        success = handle_matrix(driver, answers)
        print(f"handle_matrix returned: {success}")
        
        q1_true = driver.find_element(By.ID, "q1_true").is_selected()
        q1_false = driver.find_element(By.ID, "q1_false").is_selected()
        
        q2_true = driver.find_element(By.ID, "q2_true").is_selected()
        q2_false = driver.find_element(By.ID, "q2_false").is_selected()
        
        q3_true = driver.find_element(By.ID, "q3_true").is_selected()
        q3_false = driver.find_element(By.ID, "q3_false").is_selected()
        
        print("\n--- RESULTS VERIFICATION ---")
        print(f"Row 1: True Selected = {q1_true} | False Selected = {q1_false}")
        print(f"Row 2: True Selected = {q2_true} | False Selected = {q2_false}")
        print(f"Row 3: True Selected = {q3_true} | False Selected = {q3_false}")
        
        assert q1_true == True, "Q1 True is not selected!"
        assert q2_false == True, "Q2 False is not selected!"
        assert q3_true == True, "Q3 True is not selected!"
        print("\nALL ASSERTIONS PASSED! True/False Matrix question answering is working perfectly!")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
