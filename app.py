import os
import re
import sys
import io
import threading
from datetime import datetime

from dotenv import load_dotenv
# Load environment variables
load_dotenv()

import config

from ollama import Client
from PIL import Image
from flask import Flask, render_template, jsonify, request, Response, send_file
from pymongo import MongoClient
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

# Reconfigure stdout/stderr to use UTF-8 encoding to prevent UnicodeEncodeError on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

app = Flask(__name__)

# MongoDB connection details
mongo_client = MongoClient(config.MONGO_URI)
db = mongo_client[config.MONGO_DB]
collection = db["Worksheet_Report"]

# Thread lock to safely modify and read the analysis state
state_lock = threading.Lock()

# Stop event: set this to request graceful stop of the running analysis
stop_event = threading.Event()

# Global state dictionary representing tracking metrics
analysis_state = {
    "status": "Waiting",  # Waiting, Processing, Completed
    "total_worksheets": 0,
    "completed_worksheets": 0,
    "remaining_worksheets": 0,
    "total_questions": 0,
    "completed_questions": 0,
    "current_worksheet_id": "",
    "current_question_number": 0,
    "percent_complete": 0.0,
    "logs": [],
    "report": {},  # Format: { ws_id: { "Q1": response, "Q2": response, ... } }
    "total_issues": 0,
    "total_passed": 0,
    "start_time": None,
    "end_time": None,
    "execution_time_seconds": 0.0
}

