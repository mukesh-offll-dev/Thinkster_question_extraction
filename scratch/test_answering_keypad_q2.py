import time
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
import config
from login import launch_browser, login
from dashboard import select_student, click_start_learning
from topic_worksheet_finder import TopicWorksheetFinder
from utils import scroll_into_view, safe_click
from answering import wait_for_loading, click_question_dot, wait_for_active_question

def tokenize_math_string(s: str):
    tokens = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        
        if c == '\\':
            cmd = '\\'
            i += 1
            while i < n and (s[i].isalpha() or s[i] in ('(', ')', '[', ']')):
                cmd += s[i]
                i += 1
            tokens.append(('cmd', cmd))
            continue
            
        if c in ('^', '_', '{', '}', '(', ')'):
            tokens.append(('char', c))
            i += 1
            continue
            
        if c.isdigit() or c == '.':
            num = ''
            while i < n and (s[i].isdigit() or s[i] == '.'):
                num += s[i]
                i += 1
            for digit in num:
                tokens.append(('char', digit))
            continue
            
        if c.isalpha():
            tokens.append(('var', c))
            i += 1
            continue
            
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

def generate_keypad_actions(tokens):
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
        print(f"Error switching keypad layout to {target_layout}: {e}")
    return False

def enter_math_answer(driver: WebDriver, answer: str) -> bool:
    tokens = tokenize_math_string(answer)
    actions = generate_keypad_actions(tokens)
    print(f"Generated keypad actions: {actions}")
    
    for layout, act_type, selector in actions:
        if layout:
            switch_success = switch_keypad_layout(driver, layout)
            if not switch_success:
                print(f"Warning: Failed to switch to layout {layout}")
                
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
                print(f"Error: Button with selector {selector} not visible on page.")
        except Exception as e:
            print(f"Error executing action click on {selector}: {e}")
            
    return True

def main():
    config.HEADLESS = True
    driver = launch_browser()
    try:
        login(driver)
        select_student(driver)
        click_start_learning(driver)
        time.sleep(5)
        
        finder = TopicWorksheetFinder(driver)
        topic_el = finder._find_topic_element("Complex Numbers")
        if topic_el:
            scroll_into_view(driver, topic_el)
            safe_click(driver, topic_el)
            time.sleep(4.0)
            topic_container = driver.find_element(By.TAG_NAME, "body")
            cards = finder._collect_cards(topic_container)
            
            matching_card = None
            for card in cards:
                card_id, _ = finder.extract_worksheet_id_and_title(card)
                if card_id == "AQCMXAL211":
                    matching_card = card
                    break
            
            if matching_card:
                card_id, ws_title = finder.extract_worksheet_id_and_title(matching_card)
                finder._click_start(matching_card, "Complex Numbers", ws_title)
                
                if wait_for_loading(driver):
                    time.sleep(3.0)
                    
                    # ── TEST QUESTION 2 ──
                    print("\n--- TESTING Q2 ---")
                    click_question_dot(driver, 2)
                    wait_for_active_question(driver, 2)
                    time.sleep(2.0)
                    
                    # Focus input using the same broad selector
                    inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea, .mq-editable-field, .lrn-formula-input")
                    visible_inputs = [i for i in inputs if i.is_displayed()]
                    if visible_inputs:
                        print("Focusing on Q2 math input...")
                        driver.execute_script("arguments[0].click();", visible_inputs[0])
                        time.sleep(1.0)
                        
                        # Enter answer
                        enter_math_answer(driver, "1+2i")
                        time.sleep(2.0)
                        
                        # Save screenshot
                        os.makedirs("screenshots", exist_ok=True)
                        driver.save_screenshot("screenshots/test_keypad_q2_after_xpath.png")
                        print("Saved screenshots/test_keypad_q2_after_xpath.png")
                    else:
                        print("No visible math input found for Q2")
                        
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
