#!/usr/bin/env python3
"""
Khan Academy Quiz Auto-Solver with NVIDIA API - Enhanced Prompt

Features:
- Uses improved prompt with step-by-step chemical equation solving
- Includes examples and rules for balancing equations
- Handles multiple choice and single choice questions
- Provides detailed reasoning for answers
- Skips quizzes Khan Academy already shows as more than 80% complete
- Per-CSV checkpoint (student -> quiz), so several instances can run on
  different CSVs at the same time:
      python khan_academy_batch_automation777777.py data/unique_student_records3.csv
"""

import csv
import time
import os
import sys
import shutil
import json
import hashlib
from urllib.parse import unquote, urlparse
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

DEFAULT_CSV_FILE = "/Users/mukulkirtiverma/PycharmProjects/solve_quiz_automatically/class_10/data/unique_student_records_all.csv"
# Optional first CLI argument overrides the CSV, so one script can run per CSV in parallel.
CSV_FILE = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV_FILE)
BATCH_SIZE = 3

# Skip a quiz when Khan Academy already shows it as more than this % complete.
SKIP_QUIZ_IF_COMPLETION_ABOVE = 80
# Sidebar status span, e.g. <span class="_1vh6t21p">Mastered • 100%</span>.
# Khan Academy's class names are generated, so the link text is used as a fallback.
COMPLETION_STATUS_CLASS = "_1vh6t21p"
LOGIN_URL = "https://en.khanacademy.org/login"

# Quiz URLs
QUIZ_URLS = [
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:physical-properties-of-metals-and-nonmetals/e/identify-the-property-of-a-metal",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:physical-properties-of-metals-and-nonmetals/e/identify-a-metal-with-an-exceptional-property",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:chemical-properties-of-metals/e/metals-reacting-with-air-and-water",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:chemical-properties-of-metals/e/chemical-properties-of-metals",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:chemical-properties-of-metals/e/metal-oxide-and-non-metal-oxide",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:chemical-properties-of-metals/e/acidic-basic-and-amphoteric-oxides",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:reactivity-series/e/reactivity-series",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:reactivity-series/quiz/x5d08d26681869997:metals-and-non-metals-quiz-1",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:metals-reaction-with-non-metals/e/identify-ions-present-in-ionic-compounds",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:metals-reaction-with-non-metals/e/formation-of-ionic-compounds",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:metals-reaction-with-non-metals/quiz/x5d08d26681869997:metals-and-non-metals-quiz-2",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:corrosion/e/corrosion",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:corrosion/e/metals-making-up-an-alloy",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:corrosion/quiz/x5d08d26681869997:metals-and-non-metals-quiz-3",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:occurrence-of-metals/e/roasting-and-calcination",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:occurrence-of-metals/e/reduction-of-metal-oxide",
    "https://www.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:metals-and-non-metals/x5d08d26681869997:occurrence-of-metals/test/x5d08d26681869997:metals-and-non-metals-unit-test"
]

def make_csv_id(csv_path):
    """Stable id for a CSV: '<file stem>_<hash of its absolute path>'."""
    abs_path = os.path.abspath(csv_path)
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", Path(abs_path).stem)
    digest = hashlib.sha1(abs_path.encode("utf-8")).hexdigest()[:8]
    return f"{stem}_{digest}"


def quiz_id_from_url(url):
    """'.../quiz/x5d08d26681869997:acids-bases-and-salts-quiz-1' -> 'acids-bases-and-salts-quiz-1'"""
    path = unquote(urlparse(url).path).rstrip("/")
    return path.rsplit("/", 1)[-1].rsplit(":", 1)[-1].lower()


CSV_ID = make_csv_id(CSV_FILE)

# Everything an instance writes lives under its own CSV folder, so parallel
# instances working on different CSVs never share files.
OUTPUT_ROOT = "ka_quiz_progress"
OUTPUT_DIR = os.path.join(OUTPUT_ROOT, CSV_ID)
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "checkpoint.json")
LEGACY_CHECKPOINT_FILE = os.path.join(OUTPUT_ROOT, "checkpoint.json")  # old shared format
STUDENT_TIMEOUT = 600  # 10 minutes per student

# Error handling, from smallest to largest step:
#   a question that errors (or can't be solved) is skipped -> next question;
#   this many failing questions in a row, or one that can't be skipped -> next quiz;
#   this many quizzes in a row ending in errors, or a dead browser -> next student.
MAX_QUESTION_ERRORS_IN_A_ROW = 2
MAX_QUIZ_ERRORS_IN_A_ROW = 2

