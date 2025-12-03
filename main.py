import argparse
import threading
import time
import subprocess
from crawler import run_crawler     # <<=== Dùng file crawler mới của bạn


# =====================================================
# FIXED UID LIST (chuẩn theo yêu cầu)
# =====================================================
FIXED_UIDS = [
    10, 44, 51, 204, 178, 95,
    145, 60, 228, 243, 231,
    70, 186, 193, 89, 6, 189, 164
]

def clean_chrome_processes():
    patterns = [
        "chrome --headless",
        "chromedriver",
        "google-chrome",
        "chromium"
    ]
    for p in patterns:
        try:
            subprocess.call(["pkill", "-f", p])
        except:
            pass

clean_chrome_processes()
# =====================================================
# CLEAN OLD CHROME
# =====================================================
def clean_chrome_processes():
    patterns = [
        "chrome --headless",
        "chromedriver",
        "google-chrome",
        "chromium"
    ]
    for p in patterns:
        try:
            subprocess.call(["pkill", "-f", p])
        except:
            pass

clean_chrome_processes()


# =====================================================
# FLAGS / STATE
# =====================================================
is_running = False
is_paused  = False
active_thread = None


# =====================================================
# LOG TO CONSOLE
# =====================================================
def log_cli(msg):
    print(msg, flush=True)


# =====================================================
# FLAGS FOR CRAWLER
# =====================================================
def should_run():
    return is_running


def paused_flag():
    return is_paused


# =====================================================
# START FUNCTION (PM2 sẽ chạy hàm này)
# =====================================================
def start(minutes):
    global is_running, is_paused, active_thread

    if is_running:
        print("Restarting...")
        is_running = False
        time.sleep(1)

    print(f">>> START with fixed UIDs = {FIXED_UIDS}")

    is_running = True
    is_paused  = False

    # Thread chạy crawler
    active_thread = threading.Thread(
        target=run_crawler,
        args=(minutes, log_cli, should_run, paused_flag),
        daemon=True
    )
    active_thread.start()

    # AUTO-RESTART nếu crawler crash
    while True:
        if not active_thread.is_alive():
            print(">>> Thread crashed! Restarting crawler in 3 seconds...")
            time.sleep(3)
            active_thread = threading.Thread(
                target=run_crawler,
                args=(minutes, log_cli, should_run, paused_flag),
                daemon=True
            )
            active_thread.start()

        time.sleep(1)


# =====================================================
# MAIN
# =====================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=5)
    args = parser.parse_args()

    start(args.minutes)


if __name__ == "__main__":
    main()
