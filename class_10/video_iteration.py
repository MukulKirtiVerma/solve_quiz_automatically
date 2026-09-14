#!/usr/bin/env python3
"""
Khan Academy Batch Automation — v3 (Extension + Login Fix)
- Enables Chrome Developer mode via profile prefs BEFORE launch
- Validates extension path thoroughly (handles nested folders, .zip)
- Robust Khan Academy login with multiple fallback selectors
- Saves debug HTML on login failure so you can inspect
"""

import csv
import time
import os
import sys
import subprocess
import shutil
import json
import zipfile
import platform
import random
import urllib.request
from pathlib import Path

# ────────────────────────────────
# AUTO-INSTALL DEPENDENCIES
# ────────────────────────────────

def ensure_package(pkg):
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        print(f"[INSTALL] {pkg} not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

ensure_package("selenium")
ensure_package("webdriver-manager")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager


# ────────────────────────────────
# CONFIGURATION — UPDATE THESE
# ────────────────────────────────

CSV_FILE = "unique_student_records.csv"
EXTENSION_PATH = "/Users/mukulkirtiverma/Downloads/ka-autoplay-2x"
BATCH_SIZE = 1
WAIT_MINUTES = 9
LOGIN_URL = "https://en.khanacademy.org/login"

VIDEO_URLS = [
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:types-of-chemical-equations/v/intro-to-chemical-reactions",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:types-of-chemical-equations/v/balancing-chemical-equation-with-substitution",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:combination-and-decomposition-reactions/v/combination-and-decomposition-reaction-chemical-reactions-and-equations-chemistry-khan-academy",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:endothermic-and-exothermic-reactions/v/exothermic-and-endothermic-reactions-chemical-reactions-chemistry-khan-academy",

]

VIDEO_URLS = [
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:types-of-chemical-equations/v/intro-to-chemical-reactions",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:types-of-chemical-equations/v/balancing-chemical-equations-introduction",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:types-of-chemical-equations/v/visually-understanding-balancing-chemical-equations",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:types-of-chemical-equations/v/balancing-more-complex-chemical-equation",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:types-of-chemical-equations/v/balancing-chemical-equation-with-substitution",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:types-of-chemical-equations/v/balancing-another-combustion-reaction",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:combination-and-decomposition-reactions/v/combination-and-decomposition-reaction-chemical-reactions-and-equations-chemistry-khan-academy",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:endothermic-and-exothermic-reactions/v/exothermic-and-endothermic-reactions-chemical-reactions-chemistry-khan-academy",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:endothermic-and-exothermic-reactions/v/exothermic-and-endothermic-common-processes-and-solved-examples-chemistry-khan-academy",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:displacement-and-double-displacement-reactions/v/displacement-reaction-chemical-reactions-and-equations-chemistry-khan-academy",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:displacement-and-double-displacement-reactions/v/double-displacement-reaction-chemical-reactions-and-equations-chemistry-khan-academy",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:redox-reaction/v/oxidation-and-reduction-conventional-definition-chemical-equations-chemistry-khan-academy",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:redox-reaction/v/redox-reaction-chemical-equation-and-reactions-chemistry-khan-academy",
    "https://en.khanacademy.org/science/up-class-10th-science/x5d08d26681869997:chemical-reactions-and-equations/x5d08d26681869997:redox-reaction/v/all-types-of-reactions-solved-examples-chemical-reactions-chemistry-khan-academy",
]


# ────────────────────────────────
# EXTENSION VALIDATION
# ────────────────────────────────

def validate_extension(ext_path):
    """Find the actual extension folder containing manifest.json."""
    ext_path = os.path.expanduser(ext_path)
    ext_path = os.path.abspath(ext_path)

    if not os.path.exists(ext_path):
        print(f"    ❌ Path does not exist: {ext_path}")
        return None

    # Direct folder with manifest.json
    if os.path.isdir(ext_path) and os.path.isfile(os.path.join(ext_path, "manifest.json")):
        print(f"    ✅ Extension found: {ext_path}")
        return ext_path

    # Folder containing subfolder with manifest.json (common with GitHub downloads)
    if os.path.isdir(ext_path):
        for item in os.listdir(ext_path):
            sub = os.path.join(ext_path, item)
            if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "manifest.json")):
                print(f"    ✅ Extension subfolder found: {sub}")
                return sub

    # .zip file — auto-extract
    if ext_path.endswith(".zip") and os.path.isfile(ext_path):
        extract_dir = ext_path.replace(".zip", "_extracted")
        if not os.path.exists(extract_dir):
            print(f"    📦 Extracting zip to {extract_dir}...")
            with zipfile.ZipFile(ext_path, 'r') as z:
                z.extractall(extract_dir)
        for item in os.listdir(extract_dir):
            sub = os.path.join(extract_dir, item)
            if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "manifest.json")):
                print(f"    ✅ Extension extracted: {sub}")
                return sub

    print(f"    ⚠️  No manifest.json found anywhere under {ext_path}")
    print(f"    Contents: {os.listdir(ext_path) if os.path.isdir(ext_path) else 'not a dir'}")
    return None


