#!/usr/bin/env python3
"""
Khan Academy Quiz Auto-Solver with NVIDIA API

Features:
- Loads students from CSV
- Uses NVIDIA API to analyze questions and provide answers
- Extracts actual input IDs from the page
- Takes screenshots and sends page content to API
- Automatically fills inputs and clicks buttons based on API response
- Handles Check, Check again, Try again, Next question, Show summary buttons
- When "Try again" appears, sends feedback to AI for correct answer
- Moves to next URL when Show summary is clicked
- Checkpoint system for processed students
- 10-minute timeout per student
"""

import csv
import time
import os
import sys
import shutil
import json
import base64
import mimetypes
import requests
import dotenv
import random
from pathlib import Path
from datetime import datetime
import subprocess
import signal
from functools import wraps
import re
import io

# Load environment variables
dotenv.load_dotenv()


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
ensure_package("Pillow", "PIL")
ensure_package("python-dotenv", "dotenv")

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
from PIL import Image

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

OUTPUT_DIR = "ka_quiz_progress"
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "checkpoint.json")
STUDENT_TIMEOUT = 600  # 10 minutes per student

# NVIDIA API Configuration
INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
STREAM = False


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


def get_element_screenshot_b64(driver, element):
    """Capture screenshot of a specific element and return as base64."""
    try:
        location = element.location
        size = element.size

        screenshot = driver.get_screenshot_as_png()
        image = Image.open(io.BytesIO(screenshot))

        left = location['x']
        top = location['y']
        right = location['x'] + size['width']
        bottom = location['y'] + size['height']

        if image.size[0] > driver.get_window_size()['width'] * 2:
            left = left * 2
            top = top * 2
            right = right * 2
            bottom = bottom * 2

        cropped = image.crop((left, top, right, bottom))

        buffer = io.BytesIO()
        cropped.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"    ⚠️ Could not capture element screenshot: {e}")
        return None


# ============================================================
# NVIDIA API CALL
# ============================================================

def call_nvidia_api(payload, headers, max_retries=6):
    """
    Call NVIDIA API with automatic retry for temporary server errors.
    """
    retry_statuses = {429, 500, 502, 503, 504}

    for attempt in range(1, max_retries + 1):
        try:
            print(f"\n    🤖 Sending to NVIDIA API... Attempt {attempt}/{max_retries}")

            response = requests.post(
                INVOKE_URL,
                headers=headers,
                json=payload,
                timeout=180
            )

            if response.status_code == 200:
                return response

            if response.status_code in retry_statuses:
                print(f"    ⚠️ Temporary API error: {response.status_code}")
                print(f"    Response: {response.text[:500]}")

                if attempt == max_retries:
                    response.raise_for_status()

                wait_time = min(2 ** attempt + random.uniform(0, 1), 60)
                print(f"    Retrying in {wait_time:.1f} seconds...")
                time.sleep(wait_time)
                continue

            print(f"\n❌ API Error: {response.status_code}")
            print(response.text)
            response.raise_for_status()

        except requests.exceptions.Timeout:
            print("    ⏰ Request timed out.")
            if attempt == max_retries:
                raise
            wait_time = min(2 ** attempt, 60)
            print(f"    Retrying in {wait_time} seconds...")
            time.sleep(wait_time)

        except requests.exceptions.RequestException as e:
            print(f"    ❌ Request failed: {e}")
            if attempt == max_retries:
                raise
            wait_time = min(2 ** attempt, 60)
            print(f"    Retrying in {wait_time} seconds...")
            time.sleep(wait_time)

    raise RuntimeError("Maximum retries exceeded.")


