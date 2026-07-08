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
import re
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
    prompt_worksheet_id,
    exit_worksheet,
    hold_browser,
    scroll_into_view,
    safe_click,
    is_sidebar_element,
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

def load_answers_from_db(worksheet_id: str) -> Optional[dict]:
    """
    Attempts to retrieve answers for the given worksheet_id from MongoDB.
    Returns a dictionary formatted like: {"1": "A", "2": "5", "3": ["True", "True"]} or None if not found/error.
    """
    try:
        from pymongo import MongoClient
        client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
        # Ping the DB to fail quickly if connection is down
        client.admin.command('ping')
        
        db = client[config.MONGO_DB]
        ws_answers_coll = db[config.MONGO_ANSWERS_COLLECTION]
        
        doc = ws_answers_coll.find_one({"worksheetID": worksheet_id})
        if not doc:
            log.info("No answers found in MongoDB WS_answers for worksheet: %s", worksheet_id)
            return None
            
        answers = {}
        for key, val in doc.items():
            if key.startswith("q") and key[1:].isdigit():
                q_num = key[1:]  # e.g., "1"
                if val is not None and str(val).strip() != "":
                    if isinstance(val, bool):
                        val = str(val)
                    elif isinstance(val, list):
                        val = [str(x) if isinstance(x, bool) else x for x in val]
                    else:
                        val_str = str(val).strip()
                        if val_str.startswith("[") and val_str.endswith("]"):
                            try:
                                loaded = json.loads(val_str)
                                if isinstance(loaded, list):
                                    val = [str(x) if isinstance(x, bool) else x for x in loaded]
                                else:
                                    val = loaded
                            except Exception:
                                pass
                        elif "," in val_str or "\n" in val_str:
                            if not (val_str.startswith("(") and val_str.endswith(")")) and not (val_str.startswith("[") and val_str.endswith("]")):
                                parts = [p.strip() for p in re.split(r'[,\n]', val_str) if p.strip()]
                                val = [str(x) if isinstance(x, bool) else x for x in parts]
                        else:
                            val = val_str
                    answers[q_num] = val
        
        if answers:
            log.info("Successfully loaded answers for %s from MongoDB WS_answers: %s", worksheet_id, answers)
            return answers
            
        return None
    except Exception as e:
        log.error("Failed to retrieve answers from MongoDB for %s: %s", worksheet_id, e)
        print(f"[WARN] MongoDB connection or query failed: {e}")
        return None


