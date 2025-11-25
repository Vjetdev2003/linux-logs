### file crawler_templar_scores.py

import time
import re
import json
import os
import datetime
import shutil
from selenium import webdriver
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from discord_notify_templar_scores import send_discord1

GRAFANA_URL = (
    "https://grafana.tplr.ai/d/service_logs_validator_1/"
    "service-logs-only-for-validator-uid3d-1?orgId=1&refresh=5s"
)

TEMPLAR_KEYS = [
    "Sync average steps behind",
    "Binary Moving Average Score",
    "Gradient Score",
]

HISTORY_FILE = "templar_score_history.json"
EMISSION_OFFSET = 1
def is_emission(window):
    try:
        w = int(window) - EMISSION_OFFSET
        return w % 3 == 1
    except:
        return False


def load_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            return set(json.load(f).keys())
    except:
        return set()

def save_history(h):
    with open(HISTORY_FILE, "w") as f:
        json.dump({k: True for k in h}, f)

def start_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,3000")
    opts.add_argument("--disable-blink-features=AutomationControlled")

    # LINUX
    linux_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium",
        shutil.which("chromium"),
        shutil.which("google-chrome"),
    ]
    for p in linux_paths:
        if p and os.path.exists(p):
            opts.binary_location = p
            return webdriver.Chrome(options=opts)

    raise FileNotFoundError("❌ Linux: Chrome/Chromium không tìm thấy.")


def run_crawler_templar_scores(uids, minutes, gui_log, should_run, is_paused):

    uids = [str(u) for u in uids]       # convert to string list
    gui_log(f"[TemplarScores] UIDs: {uids}")

    sent_history = load_history()
    driver = start_driver()
    driver.get(GRAFANA_URL)

    time_range = datetime.timedelta(minutes=minutes)

    TEMPLAR_ALL = {}
    current_window = None
    while should_run():

        if is_paused():
            time.sleep(0.3)
            continue

        # scroll down to load logs
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
                ts = datetime.datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S.%f")
            except:
                continue

            if datetime.datetime.now() - ts > time_range:
                continue

            # extract labels
            window = None
            eval_uid = None
            for sp in tds[3].find_all("span"):
                title = sp.get("title", "")
                if title.startswith("current_window:"):
                    window = title.split(":", 1)[1].strip()
                elif title.startswith("eval_uid:"):
                    eval_uid = title.split(":", 1)[1].strip()

            if eval_uid not in uids or not window:
                continue

            msg = tds[4].get_text(strip=True)
            gui_log(f"[{window}] [UID {eval_uid}] {msg}")

            if current_window is None:
                current_window = window

            if window != current_window:
                old = current_window

                if old in TEMPLAR_ALL:

                    uniq = f"Templar scores|{old}"
                    if uniq not in sent_history:

                        emission = "Emission" if is_emission(old) else ""
                        report = f"Window: {old} {emission}\n\n"

                        # build per UID
                        for u in uids:
                            entry = TEMPLAR_ALL[old].get(u, {})
                            sync = entry.get("sync", "Missing")
                            binary = entry.get("binary", "Missing")
                            gradient = entry.get("gradient", "Missing")

                            report += (
                                f"### UID {u}\n"
                                f"Sync average score behind: {sync}\n"
                                f"Binary Moving Average Score: {binary}\n"
                                f"Gradient scores: {gradient}\n\n"
                            )

                        send_discord1(f"```\n{report}\n```")
                        gui_log(f"===== SENT SUMMARY {old} =====")

                        sent_history.add(uniq)
                        save_history(sent_history)

                # Xóa window cũ
                if old in TEMPLAR_ALL:
                    del TEMPLAR_ALL[old]

                current_window = window

            # ---------------------------------------------------
            # LƯU SCORE CỦA WINDOW HIỆN TẠI
            # ---------------------------------------------------
            if any(k in msg for k in TEMPLAR_KEYS):

                # init window
                if window not in TEMPLAR_ALL:
                    TEMPLAR_ALL[window] = {}
                if eval_uid not in TEMPLAR_ALL[window]:
                    TEMPLAR_ALL[window][eval_uid] = {}

                # parse values
                if "Sync average" in msg:
                    TEMPLAR_ALL[window][eval_uid]["sync"] = msg.split(":", 1)[1].strip()

                elif "Binary Moving" in msg:
                    TEMPLAR_ALL[window][eval_uid]["binary"] = msg.split(":", 1)[1].strip()

                elif "Gradient Score" in msg:
                    m = re.search(r"Gradient Score[:\s]+(.+)", msg)
                    if m:
                        TEMPLAR_ALL[window][eval_uid]["gradient"] = m.group(1).strip()

        time.sleep(0.5)

    driver.quit()
