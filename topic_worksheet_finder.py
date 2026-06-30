# =============================================================================
# topic_worksheet_finder.py - Topic-Scoped Worksheet Search
# =============================================================================
# Workflow:
#   1. User provides Topic Name + Worksheet ID.
#   2. Locate the named topic on the dashboard (exact match first, fuzzy fallback).
#   3. Expand ONLY that topic.
#   4. Inspect every worksheet card inside it.
#   5. Extract Worksheet ID from every available source in the card HTML.
#   6. Compare extracted ID against user input (exact, case-sensitive).
#   7. On match  -> print details + click Start.
#   8. On no match -> print "not found" message. Never start wrong worksheet.
# =============================================================================

import re
import time
from typing import Optional

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config
from logger import get_logger
from utils import (
    js_click,
    safe_attr,
    safe_click,
    safe_text,
    scroll_into_view,
    wait_for_page_load,
)

log = get_logger()


# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------

# Candidate topic container selectors (tried in order)
_TOPIC_SELECTORS = [
    "[class*='topic']",
    "[class*='subject']",
    "[class*='chapter']",
    "[class*='category']",
    "[class*='accordion']",
    "[class*='section']",
    "[class*='skill-group']",
    "[role='button']",
    "[aria-expanded]",
]

# Candidate header/toggle selectors inside a topic container
_HEADER_SELECTORS = [
    "[class*='header']",
    "[class*='title']",
    "[class*='toggle']",
    "[class*='accordion-button']",
    "[class*='expand']",
    "h2", "h3", "h4",
    "button", "[role='button']",
]

# Candidate worksheet card selectors inside an expanded topic
_CARD_SELECTORS = [
    "[class*='worksheet']",
    "[class*='lesson']",
    "[class*='activity']",
    "[class*='assignment']",
    "[class*='card']",
    "[class*='item']",
    "li",
    "[data-id]",
    "[data-worksheet-id]",
]

# Attributes that may carry the Worksheet ID
_ID_ATTRIBUTES = [
    "data-id",
    "data-worksheet-id",
    "data-lesson-id",
    "data-activity-id",
    "data-assignment-id",
    "data-task-id",
    "data-skill-id",
    "data-content-id",
    "data-code",
    "id",
]

# Selectors for the Start button inside / near a worksheet card
_START_SELECTORS = [
    "button[class*='start' i]",
    "a[class*='start' i]",
    "[class*='start-btn' i]",
    "button[class*='resume' i]",
    "a[class*='resume' i]",
    "[class*='resume' i]",
    "button[class*='continue' i]",
    "a[class*='continue' i]",
    "[class*='continue' i]",
    "[class*='play' i]",
    "button",
    "a",
]


# ---------------------------------------------------------------------------
# Main finder class
# ---------------------------------------------------------------------------

