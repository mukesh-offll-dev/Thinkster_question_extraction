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

def setup_driver_and_navigate() -> WebDriver:
    """
    Launch Chrome, log in, select the student, and navigate to the dashboard.
    Cleans up the browser if any setup step fails.
    """
    from login import launch_browser, login
    from dashboard import select_student, click_start_learning
    
    driver = launch_browser()
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
    Finds and clicks the exit button in the top left corner of the worksheet screen.
    Also handles any confirmation dialog that might appear.
    """
    log.info("Attempting to exit the worksheet...")
    print("\nExiting current worksheet...")
    
    js_code = """
    function clickExit() {
        // 1. Find the exit button in the top-left area
        let candidates = Array.from(document.querySelectorAll('button, a, [role="button"], .lrn-btn, [class*="exit" i], [class*="back" i], [class*="close" i], [class*="home" i]'));
        
        let bestEl = null;
        let maxScore = -1;
        
        for (let el of candidates) {
            let rect = el.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.top <= 120 && rect.left >= 0 && rect.left <= 150) {
                let text = (el.innerText || el.textContent || "").trim().toLowerCase();
                let className = (el.className || "").toString().toLowerCase();
                let id = (el.id || "").toLowerCase();
                let aria = (el.getAttribute("aria-label") || "").toLowerCase();
                let title = (el.getAttribute("title") || "").toLowerCase();
                
                let score = 0;
                
                if (/exit|back|close|quit|leave|dashboard|home|x/i.test(text)) score += 20;
                if (/exit|back|close|quit|leave|dashboard|home|x/i.test(className)) score += 20;
                if (/exit|back|close|quit|leave|dashboard|home|x/i.test(id)) score += 20;
                if (/exit|back|close|quit|leave|dashboard|home|x/i.test(aria)) score += 20;
                if (/exit|back|close|quit|leave|dashboard|home|x/i.test(title)) score += 20;
                
                let isClickable = el.tagName === 'BUTTON' || el.tagName === 'A' || el.getAttribute('role') === 'button' || window.getComputedStyle(el).cursor === 'pointer';
                if (isClickable) score += 10;
                
                if (text === '←' || text === 'x' || text === 'X' || text === '<' || className.includes('arrow') || className.includes('icon')) {
                    score += 15;
                }
                
                if (score > maxScore) {
                    maxScore = score;
                    bestEl = el;
                }
            }
        }
        
        if (bestEl) {
            bestEl.click();
            return true;
        }
        
        // Fallback: search for elements with specific selectors in top-left
        let fallbacks = [
            'button.exit', 'a.exit', 'button.back', 'a.back',
            '[class*="exit" i]', '[class*="back" i]', '[class*="close" i]', '[class*="home" i]'
        ];
        for (let sel of fallbacks) {
            let els = document.querySelectorAll(sel);
            for (let el of els) {
                let rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.top <= 120 && rect.left >= 0 && rect.left <= 150) {
                    el.click();
                    return true;
                }
            }
        }
        return false;
    }
    return clickExit();
    """
    try:
        success = driver.execute_script(js_code)
        if success:
            log.info("Exit button clicked.")
            print("Exit button clicked.")
            
            # Wait a moment to see if a confirmation dialog appears
            time.sleep(2.0)
            
            # Check for confirmation modals/dialogs
            js_confirm_code = """
            function handleConfirmation() {
                let modals = Array.from(document.querySelectorAll('.modal, [class*="modal" i], [class*="dialog" i], [class*="overlay" i], [class*="popup" i]'));
                if (modals.length === 0) return false;
                
                // Look for confirmation buttons inside visible modals
                for (let modal of modals) {
                    let rect = modal.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        let buttons = Array.from(modal.querySelectorAll('button, a, [role="button"]'));
                        for (let btn of buttons) {
                            let text = (btn.innerText || btn.textContent || "").trim().toLowerCase();
                            if (/yes|confirm|exit|quit|leave|ok|sure|agree/i.test(text)) {
                                btn.click();
                                return true;
                            }
                        }
                    }
                }
                return false;
            }
            return handleConfirmation();
            """
            confirmed = driver.execute_script(js_confirm_code)
            if confirmed:
                log.info("Confirmation dialog handled.")
                print("Exit confirmation confirmed.")
            
            time.sleep(3.0)
            return True
        else:
            log.warning("Exit button not found via top-left area. Trying wider scan...")
            js_code_wider = """
            let els = document.querySelectorAll('button, a, [class*="exit" i], [class*="back" i], [class*="close" i]');
            for (let el of els) {
                let rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && rect.top <= 150 && rect.left <= 250) {
                    let text = (el.innerText || el.textContent || "").trim().toLowerCase();
                    if (/exit|back|close|quit|leave/i.test(text) || /exit|back|close/i.test(el.className)) {
                        el.click();
                        return true;
                    }
                }
            }
            return false;
            """
            success_wider = driver.execute_script(js_code_wider)
            if success_wider:
                log.info("Exit button clicked via wider scan.")
                print("Exit button clicked (wider search).")
                
                # Check for confirmation modals
                time.sleep(2.0)
                
                # Check for confirmation modals/dialogs
                js_confirm_code = """
                function handleConfirmation() {
                    let modals = Array.from(document.querySelectorAll('.modal, [class*="modal" i], [class*="dialog" i], [class*="overlay" i], [class*="popup" i]'));
                    if (modals.length === 0) return false;
                    
                    // Look for confirmation buttons inside visible modals
                    for (let modal of modals) {
                        let rect = modal.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            let buttons = Array.from(modal.querySelectorAll('button, a, [role="button"]'));
                            for (let btn of buttons) {
                                let text = (btn.innerText || btn.textContent || "").trim().toLowerCase();
                                if (/yes|confirm|exit|quit|leave|ok|sure|agree/i.test(text)) {
                                    btn.click();
                                    return true;
                                }
                            }
                        }
                    }
                    return false;
                }
                return handleConfirmation();
                """
                driver.execute_script(js_confirm_code)
                
                time.sleep(3.0)
                return True
            else:
                log.error("Could not find exit button.")
                print("[WARN] Could not find or click the exit button.")
                return False
    except Exception as e:
        log.error("Exception during exit button click: %s", e)
        return False


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


