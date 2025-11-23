# =============================================================
# crawler_templar_scores.py — FINAL VERSION (Multi UID + Stable)
# =============================================================

import time
import re
import json
import os
import datetime
import shutil
import shutil
from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup

from discord_notify_templar_scores import send_discord1


# ======================================================
# GLOBAL VARIABLES
# ======================================================

TRACK_UIDS = []

SCORES = {
    "sync": {},
    "binary": {},
    "gradient": {},
    "final": {},
}

LAST_WINDOW = None
SENT_HISTORY_FILE = "sent_scores_history.json"


# ======================================================
# HISTORY
# ======================================================

def load_history():
    try:
        with open(SENT_HISTORY_FILE, "r") as f:
            return set(json.load(f).keys())
    except:
        return set()

def save_history(h):
    with open(SENT_HISTORY_FILE, "w") as f:
        json.dump({k: True for k in h}, f)


# ======================================================
# EMISSION WINDOW (window % 3 == 1)
# ======================================================

def is_emission_window(w):
    try:
        return int(w) % 3 == 1
    except:
        return False


# ======================================================
# STACKED REPORT
# ======================================================

def build_stacked_report():
    global LAST_WINDOW

    if LAST_WINDOW is None:
        header = "Window: ???"
    else:
        if is_emission_window(LAST_WINDOW):
            header = f"Window: {LAST_WINDOW}*"
        else:
            header = f"Window: {LAST_WINDOW}"

    text = header + "\n"

    text += "\n# SYNC AVG STEPS BEHIND\n"
    for u in TRACK_UIDS:
        text += f"UID {u}: {SCORES['sync'].get(u, '…')}\n"

    text += "\n# BINARY MOVING AVG\n"
    for u in TRACK_UIDS:
        text += f"UID {u}: {SCORES['binary'].get(u, '…')}\n"

    text += "\n# GRADIENT SCORE\n"
    for u in TRACK_UIDS:
        text += f"UID {u}: {SCORES['gradient'].get(u, '…')}\n"

    text += "\n# FINAL SCORE\n"
    for u in TRACK_UIDS:
        text += f"UID {u}: {SCORES['final'].get(u, '…')}\n"

    return text


def start_driver_linux():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,3000")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--disable-extensions")

    # ADD SNAP CHROMIUM HERE
    possible_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium",          # <---- SNAP CHROMIUM
        shutil.which("google-chrome"),
        shutil.which("chromium-browser"),
        shutil.which("chromium"),
    ]

    chrome_path = None
    for p in possible_paths:
        if p and os.path.exists(p):
            chrome_path = p
            break

    if not chrome_path:
        raise FileNotFoundError(
            "❌ Không tìm thấy Chrome/Chromium.\n"
            "Hãy cài chromium: snap install chromium"
        )

    opts.binary_location = chrome_path
    return webdriver.Chrome(options=opts)


# ======================================================
# MAIN CRAWLER — MULTI UID + ANTI-STALENESS
# ======================================================

def run_crawler_templar_scores(uid, time_range, gui_log, should_run, is_paused_flag):

    sent_history = load_history()

    driver = start_driver_linux()
    driver.get(GRAFANA_URL)

    gui_log(f"[TemplarScores] Monitoring UID {uid}")

    SCORES = {
        "sync": {},
        "binary": {},
        "gradient": {},
        "final": {}
    }

    LAST_SENT_WINDOW = None

    while should_run():

        if is_paused_flag():
            time.sleep(0.3)
            continue

        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except:
            pass

        rows = driver.find_elements(By.XPATH, "//tr[contains(@class,'logs-row')]")

        for row in rows:
            try:
                html = row.get_attribute("innerHTML")
            except:
                continue

            soup = BeautifulSoup(html, "html.parser")
            tds = soup.find_all("td")
            if len(tds) < 5:
                continue

            # timestamp
            ts_raw = tds[2].get_text(strip=True)
            try:
                log_time = datetime.datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S.%f")
            except:
                continue

            if datetime.datetime.now() - log_time > datetime.timedelta(minutes=5):
                continue

            # window + eval_uid
            window_value = None
            eval_uid = None
            spans = tds[3].find_all("span")

            for sp in spans:
                title = sp.get("title", "")
                if title.startswith("current_window:"):
                    window_value = title.split(":", 1)[1].strip()
                elif title.startswith("eval_uid:"):
                    eval_uid = title.split(":", 1)[1].strip()

            if not window_value or eval_uid != str(uid):
                continue

            msg = tds[4].get_text(strip=True)

            gui_log(f"[{window_value}] [UID {uid}] {msg}")

            # ----- GHI SCORE -----
            if "Sync average steps behind" in msg:
                SCORES["sync"][window_value] = msg.split(":", 1)[1].strip()

            elif "Binary Moving Average Score" in msg:
                SCORES["binary"][window_value] = msg.split(":", 1)[1].strip()

            elif "Gradient Score" in msg:
                m = re.search(r"Gradient Score[:\s]+(.+)", msg)
                if m:
                    SCORES["gradient"][window_value] = m.group(1).strip()

            elif "Computed Final Score for UID" in msg:
                SCORES["final"][window_value] = msg.split(":")[-1].strip()

            # ----- ĐỦ 4 SCORE → GỬI BẢNG -----
            ready = (
                window_value in SCORES["sync"]
                and window_value in SCORES["binary"]
                and window_value in SCORES["gradient"]
                and window_value in SCORES["final"]
            )

            if ready and LAST_SENT_WINDOW != window_value:

                report = (
                    f"Window: {window_value}\n\n"
                    f"# SYNC AVG STEPS BEHIND\n{SCORES['sync'][window_value]}\n\n"
                    f"# BINARY MOVING AVG\n{SCORES['binary'][window_value]}\n\n"
                    f"# GRADIENT SCORE\n{SCORES['gradient'][window_value]}\n\n"
                    f"# FINAL SCORE\n{SCORES['final'][window_value]}\n"
                )

                uniq_key = f"REPORT|{window_value}|{uid}"

                if uniq_key not in sent_history:
                    send_discord1(f"```\n{report}\n```")
                    sent_history.add(uniq_key)
                    save_history(sent_history)

                LAST_SENT_WINDOW = window_value

                # Clear window cũ
                for k in SCORES:
                    if window_value in SCORES[k]:
                        del SCORES[k][window_value]

        time.sleep(0.7)

    driver.quit()

