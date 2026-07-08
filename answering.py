# =============================================================================
# answering.py – Worksheet Question Answering and Correctness Checking
# =============================================================================

import os
import time
import json
import re
import unicodedata
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

def handle_mcq(driver: WebDriver, answer, active_item: WebElement = None) -> bool:
    """Select option(s) for MCQ or Multi-select MCQ question."""
    if active_item:
        options = active_item.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option, [class*='mcq-option']")
    else:
        options = driver.find_elements(By.CSS_SELECTOR, ".lrn-mcq-option, [class*='mcq-option']")
        
    visible_options = [o for o in options if o.is_displayed()]
    if not visible_options:
        return False
        
    log.info("MCQ/Multi-select detected. Visible options: %d", len(visible_options))
    
    # 1. Parse the answer(s) into a list of strings
    if isinstance(answer, list):
        answers_list = [str(a).strip() for a in answer]
    elif isinstance(answer, str):
        # Check if it is a list-like string or comma-separated
        val_str = answer.strip()
        if val_str.startswith("[") and val_str.endswith("]"):
            try:
                loaded = json.loads(val_str)
                if isinstance(loaded, list):
                    answers_list = [str(x).strip() for x in loaded]
                else:
                    answers_list = [str(loaded).strip()]
            except Exception:
                answers_list = [p.strip() for p in val_str[1:-1].split(",") if p.strip()]
        else:
            # Check if it has commas to split (only if not a math formula, e.g. letters)
            # MCQ options are typically single letters like A, B or short text. 
            # If it's a comma-separated list of options:
            if "," in val_str and not any(k in val_str for k in ("\\", "sqrt", "frac", "^")):
                answers_list = [p.strip() for p in val_str.split(",") if p.strip()]
            else:
                answers_list = [val_str]
    else:
        answers_list = [str(answer).strip()]
        
    success = False
    
    for ans in answers_list:
        target_idx = None
        ans_clean = ans.upper()
        
        # Method 1: Check A, B, C, D letters
        if len(ans_clean) == 1 and ans_clean in "ABCDEFGHIJ":
            target_idx = ord(ans_clean) - ord("A")
            
        # Method 2: Fuzzy match option text
        if target_idx is None or target_idx >= len(visible_options):
            for idx, opt in enumerate(visible_options):
                if ans.lower() in opt.text.strip().lower():
                    target_idx = idx
                    break
                    
        # Fallback to first option if no match and it's a single value
        if target_idx is None and len(answers_list) == 1:
            target_idx = 0
            
        if target_idx is not None and target_idx < len(visible_options):
            opt = visible_options[target_idx]
            try:
                inp = opt.find_element(By.CSS_SELECTOR, "input[type='checkbox'], input[type='radio'], input")
                driver.execute_script("arguments[0].click();", inp)
                log.info("Selected MCQ option %d (matching '%s')", target_idx, ans)
                success = True
            except Exception as e:
                log.warning("Failed to select input inside option, clicking option element: %s", e)
                try:
                    driver.execute_script("arguments[0].click();", opt)
                    success = True
                except Exception:
                    pass
                    
    return success


