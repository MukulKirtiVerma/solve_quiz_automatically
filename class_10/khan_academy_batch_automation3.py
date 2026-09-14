#!/usr/bin/env python3
"""
Khan Academy Quiz Auto-Solver with JSON-based Question Detection

Features:
- Loads students from CSV
- Processes each student through multiple quiz URLs
- Uses input.json for question detection and solving
- Recursive search through JSON values when no key match found
- Handles buttons by text content (Skip, Check, Next question, Show summary)
- Records skipped questions in skipped.json
- Checkpoint system for processed students
- 10-minute timeout per student
"""

import csv
import time
import os
import sys
import shutil
import json
from pathlib import Path
from datetime import datetime
import subprocess
import signal
from functools import wraps
import re


# ============================================================
# AUTO-INSTALL DEPENDENCIES
# ============================================================

def ensure_package(package, import_name=None):
    if import_name is None:
        import_name = package.replace("-", "_")

    try:
        __import__(import_name)
    except ImportError:
        print(f"[INSTALL] Installing {package}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package]
        )


ensure_package("selenium")
ensure_package("webdriver-manager", "webdriver_manager")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
    StaleElementReferenceException,
)

from webdriver_manager.chrome import ChromeDriverManager

# ============================================================
# CONFIGURATION
# ============================================================

CSV_FILE = "unique_student_records.csv"
BATCH_SIZE = 1
LOGIN_URL = "https://en.khanacademy.org/login"

# Quiz URLs
QUIZ_URLS = [
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:combination-and-decomposition-reactions/quiz/x5d08d26681869997:chemical-reactions-and-equations-quiz-2",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:displacement-and-double-displacement-reactions/quiz/x5d08d26681869997:chemical-reactions-and-equations-quiz-3",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:corrosion-and-rancidity/quiz/x5d08d26681869997:chemical-reactions-and-equations-quiz-4",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:corrosion-and-rancidity/test/x5d08d26681869997:chemical-reactions-and-equations-unit-test"
]

INPUT_JSON_FILE = "input.json"
OUTPUT_DIR = "ka_quiz_progress"
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "checkpoint.json")
SKIPPED_FILE = os.path.join(OUTPUT_DIR, "skipped.json")
STUDENT_TIMEOUT = 600  # 10 minutes per student


# ============================================================
# OUTPUT SETUP
# ============================================================

def setup_output():
    Path(OUTPUT_DIR).mkdir(exist_ok=True)

    screenshot_dir = Path(OUTPUT_DIR, "screenshots")
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    progress_file = Path(OUTPUT_DIR, "progress.csv")

    if not progress_file.exists():
        with open(progress_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "student_name",
                "username",
                "url",
                "status",
                "notes",
            ])

    if not os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump({"processed_students": [], "failed_students": []}, f, indent=2)

    if not os.path.exists(SKIPPED_FILE):
        with open(SKIPPED_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)

    return str(screenshot_dir), str(progress_file)


SCREENSHOT_DIR, PROGRESS_FILE = setup_output()


# ============================================================
# CHECKPOINT MANAGEMENT
# ============================================================

def load_checkpoint():
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"processed_students": [], "failed_students": []}


def save_checkpoint(processed_students, failed_students):
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "processed_students": processed_students,
            "failed_students": failed_students
        }, f, indent=2)


def is_student_processed(username):
    checkpoint = load_checkpoint()
    return username in checkpoint["processed_students"]


def mark_student_processed(username):
    checkpoint = load_checkpoint()
    if username not in checkpoint["processed_students"]:
        checkpoint["processed_students"].append(username)
    if username in checkpoint["failed_students"]:
        checkpoint["failed_students"].remove(username)
    save_checkpoint(checkpoint["processed_students"], checkpoint["failed_students"])