def get_question_number(filename):
    match = re.search(r'Question_(\d+)', filename, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 0

def save_ws_answers(ws_id):
    try:
        ws_answers_coll = db[config.MONGO_ANSWERS_COLLECTION]
        
        # Read the topic name from topic.txt if it exists
        topic_name = "Unknown Topic"
        screenshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
        topic_path = os.path.join(screenshots_dir, ws_id, "topic.txt")
        if os.path.exists(topic_path):
            try:
                with open(topic_path, "r", encoding="utf-8") as f:
                    topic_name = f.read().strip()
            except Exception as e:
                print(f"Error reading topic.txt for {ws_id}: {e}")
        else:
            existing_ws_ans = ws_answers_coll.find_one({"worksheetID": ws_id})
            if existing_ws_ans and existing_ws_ans.get("topicName"):
                topic_name = existing_ws_ans["topicName"]
        
        # Query Worksheet_Report for all questions of this worksheet
        report_docs = list(collection.find({"worksheet_id": ws_id}))
        
        # Sort documents by question number
        report_docs.sort(key=lambda d: d.get("question_number", 0))
        
        # Build the document
        doc = {
            "topicName": topic_name,
            "worksheetID": ws_id
        }
        
        # Populate q1, q2, q3, q4, q5
        for i in range(1, 6):
            doc[f"q{i}"] = ""
            
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
                doc[f"q{q_num}"] = ans_value
                
        # Save or update in MongoDB WS_answers collection
        ws_answers_coll.update_one(
            {"worksheetID": ws_id},
            {"$set": doc},
            upsert=True
        )
        print(f"Successfully saved/updated WS_answers for worksheet {ws_id}")
    except Exception as e:
        print(f"Failed to save WS_answers for {ws_id}: {e}")

# Core AI Review Prompt
prompt = """
Act as a mathematics expert and perform a complete review.

For each question image:

- Verify whether the question is mathematically correct.
- Solve the question and identify the correct answer.
- Check whether the answer key (if visible) is correct.
- Check whether more than one option can be considered correct.
- Identify confusing, ambiguous, misleading, or poorly worded questions.
- Check whether students may get confused between two or more options.
- Verify that all options are distinct and that only one answer can reasonably be selected (unless the question explicitly allows multiple answers).
- Check whether the expected answer format is clearly specified (ordered pair, fraction, interval notation, etc.).
- Check for UI issues visible in the screenshot (hidden keypad, mobile-view issues, unclear labels, missing instructions, overlapping content, etc.).

If there is any issue, provide it in exactly this format:

Issue: <clear one-line description of the issue>

Examples:

Issue: The worksheet marks the correct slope of the chord as 1/3, but the mathematically correct answer is -2/3; therefore, the answer key is incorrect.

Issue: Both Option A and Option D have eccentricity 5/3, resulting in multiple correct answers in a single-select question.

Issue: The question does not specify the expected answer format; providing a hint to enter the focus as an ordered pair using parentheses, such as (x, y), would help avoid student confusion.

Issue: The keypad is not displayed for this question, making it difficult for students to enter their answer.

If NO issue exists, respond exactly in this format:

Check: Question and options are mathematically correct; the correct answer is <answer>. The answer is unique, and no logical, ambiguity, multiple-answer, answer-key, or UI issues were found.

For True/False questions, provide the correct sequence (e.g., T, F, T, T) and report any answer-key mistakes.

Always double-check calculations before giving the final response.

CRITICAL MATH RENDERING INSTRUCTIONS:
- You must output all mathematical expressions, equations, formulas, fractions, and symbols in proper standard LaTeX format.
- DO NOT use plain text representations (e.g., do not write "x^2", "pi", "sqrt(x)", "1/2", "x1" in plain text).
- Wrap EVERY mathematical expression, symbol, variable, or equation in standard LaTeX delimiters:
  * Use $...$ for inline math (e.g., $x^2$, $\pi$, $\sqrt{x}$, $\frac{1}{2}$, $x_1$, $z_2$, $a \pm b$).
  * Use $$...$$ for display equations (e.g., $$|z_1 - z_2| = 5$$, $$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$$).
- Use proper standard LaTeX commands such as \frac{}{} for fractions, \sqrt{} for square roots, ^ for exponents, _ for subscripts, \overline{} for lines, \sum for summations, \int for integrals, \pi for Greek pi, \theta for Greek theta, etc.
- Never output escaped slashes (like \\frac or \\pi) in the raw text, as they are not interpreted correctly by the frontend. Always output a single backslash like \frac and \pi.
- Make all mathematical notation clean, readable, and structured like a premium textbook.
- Ensure your entire response is extremely short, concise, and direct. DO NOT output step-by-step derivations, long calculations, proofs, or verbose explanations. Just state the conclusion or describe the issue in one or two short sentences.

CRITICAL OUTPUT FORMAT RULES FOR DATABASE STORAGE:
At the very end of your response, on a new line, you must output exactly one of the following tags:
- If there is an issue with the question: [RESULT: Issue]
- If there is no issue, output: [RESULT: <correct_answer>]
  Format <correct_answer> strictly based on the following question type:
  1. Multiple Choice Questions (MCQ): Output ONLY the uppercase letter option (e.g., [RESULT: A], [RESULT: C]). Do NOT include any prefixes like "Option " or punctuation.
  2. True/False Matrix Tables: Output as a JSON list of strings (e.g., [RESULT: ["True", "False", "True", "False"]]). Use standard capitalization.
  3. Basic Numerical & Text Inputs: Output the exact number or text as a string value (e.g., [RESULT: 90], [RESULT: hello]). Do NOT wrap basic numerical/text inputs in LaTeX delimiters like $.
  4. Advanced Mathematical Expressions (MathQuill / LaTeX): Output in standard LaTeX format (e.g., [RESULT: \frac{3}{4}], [RESULT: x^2], [RESULT: \sqrt{5}], [RESULT: (x+2)(x-3)]). Do NOT wrap the correct answer inside $ or $$ delimiters within the [RESULT: ...] tag.
"""

# Global state dictionary for answering tracking metrics
answering_state = {
    "status": "Waiting", # Waiting, Processing, Completed, Failed
    "worksheet_id": "",
    "topic_name": "",
    "logs": [],
    "total_worksheets": 0,
    "completed_worksheets": 0,
    "current_worksheet_idx": 0,
    "remaining_worksheets": 0,
    "percent_complete": 0.0,
    "start_time": None
}

def run_pipeline_in_background(topic_name, worksheet_ids, skip_extraction):
    global analysis_state
    stop_event.clear()
    
    start_dt = datetime.now()
    total_ws = len(worksheet_ids)
    with state_lock:
        analysis_state["status"] = "Processing"
        analysis_state["start_time"] = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        analysis_state["end_time"] = None
        analysis_state["total_worksheets"] = total_ws
        analysis_state["completed_worksheets"] = 0
        analysis_state["remaining_worksheets"] = total_ws
        analysis_state["total_questions"] = 0
        analysis_state["completed_questions"] = 0
        analysis_state["current_worksheet_id"] = worksheet_ids[0] if total_ws > 0 else ""
        analysis_state["current_question_number"] = 0
        analysis_state["percent_complete"] = 0.0
        analysis_state["logs"] = []
        analysis_state["report"] = {}
        analysis_state["total_issues"] = 0
        analysis_state["total_passed"] = 0
        analysis_state["execution_time_seconds"] = 0.0

    for ws_idx, worksheet_id in enumerate(worksheet_ids):
        if stop_event.is_set():
            break
            
        with state_lock:
            analysis_state["current_worksheet_id"] = worksheet_id
            analysis_state["remaining_worksheets"] = total_ws - ws_idx

        def log_callback(msg, q_num=0):
            with state_lock:
                analysis_state["logs"].append({
                    "worksheet_id": worksheet_id,
                    "question_number": q_num,
                    "screenshot_name": f"Question_{q_num}.png" if q_num > 0 else "—",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ai_response": msg
                })

        # Step 1: Screenshot Extraction
        screenshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
        ws_dir_check = os.path.join(screenshots_dir, worksheet_id)
        existing_screenshots = []
        if os.path.isdir(ws_dir_check):
            existing_screenshots = [
                f for f in os.listdir(ws_dir_check)
                if f.lower().startswith("question_") and f.lower().endswith(".png")
            ]

        local_skip_extraction = skip_extraction
        if existing_screenshots:
            log_callback(f"✅ Found {len(existing_screenshots)} existing screenshot(s) for '{worksheet_id}'. Skipping extraction.")
            local_skip_extraction = True

        if not local_skip_extraction:
            log_callback(f"Starting screenshot extraction phase for '{worksheet_id}' (headless mode)...")
            try:
                from main import extract_screenshots_for_worksheet
                success = extract_screenshots_for_worksheet(topic_name, worksheet_id, headless=True, log_callback=log_callback)
                if not success:
                    log_callback(f"[ERROR] Screenshot extraction failed for '{worksheet_id}'. Skipping to next worksheet.")
                    with state_lock:
                        analysis_state["completed_worksheets"] += 1
                    continue
            except Exception as e:
                log_callback(f"[ERROR] Exception during screenshot extraction for '{worksheet_id}': {e}")
                with state_lock:
                    analysis_state["completed_worksheets"] += 1
                continue
        else:
            log_callback(f"Skipping screenshot extraction phase for '{worksheet_id}'. Using existing images.")

        ws_dir = os.path.join(screenshots_dir, worksheet_id)
        if not os.path.exists(ws_dir):
            log_callback(f"[ERROR] Screenshots directory for worksheet '{worksheet_id}' does not exist: {ws_dir}")
            with state_lock:
                analysis_state["completed_worksheets"] += 1
            continue

        try:
            with open(os.path.join(ws_dir, "topic.txt"), "w", encoding="utf-8") as f:
                f.write(topic_name)
        except Exception as e:
            log_callback(f"[WARN] Failed to write topic.txt: {e}")

        # Find screenshots
        files = [f for f in os.listdir(ws_dir) if f.lower().startswith("question_") and f.lower().endswith(".png")]
        files.sort(key=get_question_number)
        
        total_q = len(files)
        if total_q == 0:
            log_callback(f"[ERROR] No screenshots found for worksheet '{worksheet_id}'. Skipping.")
            with state_lock:
                analysis_state["completed_worksheets"] += 1
            continue

        with state_lock:
            analysis_state["total_questions"] += total_q
            analysis_state["report"][worksheet_id] = {}

        # Step 2: AI Analysis
        log_callback(f"Starting AI review and answer generation phase for '{worksheet_id}'...")
        
        MODEL_NAME = config.AI_MODEL
        client = Client(
            host=config.OLLAMA_BASE_URL,
            headers={'Authorization': f"Bearer {config.OLLAMA_API_KEY}"}
        )
        
        completed_q_count = 0
        def _analyze_single_image(filename):
            nonlocal completed_q_count
            if stop_event.is_set():
                return

            q_num = get_question_number(filename)
            with state_lock:
                analysis_state["current_question_number"] = q_num

            img_path = os.path.join(ws_dir, filename)

            attempt = 0
            retry_delay = 10
            while True:
                attempt += 1
                try:
                    response = client.chat(
                        model=MODEL_NAME,
                        messages=[
                            {
                                "role": "user",
                                "content": prompt,
                                "images": [img_path]
                            }
                        ]
                    )
                    if response and "message" in response and "content" in response["message"]:
                        ai_text = response["message"]["content"]
                    break
                except Exception as e:
                    err_msg = str(e)
                    is_permanent = "SAFETY" in err_msg or "safety" in err_msg.lower() or "INVALID_ARGUMENT" in err_msg
                    if is_permanent:
                        if "SAFETY" in err_msg or "safety" in err_msg.lower():
                            ai_text = "❌ Model refused to process this image due to safety filters."
                        else:
                            ai_text = f"❌ Model error: {err_msg.splitlines()[0][:180]}"
                        break
                    
                    is_rate_limit = "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower() or "limit" in err_msg.lower()
                    is_connection = "connection" in err_msg.lower() or "reach" in err_msg.lower() or "failed to connect" in err_msg.lower() or "disconnected" in err_msg.lower() or "socket" in err_msg.lower()
                    is_busy = "busy" in err_msg.lower() or "overloaded" in err_msg.lower() or "503" in err_msg or "unavailable" in err_msg.lower()
                    
                    if is_rate_limit:
                        status_msg = "⏳ AI server is busy. Retrying..."
                    elif is_connection:
                        status_msg = "⏳ Connection lost. Retrying..."
                    elif is_busy:
                        status_msg = "⏳ Waiting for the AI model to become available..."
                    else:
                        status_msg = "⏳ Waiting for AI response..."
                    
                    log_callback(status_msg, q_num)
                    time.sleep(retry_delay)

            is_issue = "Issue:" in ai_text or ai_text.startswith("❌")
            analysis_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if not ai_text.startswith("❌"):
                doc = {
                    "worksheet_id": worksheet_id,
                    "question_number": q_num,
                    "image_name": filename,
                    "ai_response": ai_text,
                    "analysis_time": analysis_time_str,
                    "status": "Issue" if "Issue:" in ai_text else "Passed",
                    "created_timestamp": datetime.now()
                }
                try:
                    collection.insert_one(doc)
                except Exception as e:
                    print(f"Failed to write to MongoDB: {e}")

            with state_lock:
                if is_issue:
                    analysis_state["total_issues"] += 1
                else:
                    analysis_state["total_passed"] += 1

                analysis_state["report"][worksheet_id][f"Q{q_num}"] = ai_text
                completed_q_count += 1
                analysis_state["completed_questions"] += 1
                if analysis_state["total_questions"] > 0:
                    analysis_state["percent_complete"] = (analysis_state["completed_questions"] / analysis_state["total_questions"]) * 100.0

                analysis_state["logs"].append({
                    "worksheet_id": worksheet_id,
                    "question_number": q_num,
                    "screenshot_name": filename,
                    "timestamp": analysis_time_str,
                    "ai_response": ai_text
                })

        # Process up to 3 images concurrently
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_analyze_single_image, fn): fn for fn in files}
            for future in as_completed(futures):
                if stop_event.is_set():
                    with state_lock:
                        analysis_state["status"] = "Stopped"
                        analysis_state["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        analysis_state["execution_time_seconds"] = (datetime.now() - start_dt).total_seconds()
                    executor.shutdown(wait=False, cancel_futures=True)
                    return
                try:
                    future.result()
                except Exception as exc:
                    log_callback(f"❌ Unexpected error processing image: {exc}")

        save_ws_answers(worksheet_id)

        with state_lock:
            analysis_state["completed_worksheets"] += 1

    end_dt = datetime.now()
    execution_time = (end_dt - start_dt).total_seconds()
    
    with state_lock:
        if stop_event.is_set():
            analysis_state["status"] = "Stopped"
        else:
            analysis_state["status"] = "Completed"
            analysis_state["percent_complete"] = 100.0
        analysis_state["end_time"] = end_dt.strftime("%Y-%m-%d %H:%M:%S")
        analysis_state["execution_time_seconds"] = execution_time


def run_answering_in_background(topic_name, ws_ids, headless):
    global answering_state
    
    with state_lock:
        answering_state["status"] = "Processing"
        answering_state["worksheet_id"] = ", ".join(ws_ids) if ws_ids else ""
        answering_state["topic_name"] = topic_name
        answering_state["logs"] = []
        answering_state["total_worksheets"] = len(ws_ids)
        answering_state["completed_worksheets"] = 0
        answering_state["current_worksheet_idx"] = 0
        answering_state["remaining_worksheets"] = len(ws_ids)
        answering_state["percent_complete"] = 0.0
        answering_state["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
    def log_callback(msg):
        with state_lock:
            answering_state["logs"].append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "message": msg
            })
            
    def state_updater(current_ws_id, current_idx, completed, remaining, percent):
        with state_lock:
            answering_state["worksheet_id"] = current_ws_id
            answering_state["current_worksheet_idx"] = current_idx
            answering_state["completed_worksheets"] = completed
            answering_state["remaining_worksheets"] = remaining
            answering_state["percent_complete"] = percent

    try:
        from main_answering import run_answering_for_worksheets
        success = run_answering_for_worksheets(
            topic_name,
            ws_ids,
            headless=headless,
            log_callback=log_callback,
            state_updater=state_updater
        )
        
        with state_lock:
            if success:
                answering_state["status"] = "Completed"
            else:
                answering_state["status"] = "Failed"
    except Exception as e:
        log_callback(f"[ERROR] Exception occurred during answering execution: {e}")
        with state_lock:
            answering_state["status"] = "Failed"


