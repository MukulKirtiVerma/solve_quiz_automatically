#!/usr/bin/env python3
"""
Khan Academy Chemical Equations Auto-Solver with Checkpoints

- Loads students from unique_student_records.csv
- Processes students in batches of 5
- Logs into Khan Academy
- Handles cookie consent and common onboarding popups
- Automatically solves balancing chemical equations exercises
- Saves screenshots and records progress in CSV
- Checkpoint system: skips already processed students
- 7-minute timeout per student
- Error handling: skips failed students and continues
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
import re
import signal
from functools import wraps


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

# Process 5 students at a time
BATCH_SIZE = 5

LOGIN_URL = "https://en.khanacademy.org/login"

EXERCISE_1_URL = "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:types-of-chemical-equations/e/balancing-simple-chemical-equations"

EXERCISE_2_URL = "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:types-of-chemical-equations/e/balanced-chemical-equations"

OUTPUT_DIR = "ka_auto_progress"
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "checkpoint.json")
DEFAULT_WAIT = 20
STUDENT_TIMEOUT = 420  # 7 minutes in seconds


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
                "batch",
                "exercise",
                "url",
                "status",
                "notes",
            ])

    # Initialize checkpoint file if it doesn't exist
    if not os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump({"processed_students": [], "failed_students": []}, f, indent=2)

    return str(screenshot_dir), str(progress_file)


SCREENSHOT_DIR, PROGRESS_FILE = setup_output()


# ============================================================
# CHECKPOINT MANAGEMENT
# ============================================================

def load_checkpoint():
    """Load the checkpoint file with processed and failed students."""
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"processed_students": [], "failed_students": []}


def save_checkpoint(processed_students, failed_students):
    """Save the checkpoint file."""
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "processed_students": processed_students,
            "failed_students": failed_students
        }, f, indent=2)


def is_student_processed(username):
    """Check if a student has already been processed."""
    checkpoint = load_checkpoint()
    return username in checkpoint["processed_students"]


def is_student_failed(username):
    """Check if a student has previously failed."""
    checkpoint = load_checkpoint()
    return username in checkpoint["failed_students"]


def mark_student_processed(username):
    """Mark a student as successfully processed."""
    checkpoint = load_checkpoint()
    if username not in checkpoint["processed_students"]:
        checkpoint["processed_students"].append(username)
    # Remove from failed if present
    if username in checkpoint["failed_students"]:
        checkpoint["failed_students"].remove(username)
    save_checkpoint(checkpoint["processed_students"], checkpoint["failed_students"])


def mark_student_failed(username, error_message=""):
    """Mark a student as failed."""
    checkpoint = load_checkpoint()
    if username not in checkpoint["failed_students"]:
        checkpoint["failed_students"].append(username)
    save_checkpoint(checkpoint["processed_students"], checkpoint["failed_students"])


def log_failed_student(username, name, error_message):
    """Log a failed student with details."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(OUTPUT_DIR, "failed_students.csv"), "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if os.path.getsize(os.path.join(OUTPUT_DIR, "failed_students.csv")) == 0:
            writer.writerow(["timestamp", "student_name", "username", "error_message"])
        writer.writerow([timestamp, name, username, error_message])


# ============================================================
# PROGRESS LOGGING
# ============================================================