# ────────────────────────────────
# PROFILE CREATION (Developer Mode)
# ────────────────────────────────

def create_profile_with_dev_mode(profile_dir):
    """Create a Chrome profile with Developer mode pre-enabled."""
    os.makedirs(profile_dir, exist_ok=True)

    # Chrome Preferences file enables Developer mode before launch
    prefs = {
        "extensions": {
            "ui": {
                "developer_mode": True
            }
        },
        "browser": {
            "window_placement": {
                "bottom": 800,
                "left": 10,
                "maximized": False,
                "right": 1280,
                "top": 10,
                "work_area_bottom": 900,
                "work_area_left": 0,
                "work_area_right": 1440,
                "work_area_top": 25
            }
        }
    }

    prefs_path = os.path.join(profile_dir, "Preferences")
    with open(prefs_path, "w", encoding="utf-8") as f:
        json.dump(prefs, f)

    return profile_dir


# ────────────────────────────────
# CHROME FOR TESTING (branded Chrome removed --load-extension in v137+)
# ────────────────────────────────

CHROME_FOR_TESTING_ROOT = os.path.join(os.path.expanduser("~"), ".cache", "chrome-for-testing")


def ensure_chrome_for_testing():
    """Download (once, cached) a Chrome for Testing build and return (binary_path, version).

    Google removed the --load-extension command-line flag from branded Chrome
    builds starting with Chrome 137 as an anti-abuse measure — it's silently
    ignored there. Chrome for Testing is a separate, non-branded binary Google
    ships specifically for automation, where --load-extension still works.
    """
    system = platform.system()
    machine = platform.machine()

    if system == "Darwin":
        platform_key = "mac-arm64" if machine == "arm64" else "mac-x64"
        binary_rel = os.path.join(
            f"chrome-{platform_key}",
            "Google Chrome for Testing.app", "Contents", "MacOS", "Google Chrome for Testing",
        )
    elif system == "Linux":
        platform_key = "linux64"
        binary_rel = os.path.join("chrome-linux64", "chrome")
    elif system == "Windows":
        platform_key = "win64"
        binary_rel = os.path.join("chrome-win64", "chrome.exe")
    else:
        raise RuntimeError(f"Unsupported platform for Chrome for Testing: {system}")

    with urllib.request.urlopen(
        "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
    ) as resp:
        data = json.load(resp)

    stable = data["channels"]["Stable"]
    version = stable["version"]

    version_dir = os.path.join(CHROME_FOR_TESTING_ROOT, version, platform_key)
    binary_path = os.path.join(version_dir, binary_rel)

    if os.path.isfile(binary_path):
        return binary_path, version

    url = next(d["url"] for d in stable["downloads"]["chrome"] if d["platform"] == platform_key)
    os.makedirs(version_dir, exist_ok=True)
    zip_path = os.path.join(version_dir, "chrome.zip")
    print(f"    ⬇️  Downloading Chrome for Testing {version} ({platform_key})... this happens once.")
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(version_dir)
    os.remove(zip_path)

    if system == "Darwin":
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", version_dir], check=False)
        # zipfile.extractall() does not reliably preserve the executable bit on
        # nested helpers inside the .app bundle (e.g. chrome_crashpad_handler),
        # which makes Chrome fail to spawn its crash handler and crash on launch.
        subprocess.run(["chmod", "-R", "+x", version_dir], check=False)
    elif system != "Windows":
        os.chmod(binary_path, 0o755)

    return binary_path, version


# ────────────────────────────────
# DRIVER CREATION
# ────────────────────────────────

