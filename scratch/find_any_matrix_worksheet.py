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
from utils import scroll_into_view, safe_click, js_click

def main():
    config.HEADLESS = True
    driver = launch_browser()
    try:
        login(driver)
        select_student(driver)
        click_start_learning(driver)
        time.sleep(5)
        
        finder = TopicWorksheetFinder(driver)
        topics = finder._get_all_topic_elements()
        print(f"Total topics to scan: {len(topics)}")
        
        all_cards = []
        for idx, topic_el in enumerate(topics):
            try:
                # Re-locate
                topics = finder._get_all_topic_elements()
                topic_el = topics[idx]
                topic_name = finder._element_heading_text(topic_el)
                print(f"\n--- Scanning Topic {idx+1}: '{topic_name}' ---")
                
                scroll_into_view(driver, topic_el)
                finder._expand_topic(topic_el)
                time.sleep(1.5)
                
                # Re-locate after animation
                topics = finder._get_all_topic_elements()
                topic_el = topics[idx]
                
                # Click Completed and Show All filters inside this topic
                buttons = topic_el.find_elements(By.XPATH, ".//button | .//a | .//span")
                for b in buttons:
                    try:
                        text = b.text.strip()
                        if b.is_displayed() and text in ("Completed", "Show All"):
                            print(f"  Clicking filter: {text}")
                            js_click(driver, b)
                            time.sleep(1.0)
                    except Exception:
                        pass
                
                # Collect cards
                cards = finder._collect_cards(topic_el)
                print(f"  Cards found: {len(cards)}")
                for card in cards:
                    card_id, title = finder.extract_worksheet_id_and_title(card)
                    print(f"    - Card ID: '{card_id}' | Title: '{title}'")
                    all_cards.append((topic_name, card_id, title, card))
            except Exception as e:
                print(f"  Error scanning topic: {e}")
                
        print("\n=== SCAN SUMMARY ===")
        print(f"Total unique worksheets found: {len(all_cards)}")
        for topic, cid, title, _ in all_cards:
            print(f"Topic: {topic} | ID: {cid} | Title: {title}")
            
    except Exception as e:
        print("Error:", e, flush=True)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