def get_ai_solution(driver, question_html, screenshot_b64, input_ids, previous_attempts=None):
    """Send question to NVIDIA API and get solution."""
    api_key = os.getenv("NVIDIA_API_KEY")

    if not api_key:
        print("❌ NVIDIA_API_KEY environment variable not set!")
        print("Please set it with: export NVIDIA_API_KEY='your-api-key'")
        return None

    try:
        # Build the input IDs info for the prompt
        input_ids_info = ""
        if input_ids:
            input_ids_info = f"\nThe input fields on this page have these IDs in order:\n{', '.join(input_ids)}\n"
            input_ids_info += "Use these exact IDs in your response for each input field.\n"

        # Add feedback if this is a retry after wrong answer
        feedback = ""
        if previous_attempts and len(previous_attempts) > 0:
            feedback = "\n\nIMPORTANT: The previous answer was WRONG. Please provide the CORRECT answer.\n"
            feedback += "Here are the previous attempts that were wrong:\n"
            for i, attempt in enumerate(previous_attempts, 1):
                feedback += f"Attempt {i}: {json.dumps(attempt)}\n"
            feedback += "\nPlease provide the correct answer. Double-check your chemistry!\n"

        prompt = f"""
You are a chemistry expert helping solve Khan Academy questions. Analyze the question and provide the answer in JSON format.

The question content includes:
1. The question text
2. Chemical equations (if any)
3. Input fields or multiple choice options
{input_ids_info}
{feedback}

Respond with a JSON object in one of these formats:

For balancing equations (input fields) - USE THE EXACT INPUT IDs PROVIDED:
{{
    "type": "balancing",
    "inputs": [
        {{"id": "actual_input_id_1", "value": 2}},
        {{"id": "actual_input_id_2", "value": 1}},
        {{"id": "actual_input_id_3", "value": 2}}
    ]
}}

For multiple choice:
{{
    "type": "multiple_choice",
    "choices": ["A", "C"]
}}

If the question is already answered or no action needed:
{{
    "type": "done"
}}

Important:
- For balancing equations, use the EXACT input IDs provided above
- For multiple choice, provide the letter(s) of the correct answer(s)
- If multiple answers are correct, include all of them
- If you're unsure, provide your best guess
"""

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"{prompt}\n\nHere is the question HTML content:\n\n{question_html}"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{screenshot_b64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 4096,
            "reasoning_budget": 2048,
            "stream": STREAM,
            "temperature": 0.2,
            "top_p": 0.95
        }

        response = call_nvidia_api(payload, headers)
        result = response.json()

        response_text = result["choices"][0]["message"]["content"]
        print(f"    🤖 API Response: {response_text[:200]}...")

        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            try:
                result_json = json.loads(json_match.group(0))
                return result_json
            except json.JSONDecodeError:
                print("    ⚠️ Could not parse JSON from API response")
                return None

        return None

    except Exception as e:
        print(f"    ❌ API Error: {e}")
        return None


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
    """Click Check or Check again button."""
    return click_button_by_text(driver, "Check") or click_button_by_text(driver, "Check again", partial=True)


def click_next_question(driver):
    """Click Next question button."""
    return click_button_by_text(driver, "Next question", partial=True)


def click_show_summary(driver):
    """Click Show summary button."""
    return click_button_by_text(driver, "Show summary", partial=True)


def click_try_again(driver):
    """Click Try again button."""
    return click_button_by_text(driver, "Try again", partial=True)


def button_exists(driver, text):
    """Check if a button with the given text exists."""
    try:
        button = find_button_by_text(driver, text, partial=True)
        return button is not None and button.is_displayed()
    except:
        return False


def is_try_again_present(driver):
    """Check if Try again button is present."""
    return button_exists(driver, "Try again")


def is_next_present(driver):
    """Check if Next question button is present."""
    return button_exists(driver, "Next question")


def is_summary_present(driver):
    """Check if Show summary button is present."""
    return button_exists(driver, "Show summary")


# ============================================================
# FIND AND FILL INPUT BY ID
# ============================================================

def get_input_ids(driver):
    """Get all input field IDs in order."""
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="text"]')
        visible_inputs = [inp for inp in inputs if inp.is_displayed()]
        input_ids = []
        for inp in visible_inputs:
            input_id = inp.get_attribute('id')
            if input_id:
                input_ids.append(input_id)
            else:
                input_ids.append(f"input_{len(input_ids)}")
        return input_ids, visible_inputs
    except Exception as e:
        print(f"    ⚠️ Error getting input IDs: {e}")
        return [], []


