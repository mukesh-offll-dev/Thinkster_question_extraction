# =============================================================================
# main.py - Entry Point for Thinkster Elevate Automation
# =============================================================================
# Run with:
#     python main.py
#
# Workflow:
#   1.  Launch Chrome + Login + Select Thomas D + Start Learning
#   2.  Ask user -> Enter Worksheet ID   (e.g. AQCMXAL209)
#   3.  Scan all topics; match by ID present anywhere in the card
#         e.g. card text: "Complex solutions of quadratics - Worksheet 3 (AQCMXAL209)"
#   4.  When found -> print Topic / Worksheet Name / Worksheet ID -> click Start
#   5.  Not found  -> print clear error message
#   6.  Optionally run AI math-expert analysis on each question
# =============================================================================

import sys
import time
from typing import Optional

# Windows terminal: ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from selenium.common.exceptions import InvalidSessionIdException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By

import config
from logger import get_logger
from utils import (
    setup_driver_and_navigate,
    prompt_topic_name,
    exit_worksheet,
    hold_browser,
    scroll_into_view,
)

log = get_logger()


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

_BANNER = """
+==================================================================+
|       Thinkster Elevate  -  Worksheet Automation Tool           |
|       Topic-targeted Search  ->  Auto-open                      |
+==================================================================+
"""


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def run_automation() -> None:
    import os
    # Step 1 – Get inputs from user first
    topic_name = prompt_topic_name()

    driver: Optional[WebDriver] = None

    try:
        # Step 2 – Browser setup and dashboard navigation
        driver = setup_driver_and_navigate()

        # Step 3 – Initialize finder and find topic
        from topic_worksheet_finder import TopicWorksheetFinder
        finder = TopicWorksheetFinder(driver)
        
        # Locate the topic
        topic_el = finder._find_topic_element(topic_name)
        if not topic_el:
            print(f"\n[ERROR] Topic '{topic_name}' was not found on the dashboard.\n")
            log.error("Topic '%s' was not found on the dashboard.", topic_name)
            return

        print(f"\nTopic Selected: {topic_name}\n")
        
        # Check if the topic element is part of a sidebar menu
        is_sidebar = False
        try:
            # Method A: x-coordinate check (sidebar is on the left w-64, w <= 256px)
            loc = topic_el.location
            if loc and loc.get('x', 999) < 250:
                is_sidebar = True
            
            # Method B: tag name or class in ancestors
            if not is_sidebar:
                curr = topic_el
                while curr:
                    classes = (curr.get_attribute("class") or "").lower()
                    tag = curr.tag_name.lower()
                    if "sidebar" in classes or tag in ("aside", "nav") or "menu" in classes or "nav" in classes:
                        is_sidebar = True
                        break
                    curr = driver.execute_script("return arguments[0].parentElement;", curr)
        except Exception:
            pass

        if is_sidebar:
            log.info("Topic is sidebar menu item. Clicking to navigate...")
            from utils import scroll_into_view, safe_click
            scroll_into_view(driver, topic_el)
            safe_click(driver, topic_el)
            time.sleep(4.0) # Wait for page contents to load fully
            
            # Since it is a sidebar-driven topic, the worksheets container is the entire page body
            topic_container = driver.find_element(By.TAG_NAME, "body")
        else:
            # Expand the topic if collapsed
            finder._expand_topic(topic_el)
            time.sleep(1.5)
            
            # For accordion-driven topics, the container is the parent card element
            try:
                topic_container = driver.execute_script("return arguments[0].parentElement;", topic_el)
                if not topic_container:
                    topic_container = topic_el
            except Exception:
                topic_container = topic_el

        # Expand sub-sections/sub-accordions
        finder._expand_subsections(topic_container)
        time.sleep(1.5)
        
        # Scroll to bottom and top of the topic container to trigger lazy loading of cards
        try:
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'end'});", topic_container)
            time.sleep(1.0)
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'start'});", topic_container)
            time.sleep(1.0)
        except Exception:
            pass
            
        # Collect cards and parse Worksheet IDs
        cards = finder._collect_cards(topic_container)
        ws_ids = []
        ws_titles = {}
        for card in cards:
            ws_id, ws_title = finder.extract_worksheet_id_and_title(card)
            if ws_id:
                if ws_id not in ws_ids:
                    ws_ids.append(ws_id)
                ws_titles[ws_id] = ws_title
            else:
                log.warning("Skipping card because Worksheet ID could not be extracted. Title: %s", ws_title)
                
        if not ws_ids:
            print(f"\n[NOT FOUND] No worksheets with extractable IDs found under topic '{topic_name}'.\n")
            return

        print(f"Found {len(ws_ids)} unique worksheets in topic '{topic_name}':")
        for ws_id in ws_ids:
            print(f" - {ws_titles[ws_id]} ({ws_id})")
        print()

        # Step 4 – Sequentially process worksheets
        for idx, ws_id in enumerate(ws_ids):
            ws_title = ws_titles[ws_id]
            print(f"\n--- [{idx + 1}/{len(ws_ids)}] Processing: {ws_title} ({ws_id}) ---")
            
            # Check if directory exists
            screenshot_dir = os.path.join("screenshots", ws_id)
            if os.path.exists(screenshot_dir) and os.path.isdir(screenshot_dir):
                print(f"Folder '{screenshot_dir}' already exists. Skipping worksheet.\n")
                log.info("Worksheet %s already processed (folder exists). Skipping.", ws_id)
                continue
                
            # Re-locate and expand topic to ensure it is open and visible
            if not is_sidebar:
                topic_el = finder._find_topic_element(topic_name)
                if not topic_el:
                    print(f"[ERROR] Could not re-locate topic '{topic_name}' during iteration.")
                    return
                finder._expand_topic(topic_el)
                time.sleep(1.0)
            
            # Re-collect cards and find the matching card
            if is_sidebar:
                topic_container = driver.find_element(By.TAG_NAME, "body")
            else:
                try:
                    topic_container = driver.execute_script("return arguments[0].parentElement;", topic_el)
                    if not topic_container:
                        topic_container = topic_el
                except Exception:
                    topic_container = topic_el
            cards = finder._collect_cards(topic_container)
            matching_card = None
            for card in cards:
                card_id, _ = finder.extract_worksheet_id_and_title(card)
                if card_id == ws_id:
                    matching_card = card
                    break
                    
            if not matching_card:
                print(f"[ERROR] Could not find card for Worksheet ID: {ws_id}. Skipping.")
                log.error("Could not locate card for Worksheet ID %s after returning to list.", ws_id)
                continue
                
            # Scroll card into view
            scroll_into_view(driver, matching_card)
            time.sleep(0.5)
            
            # Create folder using the Worksheet ID
            os.makedirs(screenshot_dir, exist_ok=True)
            print(f"Created folder: {screenshot_dir}")
            log.info("Created folder for screenshots: %s", screenshot_dir)
            
            # Click Start or Resume to open the worksheet
            success = finder._click_start(matching_card, topic_name, ws_title)
            if not success:
                print(f"[ERROR] Failed to open worksheet: {ws_title} ({ws_id})")
                log.error("Failed to open worksheet %s", ws_id)
                try:
                    os.rmdir(screenshot_dir)
                except Exception:
                    pass
                continue
                
            # Capture screenshots of every question
            print(f"Opened worksheet {ws_id} successfully. Capturing screenshots...")
            capture_question_screenshots(driver, ws_id)
            
            # Exit worksheet and return to worksheet list
            exit_success = exit_worksheet(driver)
            if not exit_success:
                print(f"[WARN] Exit button not clicked successfully. Attempting fallback URL navigation...")
                # Fallback: navigate to dashboard URL or go back
                driver.get(config.BASE_URL)
                time.sleep(5.0)
                # Re-login or navigate to start learning if needed
                from dashboard import select_student, click_start_learning
                select_student(driver)
                click_start_learning(driver)
                time.sleep(3.0)
                
            print(f"Finished processing Worksheet: {ws_id}\n")
            time.sleep(2.0)

        print("\nAll worksheets in the topic processed.")
        hold_browser(driver)

    except InvalidSessionIdException:
        log.error("Browser closed unexpectedly.")
        print("\n[ERROR] Browser closed. Do not close Chrome during automation.\n")

    except RuntimeError as exc:
        log.error("Runtime error: %s", exc)
        print(f"\n[ERROR] {exc}\n")

    except Exception as exc:
        log.exception("Unexpected error: %s", exc)
        print(f"\n[ERROR] {exc}\n")

    finally:
        if driver is not None:
            try:
                driver.quit()
                log.info("Browser closed.")
            except Exception:
                pass


