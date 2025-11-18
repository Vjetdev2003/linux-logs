# crawler.py
import time
import json
import os
import re
import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from discord_notify import send_discord

# ==========================
# UID cần theo dõi
# ==========================
TARGET_UIDS = {"10", "60", "70", "186", "193", "228", "44", "178", "243"}

GRAFANA_URL_TEMPLATE = (
    "https://grafana.tplr.ai/d/service_logs_validator_1/"
    "service-logs-only-for-validator-uid3d-1?orgId=1&refresh=5s&var-Search={UID}"
)

SENT_HISTORY_FILE = "sent_history.json"


# --------------------------------------------------------
# History
# --------------------------------------------------------
def load_sent_history():
    if not os.path.exists(SENT_HISTORY_FILE):
        return set()
    try:
        with open(SENT_HISTORY_FILE, "r") as f:
            return set(json.load(f).keys())
    except:
        return set()


def save_sent_history(sent_set):
    with open(SENT_HISTORY_FILE, "w") as f:
        json.dump({k: True for k in sent_set}, f)


# --------------------------------------------------------
# Driver
# --------------------------------------------------------
def start_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,4000")

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts
    )


# --------------------------------------------------------
# DOM
# --------------------------------------------------------
def wait_for_dom(driver, gui_log):
    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located(
                (By.XPATH, "//td[contains(@class,'logs-row__localtime')]")
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


# --------------------------------------------------------
# UID extract helpers
# --------------------------------------------------------
def match_uid_from_msg(msg):
    m = re.search(r"UID\s+(\d+)", msg)
    return m.group(1) if m else None


def match_slashing_uid(msg):
    m = re.search(r"Slashing\s+(\d+)", msg)
    return m.group(1) if m else None


# --------------------------------------------------------
# MAIN CRAWLER
# --------------------------------------------------------
def run_crawler(uid, time_range_minutes, gui_log, should_run, paused_flag):

    url = GRAFANA_URL_TEMPLATE.replace("{UID}", str(uid))
    driver = None

    seen = {}
    sent_to_discord = load_sent_history()
    soft_refresh_count = 0

    gui_log(f"Loaded {len(sent_to_discord)} sent logs history.")

    time_range = datetime.timedelta(minutes=time_range_minutes)
    last_log_time_seen = time.time()
    last_full_refresh = time.time()

    try:
        gui_log(">>> Starting Chrome headless...")
        driver = start_driver()

        gui_log(f">>> Opening Grafana for UID {uid}...")
        driver.get(url)
        time.sleep(4)
        wait_for_dom(driver, gui_log)

        gui_log(">>> Realtime monitoring started.")

        # ===============================================================
        # LOOP
        # ===============================================================
        while should_run():

            if paused_flag():
                time.sleep(0.25)
                continue

            now = datetime.datetime.now()
            logs = []

            try:
                driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);"
                )
            except:
                pass

            # HARD refresh every 60s
            if time.time() - last_full_refresh >= 60:
                gui_log(">>> HARD refresh (every 1 min)")
                try:
                    driver.get(url)
                    time.sleep(5)
                    wait_for_dom(driver, gui_log)
                except:
                    driver.quit()
                    driver = start_driver()
                    driver.get(url)
                    time.sleep(6)
                    wait_for_dom(driver, gui_log)

                last_full_refresh = time.time()
                soft_refresh_count = 0
                continue

            # SOFT refresh after 120s
            if time.time() - last_log_time_seen > 120:
                gui_log(">>> Soft refresh...")
                soft_refresh_count += 1

                try:
                    driver.refresh()
                    time.sleep(3)
                except:
                    driver.quit()
                    driver = start_driver()
                    driver.get(url)
                    time.sleep(6)

                wait_for_dom(driver, gui_log)

                if soft_refresh_count >= 5:
                    gui_log(">>> HARD reload due to many soft refreshes")
                    driver.get(url)
                    time.sleep(6)
                    wait_for_dom(driver, gui_log)
                    soft_refresh_count = 0

                continue

            rows = get_rows(driver)
            if len(rows) == 0:
                time.sleep(1)
                continue

            # ===========================================================
            # PARSE ROWS
            # ===========================================================
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
                msg = tds[4].get_text(strip=True)

                try:
                    log_time = datetime.datetime.strptime(
                        ts, "%Y-%m-%d %H:%M:%S.%f"
                    )
                except:
                    try:
                        log_time = datetime.datetime.strptime(
                            ts, "%Y-%m-%d %H:%M:%S"
                        )
                    except:
                        continue

                if now - log_time > time_range:
                    continue

                # extract eval_uid
                label_td = tds[3]
                labels = {}

                for sp in label_td.find_all("span"):
                    title = sp.get("title", "")
                    if ":" in title:
                        key, val = title.split(":", 1)
                        labels[key.strip()] = val.strip()

                eval_uid = labels.get("eval_uid") or match_uid_from_msg(msg)
                slashing_uid = match_slashing_uid(msg)

                uniq = ts + "|" + msg
                logs.append((log_time, uniq, ts, eval_uid, slashing_uid, msg))

            logs.sort(key=lambda x: x[0])

            # ===========================================================
            # PROCESS LOGS
            # ===========================================================
            for log_time, uniq, ts, eval_uid, slashing_uid, msg in logs:

                # SHOW LOG
                if uniq not in seen:
                    last_log_time_seen = time.time()
                    soft_refresh_count = 0

                    if eval_uid:
                        gui_log(f"[UID {eval_uid}] {msg}")
                    else:
                        gui_log(f"{msg}")

                    seen[uniq] = log_time

                # =========================================
                # FILTERING RULES
                # =========================================
                send_flag = False

                uid_candidates = {eval_uid, slashing_uid}
                eval_target_ok = any(
                    uid in TARGET_UIDS for uid in uid_candidates if uid
                )

                # lỗi chung
                error_patterns = [
                    "negative eval frequency",
                    "Binary Moving Average Score",
                    "No gradient gathered",
                    "Consecutive misses",
                    "Skipped score of UID",
                    "gradient not found",
                    "Skipped reducing score",
                    "No gradient received",
                    "Slashing moving average score",
                    "MEGA SLASH",
                    "negative evaluations",
                    "consecutive negative evaluations",
                ]

                if any(p in msg for p in error_patterns):
                    send_flag = True

                # sync steps behind
                if "Sync average steps behind" in msg and "interquartile mean" in msg:
                    if eval_target_ok:
                        send_flag = True

                # avg_steps_behind
                if ("avg_steps_behind=" in msg and "> max=" in msg):
                    if eval_target_ok:
                        send_flag = True

                # DCP upload (luôn gửi)
                if "[DCP][upload]" in msg:
                    send_flag = True

                # skip checkpoint
                if "Creating checkpoint at global_step" in msg:
                    send_flag = False

                # enforce target UID filter (except DCP upload)
                if "[DCP][upload]" not in msg:
                    if not eval_target_ok:
                        send_flag = False

                # =========================================
                # SEND TO DISCORD (FINAL)
                # =========================================
                if send_flag and uniq not in sent_to_discord:

                    prefix = f"[Eval UID {eval_uid}] " if eval_uid else ""

                    send_discord(f"{prefix}{msg}")

                    sent_to_discord.add(uniq)
                    save_sent_history(sent_to_discord)

            # CLEANUP
            old = []
            for k, t in seen.items():
                if now - t > time_range:
                    old.append(k)
            for k in old:
                del seen[k]

            time.sleep(0.25)

    finally:
        gui_log(">>> HEADLESS CLOSED.")
        try:
            driver.quit()
        except:
            pass
        try:
            driver.service.stop()
        except:
            pass
