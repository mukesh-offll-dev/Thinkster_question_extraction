# =============================================================================
# main_answering.py - Entry Point for Thinkster Elevate Question Answering
# =============================================================================
# Run with:
#     python main_answering.py
# =============================================================================

import sys
import os
import time
import json

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
from dashboard import click_start_learning, select_student
from utils import scroll_into_view, safe_click
from logger import get_logger
from login import launch_browser, login
from topic_worksheet_finder import TopicWorksheetFinder
from answering import answer_worksheet_questions

log = get_logger()


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

_BANNER = """
+==================================================================+
|     Thinkster Elevate  -  Worksheet Answering & Grading Tool      |
|     Answer Questions  ->  Grade Check  ->  Save Screenshots       |
+==================================================================+
"""

# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def prompt_topic_name() -> str:
    """Ask for the Topic Name and return it (loops until non-empty)."""
    print("\nEnter Topic Name:")
    while True:
        try:
            raw = input().strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
        if raw:
            return raw

def prompt_worksheet_id() -> str:
    """Ask for the Worksheet ID and return it (loops until non-empty)."""
    print("\nEnter Worksheet ID (e.g. AQCMXAL214):")
    while True:
        try:
            raw = input().strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
        if raw:
            return raw
        print("[WARN] Topic Name cannot be empty. Please try again.\n")


def exit_worksheet(driver: WebDriver) -> bool:
    """
    Finds and clicks the exit button in the top left corner of the worksheet screen.
    Also handles any confirmation dialog that might appear.
    """
    log.info("Attempting to exit the worksheet...")
    print("\nExiting current worksheet...")
    
    js_code = """
    function clickExit() {
        // 1. Find the exit button in the top-left area
        let candidates = Array.from(document.querySelectorAll('button, a, [role="button"], .lrn-btn, [class*="exit" i], [class*="back" i], [class*="close" i], [class*="home" i]'));
        
        let bestEl = null;
        let maxScore = -1;
        
        for (let el of candidates) {
            let rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.top <= 120 && rect.left >= 0 && rect.left <= 150) {
                let text = (el.innerText || el.textContent || "").trim().toLowerCase();
                let className = (el.className || "").toString().toLowerCase();
                let id = (el.id || "").toLowerCase();
                let aria = (el.getAttribute("aria-label") || "").toLowerCase();
                let title = (el.getAttribute("title") || "").toLowerCase();
                
                let score = 0;
                
                if (/exit|back|close|quit|leave|dashboard|home|x/i.test(text)) score += 20;
                if (/exit|back|close|quit|leave|dashboard|home|x/i.test(className)) score += 20;
                if (/exit|back|close|quit|leave|dashboard|home|x/i.test(id)) score += 20;
                if (/exit|back|close|quit|leave|dashboard|home|x/i.test(aria)) score += 20;
                if (/exit|back|close|quit|leave|dashboard|home|x/i.test(title)) score += 20;
                
                let isClickable = el.tagName === 'BUTTON' || el.tagName === 'A' || el.getAttribute('role') === 'button' || window.getComputedStyle(el).cursor === 'pointer';
                if (isClickable) score += 10;
                
                if (text === '←' || text === 'x' || text === 'X' || text === '<' || className.includes('arrow') || className.includes('icon')) {
                    score += 15;
                }
                
                if (score > maxScore) {
                    maxScore = score;
                    bestEl = el;
                }
            }
        }
        
        if (bestEl) {
            bestEl.click();
            return true;
        }
        
        // Fallback: search for elements with specific selectors in top-left
        let fallbacks = [
            'button.exit', 'a.exit', 'button.back', 'a.back',
            '[class*="exit" i]', '[class*="back" i]', '[class*="close" i]', '[class*="home" i]'
        ];
        for (let sel of fallbacks) {
            let els = document.querySelectorAll(sel);
            for (let el of els) {
                let rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.top <= 120 && rect.left >= 0 && rect.left <= 150) {
                    el.click();
                    return true;
                }
            }
        }
        return false;
    }
    return clickExit();
    """
    try:
        success = driver.execute_script(js_code)
        if success:
            log.info("Exit button clicked.")
            print("Exit button clicked.")
            
            # Wait a moment to see if a confirmation dialog appears
            time.sleep(2.0)
            
            # Check for confirmation modals/dialogs
            js_confirm_code = """
            function handleConfirmation() {
                let modals = Array.from(document.querySelectorAll('.modal, [class*="modal" i], [class*="dialog" i], [class*="overlay" i], [class*="popup" i]'));
                if (modals.length === 0) return false;
                
                // Look for confirmation buttons inside visible modals
                for (let modal of modals) {
                    let rect = modal.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        let buttons = Array.from(modal.querySelectorAll('button, a, [role="button"]'));
                        for (let btn of buttons) {
                            let text = (btn.innerText || btn.textContent || "").trim().toLowerCase();
                            if (/yes|confirm|exit|quit|leave|ok|sure|agree/i.test(text)) {
                                btn.click();
                                return true;
                            }
                        }
                    }
                }
                return false;
            }
            return handleConfirmation();
            """
            confirmed = driver.execute_script(js_confirm_code)
            if confirmed:
                log.info("Confirmation dialog handled.")
                print("Exit confirmation confirmed.")
            
            time.sleep(3.0)
            return True
        else:
            log.warning("Exit button not found via top-left area. Trying wider scan...")
            js_code_wider = """
            let els = document.querySelectorAll('button, a, [class*="exit" i], [class*="back" i], [class*="close" i]');
            for (let el of els) {
                let rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && rect.top <= 150 && rect.left <= 250) {
                    let text = (el.innerText || el.textContent || "").trim().toLowerCase();
                    if (/exit|back|close|quit|leave/i.test(text) || /exit|back|close/i.test(el.className)) {
                        el.click();
                        return true;
                    }
                }
            }
            return false;
            """
            success_wider = driver.execute_script(js_code_wider)
            if success_wider:
                log.info("Exit button clicked via wider scan.")
                print("Exit button clicked (wider search).")
                
                # Check for confirmation modals
                time.sleep(2.0)
                driver.execute_script(js_confirm_code)
                
                time.sleep(3.0)
                return True
            else:
                log.error("Could not find exit button.")
                print("[WARN] Could not find or click the exit button.")
                return False
    except Exception as e:
        log.error("Exception during exit button click: %s", e)
        return False


