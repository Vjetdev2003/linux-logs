import time
import re
import json
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from discord_notify_templar_scores import send_discord1


# FILE LƯU LỊCH SỬ MESSAGE ĐÃ GỬI
SENT_HISTORY_FILE = "sent_scores_history.json"

def load_history():
    try:
        with open(SENT_HISTORY_FILE, "r") as f:
            data = json.load(f)
            return set(data.keys())
    except:
        return set()

def save_history(sent_set):
    with open(SENT_HISTORY_FILE, "w") as f:
        json.dump({k: True for k in sent_set}, f)



WINDOWS_TO_MARK = {
    "60165","60168","60171","60174","60177",
    "60180","60183","60186","60189","60192",
    "60195","60198","60201","60204","60207",
    "60210","60213","60216","60219","60222",
    "60225","60228","60231","60234","60237",
    "60240","60243","60246","60249","60252",
    "60255","60258","60261","60264","60267",
    "60270","60273","60276","60279","60282",
    "60285","60288","60291","60294","60297",
    "60300"
}

GRAFANA_URL = (
    "https://grafana.tplr.ai/d/service_logs_validator_1/"
    "service-logs-only-for-validator-uid3d-1?orgId=1&refresh=5s"
)


def start_driver_headless():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,3000")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--disable-extensions")

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts
    )



def run_crawler_templar_scores(uid, time_range, gui_log, should_run, is_paused_flag):

    sent_history = load_history()

    driver = start_driver_headless()
    driver.get(GRAFANA_URL)

    gui_log(f"[TemplarScores] Monitoring UID {uid}")

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

            # ================================
            # LẤY TIMESTAMP CHUẨN
            # ================================
            ts_raw = tds[2].get_text(strip=True)
            try:
                log_time = datetime.datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S.%f")
            except:
                continue

            # CHỈ LẤY TRONG 5 PHÚT GẦN NHẤT
            if datetime.datetime.now() - log_time > datetime.timedelta(minutes=5):
                continue

            # ================================
            # LẤY WINDOW TỪ current_window
            # ================================
            window_value = None
            label_spans = tds[3].find_all("span")

            for sp in label_spans:
                title = sp.get("title", "")
                if title.startswith("current_window:"):
                    window_value = title.split(":", 1)[1].strip()
                    break

            if not window_value:
                continue

            window_marked = (
                window_value + "*" if window_value in WINDOWS_TO_MARK else window_value
            )

            # ================================
            # LẤY eval_uid TỪ LABEL
            # ================================
            eval_uid = None
            for sp in label_spans:
                title = sp.get("title", "")
                if title.startswith("eval_uid:"):
                    eval_uid = title.split(":", 1)[1].strip()
                    break

            if eval_uid != str(uid):
                continue

            # ================================
            # LẤY MESSAGE
            # ================================
            msg = tds[4].get_text(strip=True)

            # LOG RA UI
            gui_log(f"[{window_marked}] [UID {uid}] {msg}")

            # ================================
            # 4 LOẠI LOG QUAN TRỌNG
            # ================================
            important = (
                "Sync average steps behind" in msg
                or "Binary Moving Average Score" in msg
                or re.search(r"Computed Final Score for UID\s+\d+", msg)
                or re.search(r"Gradient Score[:\s]+(-?\d+\.?\d*(e-?\d+)?)", msg, re.I)
            )

            if important:
                # tạo khoá duy nhất để kiểm tra trùng
                uniq_key = f"{window_value}|{uid}|{msg}"

                if uniq_key not in sent_history:
                    send_discord1(f"[**{window_marked}**] [UID {uid}] {msg}")
                    sent_history.add(uniq_key)
                    save_history(sent_history)

        time.sleep(1)