# NVIDIA API Configuration
INVOKE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
STREAM = False


# ============================================================
# OUTPUT SETUP
# ============================================================

def setup_output():
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

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

    return str(screenshot_dir), str(progress_file)


SCREENSHOT_DIR, PROGRESS_FILE = setup_output()


# ============================================================
# CHECKPOINT MANAGEMENT
# ============================================================

# Layout of ka_quiz_progress/<CSV_ID>/checkpoint.json:
# {
#   "csv_id": "...", "csv_file": "/abs/path.csv", "updated_at": "...",
#   "students": {
#     "<username>": {
#       "status": "processed" | "failed", "error": "", "updated_at": "...",
#       "quizzes": {
#         "<quiz_id>": {"status": "complete" | "skipped" | "incomplete" | "error",
#                       "completion_at_start": 85, "url": "...", "updated_at": "..."}
#       }
#     }
#   }
# }

STUDENT_PROCESSED = "processed"
STUDENT_FAILED = "failed"

QUIZ_COMPLETE = "complete"
QUIZ_SKIPPED = "skipped"  # already above SKIP_QUIZ_IF_COMPLETION_ABOVE on Khan Academy
QUIZ_INCOMPLETE = "incomplete"
QUIZ_ERROR = "error"  # abandoned because of errors; retried on the next run
QUIZ_DONE_STATUSES = (QUIZ_COMPLETE, QUIZ_SKIPPED)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_checkpoint():
    return {"csv_id": CSV_ID, "csv_file": CSV_FILE, "students": {}}


def save_checkpoint(checkpoint):
    checkpoint["updated_at"] = _now()
    tmp_file = f"{CHECKPOINT_FILE}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2)
    # Atomic swap: a crash/timeout mid-write can never leave a truncated checkpoint.
    os.replace(tmp_file, CHECKPOINT_FILE)


def load_checkpoint():
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            checkpoint = json.load(f)
    except FileNotFoundError:
        return _new_checkpoint()
    except json.JSONDecodeError:
        backup = f"{CHECKPOINT_FILE}.corrupt_{datetime.now():%Y%m%d_%H%M%S}"
        shutil.copy(CHECKPOINT_FILE, backup)
        print(f"⚠️ Checkpoint unreadable, starting a fresh one (old file kept at {backup})")
        checkpoint = _new_checkpoint()
        save_checkpoint(checkpoint)
        return checkpoint

    checkpoint.setdefault("students", {})
    return checkpoint


def _student_entry(checkpoint, username):
    return checkpoint["students"].setdefault(username, {"status": "", "quizzes": {}})


def usernames_with_status(checkpoint, status):
    return [
        username
        for username, student in checkpoint["students"].items()
        if student.get("status") == status
    ]


def is_student_processed(username):
    student = load_checkpoint()["students"].get(username, {})
    return student.get("status") == STUDENT_PROCESSED


def mark_student_processed(username):
    checkpoint = load_checkpoint()
    _student_entry(checkpoint, username).update(
        status=STUDENT_PROCESSED, error="", updated_at=_now()
    )
    save_checkpoint(checkpoint)


def mark_student_failed(username, error_message=""):
    checkpoint = load_checkpoint()
    _student_entry(checkpoint, username).update(
        status=STUDENT_FAILED, error=error_message, updated_at=_now()
    )
    save_checkpoint(checkpoint)


def get_quiz_checkpoint(username, quiz_id):
    student = load_checkpoint()["students"].get(username, {})
    return student.get("quizzes", {}).get(quiz_id)


def mark_quiz(username, url, status, completion_at_start):
    checkpoint = load_checkpoint()
    student = _student_entry(checkpoint, username)
    student.setdefault("quizzes", {})[quiz_id_from_url(url)] = {
        "status": status,
        "completion_at_start": completion_at_start,
        "url": url,
        "updated_at": _now(),
    }
    save_checkpoint(checkpoint)