def save_answering_report_to_db(worksheet_id: str, topic_name: str, results: dict, db_answers: dict = None) -> None:
    """
    Saves the automated answering and grading results for a worksheet to MongoDB.
    """
    try:
        from pymongo import MongoClient
        from datetime import datetime
        import re
        client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[config.MONGO_DB]
        answering_report_coll = db["Answering_Report"]
        
        # Calculate summary statistics
        total_q = len(results)
        correct_q = 0
        incorrect_q = 0
        partially_correct_q = 0
        skipped_q = 0
        
        questions_list = []
        for q_no, q_data in results.items():
            status = q_data.get("status", "unknown")
            if status == "correct":
                correct_q += 1
            elif status == "incorrect":
                incorrect_q += 1
            elif status == "partially_correct":
                partially_correct_q += 1
            elif status == "skipped":
                skipped_q += 1
                
            screenshot_path = q_data.get("screenshot_path")
            screenshot_name = os.path.basename(screenshot_path) if screenshot_path else None
            
            questions_list.append({
                "question_number": int(q_no),
                "submitted_answer": q_data.get("submitted_answer"),
                "website_correct_answer": q_data.get("website_correct_answer"),
                "status": status,
                "screenshot_name": screenshot_name
            })
            
        doc = {
            "worksheet_id": worksheet_id,
            "topic_name": topic_name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_questions": total_q,
            "correct_count": correct_q,
            "incorrect_count": incorrect_q,
            "partially_correct_count": partially_correct_q,
            "skipped_count": skipped_q,
            "questions": questions_list,
            "created_at": datetime.now()
        }
        
        # Upsert report by worksheet_id
        answering_report_coll.update_one(
            {"worksheet_id": worksheet_id},
            {"$set": doc},
            upsert=True
        )
        log.info("Successfully saved answering report to MongoDB for worksheet: %s", worksheet_id)

        # 1. Update Worksheet_Report for incorrect/partially_correct questions
        worksheet_report_coll = db["Worksheet_Report"]
        
        def format_answer_for_msg(ans):
            if ans is None:
                return "None"
            if isinstance(ans, list):
                ans_str = ", ".join(map(str, ans))
            else:
                ans_str = str(ans).strip()
            
            # Check if it is a single letter A-J, prefix it with "Option "
            if len(ans_str) == 1 and ans_str.upper() in "ABCDEFGHIJ":
                return f"Option {ans_str.upper()}"
            
            # Check if it starts with a letter like "A (-2)", but not already "Option"
            if not ans_str.lower().startswith("option"):
                if len(ans_str) >= 3 and ans_str[0].upper() in "ABCDEFGHIJ" and ans_str[1] in (" ", "("):
                    return f"Option {ans_str}"
            return ans_str

        def format_db_correct_answer(ans):
            if ans is None:
                return "None"
            if isinstance(ans, list):
                ans_str = ", ".join(map(str, ans))
            else:
                ans_str = str(ans).strip()
            
            # Handle '|frac' and '|sqrt' syntax from the user requirement
            ans_str = ans_str.replace("|frac", "\\frac").replace("|sqrt", "\\sqrt")
            
            # Check if it is a LaTeX mathematical expression or fraction
            has_latex = "\\" in ans_str or "frac" in ans_str or "sqrt" in ans_str
            
            if has_latex and not (ans_str.startswith("$") and ans_str.endswith("$")):
                ans_str = f"${ans_str}$"
            return ans_str
            
        for q_no, q_data in results.items():
            status = q_data.get("status", "unknown")
            if status in ("incorrect", "partially_correct"):
                website_correct_answer = q_data.get("website_correct_answer")
                has_web = website_correct_answer is not None and str(website_correct_answer).strip().lower() not in ("none", "")
                
                db_ans_formatted = ""
                if db_answers:
                    db_ans = db_answers.get(str(q_no))
                    if db_ans is not None:
                        db_ans_formatted = f" CORRECT ANS: {format_db_correct_answer(db_ans)}"

                if has_web:
                    correct_ans_formatted = format_answer_for_msg(website_correct_answer)
                    ai_text = f"Issue: Q{q_no}. The worksheet answer key is incorrect. The correct answer is {correct_ans_formatted}.{db_ans_formatted}"
                else:
                    ai_text = f"Issue: Q{q_no}. The worksheet answer key is incorrect.\n {db_ans_formatted}"
                analysis_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                worksheet_report_coll.update_one(
                    {"worksheet_id": worksheet_id, "question_number": int(q_no)},
                    {
                        "$set": {
                            "ai_response": ai_text,
                            "status": "Issue",
                            "analysis_time": analysis_time_str
                        },
                        "$setOnInsert": {
                            "image_name": f"Question_{q_no}.png",
                            "created_timestamp": datetime.now()
                        }
                    },
                    upsert=True
                )
                log.info("Updated Worksheet_Report for worksheet %s question %s to: %s", worksheet_id, q_no, ai_text)

        # 2. Sync changes to WS_answers collection
        ws_answers_coll = db[config.MONGO_ANSWERS_COLLECTION]
        
        # Read the topic name from screenshots directory if it exists, or fallback
        resolved_topic_name = topic_name
        screenshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
        topic_path = os.path.join(screenshots_dir, worksheet_id, "topic.txt")
        
        if not resolved_topic_name or resolved_topic_name == "Unknown Topic":
            if os.path.exists(topic_path):
                try:
                    with open(topic_path, "r", encoding="utf-8") as f:
                        resolved_topic_name = f.read().strip()
                except Exception:
                    pass
            else:
                existing_ws_ans = ws_answers_coll.find_one({"worksheetID": worksheet_id})
                if existing_ws_ans and existing_ws_ans.get("topicName") and existing_ws_ans["topicName"] != "Unknown Topic":
                    resolved_topic_name = existing_ws_ans["topicName"]
                    
        # Write/ensure topic.txt is there if resolved_topic_name is valid
        if resolved_topic_name and resolved_topic_name != "Unknown Topic":
            try:
                ws_dir = os.path.join(screenshots_dir, worksheet_id)
                os.makedirs(ws_dir, exist_ok=True)
                with open(topic_path, "w", encoding="utf-8") as f:
                    f.write(resolved_topic_name)
            except Exception:
                pass
                
        # Query Worksheet_Report for all questions of this worksheet
        report_docs = list(worksheet_report_coll.find({"worksheet_id": worksheet_id}))
        
        # Sort documents by question number
        report_docs.sort(key=lambda d: d.get("question_number", 0))
        
        # Build the WS_answers document
        ans_doc = {
            "topicName": resolved_topic_name,
            "worksheetID": worksheet_id
        }
        
        # Populate q1, q2, q3, q4, q5 with default empty string first
        for i in range(1, 6):
            ans_doc[f"q{i}"] = ""
            
        for rd in report_docs:
            q_num = rd.get("question_number", 0)
            ai_res = rd.get("ai_response", "")
            if q_num > 0:
                ans_value = ""
                if ai_res:
                    match = re.search(r'\[RESULT:\s*(.*?)\]', ai_res, re.IGNORECASE)
                    if match:
                        ans_value = match.group(1).strip()
                    elif "issue:" in ai_res.lower() or ai_res.startswith("❌"):
                        ans_value = "Issue"
                    else:
                        ans_match = re.search(r'correct\s+(?:answer|sequence)\s+is\s+(.*?)\.(?:\s+|$)', ai_res, re.IGNORECASE)
                        if ans_match:
                            ans_value = ans_match.group(1).strip()
                        else:
                            ans_value = ai_res.strip()
                ans_doc[f"q{q_num}"] = ans_value
                
        # Save or update in MongoDB WS_answers collection
        ws_answers_coll.update_one(
            {"worksheetID": worksheet_id},
            {"$set": ans_doc},
            upsert=True
        )
        log.info("Synced and updated WS_answers for worksheet %s", worksheet_id)
        
    except Exception as e:
        log.error("Failed to save answering report or sync Worksheet_Report to MongoDB for %s: %s", worksheet_id, e)
        print(f"[WARN] Failed to save answering report/sync to MongoDB: {e}")


