#!/usr/bin/env python3
"""
Khan Academy Quiz Auto-Solver with NVIDIA API - Enhanced Prompt

Features:
- Uses improved prompt with step-by-step chemical equation solving
- Includes examples and rules for balancing equations
- Handles multiple choice and single choice questions
- Provides detailed reasoning for answers
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
    """Send question to NVIDIA API with enhanced prompt for better accuracy."""
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
            feedback = "\n\n⚠️ IMPORTANT: The previous answer was WRONG. Here are the incorrect attempts:\n"
            for i, attempt in enumerate(previous_attempts, 1):
                feedback += f"Attempt {i}: {json.dumps(attempt)}\n"
            feedback += "\nPlease provide the CORRECT answer. Double-check your chemistry!\n"

        prompt = f"""
You are an expert chemistry teacher specializing in balancing chemical equations and solving chemistry problems for 10th-grade students.

## YOUR TASK:
Analyze the question carefully and provide the correct answer in JSON format.

## STEP-BY-STEP APPROACH FOR BALANCING EQUATIONS:

### Step 1: Write the unbalanced equation
Identify all reactants and products from the question.

### Step 2: Count atoms on each side
Count the number of atoms of each element on both sides of the equation.

### Step 3: Add coefficients
Add coefficients to balance the atoms. Start with the most complex molecule.

### Step 4: Check your work
Verify that all atoms are balanced.

### Step 5: Simplify
If all coefficients have a common factor, divide by it.

## EXAMPLES:

### Example 1: H₂ + O₂ → H₂O
- Reactants: H=2, O=2
- Products: H=2, O=1
- Need to balance O: Add coefficient 2 to H₂O
- H₂ + O₂ → 2H₂O
- Now: Reactants H=2, O=2; Products H=4, O=2
- Need to balance H: Add coefficient 2 to H₂
- 2H₂ + O₂ → 2H₂O
- Final: H=4, O=2 on both sides ✓
- Coefficients: [2, 1, 2]

### Example 2: CH₄ + O₂ → CO₂ + H₂O
- Reactants: C=1, H=4, O=2
- Products: C=1, H=2, O=3
- Balance H: Add 2 to H₂O → CH₄ + O₂ → CO₂ + 2H₂O
- Now: Products H=4, O=4
- Balance O: Add 2 to O₂ → CH₄ + 2O₂ → CO₂ + 2H₂O
- Final: C=1, H=4, O=4 on both sides ✓
- Coefficients: [1, 2, 1, 2]

### Example 3: NH₄NO₃ → N₂ + O₂ + H₂O
- Reactants: N=2, H=4, O=3
- Products: N=2, O=3, H=2
- Balance H: Add 2 to H₂O → NH₄NO₃ → N₂ + O₂ + 2H₂O
- Now: Products H=4, O=4
- Balance O: Add coefficient 2 to NH₄NO₃
- 2NH₄NO₃ → N₂ + O₂ + 4H₂O
- Now: Reactants N=4, H=8, O=6
- Products: N=2, O=6, H=8
- Balance N: Add 2 to N₂
- 2NH₄NO₃ → 2N₂ + O₂ + 4H₂O
- Final: N=4, H=8, O=6 on both sides ✓
- Coefficients: [2, 2, 1, 4]

### Example 4: HgO → Hg + O₂
- Reactants: Hg=1, O=1
- Products: Hg=1, O=2
- Balance O: Add 2 to HgO
- 2HgO → Hg + O₂
- Now: Reactants Hg=2, O=2
- Balance Hg: Add 2 to Hg
- 2HgO → 2Hg + O₂
- Final: Hg=2, O=2 on both sides ✓
- Coefficients: [2, 2, 1]

## QUESTION TYPE DETECTION:
First, identify the question type:
- **'balancing'**: Questions with input boxes for coefficients (numbers like 1, 2, 3)
- **'single_choice'**: Questions with only ONE correct answer (radio buttons)
- **'multiple_choice'**: Questions with MULTIPLE correct answers (checkboxes)

## IMPORTANT RULES:
1. Coefficients must be the smallest possible whole numbers
2. Never leave a coefficient as 0 - use 1 if needed
3. For balancing equations, use the EXACT input IDs provided
4. For single_choice, provide ONLY ONE answer
5. For multiple_choice, provide ALL correct answers

## RESPONSE FORMAT:

### For Balancing Equations:
{{
    "type": "balancing",
    "inputs": [
        {{"id": "ACTUAL_INPUT_ID_1", "value": 2}},
        {{"id": "ACTUAL_INPUT_ID_2", "value": 1}},
        {{"id": "ACTUAL_INPUT_ID_3", "value": 2}}
    ],
    "reasoning": "Brief explanation of how you balanced the equation"
}}

### For Single Choice:
{{
    "type": "single_choice",
    "choice": "B",
    "reasoning": "Brief explanation of why this is the correct answer"
}}

### For Multiple Choice:
{{
    "type": "multiple_choice",
    "choices": ["A", "C"],
    "reasoning": "Brief explanation of why these are the correct answers"
}}

{input_ids_info}
{feedback}

**Critical**
- Please solve question correctly 
- All questions  are related to chemistry check accordingly.
- take care of Subscript and Superscript Numbers, so you will not get confused with chemical equations.
- Give result only after cross verification most important.
- 

Now, analyze the question from the screenshot and HTML content, and provide your answer in the specified JSON format.
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
            "max_tokens": 8192,
            "reasoning_budget": 4096,
            "stream": STREAM,
            "temperature": 0.1,
            "top_p": 0.99
        }

        response = call_nvidia_api(payload, headers)
        result = response.json()

        response_text = result["choices"][0]["message"]["content"]
        print(f"    🤖 API Response: {response_text[:300]}...")

        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            try:
                result_json = json.loads(json_match.group(0))
                print(f"    📋 Detected type: {result_json.get('type', 'unknown')}")
                if 'reasoning' in result_json:
                    print(f"    💡 Reasoning: {result_json['reasoning'][:100]}...")
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


def click_skip_button(driver):
    """Click Skip button."""
    return click_button_by_text(driver, "Skip")


def click_lets_go(driver):
    """Click Let's go button if present."""
    return click_button_by_text(driver, "Let's go", partial=True) or click_button_by_text(driver, "Let’s go",
                                                                                          partial=True)
def click_next_question(driver):
    """Click Next question button."""
    return click_button_by_text(driver, "Next question", partial=True)


def click_hint(driver):
    """Click Let's go button if present."""
    click_button_by_text(driver, "Hint", partial=True) or click_button_by_text(driver, "Hint",partial=True)
    return click_next_question(driver)


def click_check_button(driver):
    """Click Check or Check again button."""
    return click_button_by_text(driver, "Check") or click_button_by_text(driver, "Check again", partial=True)




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


def click_check_again(driver):
    """Click Check again button specifically."""
    return click_button_by_text(driver, "Check again", partial=True)

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


# ============================================================
# PROCESS AI SOLUTION
# ============================================================

def process_ai_solution(driver, solution):
    """Process the AI solution based on detected type."""
    if not solution:
        return 'retry', None

    solution_type = solution.get('type', '')

    if solution_type == 'balancing':
        inputs = solution.get('inputs', [])
        if inputs:
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

    elif solution_type == 'single_choice':
        choice = solution.get('choice', '')
        if choice:
            click_choice_by_letter(driver, choice)
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


# ============================================================
# PROCESS A SINGLE URL
# ============================================================

def process_url(driver, username, url, student_name):
    """Process a single quiz URL using API."""
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

    max_questions = 500
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

        while attempt_count < max_attempts_per_question:
            attempt_count += 1
            print(f"\n    🎯 Attempt {attempt_count}/{max_attempts_per_question}")
            click_lets_go(driver)
            click_hint(driver)
            html_content, content_panel = get_content_panel_html(driver)
            api_success = False
            action_result = 'retry'
            wrong_answer = None

            if html_content and content_panel:
                screenshot_b64 = get_element_screenshot_b64(driver, content_panel)
                if screenshot_b64:
                    input_ids, _ = get_input_ids(driver)
                    if input_ids:
                        print(f"    📝 Input IDs found: {input_ids}")

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
                            if wrong_answer:
                                previous_attempts.append(wrong_answer)
                                print(f"    📝 Recorded wrong attempt #{len(previous_attempts)}")
                            continue

            if not api_success and action_result != 'wrong':
                print(f"    ⚠️ API could not solve, waiting 3 seconds and retrying...")
                time.sleep(3)

                if html_content and content_panel:
                    screenshot_b64 = get_element_screenshot_b64(driver, content_panel)
                    if screenshot_b64:
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

            if attempt_count >= max_attempts_per_question:
                print(f"    ❌ Max attempts ({max_attempts_per_question}) reached for this question")
                click_skip_button(driver)
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
    options.add_argument("--headless")
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
    students = [i for i in students if i['username'] not in checkpoint['processed_students']]
    print("student need to process", len(students))

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