def find_and_fill_input_by_id(driver, input_id, value):
    """Find an input field by ID and fill it with a value."""
    try:
        element = driver.find_element(By.ID, input_id)
        if element.is_displayed():
            element.clear()
            time.sleep(0.2)
            element.send_keys(str(value))
            print(f"    ✅ Filled input {input_id} with {value}")
            return True
    except Exception as e:
        print(f"    ⚠️ Could not fill input {input_id}: {e}")
    return False


def find_all_inputs(driver):
    """Find all visible input fields."""
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="text"]')
        return [inp for inp in inputs if inp.is_displayed()]
    except Exception as e:
        print(f"    ⚠️ Error finding inputs: {e}")
        return []


def fill_inputs_by_order(driver, values):
    """Fill input fields in order with values."""
    inputs = find_all_inputs(driver)
    if not inputs:
        print("    ⚠️ No input fields found")
        return False

    fill_count = min(len(inputs), len(values))
    for i in range(fill_count):
        try:
            inputs[i].clear()
            time.sleep(0.2)
            inputs[i].send_keys(str(values[i]))
            print(f"    ✅ Filled input {i + 1} with {values[i]}")
        except Exception as e:
            print(f"    ⚠️ Could not fill input {i + 1}: {e}")

    return fill_count > 0


# ============================================================
# CLICK MULTIPLE CHOICE BY LETTER
# ============================================================

def click_choice_by_letter(driver, letter):
    """Click a choice button by letter."""
    try:
        try:
            button = driver.find_element(By.CSS_SELECTOR, f'button[aria-label="(Choice {letter})"]')
            if button.is_displayed():
                driver.execute_script("arguments[0].scrollIntoView(true);", button)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", button)
                print(f"    ✅ Selected choice {letter}")
                return True
        except:
            pass

        buttons = driver.find_elements(By.TAG_NAME, "button")
        for button in buttons:
            try:
                text = (button.text or "").strip()
                if text == letter and button.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView(true);", button)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", button)
                    print(f"    ✅ Selected choice {letter}")
                    return True
            except:
                continue

        return False
    except Exception as e:
        print(f"    ⚠️ Could not select choice {letter}: {e}")
        return False


def get_available_choices(driver):
    """Get all available choice letters on the page."""
    choices = []
    try:
        for letter in ['A', 'B', 'C', 'D', 'E']:
            try:
                button = driver.find_element(By.CSS_SELECTOR, f'button[aria-label="(Choice {letter})"]')
                if button.is_displayed():
                    choices.append(letter)
            except:
                pass

        if not choices:
            buttons = driver.find_elements(By.TAG_NAME, "button")
            for button in buttons:
                try:
                    text = (button.text or "").strip()
                    if text in ['A', 'B', 'C', 'D', 'E'] and button.is_displayed():
                        if text not in choices:
                            choices.append(text)
                except:
                    continue
    except Exception as e:
        print(f"    ⚠️ Error getting choices: {e}")

    return choices


# ============================================================
# PROCESS AI SOLUTION
# ============================================================

def process_ai_solution(driver, solution):
    """Process the AI solution and perform actions.
    Returns:
        'next' - move to next question
        'summary' - quiz complete, move to next URL
        'retry' - try again with feedback
        'wrong' - answer was wrong, need to retry
    """
    if not solution:
        return 'retry'

    solution_type = solution.get('type', '')

    if solution_type == 'balancing':
        inputs = solution.get('inputs', [])
        if inputs:
            # Check if inputs have valid IDs (not placeholder)
            has_valid_ids = all('id' in inp and inp['id'] and not inp['id'].startswith('input_') for inp in inputs)

            if has_valid_ids:
                for inp in inputs:
                    find_and_fill_input_by_id(driver, inp['id'], inp['value'])
            else:
                values = [inp['value'] for inp in inputs]
                fill_inputs_by_order(driver, values)

            time.sleep(1)

            if not click_check_button(driver):
                click_check_again(driver)
            time.sleep(2)

            if is_try_again_present(driver):
                print("    ⚠️ Wrong answer! Clicking Try again and will retry...")
                # Save the wrong answer for feedback
                wrong_answer = solution
                click_try_again(driver)
                time.sleep(1)
                return 'wrong', wrong_answer

            if is_next_present(driver):
                click_next_question(driver)
                return 'next', None
            elif is_summary_present(driver):
                click_show_summary(driver)
                return 'summary', None
        return 'retry', None

    elif solution_type == 'multiple_choice':
        choices = solution.get('choices', [])
        for choice in choices:
            click_choice_by_letter(driver, choice)
            time.sleep(0.5)

        time.sleep(1)

        if not click_check_button(driver):
            click_check_again(driver)
        time.sleep(2)

        if is_try_again_present(driver):
            print("    ⚠️ Wrong answer! Clicking Try again and will retry...")
            wrong_answer = solution
            click_try_again(driver)
            time.sleep(1)
            return 'wrong', wrong_answer

        if is_next_present(driver):
            click_next_question(driver)
            return 'next', None
        elif is_summary_present(driver):
            click_show_summary(driver)
            return 'summary', None
        return 'retry', None

    elif solution_type == 'done':
        print("    ✅ Question already answered or no action needed")
        if is_next_present(driver):
            click_next_question(driver)
            return 'next', None
        elif is_summary_present(driver):
            click_show_summary(driver)
            return 'summary', None
        return 'next', None

    else:
        print(f"    ⚠️ Unknown solution type: {solution_type}")
        return 'retry', None