def mark_student_failed(username, error_message=""):
    checkpoint = load_checkpoint()
    if username not in checkpoint["failed_students"]:
        checkpoint["failed_students"].append(username)
    save_checkpoint(checkpoint["processed_students"], checkpoint["failed_students"])


# ============================================================
# SKIPPED QUESTIONS MANAGEMENT
# ============================================================

def load_skipped():
    try:
        with open(SKIPPED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_skipped(skipped_data):
    with open(SKIPPED_FILE, "w", encoding="utf-8") as f:
        json.dump(skipped_data, f, indent=2)


def record_skipped(username, url, page_text, reason="Key not found in JSON"):
    """Record a skipped question for a user."""
    skipped = load_skipped()

    if username not in skipped:
        skipped[username] = []

    skipped[username].append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "url": url,
        "reason": reason,
        "page_text": page_text[:500]
    })

    save_skipped(skipped)
    print(f"    ⚠️ Skipped recorded for {username} at {url}")


# ============================================================
# PROGRESS LOGGING
# ============================================================

def log_progress(student_name, username, url, status, notes=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(PROGRESS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp,
            student_name,
            username,
            url,
            status,
            notes,
        ])

    print(f"    📝 {status}")


# ============================================================
# SCREENSHOT
# ============================================================

def safe_filename(text):
    return "".join(
        char if char.isalnum() or char in "_-." else "_"
        for char in str(text)
    )


def save_screenshot(driver, student_name, username, label):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    filename = (
        f"{safe_filename(student_name)}_"
        f"{safe_filename(username)}_"
        f"{safe_filename(label)}_"
        f"{timestamp}.png"
    )

    path = os.path.join(SCREENSHOT_DIR, filename)

    try:
        driver.save_screenshot(path)
        print(f"    📸 Screenshot: {path}")
        return path
    except Exception as e:
        print(f"    ⚠️ Screenshot failed: {e}")
        return None


# ============================================================
# CREATE DRIVER
# ============================================================

def create_driver(profile_dir):
    options = Options()

    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1400,900")
    options.add_argument("--disable-notifications")

    options.add_experimental_option(
        "excludeSwitches",
        ["enable-automation"]
    )

    options.add_experimental_option(
        "prefs",
        {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        }
    )

    print("    🌐 Starting Chrome...")

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"    ⚠️ Driver manager failed: {e}")
        print("    Trying Selenium default driver...")
        driver = webdriver.Chrome(options=options)

    return driver


# ============================================================
# LOGIN
# ============================================================

def khan_login(driver, username, password):
    print("    🔐 Opening login page...")
    driver.get(LOGIN_URL)
    time.sleep(3)

    try:
        email_field = None
        password_field = None

        inputs = driver.find_elements(By.TAG_NAME, "input")
        for inp in inputs:
            try:
                if not inp.is_displayed():
                    continue
                input_type = (inp.get_attribute("type") or "").lower()
                if input_type in ("email", "text") and email_field is None:
                    email_field = inp
                elif input_type == "password" and password_field is None:
                    password_field = inp
            except WebDriverException:
                continue

        if email_field is None:
            selectors = [
                (By.ID, "uid-input"),
                (By.NAME, "identifier"),
                (By.NAME, "email"),
                (By.CSS_SELECTOR, 'input[type="email"]'),
            ]
            for by, selector in selectors:
                try:
                    element = driver.find_element(by, selector)
                    if element.is_displayed():
                        email_field = element
                        break
                except NoSuchElementException:
                    continue

        if password_field is None:
            selectors = [
                (By.ID, "password-input"),
                (By.NAME, "password"),
                (By.CSS_SELECTOR, 'input[type="password"]'),
            ]
            for by, selector in selectors:
                try:
                    element = driver.find_element(by, selector)
                    if element.is_displayed():
                        password_field = element
                        break
                except NoSuchElementException:
                    continue

        if email_field is None or password_field is None:
            print("    ❌ Login fields not found")
            return False

        email_field.clear()
        email_field.send_keys(username)
        time.sleep(0.5)

        password_field.clear()
        password_field.send_keys(password)
        time.sleep(0.5)

        submit_button = None
        buttons = driver.find_elements(By.CSS_SELECTOR, 'button[type="submit"]')
        for button in buttons:
            try:
                if button.is_displayed():
                    submit_button = button
                    break
            except WebDriverException:
                continue

        if submit_button:
            submit_button.click()
            print("    🖱️ Login submitted")
        else:
            password_field.send_keys(Keys.RETURN)
            print("    ⌨️ Login submitted with Enter")

        time.sleep(6)

        if "/login" in driver.current_url:
            print("    ❌ Login failed or still on login page")
            return False

        print(f"    ✅ Logged in as {username}")
        return True

    except Exception as e:
        print(f"    ❌ Login error: {e}")
        return False