def import_legacy_checkpoint(students):
    """
    Create this CSV's checkpoint, carrying over students the old shared
    ka_quiz_progress/checkpoint.json already marked as processed.
    Only usernames that are in this CSV are imported.
    """
    try:
        with open(LEGACY_CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            legacy_processed = set(json.load(f).get("processed_students", []))
    except (FileNotFoundError, json.JSONDecodeError):
        legacy_processed = set()

    checkpoint = _new_checkpoint()
    for student in students:
        if student["username"] in legacy_processed:
            _student_entry(checkpoint, student["username"]).update(
                status=STUDENT_PROCESSED,
                error="",
                updated_at=_now(),
                note="imported from legacy checkpoint.json",
            )
    save_checkpoint(checkpoint)

    imported = len(checkpoint["students"])
    if imported:
        print(f"📥 Imported {imported} processed student(s) from {LEGACY_CHECKPOINT_FILE}")


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


def get_ai_solution(driver, question_html, screenshot_b64, input_ids, previous_attempts=None, dropdowns=None):
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
            input_ids_info += (
                "If the answer is typed into these input boxes, answer with type 'balancing' and put each "
                "value under its input id - even when it is not a balancing question "
                "(e.g. 'how many water molecules...'). Do NOT use single_choice for input boxes.\n"
            )

        # Dropdown options are not in the question HTML (they only render when a
        # dropdown is opened), so list them here.
        dropdown_info = ""
        if dropdowns:
            dropdown_info = (
                "\nThis question has DROPDOWNS, so answer with type 'dropdown' "
                "(even if the options look like letters A, B, C...).\n"
                "Dropdown 1 is the first dropdown in the question, Dropdown 2 the second, and so on. Options:\n"
            )
            for dropdown in dropdowns:
                options = ", ".join(json.dumps(option, ensure_ascii=False) for option in dropdown["options"])
                dropdown_info += f"Dropdown {dropdown['index']}: {options}\n"
            dropdown_info += "Pick exactly one option for every dropdown, copying its text exactly as listed above.\n"

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
- **'balancing'**: Questions with input boxes to type into: coefficients, or any other number/value (e.g. how many water molecules)
- **'single_choice'**: Questions with only ONE correct answer (radio buttons)
- **'multiple_choice'**: Questions with MULTIPLE correct answers (checkboxes)
- **'dropdown'**: Questions where answers are picked from dropdown menus (e.g. "Choose the solution")

## IMPORTANT RULES:
1. Coefficients must be the smallest possible whole numbers
2. Never leave a coefficient as 0 - use 1 if needed
3. For balancing equations, use the EXACT input IDs provided
4. For single_choice, provide ONLY ONE answer
5. For multiple_choice, provide ALL correct answers
6. For dropdown, give one selection per dropdown, with the option text copied exactly

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

### For Dropdowns:
{{
    "type": "dropdown",
    "selections": [
        {{"dropdown": 1, "option": "EXACT_OPTION_TEXT"}},
        {{"dropdown": 2, "option": "EXACT_OPTION_TEXT"}}
    ],
    "reasoning": "Brief explanation of each selection"
}}

{input_ids_info}
{dropdown_info}
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
    """Click Skip, then confirm 'Yes, skip' in the 'Are you sure?' modal it opens."""
    if not click_button_by_text(driver, "Skip"):
        return False

    def yes_skip_visible(d):
        button = find_button_by_text(d, "Yes, skip")
        return button is not None and button.is_displayed()

    try:
        WebDriverWait(driver, 3, ignored_exceptions=(StaleElementReferenceException,)).until(yes_skip_visible)
    except TimeoutException:
        return True  # no confirmation modal appeared
    return click_button_by_text(driver, "Yes, skip")


def click_lets_go(driver):
    """Click Let's go button if present."""
    return click_button_by_text(driver, "Let's go", partial=True) or click_button_by_text(driver, "Let’s go",
                                                                                          partial=True)
def dismiss_bonus_modal(driver, wait_seconds=0):
    """If the "You've earned a bonus question!" modal is open (waiting up to
    wait_seconds for it), click its 'Keep going' button."""
    def bonus_modal_button(d):
        for dialog in d.find_elements(By.CSS_SELECTOR, '[role="dialog"]'):
            if not dialog.is_displayed() or "bonus question" not in (dialog.text or "").lower():
                continue
            buttons = [b for b in dialog.find_elements(By.TAG_NAME, "button") if b.is_displayed()]
            keep_going = [b for b in buttons if (b.text or "").strip().lower() == "keep going"]
            close = [b for b in buttons if b.get_attribute("aria-label") == "Close modal"]
            if keep_going or close:
                return (keep_going or close)[0]
        return False

    try:
        button = WebDriverWait(
            driver, wait_seconds, poll_frequency=0.25, ignored_exceptions=(StaleElementReferenceException,)
        ).until(bonus_modal_button)
    except TimeoutException:
        return False

    try:
        driver.execute_script("arguments[0].click();", button)
        print("    🎁 Bonus question modal — clicked 'Keep going'")
        time.sleep(1)
        return True
    except Exception as e:
        print(f"    ⚠️ Could not close bonus question modal: {e}")
        return False


def click_next_question(driver):
    """Click Next question — or Bonus question, which Khan Academy shows instead
    at the end when a question was missed; it opens one more question that is
    then solved like any other. The "You've earned a bonus question!" modal
    that comes with it is closed with 'Keep going'."""
    dismiss_bonus_modal(driver)
    if click_button_by_text(driver, "Next question", partial=True):
        return True
    if click_button_by_text(driver, "Bonus question", partial=True):
        dismiss_bonus_modal(driver, wait_seconds=3)
        return True
    return False


def click_hint(driver):
    """Click Let's go button if present."""
    click_button_by_text(driver, "Hint", partial=True) or click_button_by_text(driver, "Hint",partial=True)
    return click_next_question(driver)


def cancel_skip_modal_if_open(driver):
    """If the 'Are you sure? Skipped questions will count as incorrect' modal is
    open, click its Cancel button so the question can still be checked."""
    try:
        cancel_buttons = [
            b for b in driver.find_elements(By.ID, "cancel-skip-question") if b.is_displayed()
        ]
        if not cancel_buttons:
            return False

        driver.execute_script("arguments[0].click();", cancel_buttons[0])
        print("    ✅ Skip modal was open — clicked 'Cancel'")
        try:
            WebDriverWait(driver, 3, ignored_exceptions=(StaleElementReferenceException,)).until(
                lambda d: not any(b.is_displayed() for b in d.find_elements(By.ID, "cancel-skip-question"))
            )
        except TimeoutException:
            print("    ⚠️ Skip modal still visible after clicking 'Cancel'")
        return True
    except Exception as e:
        print(f"    ⚠️ Could not close skip modal: {e}")
        return False


def click_check_button(driver):
    """Click Check or Check again button."""
    cancel_skip_modal_if_open(driver)
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
    cancel_skip_modal_if_open(driver)
    return click_button_by_text(driver, "Check again", partial=True)

def is_next_present(driver):
    """Check if Next question (or Bonus question) button is present."""
    return button_exists(driver, "Next question") or button_exists(driver, "Bonus question")


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
# DROPDOWN QUESTIONS
# ============================================================
# Khan Academy dropdowns are <button role="combobox" aria-haspopup="listbox">.
# Their options (<button role="option">) are only rendered while the dropdown is
# open, in a popup outside the question HTML (found via aria-controls), so the
# options have to be read by opening each dropdown and passed to the LLM.

DROPDOWN_SELECTOR = 'button[role="combobox"][aria-haspopup="listbox"]'

_DROPDOWN_OPTIONS_JS = """
const listbox = document.getElementById(arguments[0]);
if (!listbox) return [];
return [...listbox.querySelectorAll('[role="option"]')].map(o => ({
    text: (o.innerText || o.textContent || "").replace(/\\s+/g, " ").trim(),
    disabled: o.getAttribute("aria-disabled") === "true",
}));
"""


def _normalize_option_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def find_dropdowns(driver):
    """Visible dropdowns of the current question, in page order."""
    try:
        panels = driver.find_elements(By.CSS_SELECTOR, '[data-testid="content-panel-wrapper"]')
        root = panels[0] if panels else driver
        return [d for d in root.find_elements(By.CSS_SELECTOR, DROPDOWN_SELECTOR) if d.is_displayed()]
    except Exception as e:
        print(f"    ⚠️ Error finding dropdowns: {e}")
        return []


def _open_dropdown(driver, dropdown, wait_seconds=3):
    """Open a dropdown and return the id of its options popup (or None)."""
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dropdown)
    time.sleep(0.3)
    if dropdown.get_attribute("aria-expanded") != "true":
        driver.execute_script("arguments[0].click();", dropdown)
    listbox_id = dropdown.get_attribute("aria-controls")
    try:
        WebDriverWait(driver, wait_seconds).until(
            lambda d: d.execute_script(_DROPDOWN_OPTIONS_JS, listbox_id)
        )
        return listbox_id
    except TimeoutException:
        return None


