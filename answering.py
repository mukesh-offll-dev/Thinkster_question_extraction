# =============================================================================
# answering.py – Worksheet Question Answering and Correctness Checking
# =============================================================================

import os
import time
import json
import re
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
    # Normalize answers if it is passed as a string representation of a list
    if isinstance(answers, str):
        cleaned = answers.strip()
        matches = re.findall(r"\b(true|false|yes|no|t|f|y|n)\b", cleaned, re.IGNORECASE)
        if (cleaned.startswith("[") or "," in cleaned) and len(matches) > 1:
            answers = matches
        elif len(matches) > 1:
            answers = matches
    # Find the active question container if possible to avoid matching other questions' elements
    active_container = None
    for wrapper_class in ["lrn-active", "lrn-item-slide", "lrn-response-validate-wrapper", "lrn-question"]:
        try:
            wrappers = driver.find_elements(By.CLASS_NAME, wrapper_class)
            for w in wrappers:
                if w.is_displayed():
                    active_container = w
                    break
            if active_container:
                break
        except Exception:
            pass

    if active_container:
        log.debug("Found active question container: %s", active_container.get_attribute("class"))
        rows = active_container.find_elements(By.CSS_SELECTOR, "tr, [class*='lrn-matrix-row']")
    else:
        rows = driver.find_elements(By.CSS_SELECTOR, "tr, [class*='lrn-matrix-row']")

    # Filter only rows that contain radio or checkbox options (statement rows)
    valid_rows = []
    for r in rows:
        try:
            if r.is_displayed():
                inputs = r.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox'], [role='radio'], [role='checkbox']")
                if inputs:
                    valid_rows.append((r, inputs))
        except Exception:
            pass

    if not valid_rows:
        log.warning("No valid matrix rows with inputs found.")
        return False

    log.info("Matrix table detected. Valid rows: %d", len(valid_rows))
    for idx, (row, inputs) in enumerate(valid_rows):
        if idx >= len(answers):
            break

        val = str(answers[idx]).strip().lower()
        val_norm = "true" if val in ("true", "t", "yes", "y") else "false"

        # Match input element corresponding to the answer
        target_input = None

        # Method 1: Check aria-label
        for inp in inputs:
            aria_label = (inp.get_attribute("aria-label") or "").strip().lower()
            if val_norm == "true" and (aria_label.startswith("true") or aria_label.startswith("yes") or "true -" in aria_label or "yes -" in aria_label):
                target_input = inp
                break
            elif val_norm == "false" and (aria_label.startswith("false") or aria_label.startswith("no") or "false -" in aria_label or "no -" in aria_label):
                target_input = inp
                break

        # Method 2: Check associated label element
        if not target_input:
            for inp in inputs:
                inp_id = inp.get_attribute("id")
                if inp_id:
                    try:
                        label = row.find_element(By.CSS_SELECTOR, f"label[for='{inp_id}']")
                        label_text = label.text.strip().lower()
                        if val_norm == "true" and label_text in ("true", "t", "yes", "y"):
                            target_input = inp
                            break
                        elif val_norm == "false" and label_text in ("false", "f", "no", "n"):
                            target_input = inp
                            break
                    except Exception:
                        pass

        # Method 3: Fallback to simple index matching if inputs match True/False standard order
        if not target_input:
            select_idx = 0 if val_norm == "true" else 1
            if select_idx < len(inputs):
                target_input = inputs[select_idx]

        if target_input:
            clicked = False
            try:
                # Try clicking the input itself
                driver.execute_script("arguments[0].click();", target_input)
                clicked = True
            except Exception:
                pass

            if not clicked:
                # Fallback to clicking label if input click failed
                try:
                    inp_id = target_input.get_attribute("id")
                    if inp_id:
                        label = row.find_element(By.CSS_SELECTOR, f"label[for='{inp_id}']")
                        driver.execute_script("arguments[0].click();", label)
                        clicked = True
                except Exception:
                    pass

            if clicked:
                log.info("Selected matrix option for row %d matching '%s'", idx, val_norm)
            else:
                log.error("Failed to select matrix option for row %d", idx)
        else:
            log.error("Could not find matching input element for answer '%s' in row %d", answers[idx], idx)

    return True


def is_keypad_button(btn: WebElement) -> bool:
    """Return True if the button is part of a virtual math/text keypad."""
    try:
        if not btn.is_displayed():
            return False
            
        classes = (btn.get_attribute("class") or "").lower()
        if "lrn_btn_grid" in classes or "lrn-qwerty-btn" in classes:
            return True
            
        # Also check parent class chain
        parent_classes = ""
        try:
            parent = btn.find_element(By.XPATH, "..")
            parent_classes = (parent.get_attribute("class") or "").lower()
            gp = parent.find_element(By.XPATH, "..")
            parent_classes += " " + (gp.get_attribute("class") or "").lower()
        except Exception:
            pass
            
        combined = (classes + " " + parent_classes).lower()
        if any(k in combined for k in ["keypad", "keyboard", "palette", "formula", "math", "lrn-key", "lrn_btn_grid"]):
            return True
    except Exception:
        pass
    return False


