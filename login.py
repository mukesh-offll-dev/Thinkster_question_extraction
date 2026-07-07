# =============================================================================
# login.py – Browser Launch and Authentication
# =============================================================================
# Responsible for:
#   1. Launching Chrome with anti-detection options.
#   2. Navigating to the Thinkster Elevate login page.
#   3. Filling in credentials and submitting the login form.
#   4. Waiting for successful authentication.
# =============================================================================

import os
import time

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

import config
from logger import get_logger
from utils import (
    js_click,
    safe_click,
    scroll_into_view,
    wait_for_clickable,
    wait_for_element,
    wait_for_page_load,
)

log = get_logger()


from typing import Optional

# ---------------------------------------------------------------------------
# Browser launch
# ---------------------------------------------------------------------------

def launch_browser(profile_suffix: Optional[str] = None) -> WebDriver:
    """
    Launch and return a Chrome WebDriver with production-appropriate settings.

    Anti-detection measures applied:
    - Removes the 'webdriver' navigator property.
    - Disables the automation-controlled info bar.
    - Uses a realistic User-Agent string.
    - Disables Blink automation features.

    Returns
    -------
    WebDriver – fully configured Chrome instance.
    """
    log.info("Launching Chrome...")

    options = Options()

    # ---- Window -------------------------------------------------------
    if config.HEADLESS:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    if config.WINDOW_MAXIMIZE:
        options.add_argument("--start-maximized")

    # ---- Session Cache ------------------------------------------------
    if getattr(config, "PERSIST_SESSION", False):
        profile_dir = getattr(config, "CHROME_PROFILE_DIR", "chrome_profile")
        if profile_suffix:
            profile_dir = f"{profile_dir}_{profile_suffix}"
        profile_path = os.path.abspath(profile_dir)
        log.info("Using persistent Chrome profile directory: %s", profile_path)
        options.add_argument(f"--user-data-dir={profile_path}")

    # ---- Anti-detection -----------------------------------------------
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )

    # ---- Stability / performance -------------------------------------
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--ignore-certificate-errors")

    # ---- Logging verbosity -------------------------------------------
    options.add_argument("--log-level=3")
    options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # Patch navigator.webdriver to undefined (runtime CDP command)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """
        },
    )

    driver.set_page_load_timeout(config.PAGE_LOAD_TIMEOUT)
    driver.implicitly_wait(config.IMPLICIT_WAIT)

    log.info("Chrome launched successfully.")
    return driver


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginHandler:
    """
    Manages the login workflow for Thinkster Elevate.

    Usage
    -----
    handler = LoginHandler(driver)
    handler.login()
    """

    # CSS selectors for the login page elements
    # Confirmed from live DOM inspection of https://elevate.hellothinkster.com/login
    _SEL_EMAIL_INPUT    = "#email"
    _SEL_PASSWORD_INPUT = "#password"
    _SEL_SUBMIT_BTN     = "button.bg-blue-500"

    # Post-login indicator – adjust if the dashboard uses a different selector
    _SEL_POST_LOGIN = (
        "[class*='dashboard' i], "
        "[class*='student' i], "
        "[class*='profile' i], "
        "[class*='home' i]"
    )

    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def open_website(self) -> None:
        """Navigate to the Thinkster Elevate homepage."""
        log.info("Opening Website: %s", config.BASE_URL)
        self.driver.get(config.BASE_URL)
        wait_for_page_load(self.driver)
        log.info("Website loaded.")

    def is_logged_in(self) -> bool:
        """
        Check if we are already logged in by checking the URL and/or looking for dashboard elements.
        """
        log.debug("Checking if session is already logged in...")
        time.sleep(2.0)  # Wait for potential redirects/page loads
        url = self.driver.current_url.lower()

        # If we are on the login page or URL has /login, we are definitely not logged in.
        if "login" in url:
            log.debug("Not logged in (URL contains 'login').")
            return False

        # Check if any post-login indicators are present
        post_login_selectors = [
            "[class*='student']",
            "[class*='profile']",
            "[class*='dashboard']",
            "[class*='home']",
            "[class*='child']",
            "img[alt*='student' i]",
            "[data-testid*='student']",
            "main",
        ]
        for sel in post_login_selectors:
            if len(self.driver.find_elements(By.CSS_SELECTOR, sel)) > 0:
                log.info("Already logged in (detected post-login elements: %s).", sel)
                return True

        # Check if login fields are present. If we can't find #email, we might already be logged in
        try:
            email_field = self.driver.find_element(By.CSS_SELECTOR, self._SEL_EMAIL_INPUT)
            if not email_field.is_displayed():
                log.info("Already logged in (email input is not visible).")
                return True
        except NoSuchElementException:
            log.info("Already logged in (email input element not found).")
            return True

        log.debug("Not logged in (login fields are visible and no post-login elements detected).")
        return False

    def login(self) -> None:
        """
        Fill in email and password and submit the login form.
        Waits for post-login content to confirm success.

        Raises
        ------
        RuntimeError if login fails or times out.
        """
        if self.is_logged_in():
            log.info("Already logged in. Skipping credentials form submission.")
            print("Session cache found: already logged in.")
            return

        log.info("Logging in as %s ...", config.EMAIL)

        # Wait for the email field to be present and visible before interacting
        # The page uses a JS framework; the form may not be in DOM immediately.
        try:
            wait_for_element(self.driver, By.CSS_SELECTOR, self._SEL_EMAIL_INPUT, timeout=config.LONG_WAIT)
        except Exception:
            log.debug("Primary email selector timed out; falling back to generic search.")

        # Locate and fill email
        email_field = self._locate_email_field()
        email_field.clear()
        email_field.send_keys(config.EMAIL)
        log.debug("Email entered.")

        # Locate and fill password
        password_field = self._locate_password_field()
        password_field.clear()
        password_field.send_keys(config.PASSWORD)
        log.debug("Password entered.")

        # Submit the form
        self._submit_login()

        # Wait for successful login
        self._wait_for_successful_login()
        log.info("Login Successful.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _locate_email_field(self):
        """Find the email input using confirmed ID first, then fallbacks."""
        selectors = [
            "#email",                          # Confirmed live selector
            "input[type='email']",
            "input[name='email']",
            "input[placeholder*='email' i]",
            "input[placeholder='you@example.com']",
            "input[name='username']",
        ]
        return self._find_first(selectors, "Email input field")

    def _locate_password_field(self):
        """Find the password input using confirmed ID first, then fallbacks."""
        selectors = [
            "#password",                       # Confirmed live selector
            "input[type='password']",
            "input[name='password']",
        ]
        return self._find_first(selectors, "Password input field")

    def _submit_login(self) -> None:
        """Click the submit / sign-in button."""
        selectors = [
            "button.bg-blue-500",              # Confirmed live selector
            "button[type='submit']",
            "button[class*='login' i]",
            "button[class*='signin' i]",
            "input[type='submit']",
            "button:not([type='button'])",
        ]
        btn = self._find_first(selectors, "Login submit button")
        scroll_into_view(self.driver, btn)
        safe_click(self.driver, btn)
        log.debug("Login form submitted.")

    def _wait_for_successful_login(self) -> None:
        """
        Wait for indicators that confirm a successful login.
        Tries URL change, then DOM selectors, then timed fallback.
        """
        log.debug("Waiting for post-login page...")
        wait = WebDriverWait(self.driver, config.LONG_WAIT)

        # Strategy 1: URL must navigate away from /login
        try:
            wait.until(
                lambda d: "login" not in d.current_url.lower()
            )
            log.debug("URL changed post-login: %s", self.driver.current_url)
            wait_for_page_load(self.driver)
            return
        except TimeoutException:
            log.debug("URL did not leave /login – trying DOM indicators.")

        # Strategy 2: Look for student/profile selection or dashboard element
        post_login_selectors = [
            "[class*='student']",
            "[class*='profile']",
            "[class*='dashboard']",
            "[class*='home']",
            "[class*='child']",
            "img[alt*='student' i]",
            "[data-testid*='student']",
            "main",
        ]
        for sel in post_login_selectors:
            elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
            if elements:
                log.debug("Post-login element found: %s", sel)
                wait_for_page_load(self.driver)
                return

        # Strategy 3: Check if an error message is visible (wrong credentials)
        error_selectors = [
            "[class*='error']", "[class*='alert']",
            "[role='alert']", "p[class*='text-red']",
        ]
        for sel in error_selectors:
            els = self.driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                text = (el.text or "").strip()
                if text:
                    raise RuntimeError(
                        f"Login rejected by site: '{text}'. "
                        "Check EMAIL / PASSWORD in config.py."
                    )

        # Strategy 4: Timed fallback
        time.sleep(3)
        if "login" not in self.driver.current_url.lower():
            log.debug("Proceeding – URL does not contain 'login'.")
            return

        raise RuntimeError(
            "Login failed or page did not advance. "
            "Check credentials in config.py."
        )

    def _find_first(self, selectors: list[str], label: str):
        """
        Try each CSS selector in order, return the first visible element found.

        Raises
        ------
        RuntimeError if no selector matches.
        """
        for sel in selectors:
            elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
            for el in elements:
                if el.is_displayed():
                    log.debug("Located '%s' with selector: %s", label, sel)
                    return el
        raise RuntimeError(f"Could not locate: {label}")


def login(driver: WebDriver) -> None:
    """
    Convenience function: open the site and complete login.

    Parameters
    ----------
    driver : Active Chrome WebDriver.
    """
    handler = LoginHandler(driver)
    handler.open_website()
    handler.login()