def create_driver(profile_dir, ext_path=None):
    """Create Chrome driver with extension and dev mode enabled."""
    chrome_options = Options()

    cft_binary, cft_version = ensure_chrome_for_testing()
    chrome_options.binary_location = cft_binary
    print(f"    🧪 Using Chrome for Testing {cft_version}")

    # Lightweight settings
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,720")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    # CRITICAL: Unique profile per browser instance
    chrome_options.add_argument(f"--user-data-dir={profile_dir}")

    chrome_options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.notifications": 2,
        # Suppress the native "Save password?" doorhanger — it's browser
        # chrome, not page DOM, so no amount of Selenium clicking can
        # dismiss it; has to be turned off before launch instead.
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    })

    # Load extension (absolute path required)
    if ext_path and os.path.exists(ext_path):
        ext_path = os.path.abspath(os.path.expanduser(ext_path))
        if os.path.isdir(ext_path):
            chrome_options.add_argument(f"--load-extension={ext_path}")
            print(f"    🔌 --load-extension={ext_path}")

    # Optional: visible browser (extensions often fail in headless)
    # chrome_options.add_argument("--headless=new")

    try:
        service = Service(ChromeDriverManager(driver_version=cft_version).install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"    [WARN] webdriver-manager failed: {e}")
        driver = webdriver.Chrome(options=chrome_options)

    return driver


# ────────────────────────────────
# EXTENSION VERIFICATION
# ────────────────────────────────

def verify_extension_loaded(driver, expected_name_substring="autoplay"):
    """Check chrome://extensions/ to confirm extension loaded."""
    try:
        original = driver.current_url
        driver.get("chrome://extensions/")
        time.sleep(2)

        # Take screenshot for debugging
        # driver.save_screenshot(f"ext_debug_{time.time()}.png")

        # Try to read extension names via JavaScript (piercing shadow DOM)
        script = """
            const manager = document.querySelector('extensions-manager');
            if (!manager) return {count: 0, names: [], devMode: null};

            const toolbar = manager.shadowRoot.querySelector('extensions-toolbar');
            const devMode = toolbar ? toolbar.shadowRoot.querySelector('#devMode')?.checked : null;

            const items = manager.shadowRoot.querySelectorAll('extensions-item');
            const names = [];
            items.forEach(item => {
                const nameEl = item.shadowRoot.querySelector('#name');
                if (nameEl) names.push(nameEl.textContent);
            });
            return {count: items.length, names: names, devMode: devMode};
        """
        result = driver.execute_script(script)
        print(f"    🔍 Extensions page: {result['count']} extension(s) found")
        print(f"    🔍 Names: {result['names']}")
        print(f"    🔍 Developer mode toggle: {result['devMode']}")

        driver.get(original)

        if result['count'] == 0:
            return False

        # Check if expected extension is in the list
        found = any(expected_name_substring.lower() in n.lower() for n in result['names'])
        return found

    except Exception as e:
        print(f"    ⚠️  Could not verify extension: {e}")
        return False


# ────────────────────────────────
# KHAN ACADEMY LOGIN (Robust)
# ────────────────────────────────

