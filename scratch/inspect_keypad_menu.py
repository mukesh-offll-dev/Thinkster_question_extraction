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
from answering import wait_for_loading

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
                if card_id in ("AQCMXAL211", "AQCMXAL212"):
                    matching_card = card
                    break
            
            if matching_card:
                card_id, ws_title = finder.extract_worksheet_id_and_title(matching_card)
                finder._click_start(matching_card, "Complex Numbers", ws_title)
                
                if wait_for_loading(driver):
                    time.sleep(3.0)
                    
                    inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea, .mq-editable-field, .lrn-formula-input")
                    visible_inputs = [i for i in inputs if i.is_displayed()]
                    
                    if visible_inputs:
                        target_input = visible_inputs[0]
                        driver.execute_script("arguments[0].click();", target_input)
                        time.sleep(2.0)
                        
                        # Find the dropdown menu button in the keypad
                        # Usually it is a button with class lrn-formula-keyboard-menu-button or similar
                        menu_buttons = driver.find_elements(By.CSS_SELECTOR, "button, [role='button'], div, span")
                        keypad_menus = []
                        for el in menu_buttons:
                            try:
                                if el.is_displayed():
                                    classes = el.get_attribute("class") or ""
                                    text = el.text.strip().replace('\n', ' ')
                                    if "menu" in classes or "group" in classes or "select" in classes or "dropdown" in classes or "basic" in text.lower() or "keyboard" in text.lower():
                                        # verify if inside keypad
                                        parent = el.find_element(By.XPATH, "..")
                                        parent_classes = parent.get_attribute("class") or ""
                                        if any(k in (classes + " " + parent_classes).lower() for k in ["keypad", "keyboard", "palette", "formula", "math"]):
                                            keypad_menus.append(el)
                            except Exception:
                                pass
                                
                        print(f"Found {len(keypad_menus)} potential menu elements in keypad:")
                        for idx, el in enumerate(keypad_menus):
                            try:
                                tag = el.tag_name
                                classes = el.get_attribute("class") or ""
                                text = el.text.strip().replace('\n', ' ')
                                outer_html = driver.execute_script("return arguments[0].outerHTML;", el)
                                print(f"  [{idx}]: Tag={tag} | Class='{classes}' | Text='{text}'")
                                # Save HTML to scratch/keypad_menu_element_{idx}.html
                                with open(f"scratch/keypad_menu_element_{idx}.html", "w", encoding="utf-8") as f:
                                    f.write(outer_html)
                            except Exception as ex:
                                print(f"  [{idx}] Error: {ex}")
                                
                        # Let's try to click the first element that looks like a dropdown or selector button
                        # Typically the dropdown button has class "lrn-formula-keyboard-menu-button" or contains an arrow icon
                        # Let's search for buttons inside elements with class containing 'menu'
                        menu_toggles = driver.find_elements(By.CSS_SELECTOR, ".lrn-formula-keyboard-menu-button, [class*='menu-button'], [class*='menu-toggle']")
                        print(f"Found {len(menu_toggles)} menu toggles directly.")
                        for idx, toggle in enumerate(menu_toggles):
                            if toggle.is_displayed():
                                print(f"Clicking menu toggle [{idx}]...", flush=True)
                                driver.execute_script("arguments[0].click();", toggle)
                                time.sleep(2.0)
                                
                                # Take screenshot when menu is open
                                driver.save_screenshot(f"screenshots/keypad_menu_open_{idx}.png")
                                print(f"Saved screenshots/keypad_menu_open_{idx}.png", flush=True)
                                
                                # Find all list items or buttons that appear
                                menu_options = driver.find_elements(By.CSS_SELECTOR, "li, button, a, [role='option']")
                                visible_options = []
                                for opt in menu_options:
                                    try:
                                        if opt.is_displayed():
                                            text = opt.text.strip().replace('\n', ' ')
                                            classes = opt.get_attribute("class") or ""
                                            if text or "keyboard" in classes or "basic" in classes:
                                                visible_options.append((opt, text, classes))
                                    except Exception:
                                        pass
                                        
                                print(f"Visible options in menu:", flush=True)
                                for o_idx, (opt, text, classes) in enumerate(visible_options):
                                    html = driver.execute_script("return arguments[0].outerHTML;", opt)
                                    print(f"  Option [{o_idx}]: Text='{text}' | Class='{classes}'", flush=True)
                                    with open(f"scratch/keypad_option_{idx}_{o_idx}.html", "w", encoding="utf-8") as f:
                                        f.write(html)
                                        
                                # Close menu by clicking the toggle again or somewhere else
                                driver.execute_script("arguments[0].click();", toggle)
                                time.sleep(1.0)
                                
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
