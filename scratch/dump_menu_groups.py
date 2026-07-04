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
                        
                        # Find the container
                        containers = driver.find_elements(By.CSS_SELECTOR, ".lrn-formula-keyboard-menu-groups")
                        print(f"Found {len(containers)} menu-groups containers.")
                        for idx, container in enumerate(containers):
                            html = driver.execute_script("return arguments[0].outerHTML;", container)
                            # Let's save to a file
                            os.makedirs("scratch", exist_ok=True)
                            with open(f"scratch/menu_groups_{idx}.html", "w", encoding="utf-8") as f:
                                f.write(html)
                            print(f"Wrote scratch/menu_groups_{idx}.html")
                            
                            # Let's find all buttons/elements inside it and print their properties safely
                            descendants = container.find_elements(By.XPATH, ".//*")
                            print(f"  Container [{idx}] has {len(descendants)} descendants:")
                            for d_idx, desc in enumerate(descendants):
                                try:
                                    tag = desc.tag_name
                                    classes = desc.get_attribute("class") or ""
                                    text = desc.text.strip().replace('\n', ' ')
                                    # safe ascii print
                                    text_ascii = text.encode('ascii', errors='ignore').decode('ascii')
                                    print(f"    Desc [{d_idx}]: Tag={tag} | Class='{classes}' | Text='{text_ascii}'")
                                except Exception as ex:
                                    print(f"    Desc [{d_idx}] Error: {ex}")
                                    
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
