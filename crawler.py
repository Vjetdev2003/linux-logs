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
from discord_notify import send_discord


GRAFANA_URL_TEMPLATE = (
    "https://grafana.tplr.ai/d/service_logs_validator_1/"
    "service-logs-only-for-validator-uid3d-1?orgId=1&refresh=5s&var-Search={UID}"
)

SENT_HISTORY_FILE = "sent_history.json"


def print_table(data):
    table = PrettyTable()
    table.field_names = ["Window", "Status"]
    for window, status in data:
        table.add_row([window, status])
    return table.get_string()


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
            By.XPATH,
            "//tr[td[contains(@class,'logs-row__localtime')]]"
        )
    except:
        return []


def run_crawler(uid, time_range_minutes, gui_log, should_run, paused_flag):

    url = GRAFANA_URL_TEMPLATE.replace("{UID}", str(uid))
    driver = None
    seen = {}
    sent_to_discord = load_sent_history()
    soft_refresh_count = 0

    # memory used ONLY for Gradient Score rows
    globals()["last_window_value"] = None
    globals()["last_uid_value"] = None

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

        while should_run():

            if paused_flag():
                time.sleep(0.25)
                continue

            now = datetime.datetime.now()
            logs = []

            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except:
                pass

            if time.time() - last_log_time_seen > 120:
                gui_log(">>> Soft refresh...")
                soft_refresh_count += 1
                try:
                    driver.refresh()
                    time.sleep(3)
                    wait_for_dom(driver, gui_log)
                except:
                    gui_log(">>> Soft refresh crashed, restarting driver...")
                    driver.quit()
                    driver = start_driver()
                    driver.get(url)
                    time.sleep(6)
                    wait_for_dom(driver, gui_log)
                    continue

                if soft_refresh_count >= 5:
                    gui_log(">>> HARD RELOAD triggered")
                    try:
                        driver.get(url)
                        time.sleep(6)
                        wait_for_dom(driver, gui_log)
                        soft_refresh_count = 0
                    except:
                        gui_log(">>> HARD reload crashed — restarting driver...")
                        driver.quit()
                        driver = start_driver()
                        driver.get(url)
                        time.sleep(6)
                        wait_for_dom(driver, gui_log)
                    continue

            rows = get_rows(driver)
            if not rows:
                time.sleep(2)
                rows = get_rows(driver)

            if not rows:
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

                # extract columns
                try:
                    window_value = int(tds[0].get_text(strip=True))
                except:
                    window_value = None

                uid_value = tds[1].get_text(strip=True)
                ts = tds[2].get_text(strip=True)
                msg = tds[4].get_text(strip=True)

                # update last window/uid for Gradient Score ONLY
                if window_value is not None:
                    globals()["last_window_value"] = window_value
                if uid_value:
                    globals()["last_uid_value"] = uid_value

                # parse timestamp
                try:
                    log_time = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
                except:
                    try:
                        log_time = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    except:
                        continue

                if now - log_time > time_range:
                    continue

                # extract label eval_uid
                label_td = tds[3]
                labels = {}
                for sp in label_td.find_all("span"):
                    title = sp.get("title", "")
                    if ":" in title:
                        key, val = title.split(":", 1)
                        labels[key.strip()] = val.strip()

                eval_uid = labels.get("eval_uid")
                if not eval_uid:
                    m2 = re.search(r"UID\s+(\d+)", msg)
                    if m2:
                        eval_uid = m2.group(1)

                uniq = ts + "|" + msg
                logs.append((log_time, uniq, ts, eval_uid, msg, window_value, uid_value))

            logs.sort(key=lambda x: x[0])

            # ===========================================================
            # PROCESS LOGS
            # ===========================================================
            for (
                log_time,
                uniq,
                ts,
                eval_uid,
                msg,
                window_value,
                uid_value
            ) in logs:

                # GUI display
                if uniq not in seen:
                    last_log_time_seen = time.time()
                    soft_refresh_count = 0
                    if eval_uid:
                        gui_log(f"[{ts}] [Eval UID: {eval_uid}] {msg}")
                    else:
                        gui_log(f"[{ts}] {msg}")
                    seen[uniq] = log_time

                # =======================================================
                # SPECIAL CASE: CHECKPOINT UPLOAD (NO UID, SEND ONCE)
                # =======================================================
                if "[DCP][upload]" in msg or "checkpoints" in msg and "LATEST.json" in msg:

                    global_key = "checkpoint" + msg and "LATEST.json" in msg 

                    if global_key not in sent_to_discord:
                        send_discord(f"[CHECKPOINT] {msg}")
                        sent_to_discord.add(global_key)
                        save_sent_history(sent_to_discord)

                    continue

                # =======================================================
                # GRADIENT SCORE (special window fallback)
                # =======================================================
                mgs = re.search(
                    r"Gradient Score[:\s]+(-?\d+\.?\d*(e-?\d+)?)",
                    msg,
                    re.IGNORECASE
                )

                if mgs:

                    score = float(mgs.group(1))

                    # If this row does not have window → use last_window
                    real_window = (
                        window_value
                        if window_value is not None
                        else globals()["last_window_value"]
                    )

                    real_uid = (
                        uid_value
                        if uid_value
                        else globals()["last_uid_value"]
                    )

                    if str(real_uid) == str(uid) and real_window:

                        status = "d" if score > 0 else "a"

                        if "gradient_history" not in globals():
                            globals()["gradient_history"] = {}
                        gradient_history = globals()["gradient_history"]

                        gradient_history[real_window] = status

                        gui_log(
                            f"[Gradient Score] Window {real_window} = {score} → {status}"
                        )

                        # table (test: 1 window)
                        last1 = sorted(
                            gradient_history.keys(), reverse=True
                        )[:1]
                        table_data = [
                            (w, gradient_history[w]) for w in last1
                        ]
                        table_str = print_table(table_data)

                        gui_log(
                            "\n===== GRADIENT WINDOW STATUS =====\n"
                            + table_str
                            + "\n"
                        )
                        send_discord(f"```\n{table_str}\n```")

                        # keep only 1
                        for old in list(gradient_history.keys()):
                            if old not in last1:
                                del gradient_history[old]

                # =======================================================
                # ORIGINAL ALERT LOGIC
                # =======================================================
                send_flag = False

                if "negative eval frequency" in msg:
                    send_flag = True

                elif "avg_steps_behind=" in msg and "> max=" in msg:
                    send_flag = eval_uid == str(uid)

                elif "No gradient gathered" in msg or "Consecutive misses" in msg:
                    send_flag = True

                elif "Skipped score of UID" in msg:
                    send_flag = True

                elif "Skipped UID" in msg:
                    send_flag = eval_uid == str(uid)

                elif "Skipped reducing score of UID" in msg:
                    send_flag = eval_uid == str(uid)

                elif "No gradient received from" in msg:
                    send_flag = eval_uid == str(uid)

                elif "MEGA SLASH" in msg:
                    send_flag = eval_uid == str(uid)

                elif "negative evaluations" in msg:
                    send_flag = eval_uid == str(uid)

                elif "consecutive negative evaluations" in msg:
                    send_flag = eval_uid == str(uid)

                if eval_uid and eval_uid != str(uid):
                    send_flag = False

                if send_flag and uniq not in sent_to_discord:
                    send_discord(f"[UID: {eval_uid}] {msg}")
                    sent_to_discord.add(uniq)
                    save_sent_history(sent_to_discord)

            # cleanup
            old_keys = []
            for k, t in seen.items():
                if now - t > time_range:
                    old_keys.append(k)
            for k in old_keys:
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