# ============================================================
# COOKIE CONSENT & POPUPS
# ============================================================

def accept_cookie_consent(driver, wait_seconds=5):
    try:
        button = WebDriverWait(driver, wait_seconds).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        )
        button.click()
        print("    🍪 Cookie consent accepted")
        return True
    except TimeoutException:
        return False
    except Exception as e:
        print(f"    ⚠️ Cookie handling issue: {e}")
        return False


def handle_intro_modal(driver):
    time.sleep(2)

    for _ in range(3):
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, 'button[aria-label="Close modal"]')
            found = False
            for button in buttons:
                if button.is_displayed():
                    driver.execute_script("arguments[0].click();", button)
                    print("    ✖️ Closed popup")
                    time.sleep(1)
                    found = True
                    break
            if not found:
                break
        except Exception:
            break

    try:
        checkboxes = driver.find_elements(By.CSS_SELECTOR, 'input[type="checkbox"]')
        for checkbox in checkboxes:
            try:
                element_id = (checkbox.get_attribute("id") or "").lower()
                if "onetrust" in element_id or element_id.startswith("ot-"):
                    continue
                if checkbox.is_displayed():
                    driver.execute_script("arguments[0].click();", checkbox)
                    print("    ☑️ Onboarding checkbox selected")
                    time.sleep(1)
                    break
            except Exception:
                continue
    except Exception:
        pass

    try:
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for button in buttons:
            try:
                text = (button.text or "").strip().lower()
                if "start learning" in text and button.is_displayed():
                    driver.execute_script("arguments[0].click();", button)
                    print("    🚀 Clicked Start learning")
                    time.sleep(1)
                    break
            except Exception:
                continue
    except Exception:
        pass


# ============================================================
# TIMEOUT HANDLING
# ============================================================

def timeout_handler(signum, frame):
    raise TimeoutError("Student processing timed out")


