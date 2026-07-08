# =============================================================================
# utils.py – Shared Utility Helpers
# =============================================================================
# Contains reusable helpers for waiting, clicking, JavaScript execution,
# element inspection, and safe text extraction used across all modules.
# =============================================================================

import time
from typing import Callable, Optional, TypeVar

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

log = get_logger()

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Wait helpers
# ---------------------------------------------------------------------------

def wait_for_element(
    driver: WebDriver,
    by: str,
    value: str,
    timeout: int = config.DEFAULT_WAIT,
) -> WebElement:
    """
    Wait until an element is present and visible in the DOM.

    Parameters
    ----------
    driver  : Selenium WebDriver instance.
    by      : Locator strategy (e.g. By.CSS_SELECTOR).
    value   : Locator value string.
    timeout : Maximum seconds to wait.

    Returns
    -------
    WebElement – the found element.

    Raises
    ------
    TimeoutException if element is not found within timeout.
    """
    return WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((by, value))
    )


def wait_for_elements(
    driver: WebDriver,
    by: str,
    value: str,
    timeout: int = config.DEFAULT_WAIT,
) -> list[WebElement]:
    """
    Wait until at least one element matching the locator is present.

    Returns
    -------
    list[WebElement]
    """
    WebDriverWait(driver, timeout).until(
        EC.presence_of_all_elements_located((by, value))
    )
    return driver.find_elements(by, value)


def wait_for_clickable(
    driver: WebDriver,
    by: str,
    value: str,
    timeout: int = config.DEFAULT_WAIT,
) -> WebElement:
    """Wait until an element is clickable and return it."""
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )


def wait_for_url_contains(
    driver: WebDriver,
    fragment: str,
    timeout: int = config.DEFAULT_WAIT,
) -> bool:
    """Wait until the current URL contains *fragment*."""
    return WebDriverWait(driver, timeout).until(EC.url_contains(fragment))


def wait_for_page_load(driver: WebDriver, timeout: int = config.PAGE_LOAD_TIMEOUT) -> None:
    """Block until document.readyState == 'complete'."""
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


# ---------------------------------------------------------------------------
# Click helpers
# ---------------------------------------------------------------------------

def safe_click(
    driver: WebDriver,
    element: WebElement,
    retries: int = config.MAX_RETRIES,
) -> bool:
    """
    Attempt to click an element, falling back to JavaScript click on failure.

    Handles:
    - StaleElementReferenceException  (element detached from DOM)
    - ElementClickInterceptedException (overlapped by another element)

    Returns
    -------
    bool – True if the click succeeded.
    """
    for attempt in range(1, retries + 1):
        try:
            scroll_into_view(driver, element)
            element.click()
            return True
        except ElementClickInterceptedException:
            log.debug("Click intercepted on attempt %d – retrying with JS click.", attempt)
            try:
                js_click(driver, element)
                return True
            except Exception as exc:
                log.debug("JS click also failed on attempt %d: %s", attempt, exc)
        except StaleElementReferenceException:
            log.debug("Stale element on attempt %d.", attempt)
            time.sleep(config.RETRY_DELAY)
        except Exception as exc:
            log.debug("Unexpected click error on attempt %d: %s", attempt, exc)
            time.sleep(config.RETRY_DELAY)

    log.warning("safe_click exhausted %d retries.", retries)
    return False


def js_click(driver: WebDriver, element: WebElement) -> None:
    """Execute a click via JavaScript."""
    driver.execute_script("arguments[0].click();", element)


# ---------------------------------------------------------------------------
# JavaScript helpers
# ---------------------------------------------------------------------------

def scroll_into_view(driver: WebDriver, element: WebElement) -> None:
    """Scroll the element into the visible viewport."""
    driver.execute_script(
        "arguments[0].scrollIntoView({behavior:'smooth',block:'center'});",
        element,
    )


def scroll_to_top(driver: WebDriver) -> None:
    """Scroll the page back to the top."""
    driver.execute_script("window.scrollTo(0, 0);")


def scroll_by_pixels(driver: WebDriver, pixels: int) -> None:
    """Scroll the page by a given number of pixels vertically."""
    driver.execute_script(f"window.scrollBy(0, {pixels});")


# ---------------------------------------------------------------------------
# Text / attribute helpers
# ---------------------------------------------------------------------------

def safe_text(element: WebElement) -> str:
    """
    Return stripped inner text of *element*, or empty string on error.
    """
    try:
        return (element.text or "").strip()
    except StaleElementReferenceException:
        return ""