def tokenize_math_string(s: str) -> list:
    """Tokenizes a mathematical expression or LaTeX string into actionable commands."""
    tokens = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        
        # 1. Backslash commands
        if c == '\\':
            cmd = '\\'
            i += 1
            while i < n and (s[i].isalpha() or s[i] in ('(', ')', '[', ']')):
                cmd += s[i]
                i += 1
            tokens.append(('cmd', cmd))
            continue
            
        # 2. Exponent, Subscript, Braces, Parentheses
        if c in ('^', '_', '{', '}', '(', ')'):
            tokens.append(('char', c))
            i += 1
            continue
            
        # 3. Digits & Dot
        if c.isdigit() or c == '.':
            num = ''
            while i < n and (s[i].isdigit() or s[i] == '.'):
                num += s[i]
                i += 1
            for digit in num:
                tokens.append(('char', digit))
            continue
            
        # 4. Letters (variables)
        if c.isalpha():
            tokens.append(('var', c))
            i += 1
            continue
            
        # 5. Operators & whitespace
        if c in ('+', '-', '=', '*', '/'):
            tokens.append(('char', c))
            i += 1
            continue
            
        if c.isspace():
            i += 1
            continue
            
        tokens.append(('char', c))
        i += 1
        
    return tokens


def generate_keypad_actions(tokens: list) -> list:
    """Converts math/LaTeX tokens into sequential layout and click button actions."""
    actions = []
    i = 0
    n = len(tokens)
    while i < n:
        t_type, val = tokens[i]
        
        if t_type == 'cmd':
            if val == '\\sqrt':
                actions.append(('Basic', 'click', '//button[@data-mq-value="\\sqrt"]'))
            elif val == '\\frac':
                actions.append(('Basic', 'click', '//button[@data-mq-value="/"]'))
            elif val == '\\abs':
                actions.append(('Basic', 'click', '//button[@data-mq-value="\\abs"]'))
            elif val == '\\pi':
                actions.append(('Basic', 'click', '//button[@data-mq-value="\\pi"]'))
            elif val == '\\pm':
                actions.append(('Basic', 'click', '//button[@data-mq-value="\\pm"]'))
            elif val in ('\\infty', '\\infinity'):
                actions.append(('Basic', 'click', '//button[@data-mq-value="\\infinity"]'))
            elif val == '\\degree':
                actions.append(('Basic', 'click', '//button[@data-mq-value="\\degree"]'))
            else:
                for c in val:
                    actions.append(('Keyboard' if c.isalpha() else 'Basic', 'click', f'//button[@data-mq-value="{c}"]'))
            i += 1
            
        elif t_type == 'char' and val == '^':
            actions.append(('Basic', 'click', '//button[@data-mq-value="^"]'))
            i += 1
            if i < n and tokens[i] == ('char', '{'):
                i += 1
            else:
                if i < n:
                    next_t_type, next_val = tokens[i]
                    actions.append(('Keyboard' if next_t_type == 'var' else 'Basic', 'click', f'//button[@data-mq-value="{next_val}"]'))
                    actions.append(('Basic', 'click', '//button[@data-mq-value="Right"]'))
                    i += 1
                    
        elif t_type == 'char' and val == '_':
            actions.append(('Basic', 'click', '//button[@data-mq-value="_"]'))
            i += 1
            if i < n and tokens[i] == ('char', '{'):
                i += 1
            else:
                if i < n:
                    next_t_type, next_val = tokens[i]
                    actions.append(('Keyboard' if next_t_type == 'var' else 'Basic', 'click', f'//button[@data-mq-value="{next_val}"]'))
                    actions.append(('Basic', 'click', '//button[@data-mq-value="Right"]'))
                    i += 1
                    
        elif t_type == 'char' and val == '{':
            i += 1
            
        elif t_type == 'char' and val == '}':
            actions.append(('Basic', 'click', '//button[@data-mq-value="Right"]'))
            i += 1
            
        elif t_type == 'char' and val == '(':
            actions.append(('Basic', 'click', '//button[@data-mq-value="("]'))
            i += 1
            
        elif t_type == 'char' and val == ')':
            actions.append(('Basic', 'click', '//button[@data-mq-value="Right"]'))
            i += 1
            
        elif t_type == 'var':
            actions.append(('Keyboard', 'click', f'//button[@data-mq-value="{val.lower()}"]'))
            i += 1
            
        else:
            map_val = val
            if val == '*':
                map_val = '×'
            elif val == '/':
                map_val = '÷'
            actions.append(('Basic', 'click', f'//button[@data-mq-value="{map_val}"]'))
            i += 1
            
    return actions