def with_timeout(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(STUDENT_TIMEOUT)
        try:
            result = func(*args, **kwargs)
            signal.alarm(0)
            return result
        except TimeoutError:
            signal.alarm(0)
            print(f"    ⏰ Student processing exceeded {STUDENT_TIMEOUT // 60} minutes")
            raise
        except Exception as e:
            signal.alarm(0)
            raise

    return wrapper


# ============================================================
# LOAD INPUT JSON
# ============================================================

def load_input_json():
    try:
        with open(INPUT_JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ {INPUT_JSON_FILE} not found!")
        return {}
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing {INPUT_JSON_FILE}: {e}")
        return {}


INPUT_JSON = load_input_json()


# ============================================================
# BUTTON CLICKING FUNCTIONS - BY TEXT
# ============================================================

def find_button_by_text(driver, text, partial=False):
    """Find a button by its text content."""
    try:
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for button in buttons:
            try:
                button_text = (button.text or "").strip()
                if partial:
                    if text.lower() in button_text.lower():
                        return button
                else:
                    if button_text.lower() == text.lower():
                        return button
            except:
                continue
        return None
    except Exception as e:
        print(f"    ⚠️ Error finding button '{text}': {e}")
        return None


def click_button_by_text(driver, text, partial=False):
    """Click a button by its text content."""
    try:
        button = find_button_by_text(driver, text, partial)
        if button and button.is_displayed():
            driver.execute_script("arguments[0].scrollIntoView(true);", button)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", button)
            print(f"    ✅ Clicked button: '{text}'")
            time.sleep(1)
            return True
        return False
    except Exception as e:
        print(f"    ⚠️ Could not click button '{text}': {e}")
        return False


def click_lets_go(driver):
    """Click Let's go button if present."""
    return click_button_by_text(driver, "Let's go", partial=True) or click_button_by_text(driver, "Let’s go",
                                                                                          partial=True)


def click_check_button(driver):
    """Click Check button."""
    return click_button_by_text(driver, "Check")


def click_next_question(driver):
    """Click Next question button."""
    return click_button_by_text(driver, "Next question", partial=True)


def click_show_summary(driver):
    """Click Show summary button."""
    return click_button_by_text(driver, "Show summary", partial=True)


def click_skip_button(driver):
    """Click Skip button."""
    return click_button_by_text(driver, "Skip")


def button_exists(driver, text):
    """Check if a button with the given text exists."""
    try:
        button = find_button_by_text(driver, text, partial=True)
        return button is not None and button.is_displayed()
    except:
        return False


# ============================================================
# FIND AND CLICK ELEMENTS BY HTML
# ============================================================

def find_and_click_elements(driver, html_elements):
    """Find and click elements based on their HTML representation."""
    if not html_elements:
        return True

    if isinstance(html_elements, str):
        html_elements = [html_elements]

    for html_element in html_elements:
        try:
            # Try to find by tag and attributes
            tag_match = re.search(r'<(\w+)', html_element)
            if not tag_match:
                continue
            tag = tag_match.group(1)

            # Extract id
            id_match = re.search(r'id="([^"]+)"', html_element)
            if id_match:
                element_id = id_match.group(1)
                try:
                    element = driver.find_element(By.ID, element_id)
                    if element.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", element)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", element)
                        print(f"    ✅ Clicked element with id: {element_id}")
                        time.sleep(1)
                        continue
                except:
                    pass

            # Extract data-testid
            testid_match = re.search(r'data-testid="([^"]+)"', html_element)
            if testid_match:
                testid = testid_match.group(1)
                try:
                    element = driver.find_element(By.CSS_SELECTOR, f'[data-testid="{testid}"]')
                    if element.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", element)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", element)
                        print(f"    ✅ Clicked element with data-testid: {testid}")
                        time.sleep(1)
                        continue
                except:
                    pass

            # Extract aria-label
            aria_match = re.search(r'aria-label="([^"]+)"', html_element)
            if aria_match:
                aria_label = aria_match.group(1)
                try:
                    element = driver.find_element(By.CSS_SELECTOR, f'[aria-label="{aria_label}"]')
                    if element.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", element)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", element)
                        print(f"    ✅ Clicked element with aria-label: {aria_label}")
                        time.sleep(1)
                        continue
                except:
                    pass

            # Try by class combination
            class_match = re.findall(r'class="([^"]+)"', html_element)
            if class_match:
                classes = class_match[0].split()
                selector = ".".join([f".{c}" for c in classes if c])
                if selector:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for element in elements:
                            if element.is_displayed():
                                driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                time.sleep(0.5)
                                driver.execute_script("arguments[0].click();", element)
                                print(f"    ✅ Clicked element with classes: {classes}")
                                time.sleep(1)
                                break
                    except:
                        pass

            # If element not found, try to find by text content
            text_match = re.search(r'<[^>]*>([^<]+)</', html_element)
            if text_match:
                text = text_match.group(1).strip()
                if text and len(text) > 1:
                    try:
                        elements = driver.find_elements(By.XPATH, f'//*[text()="{text}"]')
                        for element in elements:
                            if element.is_displayed():
                                driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                time.sleep(0.5)
                                driver.execute_script("arguments[0].click();", element)
                                print(f"    ✅ Clicked element with text: {text}")
                                time.sleep(1)
                                break
                    except:
                        pass

        except Exception as e:
            print(f"    ⚠️ Could not click element: {e}")
            continue

    return True