def khan_login(driver, username, password):
    """Log into Khan Academy with multiple fallback strategies."""
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 20)
    time.sleep(3)  # Let React/Single-page-app render fully

    try:
        # ── STRATEGY 1: Find by input type (most robust) ──
        email_field = None
        pw_field = None

        inputs = driver.find_elements(By.TAG_NAME, "input")
        for inp in inputs:
            if not inp.is_displayed():
                continue
            t = inp.get_attribute("type") or ""
            if t in ("email", "text") and not email_field:
                email_field = inp
            elif t == "password" and not pw_field:
                pw_field = inp

        # ── STRATEGY 2: Find by ID / name / placeholder ──
        if not email_field:
            for by, val in [
                (By.ID, "uid-input"),
                (By.ID, "identifierId"),
                (By.NAME, "identifier"),
                (By.NAME, "email"),
                (By.CSS_SELECTOR, 'input[type="email"]'),
                (By.XPATH, '//input[@type="email"]'),
                (By.XPATH, '//input[contains(@placeholder, "mail")]'),
            ]:
                try:
                    el = driver.find_element(by, val)
                    if el.is_displayed():
                        email_field = el
                        break
                except NoSuchElementException:
                    continue

        if not pw_field:
            for by, val in [
                (By.ID, "password-input"),
                (By.NAME, "password"),
                (By.CSS_SELECTOR, 'input[type="password"]'),
                (By.XPATH, '//input[@type="password"]'),
            ]:
                try:
                    el = driver.find_element(by, val)
                    if el.is_displayed():
                        pw_field = el
                        break
                except NoSuchElementException:
                    continue

        if not email_field or not pw_field:
            print("    ❌ Could not find email/password fields")
            _save_debug(driver, username)
            return False

        # Fill credentials
        email_field.clear()
        email_field.send_keys(username)
        time.sleep(0.5)

        pw_field.clear()
        pw_field.send_keys(password)
        time.sleep(0.5)

        # ── Find submit button ──
        submit_btn = None

        # Try button[type="submit"]
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, 'button[type="submit"]')
            for b in btns:
                if b.is_displayed():
                    submit_btn = b
                    break
        except:
            pass

        # Try buttons in the same form as password field
        if not submit_btn:
            try:
                form = pw_field.find_element(By.XPATH, "ancestor::form")
                btns = form.find_elements(By.TAG_NAME, "button")
                for b in btns:
                    if b.is_displayed():
                        submit_btn = b
                        break
            except:
                pass

        # Try by text content
        if not submit_btn:
            btns = driver.find_elements(By.TAG_NAME, "button")
            for b in btns:
                if not b.is_displayed():
                    continue
                text = (b.text or b.get_attribute("aria-label") or "").lower()
                if any(w in text for w in ["log in", "sign in", "login", "submit"]):
                    submit_btn = b
                    break

        if submit_btn:
            submit_btn.click()
            print(f"    🖱️  Clicked submit button")
        else:
            pw_field.send_keys(Keys.RETURN)
            print(f"    ⌨️  Pressed Enter to submit")

        time.sleep(6)

        # Check success
        current = driver.current_url
        if "/login" in current:
            print(f"    ⚠️  Still on login page ({current})")
            _save_debug(driver, username)
            return False

        print(f"    ✅ Logged in as {username}")
        return True

    except Exception as e:
        print(f"    ❌ Login error for {username}: {e}")
        _save_debug(driver, username)
        return False


def _save_debug(driver, username):
    """Save page source and screenshot for debugging."""
    ts = int(time.time())
    html_path = f"debug_login_{username}_{ts}.html"
    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print(f"    📝 Debug HTML saved: {html_path}")
    except Exception as e:
        print(f"    ⚠️  Could not save debug HTML: {e}")


# ────────────────────────────────
# COOKIE CONSENT
# ────────────────────────────────

def accept_cookie_consent(driver, wait_seconds=10):
    """Wait a few seconds after login, then click the OneTrust cookie banner
    ('Accept All Cookies') if/when it appears. Safe to call even if it never shows up."""
    time.sleep(3)
    try:
        btn = WebDriverWait(driver, wait_seconds).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        )
        btn.click()
        print("    🍪 Accepted cookie consent")
        time.sleep(1)
        return True
    except TimeoutException:
        print("    🍪 No cookie consent banner appeared (continuing)")
        return False


# ────────────────────────────────
# VIDEO TABS
# ────────────────────────────────

def open_video_tabs(driver, urls):
    for i, url in enumerate(urls):
        if i == 0:
            driver.get(url)
        else:
            driver.execute_script(f"window.open('{url}', '_blank');")
        time.sleep(1.5)
    print(f"    📑 Opened {len(urls)} video tabs")


def _find_visible_onboarding_checkbox(driver):
    """The generic input[type=checkbox] selector also matches OneTrust's
    hidden cookie-preference-center checkboxes (ids like 'ot-group-id-...',
    'select-all-hosts-groups-handler', etc.), which sit earlier in the DOM.
    EC.element_to_be_clickable() only ever looks at the first DOM match, so a
    bare selector gets stuck checking a checkbox that will never become
    visible and times out before the real onboarding one is ever considered.
    This scans all matches for the first one that's actually visible and
    isn't OneTrust's."""
    for cb in driver.find_elements(By.CSS_SELECTOR, 'input[type="checkbox"]'):
        try:
            elem_id = (cb.get_attribute("id") or "").lower()
            if "onetrust" in elem_id or elem_id.startswith("ot-") or "vendor" in elem_id or "hosts-groups" in elem_id:
                continue
            if cb.is_displayed():
                return cb
        except WebDriverException:
            continue
    return False