def run_analysis_in_background():
    global analysis_state
    stop_event.clear()  # Reset stop signal at start
    
    start_dt = datetime.now()
    with state_lock:
        analysis_state["status"] = "Processing"
        analysis_state["start_time"] = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        analysis_state["end_time"] = None
        analysis_state["completed_worksheets"] = 0
        analysis_state["completed_questions"] = 0
        analysis_state["current_worksheet_id"] = ""
        analysis_state["current_question_number"] = 0
        analysis_state["percent_complete"] = 0.0
        analysis_state["logs"] = []
        analysis_state["report"] = {}
        analysis_state["total_issues"] = 0
        analysis_state["total_passed"] = 0
        analysis_state["execution_time_seconds"] = 0.0

    screenshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
    if not os.path.exists(screenshots_dir):
        with state_lock:
            analysis_state["status"] = "Waiting"
            analysis_state["logs"].append({
                "worksheet_id": "SYSTEM",
                "question_number": 0,
                "screenshot_name": "",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ai_response": f"Error: Screenshots directory not found: {screenshots_dir}"
            })
        return

    # Find and sort worksheets
    worksheet_ids = [d for d in os.listdir(screenshots_dir) if os.path.isdir(os.path.join(screenshots_dir, d))]
    worksheet_ids.sort()

    total_ws = len(worksheet_ids)
    total_q = 0
    all_worksheet_files = {}

    for ws_id in worksheet_ids:
        ws_dir = os.path.join(screenshots_dir, ws_id)
        files = [f for f in os.listdir(ws_dir) if f.lower().startswith("question_") and f.lower().endswith(".png")]
        files.sort(key=get_question_number)
        all_worksheet_files[ws_id] = files
        total_q += len(files)

    with state_lock:
        analysis_state["total_worksheets"] = total_ws
        analysis_state["remaining_worksheets"] = total_ws
        analysis_state["total_questions"] = total_q

    if total_q == 0:
        with state_lock:
            analysis_state["status"] = "Completed"
            analysis_state["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            analysis_state["logs"].append({
                "worksheet_id": "SYSTEM",
                "question_number": 0,
                "screenshot_name": "None",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ai_response": "No worksheets present in the screenshots directory."
            })
        return

    # Ollama Client setup
    MODEL_NAME = config.AI_MODEL
    
    client = Client(
        host=config.OLLAMA_BASE_URL,
        headers={'Authorization': f"Bearer {config.OLLAMA_API_KEY}"}
    )
    
    completed_q_count = 0
    completed_ws_count = 0

    for ws_id in worksheet_ids:
        # Check if stop was requested
        if stop_event.is_set():
            with state_lock:
                analysis_state["status"] = "Stopped"
                analysis_state["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                analysis_state["execution_time_seconds"] = (datetime.now() - start_dt).total_seconds()
            return
        # Check if this worksheet was already analyzed and saved in MongoDB
        existing_docs = list(collection.find({"worksheet_id": ws_id}))
        
        if len(existing_docs) > 0:
            # Skip worksheet: populate tracking state silently, only show ONE log message
            with state_lock:
                analysis_state["current_worksheet_id"] = ws_id
                analysis_state["report"][ws_id] = {}
                # Single summary log — no per-question spam
                analysis_state["logs"].append({
                    "worksheet_id": ws_id,
                    "question_number": 0,
                    "screenshot_name": "—",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ai_response": f"✅ Already completed. Skipping AI analysis."
                })

            # Update counts and report silently (no extra log entries)
            for doc in existing_docs:
                q_num = doc["question_number"]
                ai_text = doc["ai_response"]
                is_issue = doc.get("status", "Passed") == "Issue"
                
                with state_lock:
                    if is_issue:
                        analysis_state["total_issues"] += 1
                    else:
                        analysis_state["total_passed"] += 1
                        
                    analysis_state["report"][ws_id][f"Q{q_num}"] = ai_text
                    
                    completed_q_count += 1
                    analysis_state["completed_questions"] = completed_q_count
                    analysis_state["percent_complete"] = (completed_q_count / total_q) * 100.0

            completed_ws_count += 1
            with state_lock:
                analysis_state["completed_worksheets"] = completed_ws_count
                analysis_state["remaining_worksheets"] = total_ws - completed_ws_count
            save_ws_answers(ws_id)
            continue

        # Otherwise, process worksheet sequentially using Gemini AI
        with state_lock:
            analysis_state["current_worksheet_id"] = ws_id
            analysis_state["report"][ws_id] = {}

        files = all_worksheet_files[ws_id]

        def _analyze_ws_image(filename, _ws_id=ws_id):
            """Analyze one image for multi-worksheet mode. Runs inside a thread pool."""
            nonlocal completed_q_count
            if stop_event.is_set():
                return

            q_num = get_question_number(filename)
            with state_lock:
                analysis_state["current_question_number"] = q_num

            img_path = os.path.join(screenshots_dir, _ws_id, filename)

            attempt = 0
            retry_delay = 10
            while True:
                attempt += 1
                try:
                    response = client.chat(
                        model=MODEL_NAME,
                        messages=[
                            {
                                "role": "user",
                                "content": prompt,
                                "images": [img_path]
                            }
                        ]
                    )
                    if response and "message" in response and "content" in response["message"]:
                        ai_text = response["message"]["content"]
                    break
                except Exception as e:
                    err_msg = str(e)
                    is_permanent = "SAFETY" in err_msg or "safety" in err_msg.lower() or "INVALID_ARGUMENT" in err_msg
                    if is_permanent:
                        if "SAFETY" in err_msg or "safety" in err_msg.lower():
                            ai_text = "❌ Model refused to process this image due to safety filters."
                        else:
                            ai_text = f"❌ Model error: {err_msg.splitlines()[0][:180]}"
                        break
                    
                    is_rate_limit = "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower() or "limit" in err_msg.lower()
                    is_connection = "connection" in err_msg.lower() or "reach" in err_msg.lower() or "failed to connect" in err_msg.lower() or "disconnected" in err_msg.lower() or "socket" in err_msg.lower()
                    is_busy = "busy" in err_msg.lower() or "overloaded" in err_msg.lower() or "503" in err_msg or "unavailable" in err_msg.lower()
                    
                    if is_rate_limit:
                        status_msg = "⏳ AI server is busy. Retrying..."
                    elif is_connection:
                        status_msg = "⏳ Connection lost. Retrying..."
                    elif is_busy:
                        status_msg = "⏳ Waiting for the AI model to become available..."
                    else:
                        status_msg = "⏳ Waiting for AI response..."
                    
                    with state_lock:
                        analysis_state["logs"].append({
                            "worksheet_id": _ws_id,
                            "question_number": q_num,
                            "screenshot_name": filename,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "ai_response": status_msg
                        })
                    time.sleep(retry_delay)

            is_issue = "Issue:" in ai_text or ai_text.startswith("❌")
            analysis_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Save results to MongoDB (skip error entries)
            if not ai_text.startswith("❌") and not ai_text.startswith("⏳"):
                doc = {
                    "worksheet_id": _ws_id,
                    "question_number": q_num,
                    "image_name": filename,
                    "ai_response": ai_text,
                    "analysis_time": analysis_time_str,
                    "status": "Issue" if "Issue:" in ai_text else "Passed",
                    "created_timestamp": datetime.now()
                }
                try:
                    collection.insert_one(doc)
                except Exception as e:
                    print(f"Failed to write to MongoDB: {e}")

            with state_lock:
                if is_issue:
                    analysis_state["total_issues"] += 1
                else:
                    analysis_state["total_passed"] += 1

                analysis_state["report"][_ws_id][f"Q{q_num}"] = ai_text

                completed_q_count += 1
                analysis_state["completed_questions"] = completed_q_count
                analysis_state["percent_complete"] = (completed_q_count / total_q) * 100.0

                analysis_state["logs"].append({
                    "worksheet_id": _ws_id,
                    "question_number": q_num,
                    "screenshot_name": filename,
                    "timestamp": analysis_time_str,
                    "ai_response": ai_text
                })

        # Process up to 3 images concurrently for this worksheet
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=3) as executor:
            ws_futures = {executor.submit(_analyze_ws_image, fn): fn for fn in files}
            for future in as_completed(ws_futures):
                if stop_event.is_set():
                    with state_lock:
                        analysis_state["status"] = "Stopped"
                        analysis_state["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        analysis_state["execution_time_seconds"] = (datetime.now() - start_dt).total_seconds()
                    executor.shutdown(wait=False, cancel_futures=True)
                    return
                try:
                    future.result()
                except Exception as exc:
                    with state_lock:
                        analysis_state["logs"].append({
                            "worksheet_id": ws_id,
                            "question_number": 0,
                            "screenshot_name": ws_futures[future],
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "ai_response": f"❌ Unexpected error: {exc}"
                        })

        completed_ws_count += 1
        with state_lock:
            analysis_state["completed_worksheets"] = completed_ws_count
            analysis_state["remaining_worksheets"] = total_ws - completed_ws_count
        save_ws_answers(ws_id)

    end_dt = datetime.now()
    execution_time = (end_dt - start_dt).total_seconds()
    
    with state_lock:
        analysis_state["status"] = "Completed"
        analysis_state["end_time"] = end_dt.strftime("%Y-%m-%d %H:%M:%S")
        analysis_state["execution_time_seconds"] = execution_time

# Serve the Thinkster logo
@app.route("/logo")
def serve_logo():
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thinkster_logo.jpg")
    return send_file(logo_path, mimetype="image/jpeg")

# Web App HTML Routes
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/reports")
def reports():
    return render_template("reports.html")

@app.route("/answering")
def answering_page():
    return render_template("answering.html")


@app.route("/reports/<worksheet_id>")
def worksheet_details(worksheet_id):
    return render_template("worksheet_details.html", worksheet_id=worksheet_id)

@app.route("/reports/answering/<worksheet_id>")
def answering_worksheet_details(worksheet_id):
    return render_template("answering_report_details.html", worksheet_id=worksheet_id)

@app.route("/check/<worksheet_id>")
def check_worksheet(worksheet_id):
    return render_template("check.html", worksheet_id=worksheet_id)

@app.route("/screenshots/<worksheet_id>/<filename>")
def serve_screenshot(worksheet_id, filename):
    screenshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
    file_path = os.path.join(screenshots_dir, worksheet_id, filename)
    if os.path.exists(file_path):
        return send_file(file_path)
    else:
        return "Not Found", 404

# API Routes
@app.route("/api/start", methods=["POST"])
def start_analysis():
    global analysis_state
    
    with state_lock:
        if analysis_state["status"] == "Processing":
            return jsonify({"status": "error", "message": "Analysis/Extraction is already running."}), 400
            
    data = request.get_json() or {}
    topic_name = data.get("topic_name", "").strip()
    worksheet_id = data.get("worksheet_id", "").strip()
    worksheet_ids = data.get("worksheet_ids", [])
    skip_extraction = data.get("skip_extraction", False)
    
    if not worksheet_ids and worksheet_id:
        worksheet_ids = [worksheet_id]
        
    if topic_name and worksheet_ids:
        # Start unified pipeline: Extraction + Analysis for multiple worksheets
        thread = threading.Thread(target=run_pipeline_in_background, args=(topic_name, worksheet_ids, skip_extraction))
    else:
        # Fallback to original analysis workflow of scanned worksheets
        thread = threading.Thread(target=run_analysis_in_background)
        
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "started"})

