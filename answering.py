# =============================================================================
# answering.py – Worksheet Question Answering and Correctness Checking
# =============================================================================

import os
import time
import json
from typing import Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import NoSuchElementException

import config
from logger import get_logger
from utils import scroll_into_view, safe_click, get_element_html

log = get_logger()

# ---------------------------------------------------------------------------
# Navigation & Loading helpers
# ---------------------------------------------------------------------------

def wait_for_loading(driver: WebDriver) -> bool:
    """Wait for Learnosity loading screen to disappear."""
    log.info("Waiting for worksheet loading screen to disappear...")
    start_time = time.time()
    while time.time() - start_time < 45:
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            if "Loading worksheet..." not in body_text and "Loading" not in body_text:
                return True
        except Exception:
            pass
        time.sleep(1)
    log.error("Timed out waiting for worksheet to load.")
    return False


def get_question_dot_buttons(driver: WebDriver) -> list:
    """Return list of pagination dot button elements in order (sorted by question number)."""
    js_code = """
    function getQuestionDots() {
        let candidates = Array.from(document.querySelectorAll('button, a, .lrn-btn, [class*="nav"]'));
        let dots = [];
        for (let btn of candidates) {
            let clone = btn.cloneNode(true);
            let sr = clone.querySelectorAll('.sr-only, .lrn-sr-only, [class*="sr-only"], [class*="assistive"], [class*="accessible"]');
            sr.forEach(s => s.remove());
            
            let text = (clone.innerText || clone.textContent || "").trim();
            if (/^\\d+$/.test(text)) {
                let rect = btn.getBoundingClientRect();
                if (rect.top >= 0 && rect.top < 250 && rect.width > 5 && rect.height > 5) {
                    let classes = (btn.className || "").toString().toLowerCase();
                    let id = (btn.id || "").toLowerCase();
                    if (/keypad|keyboard|palette|formula|math/i.test(classes + " " + id)) {
                        continue;
                    }
                    dots.push({ el: btn, num: parseInt(text, 10) });
                }
            }
        }
        dots.sort((a, b) => a.num - b.num);
        return dots.map(d => d.el);
    }
    return getQuestionDots();
    """
    try:
        return driver.execute_script(js_code) or []
    except Exception as e:
        log.error("Failed to retrieve question dots: %s", e)
        return []


def get_current_question_number(driver: WebDriver) -> int:
    """Return the active question number based on navigation dots styling."""
    dots = get_question_dot_buttons(driver)
    for dot in dots:
        try:
            classes = dot.get_attribute("class") or ""
            # The active dot is larger (w-8 or text-base) and has border-blue-500
            if "border-blue-500" in classes or "w-8" in classes or "text-base" in classes:
                text = driver.execute_script(
                    "let clone = arguments[0].cloneNode(true); "
                    "let sr = clone.querySelectorAll('.sr-only, .lrn-sr-only, [class*=\"sr-only\"], [class*=\"assistive\"], [class*=\"accessible\"]'); "
                    "sr.forEach(s => s.remove()); "
                    "return (clone.innerText || clone.textContent || '').trim();",
                    dot
                )
                if text.isdigit():
                    return int(text)
        except Exception:
            pass
    return 1


def click_question_dot(driver: WebDriver, q_no: int) -> bool:
    """Click the navigation dot for a specific question number."""
    dots = get_question_dot_buttons(driver)
    for dot in dots:
        try:
            text = driver.execute_script(
                "let clone = arguments[0].cloneNode(true); "
                "let sr = clone.querySelectorAll('.sr-only, .lrn-sr-only, [class*=\"sr-only\"], [class*=\"assistive\"], [class*=\"accessible\"]'); "
                "sr.forEach(s => s.remove()); "
                "return (clone.innerText || clone.textContent || '').trim();",
                dot
            )
            if text.isdigit() and int(text) == q_no:
                scroll_into_view(driver, dot)
                driver.execute_script("arguments[0].click();", dot)
                return True
        except Exception as e:
            log.error("Failed to click dot %d: %s", q_no, e)
    return False


def wait_for_active_question(driver: WebDriver, target_q: int, timeout: int = 15) -> bool:
    """Wait until the target question number becomes active."""
    start = time.time()
    while time.time() - start < timeout:
        curr = get_current_question_number(driver)
        if curr == target_q:
            return True
        time.sleep(0.5)
    return False

# ---------------------------------------------------------------------------
# Input handlers
# ---------------------------------------------------------------------------