def handle_intro_modal(driver, wait_seconds=3, max_dismiss=3):
    """Handle KA's onboarding/promotional overlays before interacting with a
    video page:
      1. Drain any simple dismissible popups (e.g. the 'Reach new Levels!'
         promo tour) via their 'Close modal' (X) button — these can stack,
         so this loops a few times rather than assuming just one.
      2. Separately, complete the first-login onboarding modal if present:
         check its checkbox, then click 'Start learning' once it becomes
         enabled (it starts aria-disabled="true" until checked). Both of
         these have been seen open at once, so #1 no longer short-circuits
         out before #2 gets a chance.
    Both steps use a plain JS .click() rather than a coordinate-based one:
    the checkbox and the promo close button are both covered by a decorative
    sibling element (confirmed via elementFromPoint), so a real click at
    their coordinates lands on that decoration, not the control — but a
    checkbox/button's native activation behavior fires correctly via
    .click() called directly on the element regardless of what's drawn on
    top of it (unlike <video>, which has no such built-in activation and
    needs an actual trusted click for autoplay policy — see click_video_players).
    No-op wherever none of this appears — most tabs won't show any of it."""
    time.sleep(3)

    for _ in range(max_dismiss):
        try:
            close_btn = WebDriverWait(driver, wait_seconds).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'button[aria-label="Close modal"]'))
            )
            driver.execute_script("arguments[0].click();", close_btn)
            print("    ✖️  Closed a popup/tour modal")
            time.sleep(1)
        except TimeoutException:
            break

    try:
        checkbox = WebDriverWait(driver, wait_seconds).until(_find_visible_onboarding_checkbox)
    except TimeoutException:
        return

    driver.execute_script("arguments[0].click();", checkbox)
    print("    ☑️  Checked onboarding checkbox")

    def start_learning_enabled(d):
        for btn in d.find_elements(By.XPATH, '//button[.//span[normalize-space()="Start learning"]]'):
            if btn.get_attribute("aria-disabled") != "true":
                return btn
        return False

    try:
        start_btn = WebDriverWait(driver, wait_seconds).until(start_learning_enabled)
        driver.execute_script("arguments[0].click();", start_btn)
        print("    🚀 Clicked 'Start learning'")
        time.sleep(1)
    except TimeoutException:
        print("    ⚠️  'Start learning' button never became enabled")


def _wander_then_click(driver, target_element, wander_steps=3):
    """Move the mouse through a few random points, then onto target_element,
    and click there. Clicking at those screen coordinates (rather than
    calling target_element.click()) lands on whatever's actually visible on
    top — e.g. KA's play-button overlay SVG sits directly over the <video>
    element's center, which is exactly what a real user would hit, and what
    element.click()'s built-in obscured-element check refuses to click.

    Selenium 4's move_to_element_with_offset() offsets are relative to the
    target element's in-view CENTER (not its top-left corner), so the random
    deltas below are kept within +/- half of the body's actual rendered box
    (via getBoundingClientRect — driver.get_window_size() is the outer window,
    not the viewport, and is too large here) to avoid
    MoveTargetOutOfBoundsException. Each wander step is best-effort; only the
    final click actually has to succeed."""
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        rect = driver.execute_script(
            "const r = arguments[0].getBoundingClientRect(); return {w: r.width, h: r.height};", body
        )
        half_w = max(20, rect["w"] / 2 - 20)
        half_h = max(20, rect["h"] / 2 - 20)
        for _ in range(wander_steps):
            try:
                dx = random.randint(-int(half_w), int(half_w))
                dy = random.randint(-int(half_h), int(half_h))
                ActionChains(driver).move_to_element_with_offset(body, dx, dy).pause(
                    random.uniform(0.1, 0.3)
                ).perform()
            except WebDriverException:
                continue
    except WebDriverException:
        pass

    try:
        ActionChains(driver).move_to_element(target_element).pause(random.uniform(0.1, 0.3)).click().perform()
        return True
    except WebDriverException:
        return False


def _is_video_playing(driver, video):
    return driver.execute_script(
        "const v = arguments[0]; return !!v && !v.paused && !v.ended && v.currentTime > 0;",
        video,
    )