def handle_matrix(driver: WebDriver, answers: list, active_item: WebElement = None) -> bool:
    """Select options for True/False matrix/table question."""
    # Normalize answers if it is passed as a string representation of a list
    if isinstance(answers, str):
        cleaned = answers.strip()
        matches = re.findall(r"\b(true|false|yes|no|t|f|y|n)\b", cleaned, re.IGNORECASE)
        if (cleaned.startswith("[") or "," in cleaned) and len(matches) > 1:
            answers = matches
        elif len(matches) > 1:
            answers = matches

    if not active_item:
        active_item = get_active_container(driver, 1)

    if active_item:
        js_code = """
        function handleMatrixJS(activeItem, answers) {
            let table = activeItem.querySelector('table, [class*="matrix"]');
            if (!table) return false;
            
            let headerRow = table.querySelector('thead tr, tr:first-child');
            if (!headerRow) return false;
            
            let headerCells = Array.from(headerRow.querySelectorAll('th, td'));
            let colIndexMap = {};
            
            headerCells.forEach((c, idx) => {
                let txt = (c.innerText || c.textContent || "").trim().toLowerCase();
                if (txt) {
                    colIndexMap[txt] = idx;
                }
            });
            
            let rows = Array.from(table.querySelectorAll('tbody tr, tr')).filter(r => {
                if (r === headerRow) return false;
                return r.querySelector('input[type="radio"], input[type="checkbox"], [role="radio"], [role="checkbox"]');
            });
            
            if (rows.length === 0) return false;
            
            let clickedAny = false;
            rows.forEach((row, rowIdx) => {
                if (rowIdx >= answers.length) return;
                
                let dbAns = answers[rowIdx].trim().toLowerCase();
                let targetColIdx = -1;
                
                if (colIndexMap[dbAns] !== undefined) {
                    targetColIdx = colIndexMap[dbAns];
                } else {
                    for (let label in colIndexMap) {
                        if (dbAns.includes(label) || label.includes(dbAns) || 
                            (dbAns === 't' && label === 'true') || 
                            (dbAns === 'f' && label === 'false') ||
                            (dbAns === 'y' && label === 'yes') ||
                            (dbAns === 'n' && label === 'no')) {
                            targetColIdx = colIndexMap[label];
                            break;
                        }
                    }
                }
                
                if (targetColIdx === -1) {
                    let isTrueVal = (dbAns === 'true' || dbAns === 't' || dbAns === 'yes' || dbAns === 'y' || dbAns === 'positive' || dbAns === 'rational' || dbAns === 'real' || dbAns === 'even');
                    headerCells.forEach((c, idx) => {
                        let txt = (c.innerText || c.textContent || "").trim().toLowerCase();
                        if (isTrueVal && (txt === 'true' || txt === 'yes' || txt === 'positive' || txt === 'rational' || txt === 'real' || txt === 'even')) {
                            targetColIdx = idx;
                        } else if (!isTrueVal && (txt === 'false' || txt === 'no' || txt === 'negative' || txt === 'irrational' || txt === 'non-real' || txt === 'odd')) {
                            targetColIdx = idx;
                        }
                    });
                }
                
                if (targetColIdx === -1) {
                    let isTrueVal = (dbAns === 'true' || dbAns === 't' || dbAns === 'yes' || dbAns === 'y' || dbAns === 'positive' || dbAns === 'rational' || dbAns === 'real' || dbAns === 'even');
                    targetColIdx = isTrueVal ? 1 : 2;
                }
                
                let cells = Array.from(row.querySelectorAll('td, th'));
                if (targetColIdx < cells.length) {
                    let cell = cells[targetColIdx];
                    let inp = cell.querySelector('input, [role="radio"], [role="checkbox"]');
                    if (inp) {
                        inp.click();
                        clickedAny = true;
                    } else {
                        cell.click();
                        clickedAny = true;
                    }
                }
            });
            return clickedAny;
        }
        return handleMatrixJS(arguments[0], arguments[1]);
        """
        try:
            success = driver.execute_script(js_code, active_item, answers)
            if success:
                log.info("Matrix answered successfully via JS.")
                return True
        except Exception as e:
            log.warning("Matrix JS execution failed: %s. Falling back to python...", e)

    # Find the active question container if possible to avoid matching other questions' elements
    if active_item:
        rows = active_item.find_elements(By.CSS_SELECTOR, "tr, [class*='lrn-matrix-row']")
    else:
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
                try:
                    # Try clicking parent TD/element if direct input click failed
                    parent = target_input.find_element(By.XPATH, "..")
                    driver.execute_script("arguments[0].click();", parent)
                    clicked = True
                except Exception as e:
                    log.warning("Failed to select matrix option for row %d: %s", idx, e)

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