def handle_mcq(driver: WebDriver, answer: str) -> bool:
    """Select option for MCQ question."""
    options = driver.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option, [class*='mcq-option']")
    visible_options = [o for o in options if o.is_displayed()]
    if not visible_options:
        return False
        
    log.info("MCQ detected. Visible options: %d", len(visible_options))
    target_idx = None
    
    # 1. Map letters A, B, C, D... to indices
    ans_clean = answer.strip().upper()
    if len(ans_clean) == 1 and ans_clean in "ABCDEFGHIJ":
        target_idx = ord(ans_clean) - ord("A")
    
    # 2. Map text content fallback
    if target_idx is None or target_idx >= len(visible_options):
        # Fuzzy match option text
        for idx, opt in enumerate(visible_options):
            if answer.lower() in opt.text.strip().lower():
                target_idx = idx
                break
                
    if target_idx is None:
        target_idx = 0  # Default fallback
        
    target_idx = min(target_idx, len(visible_options) - 1)
    opt = visible_options[target_idx]
    
    try:
        inp = opt.find_element(By.TAG_NAME, "input")
        driver.execute_script("arguments[0].click();", inp)
        log.info("Selected MCQ option %d", target_idx)
        return True
    except Exception as e:
        log.warning("Failed to select radio input inside option, clicking option element: %s", e)
        driver.execute_script("arguments[0].click();", opt)
        return True


def handle_matrix(driver: WebDriver, answers: list) -> bool:
    """Select options for True/False matrix/table question."""
    rows = driver.find_elements(By.CSS_SELECTOR, "tr")
    visible_rows = []
    
    for r in rows:
        try:
            if r.is_displayed():
                inputs = r.find_elements(By.CSS_SELECTOR, "input[type='radio'], [role='radio']")
                if inputs:
                    visible_rows.append((r, inputs))
        except Exception:
            pass
            
    if not visible_rows:
        return False
        
    log.info("Matrix table detected. Rows: %d", len(visible_rows))
    for idx, (row, inputs) in enumerate(visible_rows):
        if idx >= len(answers):
            break
        val = str(answers[idx]).strip().lower()
        select_idx = 0 if val in ("true", "t", "yes", "y") else 1
        if select_idx < len(inputs):
            try:
                driver.execute_script("arguments[0].click();", inputs[select_idx])
            except Exception as e:
                log.error("Failed to select matrix row %d column %d: %s", idx, select_idx, e)
                
    return True


def is_keypad_button(btn: WebElement) -> bool:
    """Return True if the button is part of a virtual math/text keypad."""
    try:
        if not btn.is_displayed():
            return False
        
        # Keypad buttons are never in the top header area (which is y < 250)
        rect = btn.rect
        if not rect or rect.get('y', 0) < 250:
            return False
            
        classes = (btn.get_attribute("class") or "").lower()
        if "rounded-full" in classes:
            return False
            
        parent_classes = ""
        try:
            parent = btn.find_element(By.XPATH, "..")
            parent_classes = parent.get_attribute("class") or ""
            gp = parent.find_element(By.XPATH, "..")
            parent_classes += " " + (gp.get_attribute("class") or "")
        except Exception:
            pass
            
        combined = (classes + " " + parent_classes).lower()
        if any(k in combined for k in ["keypad", "keyboard", "palette", "formula", "math", "lrn-key", "lrn_btn_grid"]):
            return True
    except Exception:
        pass
    return False