def log_progress(
        student_name,
        username,
        batch_number,
        exercise_number,
        url,
        status,
        notes=""
):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(PROGRESS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp,
            student_name,
            username,
            batch_number,
            exercise_number,
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


def save_screenshot(
        driver,
        student_name,
        username,
        exercise_number,
        label
):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    filename = (
        f"{safe_filename(student_name)}_"
        f"{safe_filename(username)}_"
        f"ex{exercise_number}_"
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

        # Find visible input fields
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

        # Fallback email selectors
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

        # Fallback password selectors
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

        # Enter credentials
        email_field.clear()
        email_field.send_keys(username)
        time.sleep(0.5)

        password_field.clear()
        password_field.send_keys(password)
        time.sleep(0.5)

        # Submit
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
# COOKIE CONSENT
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


# ============================================================
# HANDLE POPUPS / ONBOARDING
# ============================================================

def handle_intro_modal(driver):
    time.sleep(2)

    # Close promotional popups
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

    # Handle optional onboarding checkbox
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

    # Click Start learning only if onboarding is displayed
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
# TIMEOUT DECORATOR
# ============================================================

def timeout_handler(signum, frame):
    raise TimeoutError("Student processing timed out")


def with_timeout(func):
    """Decorator to add timeout to student processing."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Set timeout alarm
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(STUDENT_TIMEOUT)
        try:
            result = func(*args, **kwargs)
            signal.alarm(0)  # Cancel alarm
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
# CLICK "LET'S GO" BUTTON
# ============================================================

def click_lets_go(driver):
    """Click the Let's go button to start the exercise."""
    try:
        # Wait for the Let's go button to be present
        wait = WebDriverWait(driver, 10)
        button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-kind="primary"] span'))
        )
        # Find the parent button and click it
        parent = button.find_element(By.XPATH, "..")
        driver.execute_script("arguments[0].click();", parent)
        print("    ✅ Clicked 'Let's go'")
        time.sleep(2)
        return True
    except Exception as e:
        print(f"    ⚠️ Could not click 'Let's go': {e}")
        return False


# ============================================================
# FIND AND FILL INPUT FIELDS
# ============================================================

def fill_inputs_by_order(driver, values, max_wait=10):
    """Find input fields in order and fill them with values."""
    try:
        wait = WebDriverWait(driver, max_wait)

        # Wait for input fields to be present
        inputs = wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'input[type="text"]'))
        )

        # Filter to visible inputs
        visible_inputs = [inp for inp in inputs if inp.is_displayed()]

        if len(visible_inputs) < len(values):
            print(f"    ⚠️ Found {len(visible_inputs)} inputs, need {len(values)}")
            # Try to find more inputs with a more specific selector
            time.sleep(1)
            inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="text"]')
            visible_inputs = [inp for inp in inputs if inp.is_displayed()]

        # Fill each input with the corresponding value
        for i, value in enumerate(values):
            if i < len(visible_inputs):
                try:
                    visible_inputs[i].clear()
                    visible_inputs[i].send_keys(str(value))
                    print(f"    ✅ Filled input {i + 1} with {value}")
                except Exception as e:
                    print(f"    ⚠️ Could not fill input {i + 1}: {e}")

        return True
    except Exception as e:
        print(f"    ❌ Failed to fill inputs: {e}")
        return False


# ============================================================
# CLICK CHECK BUTTON
# ============================================================

def click_check_button(driver):
    """Click the Check button to verify the answer."""
    try:
        wait = WebDriverWait(driver, 10)
        button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="exercise-check-answer"]'))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", button)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", button)
        print("    ✅ Clicked 'Check'")
        time.sleep(2)
        return True
    except Exception as e:
        print(f"    ⚠️ Could not click 'Check': {e}")
        return False


# ============================================================
# CLICK NEXT QUESTION BUTTON
# ============================================================

def click_next_question(driver):
    """Click the Next question or Show summary button."""
    try:
        wait = WebDriverWait(driver, 10)

        # Try by data-testid
        try:
            button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-testid="exercise-next-question"]'))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", button)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", button)
            text = button.text or "Next question"
            print(f"    ✅ Clicked '{text}'")
            time.sleep(2)
            return True
        except:
            pass

        # Try by text content
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for button in buttons:
            try:
                text = (button.text or "").strip()
                if "Next question" in text or "Show summary" in text:
                    if button.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", button)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", button)
                        print(f"    ✅ Clicked '{text}'")
                        time.sleep(2)
                        return True
            except:
                continue

        print("    ⚠️ Could not find Next question/Show summary button")
        return False
    except Exception as e:
        print(f"    ⚠️ Could not click 'Next question': {e}")
        return False


# ============================================================
# SOLVE EXERCISE 1 - Balancing Simple Chemical Equations
# ============================================================