def _locate_ka_video(driver, wait_seconds):
    """Return (video_element, in_iframe). KA embeds videos two different
    ways depending on the video: some are a directly-hosted MP4 in a plain
    <video class="ka-player-iframe"> sitting in the top frame; others are a
    YouTube embed, where that same "ka-player-iframe" class is on an
    <iframe> instead, and the real <video> lives inside it on a different
    origin (youtube-nocookie.com) — invisible to a plain CSS selector and
    reachable only via switch_to.frame(). If in_iframe is True, the driver
    is left switched into that frame; the caller is responsible for calling
    driver.switch_to.default_content() before moving to another tab."""
    try:
        WebDriverWait(driver, wait_seconds).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "video.ka-player-iframe, iframe.ka-player-iframe")
        )
    except TimeoutException:
        return None, False

    el = driver.find_element(By.CSS_SELECTOR, "video.ka-player-iframe, iframe.ka-player-iframe")
    if el.tag_name.lower() == "video":
        return el, False

    driver.switch_to.frame(el)
    try:
        video = WebDriverWait(driver, wait_seconds).until(
            EC.presence_of_element_located((By.TAG_NAME, "video"))
        )
        return video, True
    except TimeoutException:
        driver.switch_to.default_content()
        return None, False


def _ensure_video_playing(driver, video, in_iframe, max_click_attempts=3, play_wait_seconds=15):
    """Try to get `video` playing, clicking/retrying as needed, and wait
    (up to play_wait_seconds) until it actually is. Returns True if playing
    by the end. Assumes the driver is already switched to the right window
    and (for in_iframe) already inside that iframe.

    For the top-frame case: click it (a real WebDriver click, not a
    JS-dispatched one, so it counts as a trusted user gesture and satisfies
    the browser's autoplay-after-interaction policy) — once and check,
    rather than double-clicking blind, since native <video controls> toggles
    play/pause on click and a blind double-click starts it and immediately
    pauses it again.

    For the YouTube-iframe case: KA's embed grants YouTube delegated
    autoplay permission, so it's usually already playing on its own by the
    time we get here — try video.play() first and only fall back to an
    actual click if that's not enough."""
    if not in_iframe:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", video)

    attempts = 0
    while not _is_video_playing(driver, video) and attempts < max_click_attempts:
        if in_iframe:
            driver.execute_script("arguments[0].play().catch(() => {});", video)
            time.sleep(1)
            if not _is_video_playing(driver, video):
                _wander_then_click(driver, video)
        else:
            _wander_then_click(driver, video)
        attempts += 1
        time.sleep(1.5)

    try:
        WebDriverWait(driver, play_wait_seconds).until(lambda d: _is_video_playing(d, video))
        return True
    except TimeoutException:
        return False


def click_video_players(driver, wait_seconds=10, play_wait_seconds=15, max_click_attempts=3):
    """Switch to each open tab, handle any onboarding modal, find the KA
    video player (top-frame <video> or YouTube-embed <iframe>, see
    _locate_ka_video), and get it playing before moving on to the next tab."""
    handles = driver.window_handles
    for i, handle in enumerate(handles, 1):
        driver.switch_to.window(handle)
        handle_intro_modal(driver)

        video, in_iframe = _locate_ka_video(driver, wait_seconds)
        if video is None:
            print(f"    ⚠️  No video player found in tab {i}/{len(handles)}")
            continue

        try:
            playing = _ensure_video_playing(driver, video, in_iframe, max_click_attempts, play_wait_seconds)
            if playing:
                print(f"    ▶️  Video playing in tab {i}/{len(handles)}")
            else:
                print(f"    ⚠️  Video still not playing in tab {i}/{len(handles)}")
        finally:
            if in_iframe:
                driver.switch_to.default_content()


def monitor_and_keep_playing(drivers, duration_minutes, min_seconds_per_tab=2):
    """Once every video's been started, spend duration_minutes cycling
    through every open tab across all given drivers — at least
    min_seconds_per_tab on each — and resume any video found paused/stalled.
    Replaces a flat sleep so a video that stops partway through the wait
    window (an ad, a stall, a missed autoplay) gets nudged back to life
    instead of silently sitting idle for the rest of the batch."""
    end_time = time.time() + duration_minutes * 60
    print(f"    👀 Monitoring playback for {duration_minutes} minute(s)...")
    while time.time() < end_time:
        for driver in drivers:
            handles = driver.window_handles
            for i, handle in enumerate(handles, 1):
                if time.time() >= end_time:
                    return
                driver.switch_to.window(handle)
                time.sleep(min_seconds_per_tab)

                video, in_iframe = _locate_ka_video(driver, wait_seconds=3)
                if video is None:
                    continue
                try:
                    if not _is_video_playing(driver, video):
                        print(f"    ⏸️  Video paused in tab {i}/{len(handles)} — resuming")
                        _ensure_video_playing(driver, video, in_iframe)
                finally:
                    if in_iframe:
                        driver.switch_to.default_content()