def run_automation() -> None:
    # Load answers dictionary
    answers_dict = {}
    if os.path.exists(config.ANSWERS_FILE):
        try:
            with open(config.ANSWERS_FILE, "r", encoding="utf-8") as f:
                answers_dict = json.load(f)
            log.info("Loaded answers for %d worksheets from %s", len(answers_dict), config.ANSWERS_FILE)
            print(f"Loaded answers for {len(answers_dict)} worksheets from {config.ANSWERS_FILE}")
        except Exception as e:
            log.error("Failed to load answers file %s: %s", config.ANSWERS_FILE, e)
            print(f"[ERROR] Failed to load answers file: {e}")
            return
    else:
        print(f"[ERROR] Answers file '{config.ANSWERS_FILE}' not found. Please create it first.")
        return
        
    if not answers_dict:
        print("[ERROR] Answers file is empty. Nothing to answer.")
        return

    # Get topic from user
    topic_name = prompt_topic_name()
    
    # Get worksheet ID from user
    target_ws_id = prompt_worksheet_id()
    
    # Validate worksheet ID exists in answers JSON
    if target_ws_id not in answers_dict:
        print(f"\n[ERROR] Worksheet ID '{target_ws_id}' does not have any answers defined in '{config.ANSWERS_FILE}'.")
        print("Please add answers for this worksheet to the JSON file first.")
        return

    driver: WebDriver | None = None

    try:
        # Browser + Login + Student + Dashboard
        driver = launch_browser()
        login(driver)
        select_student(driver)
        click_start_learning(driver)
        time.sleep(4.0)

        # Initialize finder and find topic
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
            log.info("Topic is sidebar menu item. Clicking to navigate...")
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
                
        if not ws_ids:
            print(f"\n[NOT FOUND] No worksheets with extractable IDs found under topic '{topic_name}'.\n")
            return

        # Filter worksheets to only those matching target_ws_id
        matching_ws_ids = [w for w in ws_ids if w == target_ws_id]
        if not matching_ws_ids:
            print(f"\n[NOT FOUND] Worksheet ID '{target_ws_id}' was not found under topic '{topic_name}'.")
            print("Available worksheets in this topic:")
            for ws_id in ws_ids:
                print(f" - {ws_titles[ws_id]} ({ws_id})")
            return

        print(f"Found {len(matching_ws_ids)} matching worksheets to answer in topic '{topic_name}':")
        for ws_id in matching_ws_ids:
            print(f" - {ws_titles[ws_id]} ({ws_id})")
        print()

        # Sequentially process worksheets
        for idx, ws_id in enumerate(matching_ws_ids):
            ws_title = ws_titles[ws_id]
            print(f"\n--- [{idx + 1}/{len(matching_ws_ids)}] Answering Worksheet: {ws_title} ({ws_id}) ---")
            
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
                continue
                
            # Scroll card into view
            scroll_into_view(driver, matching_card)
            time.sleep(0.5)
            
            # Click Start or Resume to open the worksheet
            success = finder._click_start(matching_card, topic_name, ws_title)
            if not success:
                print(f"[ERROR] Failed to open worksheet: {ws_title} ({ws_id})")
                continue
                
            # Answer questions
            print(f"Opened worksheet {ws_id} successfully. Answering questions...")
            answer_worksheet_questions(driver, ws_id, answers_dict[ws_id])
            
            # Exit worksheet and return to worksheet list
            exit_success = exit_worksheet(driver)
            if not exit_success:
                print(f"[WARN] Exit button not clicked successfully. Attempting fallback URL navigation...")
                driver.get(config.BASE_URL)
                time.sleep(5.0)
                select_student(driver)
                click_start_learning(driver)
                time.sleep(3.0)
                
            print(f"Finished processing Worksheet: {ws_id}\n")
            time.sleep(2.0)

        print("\nAll worksheets in the topic processed.")
        _hold_browser(driver)

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


def _hold_browser(driver: WebDriver) -> None:
    log.info("Browser remains open. Press Ctrl+C to quit.")
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        log.info("User quit.")


def main() -> None:
    print(_BANNER)
    if config.EMAIL in ("<YOUR_EMAIL>", "", None):
        print("[ERROR] Open config.py and set EMAIL and PASSWORD first.")
        sys.exit(1)
    run_automation()


if __name__ == "__main__":
    main()
