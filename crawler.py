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


GRAFANA_URL_TEMPLATE = (
    "https://grafana.tplr.ai/d/service_logs_validator_1/"
    "service-logs-only-for-validator-uid3d-1?orgId=1&refresh=5s&var-Search={UID}"
)

SENT_HISTORY_FILE = "sent_history.json"


# --------------------------------------------------------
# LOAD / SAVE HISTORY
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
# START DRIVER
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
# WAIT FOR DOM READY
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


# --------------------------------------------------------
# GET ROWS STABLE
# --------------------------------------------------------
def get_rows(driver):
    try:
        return driver.find_elements(
            By.XPATH, "//tr[td[contains(@class,'logs-row__localtime')]]"
        )
    except:
        return []


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

            # Pause
            if paused_flag():
                time.sleep(0.25)
                continue

            now = datetime.datetime.now()
            logs = []

            # Scroll
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except:
                pass

            # ===========================================================
            # SOFT REFRESH LOGIC
            # ===========================================================
            if time.time() - last_log_time_seen > 120:
                gui_log(">>> Soft refresh...")
                soft_refresh_count += 1

                try:
                    driver.refresh()
                    time.sleep(3)
                    wait_for_dom(driver, gui_log)
                except Exception as e:
                    gui_log(f">>> Soft refresh crashed ChromeDriver: {e}")
                    driver.quit()
                    driver = start_driver()
                    driver.get(url)
                    time.sleep(6)
                    wait_for_dom(driver, gui_log)
                    continue

                # HARD RELOAD
                if soft_refresh_count >= 5:
                    gui_log(">>> HARD RELOAD triggered (5 soft refreshes)")
                    try:
                        driver.get(url)
                        time.sleep(6)
                        wait_for_dom(driver, gui_log)
                        soft_refresh_count = 0
                    except:
                        gui_log(">>> HARD reload crashed — restarting Chrome...")
                        driver.quit()
                        driver = start_driver()
                        driver.get(url)
                        time.sleep(6)
                        wait_for_dom(driver, gui_log)
                    continue

            # ===========================================================
            # GET ROWS (retry)
            # ===========================================================
            rows = get_rows(driver)

            if len(rows) == 0:
                time.sleep(2)
                rows = get_rows(driver)

            if len(rows) == 0:
                gui_log(">>> DOM not ready (0 rows), skipping...")
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

                # Parse timestamp
                try:
                    log_time = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
                except:
                    try:
                        log_time = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    except:
                        continue

                if now - log_time > time_range:
                    continue

                # Extract labels
                label_td = tds[3]
                labels = {}

                for sp in label_td.find_all("span"):
                    title = sp.get("title", "")
                    if ":" in title:
                        key, val = title.split(":", 1)
                        labels[key.strip()] = val.strip()

                eval_uid = labels.get("eval_uid")

                # fallback search
                if not eval_uid:
                    m = re.search(r"UID\s+(\d+)", msg)
                    if m:
                        eval_uid = m.group(1)

                uniq = ts + "|" + msg
                logs.append((log_time, uniq, ts, eval_uid, msg))

            # SORT logs
            logs.sort(key=lambda x: x[0])

            # ===========================================================
            # PROCESS LOGS
            # ===========================================================
            for log_time, uniq, ts, eval_uid, msg in logs:

                # Show on GUI
                if uniq not in seen:
                    last_log_time_seen = time.time()
                    soft_refresh_count = 0  # RESET COUNTER

                    if eval_uid:
                        gui_log(f"[{ts}] [Eval UID: {eval_uid}] {msg}")
                    else:
                        gui_log(f"[{ts}] {msg}")

                    seen[uniq] = log_time

                # ------------------ FILTER LỖI ------------------
                send_flag = False

                if "negative eval frequency" in msg:
                    send_flag = True

                elif "avg_steps_behind=" in msg and "> max=" in msg:
                    send_flag = True
                    # chỉ gửi khi trong danh sách UID quan tâm
                    allowed_uids = {186, 60, 70, 10, 228, 178, 193, 44, 243}
                    # tách UID ra khỏi chuỗi log (ví dụ "UID 70 ..." hoặc "[70]")
                    if eval_uid == str(uid):
                        send_flag = True
                    else:
                        send_flag = False

                elif "No gradient gathered" in msg or "Consecutive misses" in msg:
                    send_flag = True

                elif "Skipped score of UID" in msg and ("zero" in msg or "negative" in msg):
                    send_flag = True

                elif "Skipped UID" in msg and "gradient not found" in msg:
                    send_flag = True
                elif "Skipped reducing score of UID" in msg and "due to negative zero value" in msg:
                    if eval_uid == str(uid):
                        send_flag = True
                    else:
                        send_flag = False
                elif "No gradient received from" in msg and "Slashing moving average score" in msg: 
                    if eval_uid == str(uid):
                        send_flag = True
                    else:
                        send_flag = False
                elif "MEGA SLASH" in msg and " adding to naughty list for 20 windows" in msg:
                    if eval_uid == str(uid):
                        send_flag = True
                    else:
                        send_flag = False
                elif "negative evaluations" in msg and "in last 8 windows" in msg:
                    if eval_uid == str(uid):
                        send_flag = True
                    else:
                        send_flag = False
                elif "consecutive negative evaluations" in msg:
                    if eval_uid == str(uid):
                        send_flag = True
                    else:
                        send_flag = False
                elif "Gradient Score" in msg:
                    if eval_uid == str(uid):
                        send_flag = True
                    else:
                        send_flag = False
                elif "Binary Moving Average Score" in msg:
                    send_flag = True
                elif "[DCP][upload] rank 0/4 ↑ checkpoints/2.1.17/_LATEST.json 0.00 MiB in" in msg:
                    send_flag = True
                elif "Sync average steps behind:" in msg and "interquartile mean" in msg:
                    if eval_uid == str(uid):
                        send_flag = True
                    else:
                        send_flag = False
                # Only send for target UID
                if eval_uid and eval_uid != str(uid):
                    send_flag = False

                # SEND
                if send_flag and uniq not in sent_to_discord:

                    if eval_uid:
                        send_discord(f" [Eval UID: {eval_uid}] {msg}")
                    else:
                        send_discord(f"{msg}")

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