@app.route("/api/db/answers/<worksheet_id>", methods=["GET"])
def get_db_answers(worksheet_id):
    try:
        ws_answers_coll = db["WS_answers"]
        doc = ws_answers_coll.find_one({"worksheetID": worksheet_id})
        if not doc:
            return jsonify({"error": f"No answers found for worksheet {worksheet_id}."}), 404
        doc["_id"] = str(doc["_id"])
        return jsonify(doc)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/save_answers/<worksheet_id>", methods=["POST"])
def save_db_answers(worksheet_id):
    try:
        data = request.get_json()
        ws_answers_coll = db["WS_answers"]
        update_fields = {}
        for k, v in data.items():
            if k.startswith("q") or k == "topicName":
                update_fields[k] = v
        
        ws_answers_coll.update_one(
            {"worksheetID": worksheet_id},
            {"$set": update_fields},
            upsert=True
        )
        return jsonify({"status": "saved"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def get_worksheets_under_topic(topic_name):
    from selenium.webdriver.common.by import By
    from utils import setup_driver_and_navigate, is_sidebar_element, scroll_into_view, safe_click
    from topic_worksheet_finder import TopicWorksheetFinder
    import time
    
    driver = None
    try:
        # Launch browser in headless mode
        driver = setup_driver_and_navigate()
        finder = TopicWorksheetFinder(driver)
        
        # Locate the topic
        topic_el = finder._find_topic_element(topic_name)
        if not topic_el:
            print(f"Topic '{topic_name}' not found on dashboard.")
            return []
            
        is_sidebar = is_sidebar_element(driver, topic_el)
        if is_sidebar:
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
        
        # Scroll topic_container to force lazy load of cards
        try:
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'end'});", topic_container)
            time.sleep(1.0)
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'start'});", topic_container)
            time.sleep(1.0)
        except Exception:
            pass
            
        # Collect cards and parse Worksheet IDs
        cards = finder._collect_cards(topic_container)
        worksheets = []
        seen_ids = set()
        for card in cards:
            ws_id, ws_title = finder.extract_worksheet_id_and_title(card)
            if ws_id and ws_id not in seen_ids:
                seen_ids.add(ws_id)
                worksheets.append({
                    "id": ws_id,
                    "title": ws_title
                })
        return worksheets
    except Exception as e:
        print(f"Error fetching worksheets for topic '{topic_name}': {e}")
        raise e
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