def solve_exercise_1(driver, student_name, username):
    """Solve the first balancing exercise with the specified sequence."""
    print()
    print("=" * 60)
    print("📚 SOLVING EXERCISE 1: Balancing Simple Chemical Equations")
    print("=" * 60)

    # Open the exercise URL
    driver.get(EXERCISE_1_URL)
    time.sleep(5)

    accept_cookie_consent(driver)
    handle_intro_modal(driver)

    # Click Let's go
    if not click_lets_go(driver):
        print("    ❌ Failed to start exercise")
        return False

    # Question 1: 2, 1, 2
    print("    📝 Solving Question 1...")
    if fill_inputs_by_order(driver, [2, 1, 2]):
        click_check_button(driver)
        click_next_question(driver)
    else:
        print("    ❌ Failed to fill Question 1")
        return False

    # Question 2: 2, 1, 2
    print("    📝 Solving Question 2...")
    if fill_inputs_by_order(driver, [2, 1, 2]):
        click_check_button(driver)
        click_next_question(driver)
    else:
        print("    ❌ Failed to fill Question 2")
        return False

    # Question 3: 4, 3, 2
    print("    📝 Solving Question 3...")
    if fill_inputs_by_order(driver, [4, 3, 2]):
        click_check_button(driver)
        click_next_question(driver)
    else:
        print("    ❌ Failed to fill Question 3")
        return False

    # Question 4: 2, 2, 1
    print("    📝 Solving Question 4...")
    if fill_inputs_by_order(driver, [2, 2, 1]):
        click_check_button(driver)
        # This one says "Show summary"
        click_next_question(driver)
    else:
        print("    ❌ Failed to fill Question 4")
        return False

    save_screenshot(driver, student_name, username, 1, "exercise1_complete")
    log_progress(student_name, username, 0, 1, EXERCISE_1_URL, "EXERCISE_1_COMPLETE", "All questions solved")

    return True


# ============================================================
# SOLVE EXERCISE 2 - Balanced Chemical Equations
# ============================================================

def solve_exercise_2(driver, student_name, username):
    """Solve the second balancing exercise with the specified sequence."""
    print()
    print("=" * 60)
    print("📚 SOLVING EXERCISE 2: Balanced Chemical Equations")
    print("=" * 60)

    # Open the exercise URL
    driver.get(EXERCISE_2_URL)
    time.sleep(5)

    accept_cookie_consent(driver)
    handle_intro_modal(driver)

    # Click Let's go
    if not click_lets_go(driver):
        print("    ❌ Failed to start exercise")
        return False

    # Question 1: 2, 6, 2, 3
    print("    📝 Solving Question 1...")
    if fill_inputs_by_order(driver, [2, 6, 2, 3]):
        click_check_button(driver)
        click_next_question(driver)
    else:
        print("    ❌ Failed to fill Question 1")
        return False

    # Question 2: 2, 3, 2, 4
    print("    📝 Solving Question 2...")
    if fill_inputs_by_order(driver, [2, 3, 2, 4]):
        click_check_button(driver)
        click_next_question(driver)
    else:
        print("    ❌ Failed to fill Question 2")
        return False

    # Question 3: 2, 2, 1, 4
    print("    📝 Solving Question 3...")
    if fill_inputs_by_order(driver, [2, 2, 1, 4]):
        click_check_button(driver)
        click_next_question(driver)
    else:
        print("    ❌ Failed to fill Question 3")
        return False

    # Question 4: 2, 1, 1, 4
    print("    📝 Solving Question 4...")
    if fill_inputs_by_order(driver, [2, 1, 1, 4]):
        click_check_button(driver)
        click_next_question(driver)
    else:
        print("    ❌ Failed to fill Question 4")
        return False

    # Question 5: 2, 1, 1, 2
    print("    📝 Solving Question 5...")
    if fill_inputs_by_order(driver, [2, 1, 1, 2]):
        click_check_button(driver)
        # This one says "Show summary"
        click_next_question(driver)
    else:
        print("    ❌ Failed to fill Question 5")
        return False

    save_screenshot(driver, student_name, username, 2, "exercise2_complete")
    log_progress(student_name, username, 0, 2, EXERCISE_2_URL, "EXERCISE_2_COMPLETE", "All questions solved")

    return True


