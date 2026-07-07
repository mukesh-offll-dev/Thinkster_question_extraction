import os
import sys
import time
from dotenv import load_dotenv

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
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys

import config
from logger import get_logger

log = get_logger()

# ---------------------------------------------------------------------------
# Constants / Defaults
# ---------------------------------------------------------------------------
DEFAULT_STUDENT_URL = "https://tutor4.0.hellothinkster.com/students/626b0368-19b9-4c31-843d-7113872324b9"
DEFAULT_SUBJECT = "Algebra 2"
DEFAULT_EMAIL = "intern@hellothinkster.com"
DEFAULT_PASSWORD = "Password"

# ---------------------------------------------------------------------------
# React Input Dispatcher Helper
# ---------------------------------------------------------------------------
def set_react_input_value(driver, element, value):
    """
    Sets an input field's value in a way that triggers React's internal value tracking
    and dispatches the necessary input events to update the component's state.
    """
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

# ---------------------------------------------------------------------------
# Helper: Click via JS fallback
# ---------------------------------------------------------------------------
def safe_click_el(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        time.sleep(0.5)
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)

# ---------------------------------------------------------------------------
# Driver initialization and session setup
# ---------------------------------------------------------------------------
def init_driver(profile_suffix=None):
    log.info("Initializing Chrome Driver...")
    options = Options()
    if getattr(config, "HEADLESS", False):
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    else:
        options.add_argument("--window-size=1366,768")
        
    if getattr(config, "PERSIST_SESSION", False):
        profile_dir = getattr(config, "CHROME_PROFILE_DIR", "chrome_profile")
        if profile_suffix:
            profile_dir = f"{profile_dir}_{profile_suffix}"
        profile_path = os.path.abspath(profile_dir)
        log.info("Using persistent Chrome profile directory: %s", profile_path)
        options.add_argument(f"--user-data-dir={profile_path}")

    # Anti-detection arguments
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # Navigator patch
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"}
    )
    driver.implicitly_wait(5)
    return driver

def navigate_and_prep(driver, student_url, email, password):
    print("Navigating to login page...")
    driver.get("https://tutor4.0.hellothinkster.com/login")
    time.sleep(3)
    
    url = driver.current_url.lower()
    if "login" in url:
        print("Login page detected. Performing authentication...")
        email_field = driver.find_element(By.CSS_SELECTOR, "input[type='email'], #email")
        password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password'], #password")
        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        
        email_field.clear()
        email_field.send_keys(email)
        password_field.clear()
        password_field.send_keys(password)
        
        safe_click_el(driver, submit_btn)
        time.sleep(5)
        print("Login submitted.")
    else:
        print("Session cache active (already logged in). Skipping login form.")

    print(f"Navigating to Student Profile: {student_url}")
    driver.get(student_url)
    time.sleep(5)
    
    print("Locating 'Current Assignments' tab...")
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
        print(f"Clicking Tab: '{tab_el.text.strip()}'")
        safe_click_el(driver, tab_el)
        time.sleep(3)
        return True
    else:
        print("[WARNING] Could not find Current Assignments tab by text, trying xpath...")
        try:
            current_ass = driver.find_element(By.XPATH, "//*[contains(text(), 'Current Assessment') or contains(text(), 'Current Assignments')]")
            safe_click_el(driver, current_ass)
            time.sleep(3)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to switch tab: {e}")
            return False