def normalize_text(text: str) -> str:
    """Normalize and clean mathematical/variable text for matching."""
    if not text:
        return ""
    # Normalize unicode mathematical alphanumeric symbols to standard ASCII (e.g. italic x to standard x)
    n = unicodedata.normalize('NFKC', text)
    
    # If it is a fraction represented via newlines (e.g., only digits and newlines/spaces)
    # replace newlines with a slash.
    lines = [line.strip() for line in n.split('\n') if line.strip()]
    if len(lines) == 2 and all(part.isdigit() for part in lines):
        n = "/".join(lines)
        
    # Keep only alphanumeric characters and basic operators (+, -, *, /)
    cleaned = "".join(c for c in n if c.isalnum() or c in ('+', '-', '*', '/')).lower()
    return cleaned


def get_active_container(driver: WebDriver, q_no: int) -> Optional[WebElement]:
    """Retrieve the learnosity-item container representing q_no, waiting for it to be visible."""
    start_time = time.time()
    while time.time() - start_time < 5.0:
        try:
            items = driver.find_elements(By.CSS_SELECTOR, ".learnosity-item")
            if items:
                # 1. Check for active/lrn-active class
                for el in items:
                    classes = el.get_attribute("class") or ""
                    if "lrn-active" in classes or "active" in classes:
                        return el
                # 2. Check visibility in style
                for el in items:
                    style = el.get_attribute("style") or ""
                    if "visibility: visible" in style or "opacity: 1" in style:
                        return el
                # 3. Fallback to standard index
                if len(items) >= q_no:
                    return items[q_no - 1]
                # 4. Fallback to single item
                if len(items) == 1:
                    return items[0]
        except Exception:
            pass
        time.sleep(0.1)
        
    try:
        items = driver.find_elements(By.CSS_SELECTOR, ".learnosity-item")
        if items:
            for el in items:
                classes = el.get_attribute("class") or ""
                if "lrn-active" in classes or "active" in classes:
                    return el
            if len(items) >= q_no:
                return items[q_no - 1]
            return items[0]
    except Exception:
        pass
    return None

def wait_for_inputs_ready(driver: WebDriver, active_item: WebElement, timeout: float = 10.0) -> bool:
    """Wait for at least one interactive input element to be displayed within the active container."""
    if not active_item:
        return False
    start_time = time.time()
    selectors = [
        ".lrn-mcq-option", "[class*='mcq-option']",
        "input", "textarea", "select",
        ".mq-editable-field", ".lrn-formula-input",
        ".lrn_cloze_response", ".lrn_dropzone", ".lrn_assoc_col2",
        ".lrn_btn_drag", "[draggable='true']"
    ]
    while time.time() - start_time < timeout:
        for selector in selectors:
            try:
                elements = active_item.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    if el.is_displayed():
                        # Additional check: if it is standard input, ensure it is enabled
                        if el.tag_name in ("input", "textarea", "select") and not el.get_attribute("readonly"):
                            return True
                        elif el.tag_name not in ("input", "textarea", "select"):
                            return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