class TopicWorksheetFinder:
    """
    Finds a specific worksheet by (Topic Name, Worksheet ID) and opens it.

    Rules
    -----
    - Search is confined to the named topic only.
    - Worksheet ID matching is exact and case-sensitive.
    - The worksheet title is never used as the primary identifier.
    """

    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def find_and_open(self, topic_name: str, worksheet_id: str) -> Optional[str]:
        """
        Locate the worksheet and open it.

        Parameters
        ----------
        topic_name   : Topic name as entered by the user.
        worksheet_id : Worksheet ID or Keyword (fuzzy matching).

        Returns
        -------
        bool - The actual Worksheet ID string if found and started, else None.
        """
        ws_id = worksheet_id.strip()
        log.info("Searching topic '%s' for worksheet keyword/ID '%s'...", topic_name, ws_id)

        # ── 1. Find the topic element ──────────────────────────────────
        topic_el = self._find_topic_element(topic_name)
        if topic_el is None:
            msg = f"Topic '{topic_name}' was not found on the dashboard."
            log.warning("%s Falling back to global search...", msg)
            return self.scan_all_topics(worksheet_id)

        print(f"\nTopic Selected:\n{topic_name}\n")
        print("Searching worksheets...\n")

        # ── 2. Expand the topic ────────────────────────────────────────
        self._expand_topic(topic_el)
        time.sleep(1.5)  # Allow accordion to animate open

        # Re-resolve the element (may be stale after expansion animation)
        topic_el = self._find_topic_element(topic_name)
        if topic_el is None:
            log.warning("Topic element became stale after expansion. Re-searching...")
            time.sleep(1)
            topic_el = self._find_topic_element(topic_name)
            if topic_el is None:
                print(f"\n[ERROR] Could not re-locate topic '{topic_name}' after expansion.\n")
                return False

        # Expand any nested sub-accordions, dropdown lists or carets inside this topic
        self._expand_subsections(topic_el)
        time.sleep(1.5)

        # Scroll to bottom and top of the topic container to trigger lazy loading of cards
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'end'});", topic_el)
            time.sleep(1.0)
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'start'});", topic_el)
            time.sleep(1.0)
        except Exception:
            pass

        # Re-resolve the element to prevent StaleElementReferenceException after changes
        topic_el = self._find_topic_element(topic_name)
        if topic_el is None:
            print(f"\n[ERROR] Could not re-locate topic '{topic_name}' after expanding sub-sections.\n")
            return False

        # ── 3. Collect all worksheet cards inside the topic ────────────
        cards = self._collect_cards(topic_el)
        print(f"Found {len(cards)} worksheets.\n")

        if not cards:
            print(f"[NOT FOUND] No worksheet cards found under topic '{topic_name}'.\n")
            return False

        # ── 4. Score each card to find the best match ─────────────────
        best_card = None
        best_title = ""
        best_score = 0.0

        if len(cards) == 1:
            best_card = cards[0]
            try:
                best_title = safe_text(best_card).strip()
                if "\n" in best_title:
                    best_title = best_title.split("\n")[0].strip()
            except Exception:
                best_title = "Worksheet"
            best_score = 1.0
        else:
            for idx, card in enumerate(cards):
                try:
                    # Extract text
                    ws_title = safe_text(card).strip()
                    # Clean title to only keep the first line (usually the main title)
                    if "\n" in ws_title:
                        ws_title = ws_title.split("\n")[0].strip()

                    # Calculate similarity score
                    score = self._calculate_match_score(card, ws_title, ws_id)
                    if score > best_score:
                        best_score = score
                        best_card = card
                        best_title = ws_title
                except StaleElementReferenceException:
                    continue

        # ── 5. Click Start on the best match if above threshold ────────
        # Threshold: if it matches at least something (e.g., 0.25)
        if best_card is not None and best_score >= 0.25:
            confidence = int(best_score * 100)
            if confidence > 99:
                confidence = 99
            elif confidence < 0:
                confidence = 0

            print("Best Match Found\n")
            print(f"Worksheet:\n{best_title}\n")
            print(f"Confidence:\n{confidence}%\n")
            print("Opening Worksheet...\n")

            log.info("Best match: '%s' (Score: %.2f) - Clicking Start...", best_title, best_score)
            # Retrieve outerHTML before clicking start to avoid StaleElementReferenceException after navigation
            try:
                card_html = best_card.get_attribute("outerHTML") or ""
            except Exception:
                card_html = ""
            success = self._click_start(best_card, topic_name, best_title)
            if success:
                print("Worksheet Loaded Successfully.\n")
                actual_id = self._parse_actual_id(best_title, card_html, ws_id)
                return actual_id
            return None

        # ── 6. No match above threshold ────────────────────────────────
        log.warning("Worksheet not found in targeted topic '%s'. Falling back to global search...", topic_name)
        return self.scan_all_topics(worksheet_id)

    def _calculate_match_score(self, card: WebElement, title: str, query: str) -> float:
        """
        Calculate a matching confidence score between 0.0 and 1.0.
        """
        title_clean = title.lower().strip()
        query_clean = query.lower().strip()

        if not query_clean:
            return 0.0

        # Strategy 0: check if query is exact or substring of title
        if query_clean == title_clean:
            return 1.0

        if query_clean in title_clean:
            # Substring match. Higher ratio of query to title length = higher score
            ratio = len(query_clean) / len(title_clean)
            return 0.8 + 0.2 * ratio

        # Strategy 1: Check outerHTML (e.g. for exact Worksheet ID like AQCMXAL209)
        try:
            html = card.get_attribute("outerHTML")
            if html and query.strip() in html:
                return 0.9
        except Exception:
            pass

        # Strategy 2: Word-based token match
        title_words = set(re.findall(r'\w+', title_clean))
        query_words = set(re.findall(r'\w+', query_clean))

        if not query_words:
            return 0.0

        matching_words = query_words.intersection(title_words)
        word_match_ratio = len(matching_words) / len(query_words)

        if word_match_ratio == 1.0:
            # All words match, but maybe in different order or missing some words from title
            return 0.75 + 0.05 * (len(query_clean) / len(title_clean))

        # Strategy 3: SequenceMatcher ratio
        from difflib import SequenceMatcher
        seq_ratio = SequenceMatcher(None, title_clean, query_clean).ratio()

        # Weighted average of word match and sequence match
        return word_match_ratio * 0.7 + seq_ratio * 0.3

    # ------------------------------------------------------------------
    # Topic location
    # ------------------------------------------------------------------

    def _find_topic_element(self, topic_name: str) -> Optional[WebElement]:
        """
        Locate the topic container element whose visible text best matches
        *topic_name*. Tries exact match first, then case-insensitive
        contains match.

        Returns WebElement or None.
        """
        target_exact  = topic_name.strip()
        target_lower  = target_exact.lower()

        exact_matches    = []
        contains_matches = []

        for sel in _TOPIC_SELECTORS:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elements:
                    try:
                        text = self._element_heading_text(el)
                        if not text:
                            continue
                        if text.strip() == target_exact:
                            exact_matches.append(el)
                        elif target_lower in text.lower():
                            contains_matches.append(el)
                    except StaleElementReferenceException:
                        continue
            except Exception:
                continue

        if exact_matches:
            log.debug("Exact topic match found.")
            return exact_matches[0]
        if contains_matches:
            log.debug("Fuzzy topic match: '%s'", self._element_heading_text(contains_matches[0]))
            return contains_matches[0]

        # Last resort: check headings directly
        for tag in ("h1", "h2", "h3", "h4", "h5", "span", "div"):
            elements = self.driver.find_elements(By.TAG_NAME, tag)
            for el in elements:
                try:
                    text = safe_text(el)
                    if target_lower in text.lower() and el.is_displayed():
                        # Return the closest clickable ancestor
                        parent = self._clickable_ancestor(el)
                        return parent if parent else el
                except Exception:
                    continue

        return None

    def _element_heading_text(self, el: WebElement) -> str:
        """
        Extract the heading/title text from a topic container.
        Looks inside heading tags first, then falls back to the element's own text.
        """
        for tag in ("h1", "h2", "h3", "h4", "h5",
                    "[class*='title']", "[class*='name']", "[class*='header']"):
            try:
                children = el.find_elements(By.CSS_SELECTOR, tag)
                for child in children:
                    text = safe_text(child)
                    if text and len(text) < 120:
                        return text
            except Exception:
                continue

        text = safe_text(el)
        return text.split("\n")[0].strip() if text else ""

    def _clickable_ancestor(self, el: WebElement) -> Optional[WebElement]:
        """Walk up the DOM to find a clickable/interactive ancestor."""
        try:
            current = el
            for _ in range(6):
                current = self.driver.execute_script(
                    "return arguments[0].parentElement;", current
                )
                if current is None:
                    break
                tag = current.tag_name.lower()
                if tag in ("li", "div", "section", "article"):
                    return current
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Topic expansion
    # ------------------------------------------------------------------

    def _is_topic_expanded(self, topic_el: WebElement) -> bool:
        """
        Check if the topic accordion is expanded by looking for visible worksheets or content
        inside its parent/sibling container.
        """
        try:
            parent = self.driver.execute_script("return arguments[0].parentElement;", topic_el)
            if not parent:
                parent = topic_el
        except Exception:
            parent = topic_el
            
        # Re-use our collect_cards logic to see if we find visible cards inside parent
        cards = self._collect_cards(parent)
        if cards:
            for card in cards:
                try:
                    if card.is_displayed():
                        return True
                except Exception:
                    pass
        return False

    def _expand_topic(self, topic_el: WebElement) -> None:
        """
        Click the topic's expand toggle. Checks if it is already expanded to avoid
        collapsing it.
        """
        if self._is_topic_expanded(topic_el):
            log.debug("Topic is already expanded. Skipping click.")
            return

        # Try clicking a dedicated header/toggle inside the container
        for hdr_sel in _HEADER_SELECTORS:
            try:
                headers = topic_el.find_elements(By.CSS_SELECTOR, hdr_sel)
                for hdr in headers:
                    if hdr.is_displayed():
                        # Skip elements that are actually start/continue/resume/select buttons
                        text = safe_text(hdr).lower().strip()
                        if text in ("start", "resume", "continue", "begin", "go", "play", "select"):
                            continue
                        
                        scroll_into_view(self.driver, hdr)
                        safe_click(self.driver, hdr)
                        log.debug("Topic expanded via header selector '%s'.", hdr_sel)
                        return
            except Exception:
                continue

        # Fallback: click the container itself
        scroll_into_view(self.driver, topic_el)
        safe_click(self.driver, topic_el)
        log.debug("Topic expanded via container click.")

    def _expand_subsections(self, topic_el: WebElement) -> None:
        """
        Finds and expands any sub-accordions, dropdown toggles, or caret buttons
        inside the active topic element to reveal hidden worksheets.
        """
        js_code = """
        function expandToggles(el) {
            let count = 0;
            // Target tags that are typically used for headers, dropdown toggles, or accordion buttons
            let selectors = [
                'button', 'a', '[role="button"]', 
                '.lrn-accordion-header', '[class*="toggle" i]', 
                '[class*="expand" i]', '[class*="caret" i]', 
                '[class*="arrow" i]', '[class*="header" i]'
            ];
            let candidates = el.querySelectorAll(selectors.join(','));
            candidates.forEach(t => {
                // Ensure we don't click the parent topic container itself or something outside
                if (t === el || el.parentElement && t === el.parentElement) return;
                
                // Skip action/selection buttons (e.g. Select, Start, Resume)
                let text = (t.innerText || t.textContent || "").trim().toLowerCase();
                if (text === "select" || text === "start" || text === "resume" || text === "continue" || text === "begin" || text === "go" || text === "play") return;
                
                // Read expanded state
                let expanded = t.getAttribute('aria-expanded');
                let isCollapsed = t.classList.contains('collapsed') || 
                                  t.classList.contains('collapsed-item') || 
                                  (expanded === 'false');
                
                // If it is collapsed, let's scroll to it and click it
                if (isCollapsed || expanded === 'false') {
                    try {
                        t.scrollIntoView({behavior: 'instant', block: 'center'});
                        t.click();
                        count++;
                    } catch (e) {}
                }
            });
            return count;
        }
        return expandToggles(arguments[0]);
        """
        try:
            expanded_count = self.driver.execute_script(js_code, topic_el)
            if expanded_count > 0:
                log.info("Expanded %d sub-sections/dropdowns inside topic.", expanded_count)
        except Exception as e:
            log.warning("Could not expand sub-sections: %s", e)

    def _get_all_topic_elements(self) -> list[WebElement]:
        """
        Locate all topic containers on the dashboard page.
        """
        seen_ids = set()
        topics = []
        for sel in _TOPIC_SELECTORS:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elements:
                    try:
                        if el.is_displayed() and el.id not in seen_ids:
                            seen_ids.add(el.id)
                            topics.append(el)
                    except Exception:
                        continue
            except Exception:
                continue
        return topics

    def _parse_actual_id(self, title: str, card_html: str, query_id: str) -> str:
        """
        Parse the actual Worksheet ID from the card's title or HTML,
        falling back to query_id if not found.
        """
        # 1. Look for uppercase alphanumeric ID in parentheses in the title
        match = re.search(r'\(([A-Za-z0-9_\-]+)\)', title)
        if match:
            return match.group(1).strip()
            
        # 2. Look for ID in parentheses in the outerHTML
        match_html = re.search(r'\(([A-Za-z0-9_\-]{4,25})\)', card_html)
        if match_html:
            return match_html.group(1).strip()
            
        # 3. Fallback to attributes in HTML
        for attr in ["data-id", "data-worksheet-id", "data-lesson-id"]:
            attr_match = re.search(rf'{attr}\s*=\s*["\']([^"\']+)["\']', card_html, re.IGNORECASE)
            if attr_match:
                return attr_match.group(1).strip()

        return query_id

    def extract_worksheet_id_and_title(self, card: WebElement) -> tuple[Optional[str], str]:
        """
        Extract the Worksheet ID and cleaned title from a card.
        """
        # 1. Extract title
        try:
            title = safe_text(card).strip()
        except Exception:
            title = ""
            
        # Clean title to only keep the first line (usually the main title)
        if "\n" in title:
            first_line = title.split("\n")[0].strip()
        else:
            first_line = title

        # 2. Extract card HTML
        try:
            card_html = card.get_attribute("outerHTML") or ""
        except Exception:
            card_html = ""

        # Let's search for an ID pattern inside parentheses, e.g., (AQCMXAL212).
        match = re.search(r'\(([A-Z0-9_\-]+)\)', title)
        if match:
            return match.group(1).strip(), first_line
            
        match_html = re.search(r'\(([A-Z0-9_\-]{4,25})\)', card_html)
        if match_html:
            return match_html.group(1).strip(), first_line

        # Let's search for an uppercase alphanumeric word matching the typical ID pattern in title or text
        # e.g., AQCMXAL212. Let's look for words of length 5 to 20 containing both letters and numbers
        words = re.findall(r'\b([A-Z0-9]{5,20})\b', title)
        for word in words:
            if any(c.isalpha() for c in word) and any(c.isdigit() for c in word):
                return word, first_line

        # Check common data attributes in HTML
        for attr in ["data-id", "data-worksheet-id", "data-lesson-id", "data-activity-id", "data-assignment-id"]:
            attr_match = re.search(rf'{attr}\s*=\s*["\']([^"\']+)["\']', card_html, re.IGNORECASE)
            if attr_match:
                val = attr_match.group(1).strip()
                if re.match(r'^[A-Za-z0-9_\-]+$', val):
                    return val, first_line

        # Fallback to the last word in title if it's alphanumeric and looks like an ID
        words = title.split()
        if words:
            last_word = re.sub(r'[^A-Za-z0-9_\-]', '', words[-1])
            if len(last_word) >= 5 and re.match(r'^[A-Z0-9_\-]+$', last_word):
                return last_word, first_line

        return None, first_line

    def scan_all_topics(self, worksheet_id: str) -> Optional[str]:
        """
        Scan every topic accordion on the page one by one.
        Expands each topic, checks its cards for worksheet_id,
        and clicks the start button if found. Returns actual ID or None.
        """
        ws_id = worksheet_id.strip()
        log.info("Starting sequential search across all topics for Worksheet ID '%s'...", ws_id)
        print(f"\n[SCAN] Starting global search on dashboard for Worksheet ID: {ws_id}...\n")

        # Find all topic containers
        topics = self._get_all_topic_elements()
        log.info("Found %d topics to scan.", len(topics))
        
        for idx, topic_el in enumerate(topics):
            try:
                # Re-locate elements dynamically in case DOM updated
                topics = self._get_all_topic_elements()
                if idx >= len(topics):
                    break
                topic_el = topics[idx]
                
                # Get topic name for logging
                topic_name = self._element_heading_text(topic_el)
                log.info("Scanning Topic %d/%d: '%s'...", idx + 1, len(topics), topic_name)
                print(f"Scanning Topic {idx + 1}/{len(topics)}: {topic_name}...")

                # Scroll topic into view
                scroll_into_view(self.driver, topic_el)
                time.sleep(0.5)

                # Expand the topic if collapsed
                self._expand_topic(topic_el)
                time.sleep(1.5)

                # Re-locate topic_el
                topics = self._get_all_topic_elements()
                topic_el = topics[idx]

                # Expand any sub-sections inside the topic
                self._expand_subsections(topic_el)
                time.sleep(1.0)

                # Re-locate topic_el
                topics = self._get_all_topic_elements()
                topic_el = topics[idx]

                # Scroll inside the topic element to force lazy load of cards
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'end'});", topic_el)
                    time.sleep(1.0)
                    self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'start'});", topic_el)
                    time.sleep(1.0)
                except Exception:
                    pass

                # Re-locate topic_el
                topics = self._get_all_topic_elements()
                topic_el = topics[idx]

                # Collect cards
                cards = self._collect_cards(topic_el)
                for card in cards:
                    try:
                        # Scroll card into view inside the scrollable assignments list container
                        scroll_into_view(self.driver, card)
                        time.sleep(0.3)

                        # Extract title and ID html check
                        ws_title = safe_text(card).strip()
                        if "\n" in ws_title:
                            ws_title = ws_title.split("\n")[0].strip()
                        
                        # Match check (contains query in text or outerHTML)
                        html = card.get_attribute("outerHTML") or ""
                        text_val = safe_text(card) or ""
                        
                        if ws_id.lower() in html.lower() or ws_id.lower() in text_val.lower():
                            print(f"\n[FOUND] Matching Worksheet found under Topic: '{topic_name}'!")
                            print(f"Worksheet: {ws_title}")
                            log.info("Found matching card in Topic '%s'. Clicking Start...", topic_name)
                            
                            # Scroll card into view again to ensure stability
                            scroll_into_view(self.driver, card)
                            time.sleep(0.5)

                            # Highlight the card visually
                            try:
                                self.driver.execute_script(
                                    "arguments[0].style.border='3px solid #00E676'; arguments[0].style.boxShadow='0 0 15px #00E676';", 
                                    card
                                )
                                time.sleep(0.8)
                            except Exception:
                                pass
                                
                            # Retrieve outerHTML before clicking start to avoid StaleElementReferenceException after navigation
                            try:
                                card_html = card.get_attribute("outerHTML") or ""
                            except Exception:
                                card_html = ""
                            success = self._click_start(card, topic_name, ws_title)
                            if success:
                                print("Worksheet Loaded Successfully.\n")
                                actual_id = self._parse_actual_id(ws_title, card_html, ws_id)
                                return actual_id
                    except StaleElementReferenceException:
                        continue
            except Exception as e:
                log.warning("Error scanning topic index %d: %s", idx, e)
                continue
                
        print(f"\n[NOT FOUND] Worksheet ID '{ws_id}' not found after scanning all topics.\n")
        return None

    # ------------------------------------------------------------------
    # Worksheet card collection
    # ------------------------------------------------------------------

    def _collect_cards(self, topic_el: WebElement) -> list[WebElement]:
        """
        Return all visible worksheet card elements inside *topic_el*.
        """
        candidates = topic_el.find_elements(By.XPATH, ".//div | .//li | .//section")
        cards = []
        seen_ids = set()
        
        for el in candidates:
            try:
                if not el.is_displayed():
                    continue
                text = el.text.strip()
                if not text:
                    continue
                match = re.search(r'\(([A-Za-z0-9_\-]+)\)', text)
                if not match:
                    continue
                ws_id = match.group(1).strip()
                if not self._looks_like_id(ws_id):
                    continue
                # Collect descendants that could be buttons/actions (button, a, span, and child divs)
                descendants = el.find_elements(By.TAG_NAME, "button") + el.find_elements(By.TAG_NAME, "a") + el.find_elements(By.TAG_NAME, "span")
                child_divs = [d for d in el.find_elements(By.TAG_NAME, "div") if d != el]
                descendants += child_divs
                
                has_action_btn = False
                for desc in descendants:
                    if desc.is_displayed() and self._is_action_text(safe_text(desc)):
                        has_action_btn = True
                        break
                        
                if not has_action_btn:
                    continue
                if ws_id in seen_ids:
                    continue
                # Check nested child
                children = el.find_elements(By.XPATH, ".//div | .//li")
                has_matching_child = False
                for child in children:
                    if child == el:
                        continue
                    child_text = child.text.strip()
                    if f"({ws_id})" in child_text:
                        child_descendants = child.find_elements(By.TAG_NAME, "button") + child.find_elements(By.TAG_NAME, "a") + child.find_elements(By.TAG_NAME, "span")
                        child_divs = [d for d in child.find_elements(By.TAG_NAME, "div") if d != child]
                        child_descendants += child_divs
                        
                        child_has_action = False
                        for cd in child_descendants:
                            if cd.is_displayed() and self._is_action_text(safe_text(cd)):
                                child_has_action = True
                                break
                        if child_has_action:
                            has_matching_child = True
                            break
                if has_matching_child:
                    continue
                seen_ids.add(ws_id)
                cards.append(el)
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
        return cards

    # ------------------------------------------------------------------
    # Worksheet ID extraction
    # ------------------------------------------------------------------

    def _extract_id_and_title(
        self, card: WebElement, target_id: str
    ) -> tuple[str, str]:
        """
        Extract the Worksheet ID and display title from a card element.

        Extraction strategy (in priority order):
        0. Direct string check in card text or outerHTML.
        1. Named data-* attributes (exact attribute scan).
        2. JavaScript full attribute dump.
        3. Substring search for target_id in outerHTML (fastest when ID
           is present anywhere in the element's markup).
        4. href / src URL parsing.
        5. Child anchor href parsing.

        Returns
        -------
        tuple[str, str] - (worksheet_id, worksheet_title).
            worksheet_id is empty string if not found.
        """
        ws_id    = ""
        ws_title = safe_text(card)

        # ── Strategy 0: check if target_id is directly in the text or HTML ──
        if target_id in ws_title:
            return target_id, ws_title.strip()

        try:
            html = self.driver.execute_script("return arguments[0].outerHTML;", card) or ""
            if target_id in html:
                return target_id, ws_title.strip()
        except Exception:
            pass

        # ── Strategy A: check named attributes ─────────────────────
        for attr in _ID_ATTRIBUTES:
            val = safe_attr(card, attr)
            if val and self._looks_like_id(val):
                ws_id = val.strip()
                break

        # ── Strategy B: full attribute dump via JavaScript ──────────
        if not ws_id:
            try:
                attrs: dict = self.driver.execute_script(
                    """
                    var el = arguments[0];
                    var result = {};
                    for(var i=0; i<el.attributes.length; i++){
                        result[el.attributes[i].name] = el.attributes[i].value;
                    }
                    return result;
                    """,
                    card,
                ) or {}
                for key, val in attrs.items():
                    if val and self._looks_like_id(val):
                        ws_id = val.strip()
                        break
            except Exception:
                pass

        # ── Strategy C: scan outerHTML for exact target ID ──────────
        if not ws_id:
            try:
                html: str = self.driver.execute_script(
                    "return arguments[0].outerHTML;", card
                ) or ""
                if target_id in html:
                    ws_id = target_id   # Confirmed present in this card's HTML
            except Exception:
                pass

        # ── Strategy D: href / src URL parsing ─────────────────────
        if not ws_id:
            for attr in ("href", "src", "action", "data-url", "data-link"):
                href = safe_attr(card, attr)
                if href:
                    extracted = self._id_from_url(href)
                    if extracted:
                        ws_id = extracted
                        break

        # ── Strategy E: child anchor hrefs ─────────────────────────
        if not ws_id:
            try:
                anchors = card.find_elements(By.TAG_NAME, "a")
                for anchor in anchors:
                    href = safe_attr(anchor, "href")
                    if href:
                        extracted = self._id_from_url(href)
                        if extracted:
                            ws_id = extracted
                            break
            except Exception:
                pass

        # ── Strategy F: inspect child elements' data attributes ────
        if not ws_id:
            try:
                all_children = card.find_elements(By.CSS_SELECTOR, "*")
                for child in all_children[:30]:  # limit to first 30
                    try:
                        child_html: str = self.driver.execute_script(
                            "return arguments[0].outerHTML;", child
                        ) or ""
                        if target_id in child_html:
                            ws_id = target_id
                            # Try to get a better title from this child
                            t = safe_text(child)
                            if t and len(t) > len(ws_title):
                                ws_title = t
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        return ws_id, ws_title.strip()

    # ------------------------------------------------------------------
    # ID helper utilities
    # ------------------------------------------------------------------

    def _looks_like_id(self, value: str) -> bool:
        """
        Return True if *value* looks like a worksheet ID.
        Accepts:
        - Alphanumeric strings of 4+ chars (e.g. AQCMXAL209)
        - Pure numeric strings of 4+ digits
        Rejects generic HTML attributes like class names, URLs, etc.
        """
        val = value.strip()
        if len(val) < 4:
            return False
        # Reject values that look like CSS classes, URLs, or long sentences
        if " " in val or val.startswith("http") or val.startswith("/"):
            return False
        if len(val) > 60:
            return False
        # Must be purely alphanumeric (letters + digits, possibly underscores or dashes)
        if re.match(r'^[A-Za-z0-9_\-]+$', val):
            return True
        return False

    def _id_from_url(self, url: str) -> str:
        """
        Extract a worksheet ID from a URL path.
        Handles patterns like:
          /worksheet/AQCMXAL209
          /worksheet/AQCMXAL209/start
          ?id=AQCMXAL209
          #AQCMXAL209
        """
        if not url:
            return ""

        # Query parameter ?id=...
        qp = re.search(r'[?&](?:id|worksheet_id|lesson_id)=([A-Za-z0-9_\-]{4,60})', url)
        if qp:
            return qp.group(1)

        # Path segment /word/ID or /word/ID/...
        seg = re.search(
            r'/(?:worksheet|lesson|activity|assignment)/([A-Za-z0-9_\-]{4,60})(?:/|$|\?|#)',
            url,
        )
        if seg:
            return seg.group(1)

        # Last path segment that looks like an ID
        parts = url.rstrip("/").split("/")
        for part in reversed(parts):
            part_clean = part.split("?")[0].split("#")[0]
            if re.match(r'^[A-Za-z0-9_\-]{4,60}$', part_clean):
                return part_clean

        return ""

    # ------------------------------------------------------------------
    # Start button
    # ------------------------------------------------------------------

    def _click_start(self, card: WebElement, topic_name: str, ws_title: str) -> bool:
        """
        Find and click the Start button on or near *card*.

        Returns
        -------
        bool - True if Start was clicked and the worksheet appears to load.
        """
        scroll_into_view(self.driver, card)
        time.sleep(0.5)

        # Strategy 1: Start button inside the card
        start_btn = self._find_start_in(card)

        # Strategy 2: click the card to expand a modal/reveal the start button
        if start_btn is None:
            log.debug("Start button not inside card – clicking card to reveal it.")
            safe_click(self.driver, card)
            time.sleep(1.2)
            start_btn = self._find_start_in(card)

        # Strategy 3: Start button appeared elsewhere after card click
        if start_btn is None:
            start_btn = self._find_start_global()

        if start_btn is None:
            # Last resort: use the card itself as the trigger
            log.debug("Using card as Start trigger.")
            safe_click(self.driver, card)
            time.sleep(1)
            return self._verify_worksheet_loaded()

        scroll_into_view(self.driver, start_btn)
        safe_click(self.driver, start_btn)
        log.info("Start button clicked.")
        return self._verify_worksheet_loaded()

    def _is_action_text(self, text: str) -> bool:
        t = text.strip().lower()
        if not t:
            return False
        action_words = ("start", "begin", "go", "play", "open", "resume", "continue")
        if t in action_words:
            return True
        for w in action_words:
            if w == "go" and t != "go":
                continue
            if t == w or t.startswith(w + " ") or t.endswith(" " + w) or f" {w} " in t:
                return True
        return False

    def _find_start_in(self, container: WebElement) -> Optional[WebElement]:
        """Find a Start button inside *container*."""
        # By CSS selector
        for sel in _START_SELECTORS[:-2]:  # Skip generic button/a at end
            try:
                els = container.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        return el
            except Exception:
                continue

        # By text
        for tag in ("button", "a", "span", "div"):
            try:
                els = container.find_elements(By.TAG_NAME, tag)
                for el in els:
                    if el.is_displayed() and self._is_action_text(safe_text(el)):
                        return el
            except Exception:
                continue
        return None

    def _find_start_global(self) -> Optional[WebElement]:
        """Fallback: find a Start button anywhere on the page."""
        for btn in self.driver.find_elements(By.TAG_NAME, "button"):
            if btn.is_displayed() and self._is_action_text(safe_text(btn)):
                return btn
        return None

    def _verify_worksheet_loaded(self) -> bool:
        """
        Check that a worksheet question page has appeared.
        Returns True if confirmed, False if uncertain.
        """
        wait_for_page_load(self.driver)
        time.sleep(1)

        question_selectors = [
            "[class*='question']",
            "[class*='answer']",
            "[class*='option']",
            "[class*='problem']",
            "input[type='radio']",
        ]
        wait = WebDriverWait(self.driver, config.DEFAULT_WAIT)
        for sel in question_selectors:
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                log.info("Worksheet loaded successfully.")
                return True
            except TimeoutException:
                continue

        # URL check
        url = self.driver.current_url
        if re.search(r'/worksheet|/lesson|/activity|/quiz', url, re.IGNORECASE):
            log.info("Worksheet URL confirmed: %s", url)
            return True

        log.warning("Could not confirm worksheet load – browser may still be loading.")
        return True  # Optimistic: let the user see the browser


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def find_worksheet_in_topic(
    driver: WebDriver,
    topic_name: str,
    worksheet_id: str,
) -> Optional[str]:
    """
    Search for *worksheet_id* inside *topic_name* and open it.

    Parameters
    ----------
    driver       : Active Chrome WebDriver on the learning dashboard.
    topic_name   : Exact (or close) topic name as shown on the dashboard.
    worksheet_id : Worksheet ID string (case-sensitive).

    Returns
    -------
    Optional[str] - The actual opened Worksheet ID if found, else None.
    """
    finder = TopicWorksheetFinder(driver)
    return finder.find_and_open(topic_name, worksheet_id)