def run_automation() -> None:
    # Get topic from user
    topic_name = prompt_topic_name()
    
    # Get worksheet ID from user
    target_ws_id = prompt_worksheet_id()
    
    # Attempt to load answers from MongoDB first
    print(f"\nConnecting to MongoDB to search for answers for worksheet '{target_ws_id}'...")
    answers = load_answers_from_db(target_ws_id)
    
    if answers:
        print(f"[SUCCESS] Loaded answers from MongoDB for worksheet '{target_ws_id}'.")
        # Check if any answer is marked as "Issue"
        issues = [q for q, a in answers.items() if a == "Issue"]
        if issues:
            print(f"[WARN] Note: Questions {', '.join(issues)} are marked as having Issues. Answering them might fail/input 'Issue'.")
    else:
        print("[WARN] Could not find answers in MongoDB or connection failed. Falling back to local answers file...")
        
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
            
        if target_ws_id not in answers_dict:
            print(f"\n[ERROR] Worksheet ID '{target_ws_id}' does not have any answers defined in '{config.ANSWERS_FILE}' or MongoDB.")
            print("Please run the analysis tool first or define answers locally.")
            return
            
        answers = answers_dict[target_ws_id]

    driver: Optional[WebDriver] = None

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
        is_sidebar = is_sidebar_element(driver, topic_el)

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
            ws_results = answer_worksheet_questions(driver, ws_id, answers)
            worksheet_results[ws_id] = { "title": ws_title, "questions": ws_results }
            save_answering_report_to_db(ws_id, topic_name, ws_results, answers)
            
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



