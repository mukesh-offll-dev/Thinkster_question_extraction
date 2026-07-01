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
        worksheet_results = {}
        for idx, ws_id in enumerate(matching_ws_ids):
            ws_title = ws_titles[ws_id]
            print(f"\n--- [{idx + 1}/{len(matching_ws_ids)}] Answering Worksheet: {ws_title} ({ws_id}) ---")
            
            # Re-locate and expand topic to ensure it is open and visible
            if not is_sidebar:
                topic_el = finder._find_topic_element(topic_name)
                if not topic_el:
                    print(f"[ERROR] Could not re-locate topic '{topic_name}' during iteration.")
                    worksheet_results[ws_id] = { "title": ws_title, "error": "Could not re-locate topic" }
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
                worksheet_results[ws_id] = { "title": ws_title, "error": "Could not find worksheet card" }
                continue
                
            # Scroll card into view
            scroll_into_view(driver, matching_card)
            time.sleep(0.5)
            
            # Click Start or Resume to open the worksheet
            success = finder._click_start(matching_card, topic_name, ws_title)
            if not success:
                print(f"[ERROR] Failed to open worksheet: {ws_title} ({ws_id})")
                worksheet_results[ws_id] = { "title": ws_title, "error": "Failed to open worksheet" }
                continue
                
            # Answer questions
            print(f"Opened worksheet {ws_id} successfully. Answering questions...")
            ws_results = answer_worksheet_questions(driver, ws_id, answers_dict[ws_id])
            worksheet_results[ws_id] = { "title": ws_title, "questions": ws_results }
            
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
        
        # Generate and save report if we have processed worksheets
        if worksheet_results:
            os.makedirs("reports", exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            report_filename = f"answering_report_{timestamp}.md"
            report_path = os.path.join("reports", report_filename)
            
            total_worksheets = len(worksheet_results)
            total_questions = 0
            correct_questions = 0
            incorrect_questions = 0
            partially_correct_questions = 0
            skipped_questions = 0
            discrepancy_count = 0
            
            for ws_id, data in worksheet_results.items():
                if "questions" in data:
                    for q_no, q_data in data["questions"].items():
                        total_questions += 1
                        status = q_data.get("status", "unknown")
                        if status == "correct":
                            correct_questions += 1
                        elif status == "incorrect":
                            incorrect_questions += 1
                            discrepancy_count += 1
                        elif status == "partially_correct":
                            partially_correct_questions += 1
                            discrepancy_count += 1
                        elif status == "skipped":
                            skipped_questions += 1
            
            lines = []
            lines.append(f"# Thinkster Elevate - Worksheet Answering & Grading Report")
            lines.append("")
            lines.append(f"- **Generated At:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"- **Topic:** {topic_name}")
            lines.append(f"- **Student:** {config.TARGET_STUDENT}")
            lines.append("")
            lines.append("## Summary Statistics")
            lines.append(f"- **Total Worksheets Processed:** {total_worksheets}")
            lines.append(f"- **Total Questions Answered:** {total_questions}")
            lines.append(f"  - ✅ **Correct:** {correct_questions}")
            lines.append(f"  - ❌ **Incorrect (Discrepancies):** {incorrect_questions}")
            lines.append(f"  - ⚠️ **Partially Correct:** {partially_correct_questions}")
            lines.append(f"  - ⏭️ **Skipped:** {skipped_questions}")
            lines.append("")
            
            if discrepancy_count > 0:
                lines.append(f"> [!WARNING]")
                lines.append(f"> Found **{discrepancy_count}** question(s) with discrepancy (graded incorrect/partially correct by website). Please review the answer key in `worksheet_answers.json`.")
                lines.append("")
            else:
                lines.append(f"> [!NOTE]")
                lines.append(f"> All submitted answers were graded correct. No discrepancies found!")
                lines.append("")
                
            lines.append("## Detailed Worksheet Breakdown")
            lines.append("")
            
            for ws_id, data in worksheet_results.items():
                lines.append(f"### Worksheet: {data['title']} ({ws_id})")
                if "error" in data:
                    lines.append(f"- **Status:** ❌ {data['error']}")
                    lines.append("")
                    continue
                    
                lines.append("| Question | Submitted Answer | Website Expected | Status | Graded Screenshot |")
                lines.append("| :--- | :--- | :--- | :--- | :--- |")
                
                for q_no, q_data in data["questions"].items():
                    status = q_data.get("status", "unknown").upper()
                    sub_ans = q_data.get("submitted_answer")
                    if isinstance(sub_ans, list):
                        sub_ans_str = ", ".join(map(str, sub_ans))
                    else:
                        sub_ans_str = str(sub_ans) if sub_ans is not None else "N/A"
                        
                    web_ans = q_data.get("website_correct_answer")
                    web_ans_str = str(web_ans) if web_ans else "-"
                    
                    status_display = status
                    if status == "CORRECT":
                        status_display = "✅ CORRECT"
                    elif status == "INCORRECT":
                        status_display = "❌ INCORRECT"
                    elif status == "PARTIALLY_CORRECT":
                        status_display = "⚠️ PARTIALLY CORRECT"
                    elif status == "SKIPPED":
                        status_display = "⏭️ SKIPPED"
                        
                    screenshot = q_data.get("screenshot_path", "")
                    if screenshot and os.path.exists(screenshot):
                        abs_screenshot_path = os.path.abspath(screenshot)
                        screenshot_link = f"[View Screenshot](file:///{abs_screenshot_path.replace(os.sep, '/')})"
                    else:
                        screenshot_link = "-"
                        
                    lines.append(f"| {q_no} | `{sub_ans_str}` | `{web_ans_str}` | {status_display} | {screenshot_link} |")
                lines.append("")
                
            with open(report_path, "w", encoding="utf-8") as rf:
                rf.write("\n".join(lines))
            
            print(f"\n==================================================================")
            print(f"                       GRADING REPORT SUMMARY                     ")
            print(f"==================================================================")
            print(f"Topic: {topic_name}")
            print(f"Total Worksheets: {total_worksheets}")
            print(f"Total Questions : {total_questions}")
            print(f"  - Correct     : {correct_questions}")
            print(f"  - Incorrect   : {incorrect_questions} (DISCREPANCY!)")
            print(f"  - Partial     : {partially_correct_questions}")
            print(f"  - Skipped     : {skipped_questions}")
            print(f"------------------------------------------------------------------")
            print(f"Detailed Markdown report saved to:")
            print(f"  {os.path.abspath(report_path)}")
            print(f"==================================================================\n")

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