def switch_keypad_layout(driver: WebDriver, target_layout: str) -> bool:
    """Switch the virtual keypad layout between 'Basic' and 'Keyboard'."""
    try:
        title_val = "Basic" if target_layout == "Basic" else "Keyboard"
        option = driver.find_element(By.XPATH, f"//button[@class and (@title='{title_val}' or @aria-label='{title_val}')]")
        classes = option.get_attribute("class") or ""
        if "lrn_selected" in classes:
            return True
            
        toggles = driver.find_elements(By.CSS_SELECTOR, "button.lrn_dropdown_toggle")
        visible_toggles = [t for t in toggles if t.is_displayed()]
        if visible_toggles:
            driver.execute_script("arguments[0].click();", visible_toggles[0])
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", option)
            time.sleep(0.5)
            return True
    except Exception as e:
        log.warning("Failed to switch keypad layout to %s: %s", target_layout, e)
    return False


def enter_math_answer(driver: WebDriver, answer: str) -> bool:
    """Translate and enter a LaTeX/math answer via virtual keypad layout switches and clicks."""
    tokens = tokenize_math_string(answer)
    actions = generate_keypad_actions(tokens)
    log.info("Entering math answer via virtual keypad. Generated actions: %s", actions)
    
    for layout, act_type, selector in actions:
        if layout:
            switch_success = switch_keypad_layout(driver, layout)
            if not switch_success:
                log.warning("Layout switch to %s might have failed.", layout)
                
        try:
            buttons = driver.find_elements(By.XPATH, selector)
            visible_btn = None
            for btn in buttons:
                if btn.is_displayed():
                    visible_btn = btn
                    break
                    
            if visible_btn:
                driver.execute_script("arguments[0].click();", visible_btn)
                time.sleep(0.25)
            else:
                log.warning("Keypad button for selector '%s' not visible.", selector)
                if "Right" in selector:
                    # Fallback for Right arrow keystroke button
                    fallback_btns = driver.find_elements(By.XPATH, "//button[@aria-label='Move cursor right' or @title='Move cursor right' or contains(@class, 'lrn-btn-grid-dir')]")
                    for btn in fallback_btns:
                        if btn.is_displayed() and "right" in (btn.get_attribute("aria-label") or "").lower():
                            driver.execute_script("arguments[0].click();", btn)
                            time.sleep(0.25)
                            break
        except Exception as e:
            log.warning("Error clicking keypad button %s: %s", selector, e)
            
    return True


def handle_text_inputs(driver: WebDriver, answer: str) -> bool:
    """Type answer into text input boxes and handle custom keypads if shown."""
    # 1. Look for visible editable math fields or standard inputs
    math_fields = driver.find_elements(By.CSS_SELECTOR, ".mq-editable-field, .lrn-formula-input")
    visible_math_fields = [f for f in math_fields if f.is_displayed()]
    
    inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea, [class*='mq-textarea'] textarea")
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
            
            # Wait up to 3.0 seconds for the virtual keypad to appear
            keypad_btns = []
            for _ in range(6):
                buttons = driver.find_elements(By.TAG_NAME, "button")
                keypad_btns = [b for b in buttons if is_keypad_button(b)]
                if keypad_btns:
                    break
                time.sleep(0.5)
            
            if keypad_btns and len(answer) > 0:
                log.info("On-screen keypad detected. Typing '%s' via keypad...", answer)
                enter_math_answer(driver, answer)
            else:
                # Fallback path if no keypad is displayed
                classes = field.get_attribute("class") or ""
                is_mathquill = "mq-editable-field" in classes or "lrn-formula-input" in classes
                
                if is_mathquill:
                    # If this is a MathQuill field, try writing the LaTeX value directly using JavaScript
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
                
                log.info("No active keypad. Typing '%s' directly...", answer)
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
        if q_answer is None or (isinstance(q_answer, str) and q_answer.strip().lower() == "issue"):
            reason = "No answer provided" if q_answer is None else "Answer is marked as 'Issue'"
            log.warning("%s for Question %d. Skipping input.", reason, q_no)
            print(f"-> Warning: {reason} for Question {q_no}. Skipping.")
            results[q_no] = {
                "status": "skipped",
                "submitted_answer": q_answer if q_answer else None,
                "screenshot_path": None,
                "website_correct_answer": None
            }
            continue
            
        # Try to parse matrix answers if stored as string representation of a list/sequence
        matrix_answers = None
        if isinstance(q_answer, str):
            cleaned = q_answer.strip()
            # Look for a sequence of True/False/Yes/No/T/F/Y/N values
            matches = re.findall(r"\b(true|false|yes|no|t|f|y|n)\b", cleaned, re.IGNORECASE)
            if (cleaned.startswith("[") or "," in cleaned) and len(matches) > 1:
                matrix_answers = matches
            elif len(matches) > 1:
                # If the string contains multiple T/F words separated by spaces or punctuation
                matrix_answers = matches

        input_success = False
        
        # A. Try MCQ
        if isinstance(q_answer, str) and not matrix_answers and handle_mcq(driver, q_answer):
            input_success = True
            
        # B. Try Matrix (if list of values or parsed list of values)
        elif (isinstance(q_answer, list) or matrix_answers) and handle_matrix(driver, matrix_answers or q_answer):
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