# ---------------------------------------------------------------------------
# Main automation runner
# ---------------------------------------------------------------------------
def run_addition(student_url, subject, worksheet_ids, email, password, profile_suffix=None):
    print("\n" + "="*60)
    print("      Starting Thinkster Worksheet Addition Automation")
    print("="*60)
    print(f"Student URL: {student_url}")
    print(f"Subject:     {subject}")
    print(f"Worksheets:  {', '.join(worksheet_ids)}")
    print(f"Login Email: {email}")
    print("="*60 + "\n")
    
    # Split into sub-batches of 15
    batch_size = 15
    batches = [worksheet_ids[i:i+batch_size] for i in range(0, len(worksheet_ids), batch_size)]
    
    results_summary = []
    driver = None
    
    try:
        for batch_idx, batch_ids in enumerate(batches, 1):
            print(f"\n============================================================")
            print(f" Processing Sub-batch {batch_idx}/{len(batches)} (Size: {len(batch_ids)})")
            print(f"============================================================")
            
            # Retry loop for the current sub-batch
            max_retries = 3
            batch_success = False
            
            for attempt in range(1, max_retries + 1):
                try:
                    if driver is None:
                        driver = init_driver(profile_suffix)
                        success = navigate_and_prep(driver, student_url, email, password)
                        if not success:
                            raise Exception("Failed to navigate and prepare student page.")
                    
                    # 1. Locate playlist card for subject
                    print(f"Locating playlist card for subject: '{subject}'...")
                    h3_el = driver.find_element(By.XPATH, f"//h3[contains(text(), '{subject}')]")
                    card_el = h3_el
                    for _ in range(5):
                        card_el = driver.execute_script("return arguments[0].parentElement;", card_el)
                    
                    manage_btn = card_el.find_element(By.XPATH, ".//button[@title='Manage worksheets']")
                    print("Opening Manage Worksheets modal...")
                    safe_click_el(driver, manage_btn)
                    time.sleep(3)
                    
                    # 2. Click "Search Worksheets (All Grades)" tab
                    search_tab = driver.find_element(By.XPATH, "//button[contains(text(), 'Search Worksheets')]")
                    print("Selecting 'Search Worksheets (All Grades)' tab...")
                    safe_click_el(driver, search_tab)
                    time.sleep(2)
                    
                    # 3. Search and select all IDs in the sub-batch
                    any_changes = False
                    sub_batch_results = []
                    
                    for ws_idx, ws_id in enumerate(batch_ids, 1):
                        ws_id = ws_id.strip()
                        if not ws_id:
                            continue
                        
                        print(f"Searching Worksheet {ws_idx}/{len(batch_ids)} inside modal: {ws_id}")
                        search_input = driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Search by worksheet ID')]")
                        
                        # Clear and set value via React helper
                        set_react_input_value(driver, search_input, "")
                        time.sleep(0.5)
                        set_react_input_value(driver, search_input, ws_id)
                        time.sleep(3.5)
                        
                        # Parse results
                        parent = search_input.find_element(By.XPATH, "./..")
                        results_container = driver.execute_script("return arguments[0].nextElementSibling;", parent)
                        
                        card_els = results_container.find_elements(By.CSS_SELECTOR, ".border-2")
                        if not card_els:
                            container_text = results_container.text
                            if "no worksheets found" in container_text.lower() or "0 worksheets" in container_text.lower():
                                print(f"[WARNING] No worksheets found for ID: {ws_id}")
                                status = "NOT FOUND"
                            else:
                                print(f"[WARNING] Results container did not render card. Container text: '{container_text}'")
                                status = "FAILED - Results Render Error"
                            sub_batch_results.append((ws_id, status))
                            continue
                            
                        target_card = card_els[0]
                        card_text = target_card.text.strip().replace("\n", " ")
                        print(f"Found worksheet: {card_text}")
                        
                        # Check selection state (either green background or disabled/cursor-not-allowed/opacity-60 indicating already added)
                        card_class = target_card.get_attribute("class") or ""
                        is_selected = any(term in card_class for term in ["bg-green-50", "border-green-500", "cursor-not-allowed", "opacity-60"])
                        
                        if is_selected:
                            print(f"Worksheet '{ws_id}' is already selected.")
                            sub_batch_results.append((ws_id, "ALREADY ADDED"))
                        else:
                            print("Worksheet is unselected. Clicking to select...")
                            print("Card class before click:", card_class)
                            safe_click_el(driver, target_card)
                            time.sleep(2.0)
                            print("Card class after click:", target_card.get_attribute("class"))
                            sub_batch_results.append((ws_id, "ADDED"))
                            any_changes = True
                            
                    # 4. Save changes if any changes were made, else Cancel
                    if any_changes:
                        save_btn = driver.find_element(By.XPATH, "//button[text()='Save Changes']")
                        print(f"Save Changes button state: enabled={save_btn.is_enabled()}, disabled={save_btn.get_attribute('disabled')}")
                        print("Saving sub-batch changes...")
                        safe_click_el(driver, save_btn)
                        time.sleep(5.0)
                        print("Sub-batch changes saved successfully.")
                    else:
                        print("No new worksheets selected in this sub-batch. Closing modal...")
                        driver.find_element(By.XPATH, "//button[text()='Cancel']").click()
                        time.sleep(1.5)
                        
                    results_summary.extend(sub_batch_results)
                    batch_success = True
                    break # Success! Break from retry loop
                    
                except Exception as exc:
                    print(f"\n[WARNING] Attempt {attempt}/{max_retries} failed for sub-batch {batch_idx}: {exc}")
                    log.warning("Attempt %d failed for sub-batch %d: %s", attempt, batch_idx, exc)
                    
                    # Quit driver to reset session
                    if driver is not None:
                        try:
                            driver.quit()
                        except:
                            pass
                        driver = None
                        
                    if attempt < max_retries:
                        print("Sleeping 5 seconds before retrying the sub-batch...")
                        time.sleep(5)
                    else:
                        print(f"[ERROR] Sub-batch {batch_idx} failed after {max_retries} attempts.")
                        # Mark all remaining worksheet IDs in this batch as failed
                        for ws_id in batch_ids:
                            results_summary.append((ws_id, "FAILED - Session Error"))
            
            if not batch_success:
                print(f"[WARNING] Continuing to next sub-batch despite failure in sub-batch {batch_idx}.")
                
        # Print execution report
        print("\n" + "="*60)
        print("             WORKSHEET ADDITION RUN SUMMARY")
        print("="*60)
        for ws, status in results_summary:
            print(f" Worksheet {ws.ljust(15)} : {status}")
        print("="*60 + "\n")
        return True
        
    except Exception as e:
        log.exception("Unexpected exception in runner: %s", e)
        print(f"\n[CRITICAL ERROR] Automation failed: {e}\n")
        return False
    finally:
        if driver is not None:
            try:
                driver.quit()
            except:
                pass