# ============================================================
# GET CONTENT PANEL HTML
# ============================================================

def get_content_panel_html(driver):
    """Get the HTML content of the content-panel-wrapper."""
    try:
        content_panel = driver.find_element(By.CSS_SELECTOR, '[data-testid="content-panel-wrapper"]')
        html_content = content_panel.get_attribute('outerHTML')
        return html_content, content_panel
    except Exception as e:
        print(f"    ⚠️ Could not find content-panel-wrapper: {e}")
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            return body.get_attribute('outerHTML'), body
        except:
            return None, None


def detect_question_type(driver):
    """Detect the type of question on the page."""
    inputs = find_all_inputs(driver)
    if inputs:
        return 'balancing'

    choices = get_available_choices(driver)
    if choices:
        return 'multiple_choice'

    return 'unknown'


# ============================================================
# PROCESS A SINGLE URL
# ============================================================

def process_url(driver, username, url, student_name):
    """Process a single quiz URL using API.
    Returns True if quiz was completed (Show summary clicked), False otherwise.
    """
    print(f"\n    🌐 Processing URL: {url}")

    driver.get(url)
    time.sleep(5)

    if is_summary_present(driver):
        print("    ✅ Quiz already completed (Show summary found)")
        click_show_summary(driver)
        log_progress(student_name, username, url, "QUIZ_COMPLETE", "Quiz already completed")
        return True

    click_lets_go(driver)
    time.sleep(2)

    max_questions = 30
    question_count = 0
    max_attempts_per_question = 5

    while question_count < max_questions:
        question_count += 1
        attempt_count = 0
        previous_attempts = []
        print(f"\n    📝 Question {question_count}")

        if is_summary_present(driver):
            print("    ✅ Quiz completed! (Show summary found)")
            click_show_summary(driver)
            log_progress(student_name, username, url, "QUIZ_COMPLETE", "All questions solved")
            return True

        try:
            next_buttons = driver.find_elements(By.CSS_SELECTOR, 'button[data-testid="exercise-next-question"]')
            if next_buttons:
                is_disabled = next_buttons[0].get_attribute('aria-disabled')
                if is_disabled == 'true':
                    print("    ✅ All questions completed! (Next button disabled)")
                    if is_summary_present(driver):
                        click_show_summary(driver)
                    return True
        except:
            pass

        # Loop for attempts on this question
        while attempt_count < max_attempts_per_question:
            attempt_count += 1
            print(f"\n    🎯 Attempt {attempt_count}/{max_attempts_per_question}")

            question_type = detect_question_type(driver)
            print(f"    🔍 Detected question type: {question_type}")

            html_content, content_panel = get_content_panel_html(driver)
            api_success = False
            action_result = 'retry'
            wrong_answer = None

            if html_content and content_panel:
                screenshot_b64 = get_element_screenshot_b64(driver, content_panel)
                if screenshot_b64:
                    input_ids = []
                    if question_type == 'balancing':
                        input_ids, _ = get_input_ids(driver)
                        print(f"    📝 Input IDs found: {input_ids}")

                    # Send to AI with previous attempts feedback if any
                    solution = get_ai_solution(driver, html_content, screenshot_b64, input_ids, previous_attempts)
                    if solution:
                        action_result, wrong_answer = process_ai_solution(driver, solution)
                        if action_result in ['next', 'summary']:
                            print(f"    ✅ API solution applied successfully (action: {action_result})")
                            api_success = True
                            if action_result == 'summary':
                                return True
                            break
                        elif action_result == 'wrong':
                            # Store the wrong answer for feedback
                            if wrong_answer:
                                previous_attempts.append(wrong_answer)
                                print(f"    📝 Recorded wrong attempt #{len(previous_attempts)}")
                            # Click Try again was already handled in process_ai_solution
                            continue

            # If API failed or returned retry
            if not api_success and action_result != 'wrong':
                print(f"    ⚠️ API could not solve, waiting 3 seconds and retrying...")
                time.sleep(3)

                # Try one more time
                if html_content and content_panel:
                    screenshot_b64 = get_element_screenshot_b64(driver, content_panel)
                    if screenshot_b64:
                        input_ids = []
                        if question_type == 'balancing':
                            input_ids, _ = get_input_ids(driver)

                        solution = get_ai_solution(driver, html_content, screenshot_b64, input_ids, previous_attempts)
                        if solution:
                            action_result, wrong_answer = process_ai_solution(driver, solution)
                            if action_result in ['next', 'summary']:
                                print(f"    ✅ API solution applied on retry (action: {action_result})")
                                if action_result == 'summary':
                                    return True
                                break
                            elif action_result == 'wrong':
                                if wrong_answer:
                                    previous_attempts.append(wrong_answer)
                                    print(f"    📝 Recorded wrong attempt #{len(previous_attempts)}")
                                continue

            # If we've exhausted attempts on this question
            if attempt_count >= max_attempts_per_question:
                print(f"    ❌ Max attempts ({max_attempts_per_question}) reached for this question")
                # Try to click Next question to move forward
                if is_next_present(driver):
                    click_next_question(driver)
                break

        time.sleep(2)

    if is_summary_present(driver):
        print("    ✅ Quiz completed (Show summary found at end)")
        click_show_summary(driver)
        log_progress(student_name, username, url, "QUIZ_COMPLETE", "Quiz completed")
        return True

    log_progress(student_name, username, url, "INCOMPLETE", f"Could not complete after {max_questions} questions")
    return False


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

        success = khan_login(driver, username, password)
        if not success:
            save_screenshot(driver, name, username, "login_failed")
            log_progress(name, username, "", "LOGIN_FAILED", "Could not login")
            raise Exception("Login failed")

        save_screenshot(driver, name, username, "login_success")
        log_progress(name, username, "", "LOGIN_SUCCESS", "Successfully logged in")

        accept_cookie_consent(driver)
        handle_intro_modal(driver)

        all_completed = True
        for url in QUIZ_URLS:
            print(f"\n{'=' * 60}")
            print(f"📚 STARTING QUIZ: {url.split('/')[-2]}")
            print(f"{'=' * 60}")

            quiz_completed = process_url(driver, username, url, name)
            if not quiz_completed:
                all_completed = False
                print(f"    ⚠️ Quiz not completed: {url}")
            else:
                print(f"    ✅ Quiz completed: {url}")

            time.sleep(2)

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
    print("KHAN ACADEMY QUIZ AUTO-SOLVER WITH NVIDIA API")
    print("=" * 70)
    print(f"⏰ Student timeout: {STUDENT_TIMEOUT // 60} minutes")
    print(f"🤖 Model: {MODEL}")
    print(f"🔗 URLs to process: {len(QUIZ_URLS)}")

    if not os.getenv("NVIDIA_API_KEY"):
        print()
        print("⚠️ NVIDIA_API_KEY environment variable not set!")
        print("Please set it with: export NVIDIA_API_KEY='your-api-key'")
        print("Or add it to your .env file")

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
        print("=" * 70)


if __name__ == "__main__":
    main()