# ────────────────────────────────
# BATCH PROCESSING
# ────────────────────────────────

def read_students(csv_path):
    students = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            students.append({
                'name': row.get('Student name', '').strip(),
                'username': row.get('Username', '').strip(),
                'password': row.get('Password', '').strip(),
            })
    return students


def process_batch(batch, batch_num, total_batches, ext_path):
    print(f"\n{'='*60}")
    print(f"🚀 BATCH {batch_num}/{total_batches} — {len(batch)} student(s)")
    print(f"{'='*60}")

    drivers = []

    for idx, student in enumerate(batch, 1):
        name = student['name']
        user = student['username']
        pw = student['password']

        print(f"\n  [{idx}] 🧑 {name} ({user})")

        # Create isolated profile with Developer mode ON
        profile_dir = os.path.join(os.getcwd(), f"chrome_profile_{batch_num}_{idx}")
        create_profile_with_dev_mode(profile_dir)

        try:
            driver = create_driver(profile_dir=profile_dir, ext_path=ext_path)
            drivers.append(driver)

            # Verify extension loaded
            if ext_path:
                ext_ok = verify_extension_loaded(driver)
                if ext_ok:
                    print(f"    ✅ Extension verified loaded")
                else:
                    print(f"    ⚠️  Extension may not have loaded (continuing anyway)")

            # Login
            success = khan_login(driver, user, pw)
            if not success:
                print(f"    ⏭️  Skipping tabs for {user}")
                continue

            # Accept cookie consent banner if it appears
            accept_cookie_consent(driver)

            # Open video tabs
            open_video_tabs(driver, VIDEO_URLS)

            # Click each video player once to start playback
            click_video_players(driver)

        except Exception as e:
            print(f"    ❌ Browser error for {user}: {e}")
            continue

    if drivers:
        monitor_and_keep_playing(drivers, WAIT_MINUTES)

        print(f"\n🛑 Closing batch {batch_num} browsers...")
        for d in drivers:
            try:
                d.quit()
            except:
                pass
        drivers.clear()
        print(f"✅ Batch {batch_num} complete.")
    else:
        print(f"⚠️  No browsers started for batch {batch_num}.")


def cleanup_profiles():
    cwd = os.getcwd()
    for item in os.listdir(cwd):
        if item.startswith("chrome_profile_"):
            path = os.path.join(cwd, item)
            try:
                shutil.rmtree(path)
                print(f"🧹 Cleaned: {item}")
            except:
                pass


def main():
    print("=" * 60)
    print("  Khan Academy Batch Automation v3")
    print("=" * 60)

    if not os.path.exists(CSV_FILE):
        print(f"\n❌ CSV not found: {CSV_FILE}")
        sys.exit(1)

    # Validate extension
    ext_path = validate_extension(EXTENSION_PATH)
    if not ext_path:
        print(f"\n⚠️  Extension not found at: {EXTENSION_PATH}")
        print("   The script will continue WITHOUT the extension.")
        print("   Fix: Update EXTENSION_PATH to the folder containing manifest.json")

    students = read_students(CSV_FILE)
    print(f"\n📋 Loaded {len(students)} student records.")

    if not students:
        print("❌ No students found.")
        sys.exit(1)

    batches = [students[i:i + BATCH_SIZE] for i in range(0, len(students), BATCH_SIZE)]
    total_batches = len(batches)
    print(f"📦 {total_batches} batch(es) of up to {BATCH_SIZE} students.")

    try:
        for batch_num, batch in enumerate(batches, 1):
            process_batch(batch, batch_num, total_batches, ext_path)
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user. Cleaning up...")
    finally:
        cleanup_profiles()
        print("\n🏁 All done!")


if __name__ == "__main__":
    main()