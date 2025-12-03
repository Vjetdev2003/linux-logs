# crawler.py
import time
import json
import os
import re
import datetime
from prettytable import PrettyTable

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

from discord_notify import send_discord, send_discord_weight

FIRST_EMISSION = 60301


def is_emission(window):
    try:
        win = int(window)
        return (win - FIRST_EMISSION) % 3 == 0
    except:
        return False


# ============================
# FIXED UID LIST
# ============================
FIXED_UIDS = [
    10, 44, 51, 204, 178, 95,
    145, 60, 228, 243, 231,
    70, 186, 193, 89, 6, 189, 164
]


GRAFANA_URL = (
    "https://grafana.tplr.ai/d/service_logs_validator_1/"
    "service-logs-only-for-validator-uid3d-1?orgId=1&refresh=5s"
)

SENT_HISTORY_FILE = "sent_history.json"
LAST_WEIGHT_FILE = "last_sent_window.json"


# ==========================================================
# UTILS
# ==========================================================
def load_last_sent_window():
    if not os.path.exists(LAST_WEIGHT_FILE):
        return None
    try:
        with open(LAST_WEIGHT_FILE, "r") as f:
            return json.load(f).get("last_window", None)
    except:
        return None


def save_last_sent_window(w):
    with open(LAST_WEIGHT_FILE, "w") as f:
        json.dump({"last_window": w}, f)


def load_sent_history():
    if not os.path.exists(SENT_HISTORY_FILE):
        return set()
    try:
        with open(SENT_HISTORY_FILE, "r") as f:
            return set(json.load(f).keys())
    except:
        return set()


def save_sent_history(h):
    with open(SENT_HISTORY_FILE, "w") as f:
        json.dump({k: True for k in h}, f)


def print_table(data):
    table = PrettyTable()
    table.field_names = ["UID", "Window", "Weight"]
    for uid, window, w in data:
        table.add_row([uid, window, f"{w:.4f}"])
    return table.get_string()


def start_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-features=WebExtensions")
    opts.add_argument("--window-size=1920,4000")

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts
    )


def wait_for_dom(driver, gui_log):
    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located(
                (By.XPATH, "//td[contains(@class, 'logs-row__localtime')]")
            )
        )
        return True
    except:
        gui_log(">>> DOM STILL NOT READY AFTER WAIT")
        return False


def get_rows(driver):
    try:
        return driver.find_elements(
            By.XPATH, "//tr[td[contains(@class,'logs-row__localtime')]]"
        )
    except:
        return []


# ==========================================================
# PARSE WEIGHT TABLE
# ==========================================================
def parse_weight_table(msg: str):
    result = {}
    for ln in msg.splitlines():

        if not ln.strip().startswith("│"):
            continue

        parts = [p.strip() for p in ln.strip("│").split("│")]
        if len(parts) < 8:
            continue

        uid_s = parts[0]
        win_s = parts[1]
        weight_s = parts[7]

        if not uid_s.isdigit():
            continue

        uid = int(uid_s)

        try:
            win = int(win_s)
        except:
            continue

        try:
            w = float(weight_s.split()[0])
        except:
            continue

        result[uid] = (win, w)
    return result


# ==========================================================
# CHECKPOINT DETECTOR
# ==========================================================
def is_checkpoint(msg: str):
    msg_low = msg.lower()

    return (
        "[dcp][upload]" in msg
        or "_LATEST.json" in msg_low
        or "Creating checkpoint at global_step" in msg_low
    )


