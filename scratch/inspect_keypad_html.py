import time
import os
import sys

# Ensure parent directory is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium.webdriver.common.by import By
import config
from login import launch_browser, login
from dashboard import select_student, click_start_learning
from topic_worksheet_finder import TopicWorksheetFinder
from utils import scroll_into_view, safe_click
from answering import wait_for_loading, click_question_dot, wait_for_active_question

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
            # Expand and click first worksheet
            scroll_into_view(driver, topic_el)
            safe_click(driver, topic_el)
            time.sleep(4.0)
            topic_container = driver.find_element(By.TAG_NAME, "body")
            cards = finder._collect_cards(topic_container)
            
            matching_card = None
            for card in cards:
                card_id, _ = finder.extract_worksheet_id_and_title(card)
                if card_id in ("AQCMXAL211", "AQCMXAL212"):
                    matching_card = card
                    break
            
            if matching_card:
                card_id, ws_title = finder.extract_worksheet_id_and_title(matching_card)
                print(f"Opening worksheet {ws_title} ({card_id})...", flush=True)
                finder._click_start(matching_card, "Complex Numbers", ws_title)
                
                if wait_for_loading(driver):
                    time.sleep(3.0)
                    # Let's inspect Q1
                    print("Inspecting Question 1...", flush=True)
                    
                    # Save a screenshot to see the question
                    os.makedirs("screenshots", exist_ok=True)
                    driver.save_screenshot("screenshots/test_q1.png")
                    print("Saved screenshots/test_q1.png", flush=True)
                    
                    # Find all inputs
                    inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea, [class*='mq-textarea'] textarea, .mq-editable-field, .lrn-formula-input")
                    visible_inputs = [i for i in inputs if i.is_displayed()]
                    print(f"Found {len(visible_inputs)} visible inputs.", flush=True)
                    
                    if visible_inputs:
                        target_input = visible_inputs[0]
                        print("Clicking input to show keypad...", flush=True)
                        driver.execute_script("arguments[0].click();", target_input)
                        time.sleep(3.0)
                        
                        # Save screenshot with keypad
                        driver.save_screenshot("screenshots/test_q1_keypad.png")
                        print("Saved screenshots/test_q1_keypad.png", flush=True)
                        
                        # Find keypad container
                        keypad_containers = driver.find_elements(By.CSS_SELECTOR, "[class*='keypad'], [class*='keyboard'], [class*='palette'], [class*='formula-keyboard']")
                        print(f"Found {len(keypad_containers)} potential keypad containers.", flush=True)
                        
                        for idx, kc in enumerate(keypad_containers):
                            try:
                                classes = kc.get_attribute("class") or ""
                                print(f"Keypad Container [{idx}]: Tag={kc.tag_name} | Class='{classes}'", flush=True)
                                # Dump first 1000 chars of HTML
                                html = driver.execute_script("return arguments[0].outerHTML;", kc)
                                print(f"--- Keypad Container HTML (first 2000 chars) ---", flush=True)
                                print(html[:2000], flush=True)
                                print("-----------------------------------------------", flush=True)
                                
                                # Write full HTML to a scratch file
                                os.makedirs("scratch", exist_ok=True)
                                with open(f"scratch/keypad_container_{idx}.html", "w", encoding="utf-8") as f:
                                    f.write(html)
                                print(f"Wrote full HTML to scratch/keypad_container_{idx}.html", flush=True)
                            except Exception as ex:
                                print(f"Error dumping keypad: {ex}", flush=True)
                                
                        # List all visible buttons in the keypad
                        buttons = driver.find_elements(By.TAG_NAME, "button")
                        visible_keypad_btns = []
                        for btn in buttons:
                            try:
                                if btn.is_displayed():
                                    classes = btn.get_attribute("class") or ""
                                    # check if parent is keypad
                                    parent = btn.find_element(By.XPATH, "..")
                                    parent_classes = parent.get_attribute("class") or ""
                                    gp = parent.find_element(By.XPATH, "..")
                                    parent_classes += " " + (gp.get_attribute("class") or "")
                                    
                                    if any(k in (classes + " " + parent_classes).lower() for k in ["keypad", "keyboard", "palette", "formula", "math", "lrn-key"]):
                                        visible_keypad_btns.append(btn)
                            except Exception:
                                pass
                        
                        print(f"Found {len(visible_keypad_btns)} displayed keypad buttons:", flush=True)
                        for idx, btn in enumerate(visible_keypad_btns):
                            try:
                                text = btn.text.strip().replace('\n', ' ')
                                classes = btn.get_attribute("class") or ""
                                aria = btn.get_attribute("aria-label") or ""
                                print(f"  Btn [{idx}]: text='{text}' | aria='{aria}' | class='{classes}'", flush=True)
                            except Exception as ex:
                                print(f"  Btn [{idx}] Error: {ex}", flush=True)
                                
                else:
                    print("Worksheet did not load.", flush=True)
            else:
                print("No matching worksheet card found.", flush=True)
        else:
            print("Complex Numbers topic not found.", flush=True)
            
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