def safe_attr(element: WebElement, attr: str) -> str:
    """
    Return an attribute value from *element*, or empty string on error.
    """
    try:
        return (element.get_attribute(attr) or "").strip()
    except StaleElementReferenceException:
        return ""


# ---------------------------------------------------------------------------
# Retry decorator / helper
# ---------------------------------------------------------------------------

def with_retry(
    fn: Callable[[], T],
    retries: int = config.MAX_RETRIES,
    delay: float = config.RETRY_DELAY,
    exceptions: tuple = (Exception,),
    label: str = "",
) -> T:
    """
    Call *fn* up to *retries* times, sleeping *delay* seconds between
    attempts, catching *exceptions*.

    Parameters
    ----------
    fn         : Zero-argument callable to retry.
    retries    : Maximum number of attempts.
    delay      : Seconds to wait between attempts.
    exceptions : Tuple of exception types to catch.
    label      : Human-readable label for logging.

    Returns
    -------
    Return value of *fn* on success.

    Raises
    ------
    Last raised exception after all retries are exhausted.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except exceptions as exc:
            last_exc = exc
            log.debug(
                "Retry %d/%d for '%s' failed: %s",
                attempt,
                retries,
                label or fn.__name__,
                exc,
            )
            if attempt < retries:
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DOM inspection helper
# ---------------------------------------------------------------------------

def element_exists(driver: WebDriver, by: str, value: str) -> bool:
    """Return True if at least one matching element exists in the DOM."""
    return len(driver.find_elements(by, value)) > 0


def get_element_html(driver: WebDriver, element: WebElement) -> str:
    """Return the outer HTML of an element via JavaScript."""
    return driver.execute_script("return arguments[0].outerHTML;", element) or ""


# ---------------------------------------------------------------------------
# Thinkster Automation Orchestration & Shared Helpers
# ---------------------------------------------------------------------------

def setup_driver_and_navigate(profile_suffix: Optional[str] = None) -> WebDriver:
    """
    Launch Chrome, log in, select the student, and navigate to the dashboard.
    Cleans up the browser if any setup step fails.
    """
    from login import launch_browser, login
    from dashboard import select_student, click_start_learning
    
    driver = launch_browser(profile_suffix=profile_suffix)
    try:
        login(driver)
        select_student(driver)
        click_start_learning(driver)
        time.sleep(4.0)  # Wait for dashboard/worksheets to load fully
        return driver
    except Exception as e:
        log.error("Failed during driver setup and navigation: %s", e)
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        raise e


def prompt_topic_name() -> str:
    """Ask for the Topic Name and return it (loops until non-empty).
    Offers a numbered menu for known topics, or manual entry (0).
    """
    import sys
    topics = [
        "Number Representation",
        "Algebra 2 Foundations",
        "Number Relation",
        "Algebra",
        "Functions & Function Notation",
        "Multiplication",
        "Division",
        "Geometry",
        "Complex Numbers"
    ]
    
    print("\nSelect Topic:")
    for i, topic in enumerate(topics, start=1):
        print(f"  {i}. {topic}")
    print("  0. Manual entering")
    
    while True:
        try:
            print("\nEnter selection (0-9 or manual name): ", end="", flush=True)
            choice = input().strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
            
        if not choice:
            print("[WARN] Input cannot be empty. Please try again.")
            continue
            
        if choice == "0":
            try:
                print("Enter Topic Name (Manual): ", end="", flush=True)
                manual_name = input().strip()
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                sys.exit(0)
            if manual_name:
                return manual_name
            print("[WARN] Topic Name cannot be empty. Please try again.")
            continue
            
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(topics):
                selected_topic = topics[idx]
                print(f"Selected: {selected_topic}")
                return selected_topic
            else:
                print(f"[WARN] Invalid option. Please enter a number between 0 and {len(topics)}.")
                continue
                
        # If it's a non-digit string, treat it as manual entering directly
        print(f"Selected: {choice}")
        return choice


def prompt_worksheet_id() -> str:
    """Ask for the Worksheet ID and return it (loops until non-empty)."""
    import sys
    print("\nEnter Worksheet ID (e.g. AQCMXAL214):")
    while True:
        try:
            raw = input().strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
        if raw:
            return raw
        print("[WARN] Worksheet ID cannot be empty. Please try again.\n")


def exit_worksheet(driver: WebDriver) -> bool:
    """
    Handles the full worksheet completion flow based on the confirmed browser behavior:

    Flow A (unanswered questions present):
      1. "Submit Worksheet" modal appears → click "Submit as is"
      2. "Success! Worksheet submitted successfully! Redirecting to summary..." popup
      3. Browser redirects to /summary URL
      4. Summary page shows "Keep Learning" button → click it
      5. Topic/Learning page loads

    Flow B (all questions answered — auto-submitted):
      1. "Success! Worksheet submitted successfully! Redirecting to summary..." popup
      2. Browser redirects to /summary URL
      3. Summary page shows "Keep Learning" button → click it
      4. Topic/Learning page loads

    Uses WebDriverWait with no fixed sleep timers.
    Returns True on success, False on failure.
    """
    log.info("Starting worksheet completion flow...")
    print("\n--- Worksheet Completion Flow ---")

    # -----------------------------------------------------------------------
    # Step 1: Handle "Submit Worksheet" modal if it appears
    #         Modal contains "Submit as is" and "Continue worksheet" buttons.
    #         The modal appears only when some questions were skipped/unanswered.
    # -----------------------------------------------------------------------
    try:
        # Wait up to 8 seconds for the "Submit Worksheet" modal to appear
        submit_modal_present = False
        deadline = time.time() + 8.0
        while time.time() < deadline:
            try:
                # Look for the "Submit as is" button text
                result = driver.execute_script("""
                    var buttons = Array.from(document.querySelectorAll('button'));
                    for (var btn of buttons) {
                        var txt = (btn.innerText || btn.textContent || '').trim();
                        if (txt.toLowerCase() === 'submit as is') {
                            return btn;
                        }
                    }
                    return null;
                """)
                if result:
                    submit_modal_present = True
                    driver.execute_script("arguments[0].click();", result)
                    log.info("'Submit as is' button found and clicked.")
                    print("✓ Clicked 'Submit as is' button.")
                    break
            except Exception:
                pass
            time.sleep(0.4)

        if submit_modal_present:
            log.info("Submit Worksheet modal was handled.")
        else:
            log.info("No 'Submit Worksheet' modal appeared — worksheet may be auto-submitting.")
            print("No 'Submit Worksheet' modal — worksheet auto-submitting.")

    except Exception as e:
        log.warning("Error during Submit modal handling: %s", e)

    # -----------------------------------------------------------------------
    # Step 2: Wait for the "Success! Worksheet submitted successfully!
    #         Redirecting to summary..." popup to appear, then disappear.
    #         The popup appears briefly and then the browser redirects.
    # -----------------------------------------------------------------------
    print("Waiting for submission success popup...")
    try:
        # Wait up to 20 seconds for the success popup text to appear
        success_popup_seen = False
        deadline = time.time() + 20.0
        while time.time() < deadline:
            try:
                page_text = driver.execute_script(
                    "return document.body ? (document.body.innerText || document.body.textContent || '') : '';"
                )
                if "redirecting to summary" in page_text.lower() or "submitted successfully" in page_text.lower():
                    success_popup_seen = True
                    log.info("Success popup detected.")
                    print("✓ Success popup detected: 'Worksheet submitted successfully! Redirecting to summary...'")
                    break
            except Exception:
                pass
            time.sleep(0.3)

        if not success_popup_seen:
            log.warning("Success popup not detected within 20s — continuing anyway.")
            print("[WARN] Success popup not detected — proceeding to wait for /summary URL.")

    except Exception as e:
        log.warning("Error waiting for success popup: %s", e)

    # -----------------------------------------------------------------------
    # Step 3: Wait for the browser to redirect to the /summary URL
    # -----------------------------------------------------------------------
    print("Waiting for redirect to summary page...")
    try:
        WebDriverWait(driver, 30).until(
            lambda d: "/summary" in d.current_url
        )
        log.info("Redirected to summary page: %s", driver.current_url)
        print(f"✓ Summary page loaded: {driver.current_url}")
    except TimeoutException:
        log.warning("Timed out waiting for /summary URL. Current URL: %s", driver.current_url)
        print(f"[WARN] Did not detect /summary URL within 30s. Current: {driver.current_url}")
        # Still continue — maybe we're already there or the URL format differs

    # -----------------------------------------------------------------------
    # Step 4: Wait for the "Keep Learning" button on the summary page
    #         and click it.
    # -----------------------------------------------------------------------
    print("Waiting for 'Keep Learning' button on summary page...")
    keep_learning_clicked = False
    try:
        # Use WebDriverWait with a custom condition for the Keep Learning button
        def keep_learning_button_present(d):
            try:
                result = d.execute_script("""
                    var buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                    for (var btn of buttons) {
                        var txt = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                        if (txt === 'keep learning' || txt.includes('keep learning')) {
                            var rect = btn.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                return btn;
                            }
                        }
                    }
                    return null;
                """)
                return result if result else False
            except Exception:
                return False

        keep_btn = WebDriverWait(driver, 30).until(keep_learning_button_present)
        driver.execute_script("arguments[0].click();", keep_btn)
        keep_learning_clicked = True
        log.info("'Keep Learning' button clicked successfully.")
        print("✓ Clicked 'Keep Learning' button.")

    except TimeoutException:
        log.error("'Keep Learning' button not found within 30s on summary page.")
        print("[ERROR] 'Keep Learning' button not found. Attempting fallback JS click...")
        # Fallback: JS click by text search
        try:
            clicked = driver.execute_script("""
                var all = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                for (var el of all) {
                    var t = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (t === 'keep learning' || t.includes('keep learning')) {
                        el.click(); return true;
                    }
                }
                return false;
            """)
            if clicked:
                keep_learning_clicked = True
                print("✓ 'Keep Learning' clicked via JS fallback.")
        except Exception as fe:
            log.error("JS fallback for Keep Learning also failed: %s", fe)

    except Exception as e:
        log.error("Error clicking 'Keep Learning': %s", e)
        print(f"[ERROR] Keep Learning click error: {e}")

    if not keep_learning_clicked:
        log.error("Could not click 'Keep Learning'. Worksheet completion flow failed.")
        return False

    # -----------------------------------------------------------------------
    # Step 5: Wait for the Topic/Learning page to fully load
    #         (URL must no longer be the /summary or /practice URL)
    # -----------------------------------------------------------------------
    print("Waiting for Topic/Learning page to load...")
    try:
        # Wait for URL to change away from /summary
        WebDriverWait(driver, 20).until(
            lambda d: "/summary" not in d.current_url and "/practice" not in d.current_url
        )
        log.info("Left the summary/practice URL. Current URL: %s", driver.current_url)
        print(f"✓ Navigated away from summary page. URL: {driver.current_url}")
    except TimeoutException:
        log.warning("URL did not change from summary/practice within 20s. Continuing anyway.")
        print("[WARN] URL may still be on practice/summary page.")

    # Wait for the topic page DOM elements to be visible
    try:
        def topic_page_loaded(d):
            try:
                els = d.find_elements(
                    By.CSS_SELECTOR,
                    "[class*='sidebar'], [class*='topic'], [class*='dashboard'], "
                    "[class*='card'], [class*='learning'], [class*='worksheet']"
                )
                visible = [e for e in els if e.is_displayed()]
                return len(visible) >= 2
            except Exception:
                return False

        WebDriverWait(driver, 20).until(topic_page_loaded)
        log.info("Topic/Learning page is fully visible.")
        print("✓ Topic/Learning page loaded successfully.")
    except TimeoutException:
        log.warning("Timed out waiting for Topic page DOM elements. Continuing anyway.")
        print("[WARN] Topic page DOM not fully detected — proceeding.")

    return True




def hold_browser(driver: WebDriver) -> None:
    """Keep driver active and print instructions on how to close it."""
    log.info("Browser remains open. Press Ctrl+C to quit.")
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        log.info("User quit.")


def is_sidebar_element(driver: WebDriver, element: WebElement) -> bool:
    """
    Check if the given element is part of a sidebar menu.
    Checks class attributes, position, and walks ancestors.
    """
    try:
        # 1. Check classes of the element itself
        classes = (element.get_attribute("class") or "").lower()
        if "sidebar" in classes:
            return True

        # 2. Check position of the element (sidebar typically on the left side)
        loc = element.location
        if loc and loc.get('x', 999) < 250:
            return True

        # 3. Walk up ancestors to find sidebar markers (e.g. tag 'nav', tag 'aside', classes)
        curr = element
        while curr:
            try:
                classes = (curr.get_attribute("class") or "").lower()
                tag = curr.tag_name.lower()
                if "sidebar" in classes or tag in ("aside", "nav") or "menu" in classes or "nav" in classes:
                    return True
                # Traverse up using Selenium By.XPATH to avoid JavaScript parentElement null issues
                curr = curr.find_element(By.XPATH, "..")
            except NoSuchElementException:
                break
            except StaleElementReferenceException:
                break
            except Exception:
                break
    except Exception:
        pass
    return False


