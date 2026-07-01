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
from logger import get_logger
from utils import (
    setup_driver_and_navigate,
    prompt_topic_name,
    prompt_worksheet_id,
    exit_worksheet,
    hold_browser,
    scroll_into_view,
    safe_click,
)
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
# Core pipeline
# ---------------------------------------------------------------------------

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
        # Browser setup and dashboard navigation
        driver = setup_driver_and_navigate()

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



def main() -> None:
    print(_BANNER)
    if config.EMAIL in ("<YOUR_EMAIL>", "", None):
        print("[ERROR] Open config.py and set EMAIL and PASSWORD first.")
        sys.exit(1)
    run_automation()


if __name__ == "__main__":
    main()