def capture_question_screenshots(driver: WebDriver, worksheet_id: str) -> None:
    """
    Finds all question navigation dots, navigates to each question,
    and captures a screenshot saved to screenshots/<worksheet_id>/Question_<q_no>.png.
    """
    import os
    
    # Create target directory
    screenshot_dir = os.path.join("screenshots", worksheet_id)
    os.makedirs(screenshot_dir, exist_ok=True)
    log.info("Creating directory for screenshots: %s", screenshot_dir)
    print(f"\nSaving screenshots to: {screenshot_dir}\n")

    # Helper function to get maximum question index in header
    def get_num_questions() -> int:
        js_code = """
        function findMaxQuestion() {
            let candidates = document.querySelectorAll('button, a, .lrn-btn, [class*="nav"]');
            let maxNum = 0;
            candidates.forEach(btn => {
                let clone = btn.cloneNode(true);
                let sr = clone.querySelectorAll('.sr-only, .lrn-sr-only, [class*="sr-only"], [class*="assistive"], [class*="accessible"]');
                sr.forEach(s => s.remove());
                
                let text = (clone.innerText || clone.textContent || "").trim();
                if (/^\\d+$/.test(text)) {
                    let num = parseInt(text, 10);
                    let rect = btn.getBoundingClientRect();
                    if (rect.top >= 0 && rect.top < 250 && rect.width > 5 && rect.height > 5) {
                        maxNum = Math.max(maxNum, num);
                    }
                }
            });
            return maxNum;
        }
        return findMaxQuestion();
        """
        try:
            return driver.execute_script(js_code)
        except Exception as e:
            log.error("Error getting question count: %s", e)
            return 0

    # Helper function to click a specific question dot
    def click_question_dot(qNum: int) -> bool:
        js_code = """
        function clickDot(q) {
            let candidates = document.querySelectorAll('button, a, .lrn-btn, [class*="nav"]');
            for (let btn of candidates) {
                let clone = btn.cloneNode(true);
                let sr = clone.querySelectorAll('.sr-only, .lrn-sr-only, [class*="sr-only"], [class*="assistive"], [class*="accessible"]');
                sr.forEach(s => s.remove());
                
                let text = (clone.innerText || clone.textContent || "").trim();
                if (text === String(q)) {
                    let rect = btn.getBoundingClientRect();
                    if (rect.top >= 0 && rect.top < 250 && rect.width > 5 && rect.height > 5) {
                        btn.click();
                        return true;
                    }
                }
            }
            return false;
        }
        return clickDot(arguments[0]);
        """
        try:
            return driver.execute_script(js_code, qNum)
        except Exception as e:
            log.error("Error clicking navigation dot %d via JS: %s", qNum, e)
            return False

    # Wait up to 20 seconds for the navigation dots to load
    num_questions = 0
    start_time = time.time()
    while time.time() - start_time < 20:
        num_questions = get_num_questions()
        if num_questions > 0:
            break
        time.sleep(1)

    if num_questions == 0:
        log.warning("No question navigation dots detected. Defaulting to 5 questions.")
        num_questions = 5
        
    log.info("Detected %d questions to process.", num_questions)
    print(f"Detected {num_questions} questions. Starting capture...")
    
    for q_no in range(1, num_questions + 1):
        log.info("Processing Question %d of %d...", q_no, num_questions)
        print(f"Processing Question {q_no}...")
        
        # Navigate to the question (always click the dot, starting with 1)
        clicked = click_question_dot(q_no)
        if clicked:
            time.sleep(config.QUESTION_TRANSITION_DELAY)  # Wait for transition/render
        else:
            log.warning("Could not click navigation dot for Question %d", q_no)
        
        # Scroll to top/center to ensure visibility
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(config.QUESTION_SETTLE_DELAY)  # Allow rendering to settle
        
        # Save screenshot
        filename = f"Question_{q_no}.png"
        filepath = os.path.join(screenshot_dir, filename)
        try:
            driver.save_screenshot(filepath)
            log.info("Saved screenshot for Question %d: %s", q_no, filepath)
            print(f"-> Captured: {filename}")
        except Exception as e:
            log.error("Failed to capture screenshot for Question %d: %s", q_no, e)
            print(f"[ERROR] Could not save screenshot: {e}")
            
    print("\nCapture completed successfully.\n")