def handle_cloze_and_drag_drop(driver: WebDriver, answers: list, active_item: WebElement) -> bool:
    """
    Handle drag-and-drop matching, cloze fill-in-the-blanks, and custom/select dropdowns.
    Maps values in 'answers' list to active input/drop slots ordered by DOM/visual index.
    """
    if not active_item:
        return False
        
    js_get_slots = """
    function getActiveSlots(activeItem) {
        let uniqueInputIds = [];
        let slots = {};
        let elements = activeItem.querySelectorAll('.lrn_cloze_response, .lrn_dropzone, .lrn_assoc_col2, .lrn-response-input, [data-inputid]');
        
        elements.forEach(el => {
            let inputId = el.getAttribute('data-inputid');
            if (inputId === null || inputId === undefined) return;
            
            let classes = el.className || "";
            
            if (!slots[inputId]) {
                uniqueInputIds.push(inputId);
                slots[inputId] = {
                    inputId: parseInt(inputId, 10),
                    elements: []
                };
            }
            
            let tagName = el.tagName.toLowerCase();
            let isMathQuill = classes.includes('mq-editable-field') || classes.includes('lrn_math_editable') || classes.includes('lrn-clozeformula-input');
            let isDropzone = classes.includes('lrn_dropzone') || classes.includes('lrn_drop') || classes.includes('lrn_assoc_col2');
            let isDropdown = tagName === 'select' || classes.includes('lrn_dropdown');
            let isStandardInput = tagName === 'input' || tagName === 'textarea';
            
            slots[inputId].elements.push({
                tagName: tagName,
                className: classes,
                isMathQuill: isMathQuill,
                isDropzone: isDropzone,
                isDropdown: isDropdown,
                isStandardInput: isStandardInput
            });
        });
        
        return uniqueInputIds.map(id => slots[id]);
    }
    return getActiveSlots(arguments[0]);
    """
    
    try:
        active_slots = driver.execute_script(js_get_slots, active_item)
    except Exception as e:
        log.warning("Failed to retrieve active cloze/drag-drop slots via JS: %s", e)
        return False
        
    if not active_slots:
        return False
        
    log.info("Detected %d active cloze/drag-drop slots on page.", len(active_slots))
    success_count = 0
    
    # Pre-fetch visible interactive elements in DOM order within active_item
    visible_draggables = []
    draggables = driver.find_elements(By.CSS_SELECTOR, ".lrn_btn_drag.lrn_draggable, [draggable='true']")
    for d in draggables:
        classes = d.get_attribute("class") or ""
        if "lrn_invisible" not in classes and d.is_displayed():
            visible_draggables.append(d)
            
    visible_mq_spans = []
    mq_spans = active_item.find_elements(By.CSS_SELECTOR, ".lrn-clozeformula-input, .mq-editable-field, .lrn_math_editable")
    for span in mq_spans:
        classes = span.get_attribute("class") or ""
        if "lrn_invisible" not in classes and span.is_displayed():
            visible_mq_spans.append(span)
            
    # JS helper to write directly to backing input/select/textarea by visual index
    js_set_backing_input_by_index = """
    function setBackingInputByIndex(activeItem, index, value) {
        let inputs = Array.from(activeItem.querySelectorAll('input, textarea, select')).filter(el => el.getAttribute('type') !== 'hidden');
        if (index < inputs.length) {
            let el = inputs[index];
            let tagName = el.tagName.toLowerCase();
            if (tagName === 'select') {
                let options = Array.from(el.options);
                let matched = options.find(opt => opt.text.trim().toLowerCase() === value.trim().toLowerCase() || opt.value === value);
                if (matched) {
                    el.value = matched.value;
                } else {
                    el.value = value;
                }
            } else {
                el.value = value;
            }
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
            return true;
        }
        return false;
    }
    return setBackingInputByIndex(arguments[0], arguments[1], arguments[2]);
    """
    
    mathquill_idx = 0
    input_idx = 0
    for slot in active_slots:
        input_id = slot["inputId"]
        is_dropzone = any(el["isDropzone"] for el in slot["elements"])
        is_mathquill = any(el["isMathQuill"] for el in slot["elements"])
        is_dropdown = any(el["isDropdown"] for el in slot["elements"])
        is_standard = any(el["isStandardInput"] for el in slot["elements"])
        
        ans = str(answers[success_count]).strip() if success_count < len(answers) else ""
        if not ans:
            if not is_dropzone:
                input_idx += 1
            success_count += 1
            continue
            
        log.info("Processing Slot (inputId=%d, inputIdx=%d) -> answer=%s (types: dropzone=%s, mathquill=%s, dropdown=%s, standard=%s)",
                 input_id, input_idx, repr(ans), is_dropzone, is_mathquill, is_dropdown, is_standard)
                 
        action_done = False
        
        # Case A: Drag and Drop
        if is_dropzone:
            target_norm = normalize_text(ans)
            selected_draggable = None
            for d in visible_draggables:
                txt = driver.execute_script("return arguments[0].innerText || arguments[0].textContent || '';", d).strip()
                aria_label = d.get_attribute("aria-label") or ""
                d_norm = normalize_text(txt)
                aria_norm = normalize_text(aria_label)
                if (target_norm and d_norm and target_norm in d_norm) or (target_norm and aria_norm and target_norm in aria_norm):
                    selected_draggable = d
                    break
                    
            if selected_draggable:
                drop_elements = active_item.find_elements(By.CSS_SELECTOR, f"[data-inputid='{input_id}']")
                target_dropzone = None
                for de in drop_elements:
                    classes = de.get_attribute("class") or ""
                    if ("lrn_dropzone" in classes or "lrn_assoc_col2" in classes) and "lrn_invisible" not in classes:
                        target_dropzone = de
                        break
                        
                if target_dropzone:
                    log.info("Associating draggable option for inputId=%d", input_id)
                    driver.execute_script("arguments[0].click();", selected_draggable)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", target_dropzone)
                    time.sleep(0.5)
                    action_done = True
                else:
                    log.warning("Target dropzone not found for inputId %d", input_id)
            else:
                log.warning("No matching draggable option found for '%s'", ans)
                
        # Case B: MathQuill span
        elif is_mathquill:
            if mathquill_idx < len(visible_mq_spans):
                mq_span = visible_mq_spans[mathquill_idx]
                mathquill_idx += 1
                
                scroll_into_view(driver, mq_span)
                driver.execute_script("arguments[0].click();", mq_span)
                time.sleep(0.5)
                
                js_write_latex = """
                function writeLatex(el, latex) {
                    try {
                        let elements = [el].concat(Array.from(el.querySelectorAll('*')));
                        for (let target of elements) {
                            if (typeof MQ !== 'undefined' && MQ.MathField) {
                                let mf = MQ.MathField(target);
                                if (mf) { mf.latex(latex); return true; }
                            }
                            if (typeof jQuery !== 'undefined') {
                                let $el = jQuery(target);
                                let mq = $el.data('MathQuill');
                                if (mq && typeof mq.latex === 'function') { mq.latex(latex); return true; }
                            }
                        }
                    } catch(e) {}
                    return false;
                }
                return writeLatex(arguments[0], arguments[1]);
                """
                if driver.execute_script(js_write_latex, mq_span, ans):
                    log.info("Successfully wrote MathQuill via JS: %s", ans)
                    action_done = True
                else:
                    log.info("MathQuill JS API failed. Typing via keypad...")
                    enter_math_answer(driver, ans)
                    action_done = True
            else:
                log.warning("No visible MathQuill span found matching index %d", mathquill_idx)
            input_idx += 1
                
        # Case C: Dropdown Select
        elif is_dropdown:
            log.info("Setting dropdown select inputIdx=%d to value=%s via JS...", input_idx, ans)
            if driver.execute_script(js_set_backing_input_by_index, active_item, input_idx, ans):
                action_done = True
            else:
                log.warning("Failed to set dropdown value via JS.")
            input_idx += 1
                
        # Case D: Standard text inputs/textareas
        elif is_standard:
            log.info("Setting standard input inputIdx=%d to value=%s...", input_idx, ans)
            try:
                inputs = active_item.find_elements(By.CSS_SELECTOR, "input:not([type='hidden']), textarea")
                text_inputs = [i for i in inputs if i.is_displayed() and not i.get_attribute("readonly")]
                if input_idx < len(text_inputs):
                    target_el = text_inputs[input_idx]
                    scroll_into_view(driver, target_el)
                    target_el.clear()
                    target_el.send_keys(ans)
                    action_done = True
            except Exception as e:
                log.warning("Failed standard input send_keys: %s. Falling back to JS...", e)
                
            if not action_done:
                if driver.execute_script(js_set_backing_input_by_index, active_item, input_idx, ans):
                    action_done = True
                else:
                    log.warning("Failed to set standard input value via JS.")
            input_idx += 1
                
        if action_done:
            success_count += 1
            
    return success_count > 0