@app.route("/api/fetch_worksheets", methods=["POST"])
def fetch_worksheets():
    try:
        data = request.get_json() or {}
        topic_name = data.get("topic_name", "").strip()
        from_answering = data.get("from_answering", False)
        if not topic_name:
            return jsonify({"error": "Missing topic_name"}), 400
            
        worksheets = get_worksheets_under_topic(topic_name)
        
        if from_answering:
            report_coll = db["Worksheet_Report"]
            valid_ws_ids = set(report_coll.distinct("worksheet_id"))
            worksheets = [ws for ws in worksheets if ws["id"] in valid_ws_ids]
            
        return jsonify({"status": "success", "worksheets": worksheets})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/run_answering", methods=["POST"])
def start_answering():
    global answering_state
    try:
        data = request.get_json() or {}
        ws_id = data.get("worksheet_id")
        ws_ids = data.get("worksheet_ids", [])
        topic_name = data.get("topic_name")
        headless = data.get("headless", False)
        
        if not ws_ids and ws_id:
            ws_ids = [ws_id]
            
        if not ws_ids or not topic_name:
            return jsonify({"error": "Missing worksheet_ids or topic_name."}), 400
            
        # Check that all worksheet IDs are in the Worksheet_Report collection
        report_coll = db["Worksheet_Report"]
        valid_ws_ids = set(report_coll.distinct("worksheet_id"))
        for w_id in ws_ids:
            if w_id not in valid_ws_ids:
                return jsonify({"error": f"Worksheet {w_id} is not present in the reports."}), 400
                
        with state_lock:
            if answering_state["status"] == "Processing":
                return jsonify({"error": "Answering automation is already running."}), 400
                
        thread = threading.Thread(target=run_answering_in_background, args=(topic_name, ws_ids, headless))
        thread.daemon = True
        thread.start()
        
        return jsonify({"status": "started"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/answering/status", methods=["GET"])
def get_answering_status():
    global answering_state
    with state_lock:
        state_copy = dict(answering_state)
    return jsonify(state_copy)


@app.route("/api/reset", methods=["POST"])
def reset_dashboard():
    global analysis_state
    with state_lock:
        if analysis_state["status"] == "Processing":
            return jsonify({"status": "error", "message": "Cannot reset while analysis is running. Stop it first."}), 400
    stop_event.clear()
    with state_lock:
        analysis_state.update({
            "status": "Waiting",
            "total_worksheets": 0,
            "completed_worksheets": 0,
            "remaining_worksheets": 0,
            "total_questions": 0,
            "completed_questions": 0,
            "current_worksheet_id": "",
            "current_question_number": 0,
            "percent_complete": 0.0,
            "logs": [],
            "report": {},
            "total_issues": 0,
            "total_passed": 0,
            "start_time": None,
            "end_time": None,
            "execution_time_seconds": 0.0
        })
    return jsonify({"status": "reset"})

@app.route("/api/stop", methods=["POST"])
def stop_analysis():
    with state_lock:
        if analysis_state["status"] != "Processing":
            return jsonify({"status": "error", "message": "No analysis is currently running."}), 400
    stop_event.set()
    return jsonify({"status": "stopping"})

@app.route("/api/status", methods=["GET"])
def get_status():
    global analysis_state
    with state_lock:
        state_copy = dict(analysis_state)
        # Update elapsed execution time dynamically if still processing
        if state_copy["status"] == "Processing" and state_copy["start_time"]:
            start_dt = datetime.strptime(state_copy["start_time"], "%Y-%m-%d %H:%M:%S")
            state_copy["execution_time_seconds"] = (datetime.now() - start_dt).total_seconds()
    return jsonify(state_copy)

# MongoDB Query APIs
@app.route("/api/db/worksheets", methods=["GET"])
def get_db_worksheets():
    try:
        pipeline = [
            {
                "$group": {
                    "_id": "$worksheet_id",
                    "total_questions": {"$sum": 1},
                    "passed_count": {"$sum": {"$cond": [{"$eq": ["$status", "Passed"]}, 1, 0]}},
                    "issues_count": {"$sum": {"$cond": [{"$eq": ["$status", "Issue"]}, 1, 0]}}
                }
            },
            {
                "$project": {
                    "worksheet_id": "$_id",
                    "_id": 0,
                    "total_questions": 1,
                    "passed_count": 1,
                    "issues_count": 1
                }
            },
            {"$sort": {"worksheet_id": 1}}
        ]
        results = list(collection.aggregate(pipeline))
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/db/worksheet/<worksheet_id>", methods=["GET"])
def get_db_worksheet_details(worksheet_id):
    try:
        docs = list(collection.find({"worksheet_id": worksheet_id}))
        for d in docs:
            d["_id"] = str(d["_id"])
        return jsonify(docs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/db/answering_reports", methods=["GET"])
def get_db_answering_reports():
    try:
        answering_report_coll = db["Answering_Report"]
        results = list(answering_report_coll.find({}, {
            "_id": 0,
            "worksheet_id": 1,
            "topic_name": 1,
            "timestamp": 1,
            "total_questions": 1,
            "correct_count": 1,
            "incorrect_count": 1,
            "partially_correct_count": 1,
            "skipped_count": 1
        }))
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/db/answering_report/<worksheet_id>", methods=["GET"])
def get_db_answering_report_details(worksheet_id):
    try:
        answering_report_coll = db["Answering_Report"]
        doc = answering_report_coll.find_one({"worksheet_id": worksheet_id})
        if not doc:
            return jsonify({"error": f"No answering report found for worksheet {worksheet_id}."}), 404
        doc["_id"] = str(doc["_id"])
        if "created_at" in doc and isinstance(doc["created_at"], datetime):
            doc["created_at"] = doc["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        return jsonify(doc)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Report Exporters
@app.route("/api/export/html", methods=["GET"])
def export_html():
    global analysis_state
    with state_lock:
        state = dict(analysis_state)
    
    max_q = 0
    for ws_id, qs in state.get("report", {}).items():
        for q_key in qs.keys():
            try:
                q_num = int(q_key.replace("Q", ""))
                if q_num > max_q:
                    max_q = q_num
            except:
                pass
                
    header_cols = "".join(f"<th>Q{i}</th>" for i in range(1, max_q + 1))
    
    rows_html = ""
    for ws_id in sorted(state.get("report", {}).keys()):
        row_cells = f"<td style='font-weight:bold; color: #1e3a8a;'>{ws_id}</td>"
        for i in range(1, max_q + 1):
            cell_val = state["report"][ws_id].get(f"Q{i}", "")
            if cell_val:
                is_issue = "Issue:" in cell_val
                badge = f"<span class='badge {'badge-danger' if is_issue else 'badge-success'}'>{'Issue' if is_issue else 'Passed'}</span>"
                row_cells += f"<td>{badge}<div class='content'>{cell_val}</div></td>"
            else:
                row_cells += "<td>N/A</td>"
        rows_html += f"<tr>{row_cells}</tr>"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Worksheet AI Analysis Report</title>
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 40px; background: #f9fafb; color: #111827; }}
        h1 {{ color: #1e3a8a; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; }}
        .summary {{ display: flex; gap: 20px; margin-bottom: 30px; flex-wrap: wrap; }}
        .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e5e7eb; min-width: 150px; }}
        .card .lbl {{ font-size: 12px; color: #6b7280; text-transform: uppercase; }}
        .card .val {{ font-size: 20px; font-weight: bold; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e5e7eb; }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
        th {{ background: #f3f4f6; font-weight: bold; color: #374151; }}
        .badge {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-bottom: 5px; }}
        .badge-success {{ background: #d1fae5; color: #065f46; }}
        .badge-danger {{ background: #fee2e2; color: #991b1b; }}
        .content {{ font-size: 12px; white-space: pre-line; max-height: 150px; overflow-y: auto; color: #4b5563; }}
    </style>
</head>
<body>
    <h1>Worksheet AI Analysis Report</h1>
    <div class="summary">
        <div class="card"><div class="lbl">Total Worksheets</div><div class="val">{state.get('total_worksheets', 0)}</div></div>
        <div class="card"><div class="lbl">Total Questions</div><div class="val">{state.get('total_questions', 0)}</div></div>
        <div class="card"><div class="lbl">Issues Found</div><div class="val">{state.get('total_issues', 0)}</div></div>
        <div class="card"><div class="lbl">Passed Questions</div><div class="val">{state.get('total_passed', 0)}</div></div>
        <div class="card"><div class="lbl">Start Time</div><div class="val">{state.get('start_time') or '-'}</div></div>
        <div class="card"><div class="lbl">End Time</div><div class="val">{state.get('end_time') or '-'}</div></div>
        <div class="card"><div class="lbl">Execution Time</div><div class="val">{round(state.get('execution_time_seconds', 0), 1)}s</div></div>
    </div>
    <table>
        <thead>
            <tr>
                <th>Worksheet ID</th>
                {header_cols}
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>"""
    return Response(html_content, mimetype="text/html", headers={"Content-disposition": "attachment; filename=worksheet_analysis_report.html"})

def generate_pdf_table_html(title, worksheet_rows, max_q, stats_data=None):
    header_cols = "".join(f"<th>Q{i}</th>" for i in range(1, max_q + 1))
    
    rows_html = ""
    for ws_id, qs in sorted(worksheet_rows.items()):
        row_cells = f"<td style='font-weight:bold; color: #111827;'>{ws_id}</td>"
        for i in range(1, max_q + 1):
            cell_val = qs.get(f"Q{i}", "")
            if cell_val:
                is_issue = "Issue:" in cell_val
                badge_class = 'badge-danger' if is_issue else 'badge-success'
                badge_text = 'Issue' if is_issue else 'Passed'
                badge = f"<span class='badge {badge_class}'>{badge_text}</span>"
                row_cells += f"<td>{badge}<div class='content'>{cell_val}</div></td>"
            else:
                row_cells += "<td><span style='color: #6b7280;'>N/A</span></td>"
        rows_html += f"<tr>{row_cells}</tr>"

    stats_html = ""
    if stats_data:
        stats_html = f"""
        <div class="summary">
            <div class="card"><div class="lbl">Total Worksheets</div><div class="val">{stats_data.get('total_ws', 0)}</div></div>
            <div class="card"><div class="lbl">Total Questions</div><div class="val">{stats_data.get('total_q', 0)}</div></div>
            <div class="card"><div class="lbl">Issues Found</div><div class="val">{stats_data.get('issues_count', 0)}</div></div>
            <div class="card"><div class="lbl">Passed Questions</div><div class="val">{stats_data.get('passed_count', 0)}</div></div>
            <div class="card"><div class="lbl">Export Date</div><div class="val">{datetime.now().strftime("%Y-%m-%d %H:%M")}</div></div>
        </div>
        """

    pdf_print_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>
    <style>
        body {{
            font-family: 'Inter', sans-serif;
            margin: 30px;
            background: #F9FAFB;
            color: #111827;
        }}
        h1 {{
            font-size: 24px;
            font-weight: 800;
            color: #111827;
            border-bottom: 2px solid #E5E7EB;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .summary {{ display: flex; gap: 15px; margin-bottom: 30px; flex-wrap: wrap; }}
        .card {{
            background: #FFFFFF;
            border: 1px solid #E5E7EB;
            padding: 15px;
            border-radius: 8px;
            min-width: 140px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        .card .lbl {{ font-size: 11px; color: #6B7280; text-transform: uppercase; letter-spacing: 0.5px; }}
        .card .val {{ font-size: 16px; font-weight: bold; margin-top: 5px; color: #111827; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: #FFFFFF;
            border: 1px solid #E5E7EB;
            border-radius: 8px;
            overflow: hidden;
            font-size: 13px;
        }}
        th, td {{
            padding: 12px 14px;
            border: 1px solid #E5E7EB;
            vertical-align: top;
            text-align: left;
            color: #374151;
        }}
        th {{
            background: #F3F4F6;
            font-weight: 600;
            color: #111827;
        }}
        .badge {{
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: bold;
            margin-bottom: 6px;
        }}
        .badge-success {{ background: #D1FAE5; color: #065F46; border: 1px solid #A7F3D0; }}
        .badge-danger {{ background: #FEE2E2; color: #991B1B; border: 1px solid #FECACA; }}
        .content {{ font-size: 12px; white-space: pre-line; color: #4B5563; }}
        
        .no-print-btn {{
            font-family: inherit;
            font-weight: 600;
            font-size: 14px;
            padding: 8px 16px;
            border-radius: 8px;
            border: 1px solid #E5E7EB;
            background: #1F2937;
            color: white;
            cursor: pointer;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
            transition: all 0.2s;
        }}
        .no-print-btn:hover {{
            background: #111827;
        }}
        @media print {{
            body {{
                background: white !important;
                color: black !important;
                margin: 0;
            }}
            h1 {{
                color: black !important;
                border-bottom: 2px solid #ddd;
            }}
            .card {{
                background: white !important;
                border: 1px solid #ddd !important;
                box-shadow: none !important;
            }}
            .card .val {{ color: black !important; }}
            table {{
                background: white !important;
                border: 1px solid #ddd !important;
                color: black !important;
            }}
            th, td {{
                border: 1px solid #ddd !important;
                color: black !important;
            }}
            th {{ background: #f3f4f6 !important; }}
            .badge-success {{ background: #d1fae5 !important; color: #065f46 !important; border: 1px solid #a7f3d0 !important; }}
            .badge-danger {{ background: #fee2e2 !important; color: #991b1b !important; border: 1px solid #fecaca !important; }}
            .content {{ color: #374151 !important; }}
            .no-print {{ display: none; }}
            table {{ page-break-inside: auto; }}
            tr {{ page-break-inside: avoid; page-break-after: auto; }}
            thead {{ display: table-header-group; }}
        }}
    </style>
</head>
<body>
    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #E5E7EB; padding-bottom: 10px; margin-bottom: 20px;">
        <h1 style="border: none; margin: 0;">{title}</h1>
        <button class="no-print no-print-btn" onclick="window.print()">
            Print Report / Save to PDF
        </button>
    </div>
    
    {stats_html}
    
    <table>
        <thead>
            <tr>
                <th>Worksheet ID</th>
                {header_cols}
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    <script>
        window.onload = function() {{
            setTimeout(function() {{
                window.print();
            }}, 1200);
        }};
    </script>
</body>
</html>
"""
    return Response(pdf_print_content, mimetype="text/html")

@app.route("/api/export/pdf", methods=["GET"])
def export_pdf():
    global analysis_state
    with state_lock:
        state = dict(analysis_state)
    
    max_q = 0
    worksheet_rows = {}
    for ws_id, qs in state.get("report", {}).items():
        worksheet_rows[ws_id] = {}
        for q_key, val in qs.items():
            worksheet_rows[ws_id][q_key] = val
            try:
                q_num = int(q_key.replace("Q", ""))
                if q_num > max_q:
                    max_q = q_num
            except:
                pass

    stats = {
        "total_ws": len(worksheet_rows),
        "total_q": state.get("completed_questions", 0),
        "issues_count": state.get("total_issues", 0),
        "passed_count": state.get("total_passed", 0)
    }
    return generate_pdf_table_html("Live Worksheet AI Analysis Report", worksheet_rows, max_q, stats)

@app.route("/api/export/pdf/batch", methods=["GET"])
def export_pdf_batch():
    try:
        ids_str = request.args.get("ids", "")
        if not ids_str:
            return jsonify({"error": "Missing worksheet ids."}), 400
            
        worksheet_ids = [ws_id.strip() for ws_id in ids_str.split(",") if ws_id.strip()]
        if not worksheet_ids:
            return jsonify({"error": "Empty worksheet ids list."}), 400

        # Load all reviews for these worksheets from MongoDB
        docs = list(collection.find({"worksheet_id": {"$in": worksheet_ids}}))
        if len(docs) == 0:
            return jsonify({"error": "No records found in database for selected worksheets."}), 404
            
        # Group answers by worksheet ID and find maximum question number
        ws_answers = {}
        max_q = 0
        total_q = 0
        issues_count = 0
        passed_count = 0
        
        for doc in docs:
            ws_id = doc["worksheet_id"]
            q_num = doc.get("question_number", 0)
            if q_num > max_q:
                max_q = q_num
            
            if ws_id not in ws_answers:
                ws_answers[ws_id] = {}
            
            ai_res = doc.get("ai_response", "")
            ws_answers[ws_id][f"Q{q_num}"] = ai_res
            total_q += 1
            if doc.get("status", "Passed") == "Issue":
                issues_count += 1
            else:
                passed_count += 1

        stats = {
            "total_ws": len(ws_answers),
            "total_q": total_q,
            "issues_count": issues_count,
            "passed_count": passed_count
        }
        
        return generate_pdf_table_html("Consolidated Worksheet Analysis Report", ws_answers, max_q, stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/export/pdf/<worksheet_id>", methods=["GET"])
def export_pdf_single(worksheet_id):
    try:
        # Load all question review documents for this worksheet from MongoDB
        docs = list(collection.find({"worksheet_id": worksheet_id}))
        if len(docs) == 0:
            return jsonify({"error": f"No records found in database for Worksheet ID {worksheet_id}."}), 404
            
        # Group answers and find maximum question number
        ws_answers = {worksheet_id: {}}
        max_q = 0
        total_q = 0
        issues_count = 0
        passed_count = 0
        
        for doc in docs:
            q_num = doc.get("question_number", 0)
            if q_num > max_q:
                max_q = q_num
            ai_res = doc.get("ai_response", "")
            ws_answers[worksheet_id][f"Q{q_num}"] = ai_res
            total_q += 1
            if doc.get("status", "Passed") == "Issue":
                issues_count += 1
            else:
                passed_count += 1

        stats = {
            "total_ws": 1,
            "total_q": total_q,
            "issues_count": issues_count,
            "passed_count": passed_count
        }
        
        return generate_pdf_table_html(f"Worksheet Report for {worksheet_id}", ws_answers, max_q, stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/db/delete", methods=["POST"])
def delete_worksheets():
    try:
        data = request.get_json()
        if not data or "worksheet_ids" not in data:
            return jsonify({"error": "Missing worksheet_ids parameter."}), 400
            
        worksheet_ids = data["worksheet_ids"]
        if not isinstance(worksheet_ids, list):
            return jsonify({"error": "worksheet_ids must be a list."}), 400
            
        res = collection.delete_many({"worksheet_id": {"$in": worksheet_ids}})
        
        # Also delete from WS_answers
        try:
            ws_answers_coll = db["WS_answers"]
            ws_answers_coll.delete_many({"worksheetID": {"$in": worksheet_ids}})
        except Exception as db_err:
            print(f"Failed to delete from WS_answers: {db_err}")
            
        # Also delete from Answering_Report
        try:
            answering_report_coll = db["Answering_Report"]
            answering_report_coll.delete_many({"worksheet_id": {"$in": worksheet_ids}})
        except Exception as db_err:
            print(f"Failed to delete from Answering_Report: {db_err}")
            
        return jsonify({"status": "deleted", "count": res.deleted_count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