# ==========================================================
# MAIN CRAWLER
# ==========================================================
def run_crawler(minutes, gui_log, should_run, paused_flag):

    gui_log(">>> Starting Chrome…")
    driver = start_driver()

    gui_log(">>> Loading Grafana…")
    driver.get(GRAFANA_URL)
    time.sleep(4)
    wait_for_dom(driver, gui_log)

    gui_log(">>> Monitoring started.")

    sent_history = load_sent_history()
    last_sent_window = load_last_sent_window()
    seen = {}
    time_range = datetime.timedelta(minutes=minutes)

    # ==========================================================
    # MAIN LOOP
    # ==========================================================
    while should_run():

        if paused_flag():
            time.sleep(0.5)
            continue

        now = datetime.datetime.now()

        try:
            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
        except:
            pass

        rows = get_rows(driver)
        if not rows:
            time.sleep(1)
            continue

        logs = []

        # ----------------------------------------------------------
        # Extract logs
        # ----------------------------------------------------------
        for row in rows:
            try:
                html = row.get_attribute("innerHTML")
            except:
                continue

            soup = BeautifulSoup(html, "html.parser")
            tds = soup.find_all("td")
            if len(tds) < 5:
                continue

            ts = tds[2].get_text(strip=True)

            try:
                log_time = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
            except:
                try:
                    log_time = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                except:
                    continue

            if now - log_time > time_range:
                continue

            msg = tds[4].get_text("\n", strip=False)
            uniq = ts + "|" + msg

            logs.append((log_time, uniq, msg))

        logs.sort(key=lambda x: x[0])

        # ==========================================================
        # PROCESS LOGS
        # ==========================================================
        for (log_time, uniq, msg) in logs:

            if uniq not in seen:
                gui_log(msg)
                seen[uniq] = now

            # ======================================================
            # CHECKPOINT (send once)
            # ======================================================
            if is_checkpoint(msg):

                key = f"CHECKPOINT|{uniq}"

                if key not in sent_history:
                    send_discord(f"[CHECKPOINT] {msg}")
                    sent_history.add(key)
                    save_sent_history(sent_history)

                continue

            # ======================================================
            # MEGA SLASH
            # ======================================================
            if "MEGA SLASH" in msg and "MEGA" in msg:

                m = re.search(r"UID\s+(\d+)", msg)
                mega_uid = int(m.group(1)) if m else None

                if mega_uid in FIXED_UIDS:
                    key = f"MEGA|{uniq}"

                    if key not in sent_history:
                        send_discord(f"[MEGA] {msg}")
                        sent_history.add(key)
                        save_sent_history(sent_history)

                continue

            # ======================================================
            # ERROR FILTER
            # ======================================================
            error_patterns = [
                "negative eval frequency",
                "avg_steps_behind=",
                "No gradient gathered",
                "Consecutive misses",
                "Skipped score of UID",
                "Skipped UID",
                "Skipped reducing score of UID",
                "No gradient received from",
                "negative evaluations",
                "consecutive negative evaluations",
            ]

            if any(p in msg for p in error_patterns):

                m = re.search(r"UID\s+(\d+)", msg)
                eval_uid = int(m.group(1)) if m else None

                if eval_uid in FIXED_UIDS:
                    if uniq not in sent_history:
                        send_discord(f"[UID {eval_uid}] {msg}")
                        sent_history.add(uniq)
                        save_sent_history(sent_history)

            # ======================================================
            # WEIGHT BLOCK – send once per new window
            # ======================================================
            if "Updated scores for evaluated UIDs" in msg:

                parsed = parse_weight_table(msg)
                if not parsed:
                    continue

                raw_window = max(w for (w, _) in parsed.values())
                real_window = raw_window + 1
                emission = "Emission" if is_emission(real_window) else ""

                if last_sent_window == real_window:
                    continue

                rows_out = []
                total = 0.0

                for u in FIXED_UIDS:
                    if u not in parsed:
                        continue

                    _, wt = parsed[u]

                    if wt == 0:
                        continue

                    rows_out.append((u, raw_window, wt))
                    total += wt

                if not rows_out:
                    continue

                table_str = print_table(rows_out)
                send_discord_weight(
                    f"```\nWindow = {real_window} {emission}\n"
                    f"{table_str}\nTotal = {total:.4f}\n```"
                )

                last_sent_window = real_window
                save_last_sent_window(real_window)

        # cleanup seen logs
        old = [k for k, t in seen.items() if now - t > time_range]
        for k in old:
            del seen[k]

        time.sleep(5)

    # shutdown
    try:
        driver.quit()
    except:
        pass