def handle_text_inputs(driver: WebDriver, answer: str, active_item: WebElement = None) -> bool:
    """Type answer into text input boxes and handle custom keypads if shown."""
    # 1. Look for visible editable math fields or standard inputs
    if active_item:
        math_fields = active_item.find_elements(By.CSS_SELECTOR, ".mq-editable-field, .lrn-formula-input")
        inputs = active_item.find_elements(By.CSS_SELECTOR, "input, textarea, [class*='mq-textarea'] textarea")
    else:
        math_fields = driver.find_elements(By.CSS_SELECTOR, ".mq-editable-field, .lrn-formula-input")
        inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea, [class*='mq-textarea'] textarea")
        
    visible_math_fields = [f for f in math_fields if f.is_displayed()]
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
    # Normalize and copy answers to avoid modifying the caller's copy
    import re
    normalized_answers = {}
    for q_num, val in answers.items():
        if val is not None and str(val).strip() != "":
            if isinstance(val, bool):
                val = str(val)
            elif isinstance(val, list):
                val = [str(x) if isinstance(x, bool) else x for x in val]
            else:
                val_str = str(val).strip()
                # Self-healing: if it starts with "[" but is missing the closing bracket "]", try to repair it
                if val_str.startswith("[") and not val_str.endswith("]"):
                    for suffix in ("]", '"]', '", "True"]', '", "False"]'):
                        try:
                            loaded = json.loads(val_str + suffix)
                            if isinstance(loaded, list):
                                val = [str(x) if isinstance(x, bool) else x for x in loaded]
                                break
                        except Exception:
                            pass

                if isinstance(val, str):
                    if val.startswith("[") and val.endswith("]"):
                        try:
                            loaded = json.loads(val)
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
            normalized_answers[str(q_num)] = val
    answers = normalized_answers

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
            
        question_success = False
        correctness = "unknown"
        
        for q_attempt in range(3):
            log.info("Answering attempt %d for Question %d...", q_attempt + 1, q_no)
            
            # Ensure we are on the correct question dot
            if get_current_question_number(driver) != q_no:
                click_question_dot(driver, q_no)
                wait_for_active_question(driver, q_no)
                time.sleep(1.5)
                
            active_item = get_active_container(driver, q_no)
            # Wait up to 10 seconds for inputs inside the active item to be ready
            wait_for_inputs_ready(driver, active_item, timeout=10.0)
            
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
            
            # Attempt to input answers, retrying up to 3 times if unsuccessful
            for attempt in range(3):
                active_item = get_active_container(driver, q_no)
                
                # A. Try MCQ (single choice or multi-select list)
                if handle_mcq(driver, q_answer, active_item):
                    input_success = True
                    
                # B. Try Matrix (if list of values or parsed list of values)
                elif (isinstance(q_answer, list) or matrix_answers) and handle_matrix(driver, matrix_answers or q_answer, active_item):
                    input_success = True
                    
                # B2. Try Cloze / Drag-and-drop (if list of values)
                elif isinstance(q_answer, list) and handle_cloze_and_drag_drop(driver, q_answer, active_item):
                    input_success = True
                    
                # C. Try Text/Keypad / Cloze / Drag-and-drop (if single string value)
                elif isinstance(q_answer, str) and (handle_cloze_and_drag_drop(driver, [q_answer], active_item) or handle_text_inputs(driver, q_answer, active_item)):
                    input_success = True
                    
                if input_success:
                    break
                    
                log.warning("Attempt %d to enter answer for Question %d failed, retrying in 1.5 seconds...", attempt + 1, q_no)
                time.sleep(1.5)
                
            if not input_success:
                log.warning("No active input fields could be resolved for Question %d on attempt %d.", q_no, q_attempt + 1)
                continue
                
            # Submit the answer
            submit_btn = None
            all_btns = []
            for tag in ["button", "input", "span", "a", "div"]:
                all_btns.extend(driver.find_elements(By.TAG_NAME, tag))
                
            # Priority 1: Visible elements with text exactly containing "submit answer", "check answer", "submit", "check"
            for btn in all_btns:
                try:
                    if btn.is_displayed():
                        txt = (btn.text or "").strip().lower()
                        # Exclude any timer toggles or elements containing "timer"
                        if "timer" in txt:
                            continue
                        # Check text content matches
                        if txt in ("submit answer", "check answer", "submit", "check"):
                            submit_btn = btn
                            break
                except Exception:
                    pass
                    
            # Priority 2: Visible elements where the text contains "submit" or "check" (but not "timer")
            if not submit_btn:
                for btn in all_btns:
                    try:
                        if btn.is_displayed():
                            txt = (btn.text or "").strip().lower()
                            if "timer" in txt:
                                continue
                            if any(w in txt for w in ["submit", "check"]):
                                is_checkbox = (btn.get_attribute("type") == "checkbox")
                                if not is_checkbox:
                                    submit_btn = btn
                                    break
                    except Exception:
                        pass
                        
            # Priority 3: Fallback value/class lookup, strictly avoiding "timer"
            if not submit_btn:
                for btn in all_btns:
                    try:
                        txt = (btn.text or "").strip().lower()
                        val = (btn.get_attribute("value") or "").strip().lower()
                        cls = (btn.get_attribute("class") or "").strip().lower()
                        if "timer" in txt or "timer" in val or "timer" in cls:
                            continue
                        is_submit = any(w in txt or w in val or w in cls for w in ["submit", "check"])
                        is_checkbox = (btn.get_attribute("type") == "checkbox")
                        if is_submit and not is_checkbox and "toggle" not in cls and "switch" not in cls:
                            submit_btn = btn
                            break
                    except Exception:
                        pass
                    
            if submit_btn:
                log.info("Clicking Submit Answer...")
                driver.execute_script("arguments[0].click();", submit_btn)
                time.sleep(3.0)  # Wait for submission grading to complete
            else:
                log.warning("Submit Answer button not found for Question %d.", q_no)
                
            # Determine correctness by looking at the pagination dot classes (with a retry/wait loop)
            correctness = "unknown"
            start_check = time.time()
            while time.time() - start_check < 5.0:
                dots_after = get_question_dot_buttons(driver)
                if 1 <= q_no <= len(dots_after):
                    try:
                        classes = (dots_after[q_no - 1].get_attribute("class") or "").lower()
                        if "green" in classes:
                            correctness = "correct"
                            break
                        elif "orange" in classes or "red" in classes:
                            correctness = "incorrect"
                            break
                        elif "purple" in classes or "blue" in classes:
                            correctness = "partially_correct"
                            break
                    except Exception:
                        pass
                time.sleep(0.5)
                
            if correctness != "unknown":
                question_success = True
                break
                
            log.warning("Submission verification failed for Question %d on attempt %d. Retrying entire question flow...", q_no, q_attempt + 1)
            time.sleep(2.0)
            
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
                # Ensure we are currently viewing the correct question to take the screenshot
                if get_current_question_number(driver) != q_no:
                    click_question_dot(driver, q_no)
                    wait_for_active_question(driver, q_no)
                    time.sleep(1.0)
                    
                active_item = get_active_container(driver, q_no)
                if active_item:
                    scroll_into_view(driver, active_item)
                    time.sleep(0.5)
                    
                driver.save_screenshot(screenshot_path)
                log.info("Saved graded screenshot for Question %d: %s", q_no, screenshot_path)
            except Exception as e:
                log.error("Failed to save graded screenshot: %s", e)
                screenshot_path = None
            
        # Try to extract the website's correct answer if it's not correct
        website_correct_answer = None
        if correctness != "correct":
            try:
                if get_current_question_number(driver) != q_no:
                    click_question_dot(driver, q_no)
                    wait_for_active_question(driver, q_no)
                    time.sleep(1.0)
                website_correct_answer = extract_website_correct_answer(driver)
            except Exception:
                pass
            if website_correct_answer:
                log.info("Extracted correct answer from website: %s", website_correct_answer)
                print(f"-> Website expects: {website_correct_answer}")
                
        results[q_no] = {
            "status": correctness,
            "submitted_answer": q_answer,
            "screenshot_path": screenshot_path,
            "website_correct_answer": website_correct_answer
        }
            
        # Transition to next question
        if q_no < num_questions:
            if get_current_question_number(driver) != q_no + 1:
                log.info("Navigating to next question dot: %d", q_no + 1)
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