def find_and_fill_input(driver, input_html, value):
    """Find an input field and fill it with a value."""
    try:
        # Extract id
        id_match = re.search(r'id="([^"]+)"', input_html)
        if id_match:
            element_id = id_match.group(1)
            try:
                element = driver.find_element(By.ID, element_id)
                if element.is_displayed():
                    element.clear()
                    time.sleep(0.2)
                    element.send_keys(str(value))
                    print(f"    ✅ Filled input {element_id} with {value}")
                    return True
            except:
                pass

        # Extract aria-label
        aria_match = re.search(r'aria-label="([^"]+)"', input_html)
        if aria_match:
            aria_label = aria_match.group(1)
            try:
                element = driver.find_element(By.CSS_SELECTOR, f'[aria-label="{aria_label}"]')
                if element.is_displayed():
                    element.clear()
                    time.sleep(0.2)
                    element.send_keys(str(value))
                    print(f"    ✅ Filled input with aria-label: {aria_label} with {value}")
                    return True
            except:
                pass

        # Try by class
        class_match = re.search(r'class="([^"]+)"', input_html)
        if class_match:
            classes = class_match.group(1).split()
            selector = ".".join([f".{c}" for c in classes if c])
            if selector:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed():
                            element.clear()
                            time.sleep(0.2)
                            element.send_keys(str(value))
                            print(f"    ✅ Filled input with classes: {classes} with {value}")
                            return True
                except:
                    pass

        return False
    except Exception as e:
        print(f"    ⚠️ Could not fill input: {e}")
        return False


# ============================================================
# FIND KEY IN PAGE - RECURSIVE SEARCH
# ============================================================

def find_key_in_page(driver, key):
    """Search for a key in the current page."""
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text

        # Remove HTML tags for comparison
        key_text = re.sub(r'<[^>]+>', '', key).strip()

        if key_text and key_text in page_text:
            return True

        # Also check HTML source for the exact key
        html_source = driver.page_source
        if key in html_source:
            return True

        return False
    except Exception as e:
        print(f"    ⚠️ Error searching for key: {e}")
        return False


def search_value_in_page(driver, value):
    """
    Search for a value (HTML snippet) in the page.
    Returns True if any part of the value is found in the page.
    """
    try:
        page_html = driver.page_source

        if isinstance(value, str):
            # Search for the HTML snippet
            if value in page_html:
                return True

            # Also search for text content without tags
            text_only = re.sub(r'<[^>]+>', '', value).strip()


            # Search for specific attributes
            id_match = re.search(r'id="([^"]+)"', value)
            if id_match:
                element_id = id_match.group(1)
                if f'id="{element_id}"' in page_html:
                    return True

            aria_match = re.search(r'aria-labelledby="([^"]+)"', value)
            if aria_match:
                aria_label = aria_match.group(1)
                if f'aria-labelledby="{aria_label}"' in page_html:
                    return True


            return False

        elif isinstance(value, dict):
            # Recursively search dictionary values
            for v in value.values():
                if search_value_in_page(driver, v):
                    return True
            return False

        elif isinstance(value, list):
            # Recursively search list items
            for item in value:
                if search_value_in_page(driver, item):
                    return True
            return False

        return False
    except Exception as e:
        print(f"    ⚠️ Error searching for value: {e}")
        return False