def run_answering_for_worksheet(topic_name: str, target_ws_id: str, headless: bool = False, log_callback = None) -> bool:
    import os
    original_headless = config.HEADLESS
    config.HEADLESS = headless

    def log_msg(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
        log.info(msg)

    # Attempt to load answers from MongoDB first
    log_msg(f"Connecting to MongoDB to search for answers for worksheet '{target_ws_id}'...")
    answers = load_answers_from_db(target_ws_id)
    
    if answers:
        log_msg(f"[SUCCESS] Loaded answers from MongoDB for worksheet '{target_ws_id}'.")
        issues = [q for q, a in answers.items() if a == "Issue"]
        if issues:
            log_msg(f"[WARN] Note: Questions {', '.join(issues)} are marked as having Issues. Answering them might fail.")
    else:
        log_msg("[WARN] Could not find answers in MongoDB. Checking local answers file...")
        answers_dict = {}
        if os.path.exists(config.ANSWERS_FILE):
            try:
                with open(config.ANSWERS_FILE, "r", encoding="utf-8") as f:
                    answers_dict = json.load(f)
            except Exception as e:
                log_msg(f"[ERROR] Failed to load answers file: {e}")
                return False
        else:
            log_msg(f"[ERROR] Answers file '{config.ANSWERS_FILE}' not found.")
            return False
            
        if target_ws_id not in answers_dict:
            log_msg(f"[ERROR] Worksheet ID '{target_ws_id}' has no answers defined locally or in DB.")
            return False
        answers = answers_dict[target_ws_id]

    driver: Optional[WebDriver] = None

    try:
        log_msg(f"Launching browser (headless={headless})...")
        driver = setup_driver_and_navigate()

        from topic_worksheet_finder import TopicWorksheetFinder
        finder = TopicWorksheetFinder(driver)
        
        # Locate the topic
        topic_el = finder._find_topic_element(topic_name)
        if not topic_el:
            log_msg(f"[ERROR] Topic '{topic_name}' was not found on the dashboard.")
            return False

        log_msg(f"Topic Selected: {topic_name}")
        
        # Check if the topic element is part of a sidebar menu
        is_sidebar = is_sidebar_element(driver, topic_el)

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
        log_msg(f"Opening worksheet: {ws_title} ({target_ws_id})")
        
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
            
        scroll_into_view(driver, matching_card)
        time.sleep(0.5)
        
        success = finder._click_start(matching_card, topic_name, ws_title)
        if not success:
            log_msg(f"[ERROR] Failed to open worksheet: {ws_title} ({target_ws_id})")
            return False
            
        log_msg("Opened worksheet successfully. Answering questions...")
        ws_results = answer_worksheet_questions(driver, target_ws_id, answers)
        save_answering_report_to_db(target_ws_id, topic_name, ws_results)
        
        exit_success = exit_worksheet(driver)
        if not exit_success:
            log_msg("[WARN] Exit button not clicked successfully. Attempting fallback URL navigation...")
            driver.get(config.BASE_URL)
            time.sleep(5.0)
            
        log_msg(f"[SUCCESS] Finished answering Worksheet: {target_ws_id}")
        return True

    except Exception as exc:
        log_msg(f"[ERROR] Answering error: {exc}")
        return False

    finally:
        config.HEADLESS = original_headless
        if driver is not None:
            try:
                driver.quit()
                log_msg("Browser closed.")
            except Exception:
                pass


def run_answering_for_worksheets(topic_name: str, target_ws_ids: list[str], headless: bool = False, log_callback = None, state_updater = None, profile_suffix: Optional[str] = None) -> bool:
    import os
    original_headless = config.HEADLESS
    config.HEADLESS = headless

    def log_msg(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
        log.info(msg)

    # 1. Load answers for all worksheets
    all_answers = {}
    for ws_id in target_ws_ids:
        log_msg(f"Connecting to MongoDB to search for answers for worksheet '{ws_id}'...")
        answers = load_answers_from_db(ws_id)
        if answers:
            log_msg(f"[SUCCESS] Loaded answers from MongoDB for worksheet '{ws_id}'.")
        else:
            log_msg(f"[WARN] Could not find answers in MongoDB for '{ws_id}'. Checking local answers file...")
            answers_dict = {}
            if os.path.exists(config.ANSWERS_FILE):
                try:
                    with open(config.ANSWERS_FILE, "r", encoding="utf-8") as f:
                        answers_dict = json.load(f)
                except Exception as e:
                    log_msg(f"[ERROR] Failed to load answers file: {e}")
                    return False
            else:
                log_msg(f"[ERROR] Answers file '{config.ANSWERS_FILE}' not found.")
                return False
                
            if ws_id not in answers_dict:
                log_msg(f"[ERROR] Worksheet ID '{ws_id}' has no answers defined locally or in DB.")
                return False
            answers = answers_dict[ws_id]
        all_answers[ws_id] = answers

    driver: Optional[WebDriver] = None

    try:
        log_msg(f"Launching browser (headless={headless})...")
        driver = setup_driver_and_navigate(profile_suffix=profile_suffix)

        from topic_worksheet_finder import TopicWorksheetFinder
        finder = TopicWorksheetFinder(driver)
        
        # Locate the topic
        topic_el = finder._find_topic_element(topic_name)
        if not topic_el:
            log_msg(f"[ERROR] Topic '{topic_name}' was not found on the dashboard.")
            return False

        log_msg(f"Topic Selected: {topic_name}")
        
        # Check if the topic element is part of a sidebar menu
        is_sidebar = is_sidebar_element(driver, topic_el)

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

        completed_count = 0
        total_worksheets = len(target_ws_ids)
        
        for idx, target_ws_id in enumerate(target_ws_ids):
            log_msg(f"--- Processing Worksheet {idx + 1}/{total_worksheets}: {target_ws_id} ---")
            
            # Update state for progress tracking
            if state_updater:
                state_updater(
                    current_ws_id=target_ws_id,
                    current_idx=idx + 1,
                    completed=completed_count,
                    remaining=total_worksheets - completed_count,
                    percent=(completed_count / total_worksheets) * 100.0
                )

            # Re-locate and expand topic to ensure it is open and visible
            if not is_sidebar:
                topic_el = finder._find_topic_element(topic_name)
                if not topic_el:
                    log_msg(f"[ERROR] Could not re-locate topic '{topic_name}' during iteration.")
                    return False
                finder._expand_topic(topic_el)
                time.sleep(1.0)
                try:
                    topic_container = driver.execute_script("return arguments[0].parentElement;", topic_el)
                    if not topic_container:
                        topic_container = topic_el
                except Exception:
                    topic_container = topic_el
            else:
                topic_container = driver.find_element(By.TAG_NAME, "body")
                
            # Expand sub-sections to ensure all worksheet cards are visible
            finder._expand_subsections(topic_container)
            time.sleep(1.5)
            
            # Re-collect cards and find the matching card
            cards = finder._collect_cards(topic_container)
            matching_card = None
            ws_title = target_ws_id  # Fallback title
            for card in cards:
                card_id, card_title = finder.extract_worksheet_id_and_title(card)
                if card_id == target_ws_id:
                    matching_card = card
                    ws_title = card_title
                    break
            
            if not matching_card:
                log_msg(f"[ERROR] Could not find card for Worksheet ID: {target_ws_id}. Skipping.")
                continue
                
            scroll_into_view(driver, matching_card)
            time.sleep(0.5)
            
            # Click Start or Resume to open the worksheet
            success = finder._click_start(matching_card, topic_name, ws_title)
            if not success:
                log_msg(f"[ERROR] Failed to open worksheet: {ws_title} ({target_ws_id})")
                continue
                
            # Answer questions
            log_msg(f"Opened worksheet {target_ws_id} successfully. Answering questions...")
            ws_results = answer_worksheet_questions(driver, target_ws_id, all_answers[target_ws_id])
            save_answering_report_to_db(target_ws_id, topic_name, ws_results, all_answers[target_ws_id])
            
            # Exit worksheet and return to worksheet list
            exit_success = exit_worksheet(driver)
            if not exit_success:
                log_msg("[WARN] Exit button not clicked successfully. Attempting fallback URL navigation...")
                driver.get(config.BASE_URL)
                time.sleep(5.0)
                from dashboard import select_student, click_start_learning
                select_student(driver)
                click_start_learning(driver)
                time.sleep(3.0)
                
            log_msg(f"[SUCCESS] Finished answering Worksheet: {target_ws_id}")
            completed_count += 1
            time.sleep(2.0)

        # Update progress after all completed
        if state_updater:
            state_updater(
                current_ws_id="",
                current_idx=total_worksheets,
                completed=completed_count,
                remaining=0,
                percent=100.0
            )

        return True

    except Exception as exc:
        log_msg(f"[ERROR] Answering error: {exc}")
        return False

    finally:
        config.HEADLESS = original_headless
        if driver is not None:
            try:
                driver.quit()
                log_msg("Browser closed.")
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