def _close_dropdown(driver, dropdown):
    if dropdown.get_attribute("aria-expanded") != "true":
        return
    try:
        driver.switch_to.active_element.send_keys(Keys.ESCAPE)
        time.sleep(0.3)
    except Exception:
        pass
    if dropdown.get_attribute("aria-expanded") == "true":
        driver.execute_script("arguments[0].click();", dropdown)  # toggles it closed
        time.sleep(0.3)


def get_dropdowns(driver):
    """
    Read every dropdown's options by opening it and closing it again.
    Returns [{"index": 1, "options": ["A", "B", ...], "selected": "..."}, ...]
    (the disabled placeholder such as 'Choose the solution' is left out).
    """
    dropdowns = []
    for index, dropdown in enumerate(find_dropdowns(driver), start=1):
        try:
            listbox_id = _open_dropdown(driver, dropdown)
            options = driver.execute_script(_DROPDOWN_OPTIONS_JS, listbox_id) if listbox_id else []
            _close_dropdown(driver, dropdown)
            dropdowns.append({
                "index": index,
                "options": [o["text"] for o in options if not o["disabled"] and o["text"]],
                "selected": re.sub(r"\s+", " ", dropdown.text or "").strip(),
            })
        except Exception as e:
            print(f"    ⚠️ Could not read dropdown {index}: {e}")
    return dropdowns