# ---------------------------------------------------------------------------
# CLI / Interactive Entrance
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    # Load environment variables
    load_dotenv()

    parser = argparse.ArgumentParser(description="Thinkster Worksheet Addition Automation")
    parser.add_argument("--student-url", type=str, help="Student profile URL")
    parser.add_argument("--subject", type=str, help="Subject/playlist name")
    parser.add_argument("--worksheet-ids", type=str, help="Comma-separated worksheet IDs or file path")
    parser.add_argument("--profile-suffix", type=str, help="Profile suffix for Chrome user data directory")
    parser.add_argument("--email", type=str, help="Thinkster tutor login email")
    parser.add_argument("--password", type=str, help="Thinkster tutor login password")
    
    args = parser.parse_args()
    
    # 1. Parse student URL
    student_url = args.student_url or input(f"Enter Student URL (default '{DEFAULT_STUDENT_URL}'): ").strip()
    if not student_url:
        student_url = DEFAULT_STUDENT_URL
        
    # 2. Parse Subject / Playlist name
    subject = args.subject or input(f"Enter subject name (default '{DEFAULT_SUBJECT}'): ").strip()
    if not subject:
        subject = DEFAULT_SUBJECT
        
    # 3. Parse Worksheet IDs
    ws_input = args.worksheet_ids
    if not ws_input:
        print("\nEnter worksheet IDs (comma-separated, e.g. AQCONAL211, AQCMXAL213)")
        print("Or enter a path to a text file containing IDs:")
        ws_input = input("IDs or File Path: ").strip()
        
    worksheet_ids = []
    if os.path.exists(ws_input) and os.path.isfile(ws_input):
        print(f"Loading worksheet IDs from file: {ws_input}")
        with open(ws_input, "r", encoding="utf-8") as f:
            for line in f:
                parts = [p.strip() for p in line.split(",") if p.strip()]
                worksheet_ids.extend(parts)
    else:
        worksheet_ids = [p.strip() for p in ws_input.split(",") if p.strip()]
        
    if not worksheet_ids:
        print("[ERROR] No worksheet IDs provided. Exiting.")
        sys.exit(1)
        
    # 4. Login credentials
    email = args.email or os.getenv("THINKSTER_EMAIL", DEFAULT_EMAIL)
    password = args.password or os.getenv("THINKSTER_PASSWORD", DEFAULT_PASSWORD)
    
    # Prompt confirmation for credentials if default is used and NOT running in non-interactive argument mode
    if not args.email and email == DEFAULT_EMAIL:
        print(f"\nUsing default tutor credentials: {DEFAULT_EMAIL}")
        use_custom = input("Do you want to use custom credentials instead? (y/N): ").strip().lower()
        if use_custom == 'y':
            email = input("Email: ").strip()
            password = input("Password: ").strip()
            
    # Run the automation
    run_addition(student_url, subject, worksheet_ids, email, password, profile_suffix=args.profile_suffix)