def process_value_action(driver, value, username, url, student_name):
    """
    Process a value found in the JSON - handles both lists (buttons) and dicts (inputs).
    Returns True if action was taken, False otherwise.
    """
    try:
        if isinstance(value, list):
            # List of buttons to click
            print(f"    📋 Found {len(value)} buttons to click from value")
            find_and_click_elements(driver, value)
            time.sleep(1)

            # Check for Check button
            if click_check_button(driver):
                time.sleep(2)
                click_next_question(driver)
                return True
            elif click_next_question(driver):
                return True
            elif click_show_summary(driver):
                print("    ✅ Quiz completed (Show summary)")
                log_progress(student_name, username, url, "QUIZ_COMPLETE", "Quiz completed")
                return True
            return True

        elif isinstance(value, dict):
            # Dictionary of inputs to fill
            print(f"    📋 Found {len(value)} inputs to fill from value")
            for input_html, fill_value in value.items():
                find_and_fill_input(driver, input_html, fill_value)

            time.sleep(1)

            # Check for Check button
            if click_check_button(driver):
                time.sleep(2)
                click_next_question(driver)
                return True
            elif click_next_question(driver):
                return True
            elif click_show_summary(driver):
                print("    ✅ Quiz completed (Show summary)")
                log_progress(student_name, username, url, "QUIZ_COMPLETE", "Quiz completed")
                return True
            return True

        return False
    except Exception as e:
        print(f"    ⚠️ Error processing value action: {e}")
        return False


# ============================================================
# PROCESS A SINGLE URL
# ============================================================

def process_url(driver, username, url, student_name):
    """Process a single quiz URL."""
    print(f"\n    🌐 Processing URL: {url}")

    # Load page
    driver.get(url)
    time.sleep(5)

    # Check for Show summary button first (quiz already completed)
    if button_exists(driver, "Show summary"):
        print("    ✅ Quiz already completed (Show summary found)")
        click_show_summary(driver)
        log_progress(student_name, username, url, "QUIZ_COMPLETE", "Quiz already completed")
        return True

    # Click Let's go if present
    click_lets_go(driver)

    # Main loop - process questions until completion
    max_attempts = 25
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        print(f"    📝 Attempt {attempt}")

        # Check if we're on the summary page
        if button_exists(driver, "Show summary"):
            print("    ✅ All questions completed! (Show summary found)")
            click_show_summary(driver)
            log_progress(student_name, username, url, "QUIZ_COMPLETE", "All questions solved")
            return True

        # Get current page HTML for detection
        page_html = driver.page_source
        found_match = False
        action_taken = False

        # Search for matching key in INPUT_JSON
        for key, value in INPUT_JSON.items():
            # Check if key exists in page
            key_text = re.sub(r'<[^>]+>', '', key).strip()
            if key_text and key_text in page_html:
                print(f"    🔍 Found matching key: {key_text[:50]}...")
                found_match = True

                # Process the action based on value type
                if process_value_action(driver, value, username, url, student_name):
                    action_taken = True
                    break

        # If key matched but action was taken, continue to next question
        if found_match and action_taken:
            time.sleep(2)
            continue

        # If no key match found, try searching through values recursively
        if not found_match:
            print("    🔍 No key match found, searching values recursively...")

            # Search through all values in the JSON
            for key, value in INPUT_JSON.items():
                if search_value_in_page(driver, value):
                    print(f"    🔍 Found matching value from key: {key[:50]}...")
                    found_match = True

                    # Process the action based on value type
                    if process_value_action(driver, value, username, url, student_name):
                        action_taken = True
                        break

            # If value match found and action was taken, continue
            if found_match and action_taken:
                time.sleep(2)
                continue

        # If still no match found, try Skip button
        if not found_match or not action_taken:
            print("    ⚠️ No matching content found in JSON")

            # Try Skip button first
            if click_skip_button(driver):
                print("    ⏭️ Skipped question")
                page_text = driver.find_element(By.TAG_NAME, "body").text
                record_skipped(username, url, page_text[:200], "No matching content - Skipped")
                continue

            # Try other buttons
            if click_check_button(driver):
                time.sleep(2)
                click_next_question(driver)
                continue

            if click_next_question(driver):
                continue

            if click_show_summary(driver):
                print("    ✅ Quiz completed (Show summary)")
                log_progress(student_name, username, url, "QUIZ_COMPLETE", "Quiz completed")
                return True

            # If nothing worked, record as skipped and break
            print("    ❌ Could not proceed further")
            page_text = driver.find_element(By.TAG_NAME, "body").text
            record_skipped(username, url, page_text[:200], "Could not proceed - No action taken")
            break

    # Check for Show summary one last time
    if button_exists(driver, "Show summary"):
        print("    ✅ Quiz completed (Show summary)")
        click_show_summary(driver)
        log_progress(student_name, username, url, "QUIZ_COMPLETE", "Quiz completed")
        return True

    log_progress(student_name, username, url, "INCOMPLETE", f"Could not complete after {max_attempts} attempts")
    return False