def select_dropdown_option(driver, dropdown_number, option_text):
    """Open dropdown #dropdown_number (1-based) and pick the option matching option_text."""
    dropdowns = find_dropdowns(driver)
    try:
        dropdown = dropdowns[int(dropdown_number) - 1]
    except (ValueError, TypeError, IndexError):
        print(f"    ⚠️ Dropdown {dropdown_number} not found ({len(dropdowns)} on page)")
        return False

    wanted = _normalize_option_text(option_text)
    try:
        listbox_id = _open_dropdown(driver, dropdown)
        if not listbox_id:
            print(f"    ⚠️ Dropdown {dropdown_number} did not open")
            return False

        options = [
            o for o in driver.find_element(By.ID, listbox_id).find_elements(By.CSS_SELECTOR, '[role="option"]')
            if o.get_attribute("aria-disabled") != "true"
        ]
        texts = [_normalize_option_text(o.text) for o in options]

        # Exact text match first, then a unique partial match.
        match = next((o for o, t in zip(options, texts) if t == wanted), None)
        if match is None:
            partial = [o for o, t in zip(options, texts) if wanted and (wanted in t or t in wanted)]
            match = partial[0] if len(partial) == 1 else None

        if match is None:
            print(f"    ⚠️ Option '{option_text}' not in dropdown {dropdown_number}: {[o.text for o in options]}")
            _close_dropdown(driver, dropdown)
            return False

        driver.execute_script("arguments[0].click();", match)
        time.sleep(0.5)
        _close_dropdown(driver, dropdown)
        print(f"    ✅ Dropdown {dropdown_number}: selected '{option_text}'")
        return True
    except Exception as e:
        print(f"    ⚠️ Could not select '{option_text}' in dropdown {dropdown_number}: {e}")
        return False


# ============================================================
# PROCESS AI SOLUTION
# ============================================================

def process_ai_solution(driver, solution):
    """Process the AI solution based on detected type."""
    if not solution:
        return 'retry', None

    solution_type = solution.get('type', '')

    # The LLM sometimes labels a typed answer as a choice ("choice": "2"). If the
    # page has input boxes but no answer-choice buttons, type the value(s) instead.
    if solution_type in ('single_choice', 'multiple_choice'):
        values = [solution.get('choice')] if solution_type == 'single_choice' else solution.get('choices', [])
        values = [v for v in values if v not in (None, "")]
        has_choice_buttons = driver.find_elements(By.CSS_SELECTOR, 'button[aria-label^="(Choice "]')
        if values and find_all_inputs(driver) and not has_choice_buttons:
            print(f"    ↪️ Got '{solution_type}' but this question has input boxes — typing {values} instead")
            solution = {**solution, 'type': 'balancing',
                        'inputs': [{'id': f'input_{i}', 'value': v} for i, v in enumerate(values)]}
            solution_type = 'balancing'

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

    elif solution_type == 'dropdown':
        selections = solution.get('selections', [])
        for selection in selections:
            select_dropdown_option(driver, selection.get('dropdown'), selection.get('option'))
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


# ============================================================
# QUIZ COMPLETION DETECTION
# ============================================================