def handle_text_inputs(driver: WebDriver, answer: str) -> bool:
    """Type answer into text input boxes and handle custom keypads if shown."""
    # 1. Look for visible editable math fields (e.g. MathQuill)
    math_fields = driver.find_elements(By.CSS_SELECTOR, ".mq-editable-field, .lrn-formula-input")
    visible_math_fields = [f for f in math_fields if f.is_displayed()]
    
    # 2. Look for standard inputs
    inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='number'], textarea")
    visible_inputs = [i for i in inputs if i.is_displayed() and not i.get_attribute("readonly")]
    
    all_fields = visible_math_fields + visible_inputs
    if not all_fields:
        return False
        
    log.info("Inputs/Math fields detected: %d", len(all_fields))
    for field in all_fields:
        try:
            scroll_into_view(driver, field)
            driver.execute_script("arguments[0].click();", field)
            time.sleep(1.0)
            
            # If this is a MathQuill field, try writing the LaTeX value directly using JavaScript
            classes = field.get_attribute("class") or ""
            is_mathquill = "mq-editable-field" in classes or "lrn-formula-input" in classes
            if is_mathquill:
                js_write_latex = """
                function setMathQuillLatex(el, latex) {
                    try {
                        if (typeof MQ !== 'undefined' && MQ.MathField) {
                            let mf = MQ.MathField(el);
                            if (mf) {
                                mf.latex(latex);
                                return true;
                            }
                        }
                        if (typeof jQuery !== 'undefined') {
                            let $el = jQuery(el);
                            let mq = $el.data('MathQuill');
                            if (mq) {
                                if (typeof mq.latex === 'function') {
                                    mq.latex(latex);
                                    return true;
                                }
                                if (mq.__controller && typeof mq.__controller.write === 'function') {
                                    mq.__controller.write(latex);
                                    return true;
                                }
                            }
                            if (typeof $el.mathquill === 'function') {
                                $el.mathquill('latex', latex);
                                return true;
                            }
                        }
                    } catch(e) {
                        console.error('Error setting MathQuill LaTeX:', e);
                    }
                    return false;
                }
                return setMathQuillLatex(arguments[0], arguments[1]);
                """
                latex_success = driver.execute_script(js_write_latex, field, answer)
                if latex_success:
                    log.info("Successfully wrote LaTeX '%s' via MathQuill JS API", answer)
                    continue
            
            # Check if there are visible keypad buttons on the page
            buttons = driver.find_elements(By.TAG_NAME, "button")
            keypad_btns = [b for b in buttons if is_keypad_button(b)]
            
            if keypad_btns and len(answer) > 0:
                log.info("On-screen keypad detected. Typing '%s' via keypad...", answer)
                for char in answer:
                    clicked = False
                    for btn in keypad_btns:
                        try:
                            # Clean up the button text to match characters
                            btn_text = btn.text.strip().split('\n')[0].strip().lower()
                            if btn_text == char.lower():
                                driver.execute_script("arguments[0].click();", btn)
                                time.sleep(0.25)
                                clicked = True
                                break
                        except Exception:
                            pass
                    if not clicked:
                        # Special character mapping fallback (e.g. fraction slash /)
                        for btn in keypad_btns:
                            try:
                                btn_text = btn.text.strip().lower()
                                if char == "/" and ("fraction" in btn_text or "/" in btn_text or "÷" in btn_text):
                                    driver.execute_script("arguments[0].click();", btn)
                                    time.sleep(0.25)
                                    clicked = True
                                    break
                            except Exception:
                                pass
                    if not clicked:
                        # Fallback: type character via active element keyboard keys
                        log.info("Character '%s' not found on keypad. Sending keys fallback.", char)
                        try:
                            active_el = driver.switch_to.active_element
                            active_el.send_keys(char)
                            time.sleep(0.25)
                        except Exception:
                            pass
            else:
                log.info("No keypad detected. Typing '%s' directly...", answer)
                # If it is a standard input, try typing directly
                if field.tag_name in ("input", "textarea"):
                    try:
                        field.clear()
                        field.send_keys(answer)
                    except Exception:
                        pass
                else:
                    # MathQuill editable field: try to find its nested textarea
                    try:
                        ta = field.find_element(By.TAG_NAME, "textarea")
                        driver.execute_script("arguments[0].focus();", ta)
                        ta.send_keys(answer)
                    except Exception:
                        pass
        except Exception as e:
            log.warning("Failed input for field: %s", e)
            
    return True

def extract_website_correct_answer(driver: WebDriver) -> Optional[str]:
    """Attempt to extract the correct answer displayed by the website (Learnosity)."""
    selectors = [
        ".lrn_correctAnswerList",
        ".lrn-correct-answer-list",
        "[class*='correctAnswerList']",
        "[class*='correct-answer-list']",
        ".lrn-suggested-answer",
        "[class*='suggested-answer']",
        ".lrn_correct_answer",
        "[class*='correct_answer']",
    ]
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                if el.is_displayed():
                    text = el.text.strip()
                    if text:
                        # Clean up prefix like "Correct Answer:" if present
                        for prefix in ["Correct Answer:", "Correct Answer", "Suggested Answer:", "Suggested Answer"]:
                            if text.lower().startswith(prefix.lower()):
                                text = text[len(prefix):].strip()
                        return text
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Main Workflow
# ---------------------------------------------------------------------------