def extract_screenshots_for_worksheet(topic_name: str, target_ws_id: str, headless: bool = True, log_callback = None) -> bool:
    import os
    original_headless = config.HEADLESS
    config.HEADLESS = headless

    def log_msg(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
        log.info(msg)

    driver: Optional[WebDriver] = None

    try:
        log_msg(f"Launching browser (headless={headless})...")
        driver = setup_driver_and_navigate()

        log_msg(f"Searching for topic: {topic_name}")
        from topic_worksheet_finder import TopicWorksheetFinder
        finder = TopicWorksheetFinder(driver)
        
        # Locate the topic
        topic_el = finder._find_topic_element(topic_name)
        if not topic_el:
            log_msg(f"[ERROR] Topic '{topic_name}' was not found on the dashboard.")
            return False

        log_msg(f"Topic Selected: {topic_name}")
        
        # Check if the topic element is part of a sidebar menu
        is_sidebar = False
        try:
            loc = topic_el.location
            if loc and loc.get('x', 999) < 250:
                is_sidebar = True
            
            if not is_sidebar:
                curr = topic_el
                while curr:
                    classes = (curr.get_attribute("class") or "").lower()
                    tag = curr.tag_name.lower()
                    if "sidebar" in classes or tag in ("aside", "nav") or "menu" in classes or "nav" in classes:
                        is_sidebar = True
                        break
                    curr = driver.execute_script("return arguments[0].parentElement;", curr)
        except Exception:
            pass

        if is_sidebar:
            log_msg("Topic is sidebar menu item. Clicking to navigate...")
            from utils import scroll_into_view, safe_click
            scroll_into_view(driver, topic_el)
            safe_click(driver, topic_el)
            time.sleep(4.0)
            topic_container = driver.find_element(By.TAG_NAME, "body")
        else:
            finder._expand_topic(topic_el)
            time.sleep(1.5)
            try:
                topic_container = driver.execute_script("return arguments[0].parentElement;", topic_el)
                if not topic_container:
                    topic_container = topic_el
            except Exception:
                topic_container = topic_el

        # Expand sub-sections
        finder._expand_subsections(topic_container)
        time.sleep(1.5)
        
        try:
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'end'});", topic_container)
            time.sleep(1.0)
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'start'});", topic_container)
            time.sleep(1.0)
        except Exception:
            pass
            
        # Collect cards and parse Worksheet IDs
        cards = finder._collect_cards(topic_container)
        ws_ids = []
        ws_titles = {}
        for card in cards:
            ws_id, ws_title = finder.extract_worksheet_id_and_title(card)
            if ws_id:
                if ws_id not in ws_ids:
                    ws_ids.append(ws_id)
                ws_titles[ws_id] = ws_title

        if target_ws_id not in ws_ids:
            log_msg(f"[ERROR] Worksheet ID '{target_ws_id}' not found under topic '{topic_name}'.")
            return False

        ws_title = ws_titles[target_ws_id]
        log_msg(f"Found target worksheet: {ws_title} ({target_ws_id})")
        
        screenshot_dir = os.path.join("screenshots", target_ws_id)
        os.makedirs(screenshot_dir, exist_ok=True)

        # Re-collect cards and find the matching card
        if is_sidebar:
            topic_container = driver.find_element(By.TAG_NAME, "body")
        else:
            try:
                topic_container = driver.execute_script("return arguments[0].parentElement;", topic_el)
                if not topic_container:
                    topic_container = topic_el
            except Exception:
                topic_container = topic_el
        cards = finder._collect_cards(topic_container)
        matching_card = None
        for card in cards:
            card_id, _ = finder.extract_worksheet_id_and_title(card)
            if card_id == target_ws_id:
                matching_card = card
                break
                
        if not matching_card:
            log_msg(f"[ERROR] Could not find card for Worksheet ID: {target_ws_id}")
            return False
            
        # Scroll card into view
        scroll_into_view(driver, matching_card)
        time.sleep(0.5)
        
        # Click Start or Resume to open the worksheet
        success = finder._click_start(matching_card, topic_name, ws_title)
        if not success:
            log_msg(f"[ERROR] Failed to open worksheet: {ws_title} ({target_ws_id})")
            return False
            
        # Capture screenshots of every question
        log_msg(f"Opened worksheet {target_ws_id} successfully. Capturing screenshots...")
        capture_question_screenshots_programmatic(driver, target_ws_id, log_msg)
        
        # Exit worksheet
        exit_success = exit_worksheet(driver)
        if not exit_success:
            log_msg("[WARN] Exit button not clicked successfully. Attempting fallback URL navigation...")
            driver.get(config.BASE_URL)
            time.sleep(5.0)
            
        log_msg(f"[SUCCESS] Finished capturing screenshots for Worksheet: {target_ws_id}")
        return True

    except Exception as exc:
        log_msg(f"[ERROR] Extraction error: {exc}")
        return False

    finally:
        config.HEADLESS = original_headless
        if driver is not None:
            try:
                driver.quit()
                log_msg("Browser closed.")
            except Exception:
                pass


