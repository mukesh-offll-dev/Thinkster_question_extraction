# =============================================================================
# dashboard.py – Student Selection and Learning Dashboard Navigation
# =============================================================================
# Responsible for:
#   1. Selecting the target student (Thomas D).
#   2. Clicking "Start Learning" to open the learning dashboard.
#
# DOM findings from live inspection of https://elevate.hellothinkster.com:
#   - After login, the site shows student cards each containing a "Select" button.
#   - After selecting a student the URL becomes /dashboard.
#   - The "Start Learning" button on /dashboard uses ONLY Tailwind utility classes
#     (bg-blue-500, text-white, px-16, etc.) -- no semantic class substring to match.
#     It must be found by its visible text "Start Learning".
# =============================================================================

import time

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config
from logger import get_logger
from utils import (
    js_click,
    safe_click,
    safe_text,
    scroll_into_view,
    wait_for_clickable,
    wait_for_element,
    wait_for_elements,
    wait_for_page_load,
)

log = get_logger()


class DashboardHandler:
    """
    Handles post-login navigation:
    - Student profile selection.
    - Navigating to the learning dashboard via the Start Learning button.
    """

    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def select_student(self) -> None:
        """
        Locate the student card for config.TARGET_STUDENT and click its
        inner "Select" button.

        The site renders a list of student profile cards. Each card shows
        the student name and a "Select" button. We find the card whose text
        contains the target name, then click the "Select" button inside it.

        Raises
        ------
        RuntimeError if the target student cannot be found.
        """
        log.info("Selecting student: %s ...", config.TARGET_STUDENT)

        # Wait for the student list to render after login redirect
        time.sleep(2)
        wait_for_page_load(self.driver)

        # Wait for at least one button to appear (student "Select" buttons)
        try:
            WebDriverWait(self.driver, config.DEFAULT_WAIT).until(
                EC.presence_of_element_located((By.TAG_NAME, "button"))
            )
        except TimeoutException:
            log.debug("No buttons appeared in time -- proceeding anyway.")

        target = config.TARGET_STUDENT.strip().lower()

        # Strategy 1: find the "Select" button that is a sibling/child
        # of the element containing the student name.
        select_btn = self._find_select_button_for_student(target)

        if select_btn is not None:
            scroll_into_view(self.driver, select_btn)
            safe_click(self.driver, select_btn)
            log.info("Student '%s' selected via Select button.", config.TARGET_STUDENT)
            time.sleep(1)
            return

        # Strategy 2: click any element whose text directly matches the name
        log.debug("Select button not found -- trying direct name element click.")
        name_el = self._find_element_by_text(target)
        if name_el is not None:
            scroll_into_view(self.driver, name_el)
            safe_click(self.driver, name_el)
            log.info("Student '%s' selected by clicking name element.", config.TARGET_STUDENT)
            time.sleep(1)
            return

        raise RuntimeError(
            f"Student '{config.TARGET_STUDENT}' not found on the page. "
            "Verify the student name in config.TARGET_STUDENT."
        )

    def click_start_learning(self) -> None:
        """
        Click the 'Start Learning' button on /dashboard.

        The button has no semantic class -- only Tailwind utility classes.
        We locate it exclusively by its visible text "Start Learning".

        Raises
        ------
        RuntimeError if the button cannot be located.
        """
        log.info("Opening Learning Dashboard...")

        # Wait for the page to navigate to /dashboard after student selection
        try:
            WebDriverWait(self.driver, config.DEFAULT_WAIT).until(
                lambda d: "dashboard" in d.current_url.lower()
            )
            log.debug("Confirmed on /dashboard: %s", self.driver.current_url)
        except TimeoutException:
            log.debug("URL did not contain 'dashboard' -- proceeding anyway.")

        wait_for_page_load(self.driver)
        time.sleep(1)  # Allow React/Next.js components to finish hydrating

        btn = self._find_start_learning_button()
        if btn is None:
            raise RuntimeError(
                "Could not locate the 'Start Learning' button. "
                "The page layout may have changed."
            )

        scroll_into_view(self.driver, btn)
        safe_click(self.driver, btn)
        log.debug("'Start Learning' clicked.")

        self._wait_for_post_dashboard()
        log.info("Learning Dashboard loaded successfully.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_select_button_for_student(self, target_name_lower: str):
        """
        Find the 'Select' button that belongs to the target student's card.

        Strategy: iterate every button with text "Select" (or similar),
        then walk up its ancestor tree to check if any ancestor element
        contains the student name in its text content.

        Returns WebElement or None.
        """
        all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
        select_buttons = [
            btn for btn in all_buttons
            if safe_text(btn).lower() in ("select", "choose", "pick", "go", "start")
            and btn.is_displayed()
        ]

        log.debug("Found %d select-type buttons on page.", len(select_buttons))

        for btn in select_buttons:
            # Walk up to 5 ancestor levels looking for the student name
            try:
                ancestor = btn
                for _ in range(5):
                    ancestor = self.driver.execute_script(
                        "return arguments[0].parentElement;", ancestor
                    )
                    if ancestor is None:
                        break
                    ancestor_text = (
                        self.driver.execute_script(
                            "return arguments[0].innerText;", ancestor
                        ) or ""
                    ).lower()
                    if target_name_lower in ancestor_text:
                        log.debug(
                            "Found Select button for '%s' in ancestor: %.60s",
                            target_name_lower,
                            ancestor_text,
                        )
                        return btn
            except Exception as exc:
                log.debug("Ancestor walk error: %s", exc)
                continue

        return None

    def _find_element_by_text(self, target_lower: str):
        """
        Fallback: find any visible interactive element whose text matches
        the target student name.
        """
        for tag in ("button", "a", "div", "span", "li", "p"):
            elements = self.driver.find_elements(By.TAG_NAME, tag)
            for el in elements:
                try:
                    if el.is_displayed() and target_lower in safe_text(el).lower():
                        return el
                except Exception:
                    continue
        return None

    def _find_start_learning_button(self):
        """
        Locate the 'Start Learning' button by its visible text.

        The site uses Tailwind utility classes exclusively -- no semantic
        class names. Text matching is the only reliable strategy.

        Returns WebElement or None.
        """
        all_buttons = self.driver.find_elements(By.TAG_NAME, "button")

        # Exact match first
        for btn in all_buttons:
            try:
                if safe_text(btn).lower() == "start learning" and btn.is_displayed():
                    log.debug("Start Learning button found by exact text match.")
                    return btn
            except Exception:
                continue

        # Looser partial match
        for btn in all_buttons:
            try:
                text = safe_text(btn).lower()
                if "start" in text and "learn" in text and btn.is_displayed():
                    log.debug("Start Learning button found by partial text: '%s'", text)
                    return btn
            except Exception:
                continue

        # Also check anchor tags
        for anchor in self.driver.find_elements(By.TAG_NAME, "a"):
            try:
                if "start learning" in safe_text(anchor).lower() and anchor.is_displayed():
                    return anchor
            except Exception:
                continue

        return None

    def _wait_for_post_dashboard(self) -> None:
        """
        Wait for the page to transition after clicking 'Start Learning'.

        'Start Learning' navigates from /dashboard to another URL
        (e.g. /learning-journey, /topics, /worksheets, etc.).
        We wait for the URL to change, then wait for any content to load.
        """
        current_url = self.driver.current_url
        log.debug("Waiting for URL change from: %s", current_url)

        # Wait for the URL to change away from /dashboard
        try:
            WebDriverWait(self.driver, config.DEFAULT_WAIT).until(
                lambda d: d.current_url != current_url
            )
            log.debug("URL changed to: %s", self.driver.current_url)
        except TimeoutException:
            log.debug("URL did not change after clicking Start Learning -- may be a SPA transition.")

        wait_for_page_load(self.driver)
        time.sleep(2)  # Allow SPA components to render

        # Broad content selectors -- just confirm the page has rendered something
        content_selectors = [
            "main",
            "h1", "h2", "h3",
            "ul", "ol",
            "[class*='container']",
            "button",
            "div",
        ]
        wait = WebDriverWait(self.driver, config.SHORT_WAIT)
        for sel in content_selectors:
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                log.debug("Post-Start-Learning content confirmed via: %s", sel)
                return
            except TimeoutException:
                continue

        log.warning("Could not confirm post-Start-Learning page load -- proceeding anyway.")


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def select_student(driver: WebDriver) -> None:
    """Select the configured target student from the student list."""
    DashboardHandler(driver).select_student()


def click_start_learning(driver: WebDriver) -> None:
    """Click 'Start Learning' and wait for the dashboard to appear."""
    DashboardHandler(driver).click_start_learning()
