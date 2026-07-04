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
from utils import scroll_into_view, safe_click, is_sidebar_element

def main():
    config.HEADLESS = True
    driver = launch_browser()
    try:
        login(driver)
        select_student(driver)
        click_start_learning(driver)
        time.sleep(5)
        
        print("\n=== SCANNING STUDENT DASHBOARD FOR TOPICS AND WORKSHEETS ===", flush=True)
        
        finder = TopicWorksheetFinder(driver)
        
        known_topics = [
            "Complex Numbers",
            "Algebra 2 Foundations",
            "Number Representation",
            "Number Relation",
            "Algebra",
            "Functions & Function Notation",
            "Multiplication",
            "Division",
            "Geometry"
        ]
        
        for topic_name in known_topics:
            topic_el = finder._find_topic_element(topic_name)
            if topic_el:
                print(f"\nFound Topic: '{topic_name}'", flush=True)
                try:
                    is_sidebar = is_sidebar_element(driver, topic_el)
                    if is_sidebar:
                        print(f"  Topic '{topic_name}' is sidebar. Clicking...", flush=True)
                        scroll_into_view(driver, topic_el)
                        safe_click(driver, topic_el)
                        time.sleep(4.0)
                        topic_container = driver.find_element(By.TAG_NAME, "body")
                    else:
                        print(f"  Topic '{topic_name}' is accordion. Expanding...", flush=True)
                        finder._expand_topic(topic_el)
                        time.sleep(1.5)
                        # Re-locate
                        topic_el = finder._find_topic_element(topic_name)
                        finder._expand_subsections(topic_el)
                        time.sleep(1.5)
                        # Re-locate
                        topic_el = finder._find_topic_element(topic_name)
                        try:
                            topic_container = driver.execute_script("return arguments[0].parentElement;", topic_el)
                            if not topic_container:
                                topic_container = topic_el
                        except Exception:
                            topic_container = topic_el
                    
                    cards = finder._collect_cards(topic_container)
                    print(f"  Collected {len(cards)} cards for '{topic_name}'", flush=True)
                    for card in cards:
                        try:
                            ws_id, ws_title = finder.extract_worksheet_id_and_title(card)
                            if ws_id:
                                print(f"    - Worksheet ID: {ws_id} | Title: {ws_title}", flush=True)
                            else:
                                # Snippet of text
                                text = card.text.strip().replace('\n', ' ')
                                if len(text) > 60:
                                    text = text[:57] + "..."
                                print(f"    - Could not extract ID. Card text: '{text}'", flush=True)
                        except Exception as ce:
                            print(f"    - Error reading card: {ce}", flush=True)
                except Exception as te:
                    print(f"  Error expanding/inspecting topic '{topic_name}': {te}", flush=True)
            else:
                print(f"\nTopic not found: '{topic_name}'", flush=True)
                
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