def capture_question_screenshots_programmatic(driver: WebDriver, worksheet_id: str, log_callback) -> None:
    import os
    screenshot_dir = os.path.join("screenshots", worksheet_id)
    os.makedirs(screenshot_dir, exist_ok=True)

    def get_num_questions() -> int:
        js_code = """
        function findMaxQuestion() {
            let candidates = document.querySelectorAll('button, a, .lrn-btn, [class*="nav"]');
            let maxNum = 0;
            candidates.forEach(btn => {
                let clone = btn.cloneNode(true);
                let sr = clone.querySelectorAll('.sr-only, .lrn-sr-only, [class*="sr-only"], [class*="assistive"], [class*="accessible"]');
                sr.forEach(s => s.remove());
                
                let text = (clone.innerText || clone.textContent || "").trim();
                if (/^\\d+$/.test(text)) {
                    let num = parseInt(text, 10);
                    let rect = btn.getBoundingClientRect();
                    if (rect.top >= 0 && rect.top < 250 && rect.width > 5 && rect.height > 5) {
                        maxNum = Math.max(maxNum, num);
                    }
                }
            });
            return maxNum;
        }
        return findMaxQuestion();
        """
        try:
            return driver.execute_script(js_code)
        except Exception:
            return 0

    def click_question_dot(qNum: int) -> bool:
        js_code = """
        function clickDot(q) {
            let candidates = document.querySelectorAll('button, a, .lrn-btn, [class*="nav"]');
            for (let btn of candidates) {
                let clone = btn.cloneNode(true);
                let sr = clone.querySelectorAll('.sr-only, .lrn-sr-only, [class*="sr-only"], [class*="assistive"], [class*="accessible"]');
                sr.forEach(s => s.remove());
                
                let text = (clone.innerText || clone.textContent || "").trim();
                if (text === String(q)) {
                    let rect = btn.getBoundingClientRect();
                    if (rect.top >= 0 && rect.top < 250 && rect.width > 5 && rect.height > 5) {
                        btn.click();
                        return true;
                    }
                }
            }
            return false;
        }
        return clickDot(arguments[0]);
        """
        try:
            return driver.execute_script(js_code, qNum)
        except Exception:
            return False

    num_questions = 0
    start_time = time.time()
    while time.time() - start_time < 20:
        num_questions = get_num_questions()
        if num_questions > 0:
            break
        time.sleep(1)

    if num_questions == 0:
        log_callback("[WARN] No question navigation dots detected. Defaulting to 5 questions.")
        num_questions = 5
        
    log_callback(f"Detected {num_questions} questions. Starting capture...")
    
    for q_no in range(1, num_questions + 1):
        log_callback(f"Processing Question {q_no} of {num_questions}...")
        
        clicked = click_question_dot(q_no)
        if clicked:
            time.sleep(config.QUESTION_TRANSITION_DELAY)
        else:
            log_callback(f"[WARN] Could not click navigation dot for Question {q_no}")
        
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(config.QUESTION_SETTLE_DELAY)
        
        filename = f"Question_{q_no}.png"
        filepath = os.path.join(screenshot_dir, filename)
        try:
            driver.save_screenshot(filepath)
            log_callback(f"-> Captured: {filename}")
        except Exception as e:
            log_callback(f"[ERROR] Could not save screenshot for Question {q_no}: {e}")
            
    log_callback("Capture completed successfully.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print(_BANNER)
    if config.EMAIL in ("<YOUR_EMAIL>", "", None):
        print("[ERROR] Open config.py and set EMAIL and PASSWORD first.")
        sys.exit(1)
    run_automation()


if __name__ == "__main__":
    main()