# Finds every link on the page whose URL slug equals the current quiz's slug and
# returns its status text. The sidebar shows the same status span for *every*
# item in the lesson, so matching on the slug is what ties a % to this quiz.
_QUIZ_LINK_STATUS_JS = """
const [quizId, statusClass] = arguments;
const slugOf = (href) => {
    try {
        const path = decodeURIComponent(new URL(href, location.href).pathname).replace(/\\/+$/, "");
        return path.split("/").pop().split(":").pop().toLowerCase();
    } catch (e) {
        return "";
    }
};
// Join text nodes with a separator: textContent would glue "Quiz 2" + "85%" into "Quiz 285%".
const textOf = (el) => {
    const parts = [];
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
        const t = walker.currentNode.nodeValue.trim();
        if (t) parts.push(t);
    }
    return parts.join(" | ");
};
const links = [];
for (const a of document.querySelectorAll("a[href]")) {
    if (slugOf(a.getAttribute("href")) !== quizId) continue;
    const status = a.querySelector("span." + statusClass);
    const ariaCurrent = a.getAttribute("aria-current");
    links.push({
        current: !!ariaCurrent && ariaCurrent !== "false",
        status: status ? textOf(status) : "",
        text: textOf(a),
    });
}
return links;
"""


def _parse_completion(text):
    """'Mastered • 100%' -> 100, 'Mastered' -> 100, '' -> None."""
    text = text or ""
    for match in re.finditer(r"(?<![\d.])(\d{1,3})\s*%", text):
        percent = int(match.group(1))
        if percent <= 100:
            return percent
    if "mastered" in text.lower():
        return 100
    return None


def get_quiz_completion(driver, url, wait_seconds=3):
    """
    Completion % that the course sidebar shows for the quiz at `url`.
    Returns 0 when it cannot be detected.
    """
    quiz_id = quiz_id_from_url(url)
    try:
        links = WebDriverWait(driver, wait_seconds).until(
            lambda d: d.execute_script(_QUIZ_LINK_STATUS_JS, quiz_id, COMPLETION_STATUS_CLASS)
        )
    except WebDriverException:
        print(f"    ℹ️ No sidebar link found for '{quiz_id}', treating completion as 0%")
        return 0

    # The highlighted (aria-current) sidebar entry is the most reliable one.
    links.sort(key=lambda link: not link.get("current"))
    for link in links:
        for text in (link.get("status"), link.get("text")):
            completion = _parse_completion(text)
            if completion is not None:
                return completion

    print(f"    ℹ️ No completion status shown for '{quiz_id}', treating completion as 0%")
    return 0


# ============================================================
# ERROR RECOVERY
# ============================================================

def browser_alive(driver):
    """False once the browser/driver has died (every call would fail)."""
    try:
        driver.current_url
        return True
    except Exception:
        return False


def _question_signature(driver):
    """Fingerprint of the question area, to tell whether the page moved on."""
    try:
        panels = driver.find_elements(By.CSS_SELECTOR, '[data-testid="content-panel-wrapper"]')
        text = panels[0].text if panels else driver.find_element(By.TAG_NAME, "body").text
        return hashlib.md5(text.encode("utf-8")).hexdigest()
    except Exception:
        return None


def move_past_question(driver):
    """
    Get off the current question: Skip it (confirming 'Yes, skip'), and if that
    changes nothing, try Next question / Bonus question.
    Returns True if the page actually moved on.
    """
    def moved(before):
        after = _question_signature(driver)
        return is_summary_present(driver) or (after is not None and after != before)

    before = _question_signature(driver)
    try:
        dismiss_bonus_modal(driver)
        click_skip_button(driver)
        time.sleep(1)
        if moved(before):
            return True
        click_next_question(driver)
        time.sleep(1)
        return moved(before)
    except Exception as e:
        print(f"    ⚠️ Could not move past question: {e}")
        return False


# ============================================================
# PROCESS A SINGLE URL
# ============================================================

