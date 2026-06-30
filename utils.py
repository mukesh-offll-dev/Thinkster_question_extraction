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