# ============================================================
# PROCESS STUDENT
# ============================================================

@with_timeout
def process_student_with_timeout(student, batch_number, student_number):
    """Process a single student with timeout protection."""
    name = student["name"]
    username = student["username"]
    password = student["password"]

    print()
    print("━" * 70)
    print(f"🧑 STUDENT: {name}")
    print(f"📧 USERNAME: {username}")
    print("━" * 70)

    profile_dir = os.path.join(
        os.getcwd(),
        f"chrome_profile_batch_{batch_number}_student_{student_number}"
    )

    driver = None

    try:
        driver = create_driver(profile_dir)

        # Login
        success = khan_login(driver, username, password)
        if not success:
            save_screenshot(driver, name, username, "login_failed")
            log_progress(name, username, "", "LOGIN_FAILED", "Could not login")
            raise Exception("Login failed")

        save_screenshot(driver, name, username, "login_success")
        log_progress(name, username, "", "LOGIN_SUCCESS", "Successfully logged in")

        accept_cookie_consent(driver)
        handle_intro_modal(driver)

        # Process each URL
        all_completed = True
        for url in QUIZ_URLS:
            if not process_url(driver, username, url, name):
                all_completed = False

        if all_completed:
            save_screenshot(driver, name, username, "student_complete")
            log_progress(name, username, "", "STUDENT_COMPLETE", "All quizzes completed successfully")
            mark_student_processed(username)
            print(f"\n    ✅ Student complete: {name}")
            return True
        else:
            save_screenshot(driver, name, username, "student_partial")
            log_progress(name, username, "", "STUDENT_PARTIAL", "Some quizzes not completed")
            mark_student_processed(username)
            return True

    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ Error processing {name}: {error_msg}")
        if driver:
            save_screenshot(driver, name, username, "error")
        log_progress(name, username, "", "ERROR", error_msg)

        mark_student_failed(username, error_msg)
        return False

    finally:
        if driver:
            try:
                driver.quit()
                print("    🔒 Browser closed")
            except Exception:
                pass

        try:
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir, ignore_errors=True)
        except Exception:
            pass


def process_student(student, batch_number, student_number):
    """Wrapper for process_student_with_timeout."""
    try:
        return process_student_with_timeout(student, batch_number, student_number)
    except TimeoutError:
        name = student["name"]
        username = student["username"]
        print(f"\n⏰ TIMEOUT: Student {name} took more than {STUDENT_TIMEOUT // 60} minutes")

        log_progress(name, username, "", "TIMEOUT", f"Exceeded {STUDENT_TIMEOUT // 60} minute limit")
        mark_student_failed(username, f"Timeout after {STUDENT_TIMEOUT // 60} minutes")
        return False
    except Exception as e:
        name = student["name"]
        username = student["username"]
        print(f"\n❌ Unexpected error processing {name}: {e}")
        mark_student_failed(username, str(e))
        return False


# ============================================================
# READ CSV
# ============================================================