def process_url(driver, username, url, student_name):
    """
    Process a single quiz URL using API.
    Returns (status, completion_at_start) where status is QUIZ_COMPLETE,
    QUIZ_SKIPPED, QUIZ_INCOMPLETE, or QUIZ_ERROR when it had to give up on the
    quiz because questions kept failing (the caller then moves to the next quiz).
    """
    print(f"\n    🌐 Processing URL: {url}")

    driver.get(url)
    time.sleep(5)

    completion = get_quiz_completion(driver, url)
    print(f"    📊 Current completion: {completion}%")
    if completion > SKIP_QUIZ_IF_COMPLETION_ABOVE:
        print(f"    ⏭️ Skipping quiz, already above {SKIP_QUIZ_IF_COMPLETION_ABOVE}%")
        log_progress(student_name, username, url, "QUIZ_SKIPPED", f"Already {completion}% complete")
        return QUIZ_SKIPPED, completion

    if is_summary_present(driver):
        print("    ✅ Quiz already completed (Show summary found)")
        click_show_summary(driver)
        log_progress(student_name, username, url, "QUIZ_COMPLETE", "Quiz already completed")
        return QUIZ_COMPLETE, completion

    click_lets_go(driver)
    time.sleep(2)

    max_questions = 500
    question_count = 0
    max_attempts_per_question = 3  # not solved after this many attempts -> skip the question
    question_errors_in_a_row = 0

    while question_count < max_questions:
        question_count += 1
        attempt_count = 0
        previous_attempts = []
        print(f"\n    📝 Question {question_count}")
        try:
            if is_summary_present(driver):
                print("    ✅ Quiz completed! (Show summary found)")
                click_show_summary(driver)
                log_progress(student_name, username, url, "QUIZ_COMPLETE", "All questions solved")
                return QUIZ_COMPLETE, completion

            try:
                next_buttons = driver.find_elements(By.CSS_SELECTOR, 'button[data-testid="exercise-next-question"]')
                if next_buttons:
                    is_disabled = next_buttons[0].get_attribute('aria-disabled')
                    if is_disabled == 'true':
                        print("    ✅ All questions completed! (Next button disabled)")
                        if is_summary_present(driver):
                            click_show_summary(driver)
                        return QUIZ_COMPLETE, completion
            except:
                pass

            solved = False
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
                        dropdowns = get_dropdowns(driver)
                        if dropdowns:
                            print(f"    🔽 Dropdowns found: {dropdowns}")

                        solution = get_ai_solution(driver, html_content, screenshot_b64, input_ids, previous_attempts, dropdowns)
                        if solution:
                            action_result, wrong_answer = process_ai_solution(driver, solution)
                            if action_result in ['next', 'summary']:
                                print(f"    ✅ API solution applied successfully (action: {action_result})")
                                api_success = True
                                if action_result == 'summary':
                                    return QUIZ_COMPLETE, completion
                                solved = True
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
                            dropdowns = get_dropdowns(driver)

                            solution = get_ai_solution(driver, html_content, screenshot_b64, input_ids, previous_attempts, dropdowns)
                            if solution:
                                action_result, wrong_answer = process_ai_solution(driver, solution)
                                if action_result in ['next', 'summary']:
                                    print(f"    ✅ API solution applied on retry (action: {action_result})")
                                    if action_result == 'summary':
                                        return QUIZ_COMPLETE, completion
                                    solved = True
                                    break
                                elif action_result == 'wrong':
                                    if wrong_answer:
                                        previous_attempts.append(wrong_answer)
                                        print(f"    📝 Recorded wrong attempt #{len(previous_attempts)}")
                                    continue

            # Checked after the loop (not inside it) so a wrong answer on the last
            # attempt — which `continue`s straight out of the loop — is skipped too.
            if not solved:
                print(f"    ❌ Not solved in {max_attempts_per_question} attempts — skipping this question")
                if not move_past_question(driver):
                    raise RuntimeError("could not skip this question")
        except Exception as e:  # (StudentTimeout is not an Exception, so the time limit passes through)
            question_errors_in_a_row += 1
            print(f"    ❌ Error on question {question_count}: {e}")
            if question_errors_in_a_row >= MAX_QUESTION_ERRORS_IN_A_ROW or not move_past_question(driver):
                print("    ⏭️ Cannot get past this question — moving on to the next quiz")
                log_progress(student_name, username, url, "QUIZ_ERROR", f"Question {question_count}: {e}")
                return QUIZ_ERROR, completion
            print("    ⏭️ Skipped the failing question — moving on to the next question")
        else:
            question_errors_in_a_row = 0

        time.sleep(2)

    if is_summary_present(driver):
        print("    ✅ Quiz completed (Show summary found at end)")
        click_show_summary(driver)
        log_progress(student_name, username, url, "QUIZ_COMPLETE", "Quiz completed")
        return QUIZ_COMPLETE, completion

    log_progress(student_name, username, url, "INCOMPLETE", f"Could not complete after {max_questions} questions")
    return QUIZ_INCOMPLETE, completion


# ============================================================
# CREATE DRIVER
# ============================================================

def create_driver(profile_dir):
    options = Options()

    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--no-sandbox")
    options.add_argument("--headless")
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

    # First page load for this student's fresh browser: accept the cookie banner.
    accept_cookie_consent(driver, wait_seconds=3)

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

COOKIE_ACCEPT_BUTTONS = (
    (By.ID, "truste-consent-button"),        # TrustArc banner: "Accept All Cookies"
    (By.ID, "onetrust-accept-btn-handler"),  # OneTrust banner
)


