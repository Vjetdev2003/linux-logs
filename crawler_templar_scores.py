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

# ============================================================
# CONFIG
# ============================================================

GRAFANA_URL = (
    "https://grafana.tplr.ai/d/service_logs_validator_1/"
    "service-logs-only-for-validator-uid3d-1?orgId=1&refresh=5s"
)

TEMPLAR_KEYS = [
    "Sync average steps behind",
    "Binary Moving Average Score",
    "Gradient Score",
    "Computed Final Score"
]

HISTORY_FILE = "templar_score_history.json"

# Thời gian chờ trước khi chốt 1 window
WINDOW_DELAY_SECONDS = 60 * 14  # 10 phút

FIRST_EMISSION = 60301

def is_emission(window):
    try:
        win = int(window)
        return (win - FIRST_EMISSION) % 3 == 0
    except:
        return False
# ============================================================
# HISTORY
# ============================================================

def load_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            return set(json.load(f).keys())
    except:
        return set()

def save_history(h):
    with open(HISTORY_FILE, "w") as f:
        json.dump({k: True for k in h}, f)


# ============================================================
# SELENIUM DRIVER
# ============================================================

def start_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,3000")
    opts.add_argument("--disable-blink-features=AutomationControlled")

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

    raise FileNotFoundError("❌ Chrome/Chromium not found.")


# ============================================================
# REPORT BUILDER
# ============================================================

def build_and_send(window, data, uids, delayed_for_window, delayed_window, sent_history):
    uniq = f"Templar scores|{window}"
    if uniq in sent_history:
        return
    emission = "Emission" if is_emission(window) else ""
    report = f"Window: {window} {emission}\n\n"

    # --- MAIN WINDOW SECTION ---
    for uid in uids:
        entry = data.get(uid, {})
        sync = entry.get("sync", "Missing")
        binary = entry.get("binary", "Missing")
        gradient = entry.get("gradient", "Missing")
        computed = entry.get("computed", "Missing")
        report += (
            f"### UID {uid}\n"
            f"Sync average score behind: {sync}\n"
            f"Binary moving average score: {binary}\n"
            f"Gradient score: {gradient}\n"
            f"Computed final score: {computed}\n\n"
        )

    # --- DELAYED SECTION ---
    if delayed_for_window:
        report += f"Delayed logs for Window {delayed_window}\n\n"

        for uid, entry in delayed_for_window.items():
            sync = entry.get("sync", "Missing")
            binary = entry.get("binary", "Missing")
            gradient = entry.get("gradient", "Missing")
            computed = entry.get("computed", "Missing")
            report += (
                f"### UID {uid}\n"
                f"Sync average score behind: {sync}\n"
                f"Binary moving average score: {binary}\n"
                f"Gradient score: {gradient}\n"
                f"Computed final score: {computed}\n\n"
            )

    send_discord1(f"```\n{report}\n```")
    sent_history.add(uniq)
    save_history(sent_history)


# ============================================================
# MAIN CRAWLER
# ============================================================

def run_crawler_templar_scores(uids, minutes, gui_log, should_run, is_paused):

    uids = [str(u) for u in uids]
    gui_log(f"[TemplarScores] Monitoring: {uids}")

    sent_history = load_history()
    driver = start_driver()
    driver.get(GRAFANA_URL)

    time_range = datetime.timedelta(minutes=minutes)

    TEMPLAR_ALL = {}        # window → uid → data
    WINDOW_TIME = {}        # window → first seen timestamp
    DELAYED = {}            # window → uid → data

    current_window = None

    while should_run():

        if is_paused():
            time.sleep(0.3)
            continue

        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except:
            pass

        rows = driver.find_elements(By.XPATH, "//tr[contains(@class,'logs-row')]")
        now = time.time()

        # ====================================================
        # CHECK WINDOW READY TO SEND (timeout)
        # ====================================================
        finished = []
        for win, first_time in WINDOW_TIME.items():
            if now - first_time >= WINDOW_DELAY_SECONDS:
                finished.append(win)

        for win in finished:
            build_and_send(
                window=win,
                data=TEMPLAR_ALL.get(win, {}),
                uids=uids,
                delayed_for_window=DELAYED.get(win, {}),
                delayed_window=win,
                sent_history=sent_history
            )

            if win in TEMPLAR_ALL:
                del TEMPLAR_ALL[win]
            if win in DELAYED:
                del DELAYED[win]
            if win in WINDOW_TIME:
                del WINDOW_TIME[win]

        # ====================================================
        # PARSE NEW LOG LINES
        # ====================================================
        for row in rows:
            try:
                html = row.get_attribute("innerHTML")
            except:
                continue

            soup = BeautifulSoup(html, "html.parser")
            tds = soup.find_all("td")
            if len(tds) < 5:
                continue

            ts_raw = tds[2].get_text(strip=True)
            try:
                ts = datetime.datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S.%f")
            except:
                continue

            if datetime.datetime.now() - ts > time_range:
                continue

            window = None
            eval_uid = None

            for sp in tds[3].find_all("span"):
                title = sp.get("title", "")
                if "current_window:" in title:
                    window = title.split(":", 1)[1].strip()
                elif "eval_uid:" in title:
                    eval_uid = title.split(":", 1)[1].strip()

            if eval_uid not in uids or not window:
                continue

            msg = tds[4].get_text(strip=True)
            gui_log(f"[{window}] [UID {eval_uid}] {msg}")

            # ghi thời điểm xuất hiện window
            if window not in WINDOW_TIME:
                WINDOW_TIME[window] = now

            # --- detect window switching ---
            if current_window is None:
                current_window = window
                prev_window = None

            elif window != current_window:
                prev_window = current_window

            else:
                prev_window = None

            # --- logs arriving late for previous window ---
            if prev_window is not None and window == prev_window:
                if prev_window not in DELAYED:
                    DELAYED[prev_window] = {}

                if eval_uid not in DELAYED[prev_window]:
                    DELAYED[prev_window][eval_uid] = {}

                if "Sync average" in msg:
                    DELAYED[prev_window][eval_uid]["sync"] = msg.split(":", 1)[1].strip()

                elif "Binary Moving" in msg:
                    DELAYED[prev_window][eval_uid]["binary"] = msg.split(":", 1)[1].strip()

                elif "Gradient Score" in msg:
                    m = re.search(r"Gradient Score[:\s]+(.+)", msg)
                    if m:
                        DELAYED[prev_window][eval_uid]["gradient"] = m.group(1).strip()
                elif "Computed final score" in msg:
                    DELAYED[prev_window][eval_uid]["computed"] = msg.split(":", 1)[1].strip()

            # Sau khi xử lý delayed → Bây giờ mới cập nhật current_window
            if prev_window is not None:
                current_window = window

            # --- normal logs (current window) ---
            if any(k in msg for k in TEMPLAR_KEYS):

                bucket = TEMPLAR_ALL.setdefault(window, {})
                uidbucket = bucket.setdefault(eval_uid, {})

                if "Sync average" in msg:
                    uidbucket["sync"] = msg.split(":", 1)[1].strip()

                elif "Binary Moving" in msg:
                    uidbucket["binary"] = msg.split(":", 1)[1].strip()

                elif "Gradient Score" in msg:
                    m = re.search(r"Gradient Score[:\s]+(.+)", msg)
                    if m:
                        uidbucket["gradient"] = m.group(1).strip()
                elif "Computed Final Score" in msg:
                    uidbucket["computed"] = msg.split(":", 1)[1].strip()

        time.sleep(0.5)

    driver.quit()