def read_students(csv_path):
    students = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("Student name", "") or "").strip()
            username = (row.get("Username", "") or "").strip()
            password = (row.get("Password", "") or "").strip()

            if not username:
                print(f"⚠️ Skipping student without username: {name}")
                continue

            students.append({
                "name": name,
                "username": username,
                "password": password,
            })

    return students


def filter_unprocessed_students(students):
    unprocessed = []

    for student in students:
        username = student["username"]
        if is_student_processed(username):
            print(f"    ⏭️ Skipping already processed: {username}")
        else:
            unprocessed.append(student)

    return unprocessed


# ============================================================
# PROCESS BATCH
# ============================================================

def process_batch(batch, batch_number, total_batches):
    print()
    print("=" * 70)
    print(f"🚀 BATCH {batch_number}/{total_batches}")
    print(f"👥 STUDENTS IN BATCH: {len(batch)}")
    print("=" * 70)

    unprocessed = filter_unprocessed_students(batch)

    if not unprocessed:
        print("    ✅ All students in this batch are already processed")
        return

    print(f"    📋 Processing {len(unprocessed)} unprocessed students")

    for student_number, student in enumerate(unprocessed, start=1):
        print()
        print(f"Processing student {student_number}/{len(unprocessed)}")
        process_student(student, batch_number, student_number)


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print("=" * 70)
    print("KHAN ACADEMY QUIZ AUTO-SOLVER")
    print("=" * 70)
    print(f"⏰ Student timeout: {STUDENT_TIMEOUT // 60} minutes")
    print(f"📄 Using input.json: {INPUT_JSON_FILE}")
    print(f"🔗 URLs to process: {len(QUIZ_URLS)}")
    print("🔍 Button detection: by text content")
    print("🔍 Recursive value search: Enabled")

    if not os.path.exists(CSV_FILE):
        print()
        print(f"❌ CSV NOT FOUND: {CSV_FILE}")
        print()
        print("Required CSV columns:")
        print("Student name, Username, Password")
        sys.exit(1)

    if not os.path.exists(INPUT_JSON_FILE):
        print()
        print(f"❌ {INPUT_JSON_FILE} NOT FOUND!")
        sys.exit(1)

    students = read_students(CSV_FILE)

    print()
    print(f"📋 Loaded {len(students)} student(s) from CSV")

    checkpoint = load_checkpoint()
    processed_count = len(checkpoint["processed_students"])
    failed_count = len(checkpoint["failed_students"])
    print(f"📊 Checkpoint: {processed_count} processed, {failed_count} failed")

    if not students:
        print("❌ No valid students found")
        sys.exit(1)

    batches = [
        students[i:i + BATCH_SIZE]
        for i in range(0, len(students), BATCH_SIZE)
    ]

    total_batches = len(batches)

    print(f"📦 Total batches: {total_batches}")
    print(f"👥 Batch size: {BATCH_SIZE}")

    total_processed = 0
    total_failed = 0

    try:
        for batch_number, batch in enumerate(batches, start=1):
            process_batch(batch, batch_number, total_batches)

            checkpoint = load_checkpoint()
            total_processed = len(checkpoint["processed_students"])
            total_failed = len(checkpoint["failed_students"])

    except KeyboardInterrupt:
        print()
        print("🛑 Program interrupted by user")

    finally:
        print()
        print("=" * 70)
        print("🏁 ALL PROCESSING FINISHED")
        print()
        print(f"✅ Successfully processed: {total_processed} students")
        print(f"❌ Failed: {total_failed} students")
        print()
        print(f"📸 Screenshots: {SCREENSHOT_DIR}")
        print(f"📝 Progress CSV: {PROGRESS_FILE}")
        print(f"📊 Checkpoint: {CHECKPOINT_FILE}")
        print(f"📋 Skipped: {SKIPPED_FILE}")
        print("=" * 70)


if __name__ == "__main__":
    main()