def answer_worksheet_questions(driver: WebDriver, worksheet_id: str, answers: dict) -> dict:
    """
    Sequentially process, answer, submit, and verify correctness of all questions in worksheet.
    
    Returns:
        dict - Summary of correctness results per question number.
    """
    if not wait_for_loading(driver):
        log.error("Worksheet did not load in time. Skipping answering flow.")
        return {}
        
    time.sleep(3.0)
    
    # 1. Check if we need to navigate back to Question 1 to start fresh
    curr_q = get_current_question_number(driver)
    if curr_q > 1:
        log.info("Worksheet loaded in resumed state (Question %d). Navigating to Question 1...", curr_q)
        click_question_dot(driver, 1)
        wait_for_active_question(driver, 1)
        time.sleep(2.0)
        
    # Get total number of questions
    dots = get_question_dot_buttons(driver)
    num_questions = len(dots) if dots else 5
            
    log.info("Answering %d questions using provided answers...", num_questions)
    results = {}
    
    for q_no in range(1, num_questions + 1):
        log.info("--- Question %d of %d ---", q_no, num_questions)
        print(f"Processing Question {q_no}...")
        
        # Ensure we are on the correct question dot
        if get_current_question_number(driver) != q_no:
            click_question_dot(driver, q_no)
            wait_for_active_question(driver, q_no)
            time.sleep(1.5)
            
        q_answer = answers.get(str(q_no))
        if q_answer is None:
            log.warning("No answer provided for Question %d. Skipping input.", q_no)
            print(f"-> Warning: No answer found in JSON for Question {q_no}.")
            results[q_no] = {
                "status": "skipped",
                "submitted_answer": None,
                "screenshot_path": None,
                "website_correct_answer": None
            }
            continue
            
        input_success = False
        
        # A. Try MCQ
        if isinstance(q_answer, str) and handle_mcq(driver, q_answer):
            input_success = True
            
        # B. Try Matrix (if list of values)
        elif isinstance(q_answer, list) and handle_matrix(driver, q_answer):
            input_success = True
            
        # C. Try Text/Keypad
        elif isinstance(q_answer, str) and handle_text_inputs(driver, q_answer):
            input_success = True
            
        if not input_success:
            log.warning("No active input fields could be resolved for Question %d.", q_no)
            
        # Submit the answer
        submit_btn = None
        for tag in ["button", "input", "span"]:
            for btn in driver.find_elements(By.TAG_NAME, tag):
                try:
                    if btn.is_displayed() and "submit" in btn.text.strip().lower():
                        submit_btn = btn
                        break
                except Exception:
                    pass
            if submit_btn:
                break
                
        if submit_btn:
            log.info("Clicking Submit Answer...")
            driver.execute_script("arguments[0].click();", submit_btn)
            time.sleep(3.0)  # Wait for submission grading to complete
        else:
            log.warning("Submit Answer button not found for Question %d.", q_no)
            
        # Determine correctness by looking at the pagination dot classes
        correctness = "unknown"
        dots_after = get_question_dot_buttons(driver)
        if 1 <= q_no <= len(dots_after):
            try:
                classes = (dots_after[q_no - 1].get_attribute("class") or "").lower()
                if "green" in classes:
                    correctness = "correct"
                elif "orange" in classes or "red" in classes:
                    correctness = "incorrect"
                elif "purple" in classes or "blue" in classes:
                    correctness = "partially_correct"
            except Exception:
                pass
                
        # Fallback
        if correctness == "unknown" and get_current_question_number(driver) > q_no:
            correctness = "correct"
            
        log.info("Question %d result: %s", q_no, correctness.upper())
        print(f"-> Question {q_no} is: {correctness.upper()}")
        
        # Save screenshot only if answer is incorrect / partially correct
        screenshot_path = None
        if correctness != "correct":
            screenshot_dir = os.path.join("screenshots", worksheet_id)
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, f"Question_{q_no}_graded.png")
            try:
                driver.save_screenshot(screenshot_path)
                log.info("Saved graded screenshot: %s", screenshot_path)
            except Exception as e:
                log.error("Failed to save graded screenshot: %s", e)
                screenshot_path = None
            
        # Try to extract the website's correct answer if it's not correct
        website_correct_answer = None
        if correctness != "correct":
            website_correct_answer = extract_website_correct_answer(driver)
            if website_correct_answer:
                log.info("Extracted correct answer from website: %s", website_correct_answer)
                print(f"-> Website expects: {website_correct_answer}")
                
        results[q_no] = {
            "status": correctness,
            "submitted_answer": q_answer,
            "screenshot_path": screenshot_path,
            "website_correct_answer": website_correct_answer
        }
            
        # Manually transition if it didn't do so automatically
        if q_no < num_questions and get_current_question_number(driver) == q_no:
            log.info("Question %d did not transition automatically. Navigating manually to next question...", q_no)
            click_question_dot(driver, q_no + 1)
            wait_for_active_question(driver, q_no + 1)
            time.sleep(1.5)
            
    print(f"\n--- Answering Summary for {worksheet_id} ---")
    for q, res_detail in results.items():
        status = res_detail["status"].upper()
        sub_ans = res_detail["submitted_answer"]
        web_ans = res_detail["website_correct_answer"]
        if web_ans:
            print(f"Question {q}: {status} (Submitted: {sub_ans} | Website Expected: {web_ans})")
        else:
            print(f"Question {q}: {status} (Submitted: {sub_ans})")
    print()
    
    return results