# ============================================================
# PROCESS ONE STUDENT WITH TIMEOUT
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

        # LOGIN
        success = khan_login(driver, username, password)
        if not success:
            save_screenshot(driver, name, username, 0, "login_failed")
            log_progress(name, username, batch_number, 0, "", "LOGIN_FAILED", "Could not login")
            raise Exception("Login failed")

        # LOGIN SUCCESS
        save_screenshot(driver, name, username, 0, "login_success")
        log_progress(name, username, batch_number, 0, "", "LOGIN_SUCCESS", "Successfully logged in")

        # COOKIE CONSENT
        accept_cookie_consent(driver)

        # SOLVE EXERCISE 1
        if not solve_exercise_1(driver, name, username):
            raise Exception("Exercise 1 failed")

        # SOLVE EXERCISE 2
        if not solve_exercise_2(driver, name, username):
            raise Exception("Exercise 2 failed")

        # COMPLETE
        save_screenshot(driver, name, username, 0, "student_complete")
        log_progress(name, username, batch_number, 0, "", "STUDENT_COMPLETE", "All exercises completed automatically")

        print()
        print(f"    ✅ Student complete: {name}")

        # Mark as successfully processed
        mark_student_processed(username)
        return True

    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ Error processing {name}: {error_msg}")
        if driver:
            save_screenshot(driver, name, username, 0, "error")
        log_progress(name, username, batch_number, 0, "", "ERROR", error_msg)

        # Mark as failed
        mark_student_failed(username, error_msg)
        log_failed_student(username, name, error_msg)
        return False

    finally:
        if driver:
            try:
                driver.quit()
                print("    🔒 Browser closed")
            except Exception:
                pass

        # Remove temporary profile
        try:
            if os.path.exists(profile_dir):
                shutil.rmtree(profile_dir, ignore_errors=True)
        except Exception:
            pass


def process_student(student, batch_number, student_number):
    """Wrapper for process_student_with_timeout to handle timeout exceptions."""
    try:
        return process_student_with_timeout(student, batch_number, student_number)
    except TimeoutError:
        name = student["name"]
        username = student["username"]
        print(f"\n⏰ TIMEOUT: Student {name} took more than {STUDENT_TIMEOUT // 60} minutes")

        # Log timeout
        log_progress(name, username, batch_number, 0, "", "TIMEOUT", f"Exceeded {STUDENT_TIMEOUT // 60} minute limit")
        mark_student_failed(username, f"Timeout after {STUDENT_TIMEOUT // 60} minutes")
        log_failed_student(username, name, f"Timeout after {STUDENT_TIMEOUT // 60} minutes")
        return False
    except Exception as e:
        name = student["name"]
        username = student["username"]
        print(f"\n❌ Unexpected error processing {name}: {e}")
        mark_student_failed(username, str(e))
        log_failed_student(username, name, str(e))
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


# ============================================================
# FILTER STUDENTS BY CHECKPOINT
# ============================================================

def filter_unprocessed_students(students):
    """Filter out students that have already been processed or failed."""
    unprocessed = []
    skipped_processed = []
    skipped_failed = []

    for student in students:
        username = student["username"]
        if is_student_processed(username):
            skipped_processed.append(username)
        elif is_student_failed(username):
            skipped_failed.append(username)
        else:
            unprocessed.append(student)

    if skipped_processed:
        print(f"    ⏭️ Skipping {len(skipped_processed)} already processed students")
    if skipped_failed:
        print(f"    ⏭️ Skipping {len(skipped_failed)} previously failed students")

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

    # Filter out already processed students
    unprocessed = filter_unprocessed_students(batch)

    if not unprocessed:
        print("    ✅ All students in this batch are already processed or failed")
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
    print("KHAN ACADEMY CHEMICAL EQUATIONS AUTO-SOLVER WITH CHECKPOINTS")
    print("=" * 70)
    print(f"⏰ Student timeout: {STUDENT_TIMEOUT // 60} minutes")

    if not os.path.exists(CSV_FILE):
        print()
        print(f"❌ CSV NOT FOUND: {CSV_FILE}")
        print()
        print("Required CSV columns:")
        print("Student name, Username, Password")
        sys.exit(1)

    students = read_students(CSV_FILE)

    print()
    print(f"📋 Loaded {len(students)} student(s) from CSV")

    # Show checkpoint status
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

    # Statistics
    total_processed = 0
    total_failed = 0

    try:
        for batch_number, batch in enumerate(batches, start=1):
            # Count unprocessed in this batch
            unprocessed = filter_unprocessed_students(batch)
            if unprocessed:
                process_batch(batch, batch_number, total_batches)

            # Update statistics
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
        print("=" * 70)


if __name__ == "__main__":
    main()