def accept_cookie_consent(driver, wait_seconds=5):
    """Click the cookie banner's accept button (TrustArc or OneTrust) if one shows up."""
    def visible_accept_button(d):
        for by, selector in COOKIE_ACCEPT_BUTTONS:
            for button in d.find_elements(by, selector):
                if button.is_displayed() and button.is_enabled():
                    return button
        return False

    try:
        button = WebDriverWait(
            driver, wait_seconds, ignored_exceptions=(StaleElementReferenceException,)
        ).until(visible_accept_button)
        try:
            button.click()
        except WebDriverException:
            driver.execute_script("arguments[0].click();", button)
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

class StudentTimeout(BaseException):
    """Raised when a student exceeds STUDENT_TIMEOUT. It derives from
    BaseException, not Exception, so the many `except Exception` blocks in the
    helpers can't swallow it (a plain TimeoutError was being swallowed by e.g.
    click_button_by_text, so the time limit silently never applied)."""


def timeout_handler(signum, frame):
    # Re-arm: if a bare `except:` somewhere still swallows this, it fires again shortly.
    signal.alarm(5)
    raise StudentTimeout(f"Student processing timed out after {STUDENT_TIMEOUT // 60} minutes")


def with_timeout(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(STUDENT_TIMEOUT)
        try:
            return func(*args, **kwargs)
        except StudentTimeout:
            print(f"    ⏰ Student processing exceeded {STUDENT_TIMEOUT // 60} minutes")
            raise
        finally:
            signal.alarm(0)

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

    # Unique per CSV + student: parallel instances must never share (or delete)
    # each other's Chrome profile directory.
    profile_dir = os.path.join(
        os.getcwd(),
        f"chrome_profile_{CSV_ID}_{safe_filename(username)}"
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
        quiz_errors_in_a_row = 0
        for url in QUIZ_URLS:
            quiz_id = quiz_id_from_url(url)
            print(f"\n{'=' * 60}")
            print(f"📚 STARTING QUIZ: {quiz_id}")
            print(f"{'=' * 60}")

            previous = get_quiz_checkpoint(username, quiz_id)
            if previous and previous.get("status") in QUIZ_DONE_STATUSES:
                print(f"    ⏭️ Already {previous['status']} in checkpoint, skipping: {quiz_id}")
                continue

            try:
                quiz_status, completion_at_start = process_url(driver, username, url, name)
            except Exception as e:  # (StudentTimeout is not an Exception, so the time limit passes through)
                print(f"    ❌ Error in quiz {quiz_id}: {e}")
                log_progress(name, username, url, "QUIZ_ERROR", str(e))
                quiz_status, completion_at_start = QUIZ_ERROR, None
            mark_quiz(username, url, quiz_status, completion_at_start)

            if quiz_status == QUIZ_ERROR:
                all_completed = False
                quiz_errors_in_a_row += 1
                if not browser_alive(driver):
                    raise RuntimeError("Browser stopped responding — moving on to the next student")
                if quiz_errors_in_a_row >= MAX_QUIZ_ERRORS_IN_A_ROW:
                    raise RuntimeError(
                        f"{quiz_errors_in_a_row} quizzes in a row ended with errors — moving on to the next student"
                    )
                print(f"    ⏭️ Quiz ended with errors — moving on to the next quiz")
            else:
                quiz_errors_in_a_row = 0
                if quiz_status == QUIZ_INCOMPLETE:
                    all_completed = False
                    print(f"    ⚠️ Quiz not completed: {url}")
                else:
                    print(f"    ✅ Quiz {quiz_status}: {url}")

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
        signal.alarm(0)  # stop the (re-arming) time limit so it can't interrupt the cleanup
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
    except StudentTimeout:
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
    print(f"📋 Loaded {len(students)} student(s) from CSV: {CSV_FILE}")
    print(f"🆔 CSV id: {CSV_ID}")
    print(f"📊 Checkpoint file: {CHECKPOINT_FILE}")

    if not os.path.exists(CHECKPOINT_FILE):
        import_legacy_checkpoint(students)

    checkpoint = load_checkpoint()
    processed = set(usernames_with_status(checkpoint, STUDENT_PROCESSED))
    failed_count = len(usernames_with_status(checkpoint, STUDENT_FAILED))
    print(f"📊 Checkpoint: {len(processed)} processed, {failed_count} failed")
    students = [i for i in students if i['username'] not in processed]
    print("student need to process================================", len(students))

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
            total_processed = len(usernames_with_status(checkpoint, STUDENT_PROCESSED))
            total_failed = len(usernames_with_status(checkpoint, STUDENT_FAILED))

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