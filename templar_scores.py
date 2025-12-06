import argparse
import threading
import time
import subprocess
from crawler_templar_scores import run_crawler_templar_scores

# ==========================
# FIXED UID LIST
# ==========================
FIXED_UIDS = [
    "10","44","51","204","178","95",
    "145","60","228","243","231",
    "70","186","193","89","6","189","164",
    "180","217","197","219","29","108","49",
    "170","162", "215","235","131", "15","25","50"
]

# ==========================
# KILL OLD CHROME INSTANCES
# ==========================
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


# ==========================
# FLAGS
# ==========================
is_running = False
is_paused = False

crawler_thread = None


# ==========================
# HELPERS
# ==========================
def log_cli(msg):
    print(msg, flush=True)

def should_run():
    return is_running

def paused_flag():
    return is_paused


# ==========================
# START WORKER THREAD
# ==========================
def start_worker(minutes):
    global crawler_thread

    crawler_thread = threading.Thread(
        target=run_crawler_templar_scores,
        args=(FIXED_UIDS, minutes, log_cli, should_run, paused_flag),
        daemon=True
    )
    crawler_thread.start()


# ==========================
# MAIN LOOP (NO WHILE TRUE)
# ==========================
def start(minutes):
    global is_running, is_paused

    print(f">>> START with fixed UIDs = {FIXED_UIDS}")

    is_running = True
    is_paused = False

    start_worker(minutes)

    # Instead of infinite while True, use a soft-loop so PM2 can restart process
    while is_running:
        # If thread dies unexpectedly → restart it
        if not crawler_thread.is_alive():
            print(">>> Worker crashed! Restarting worker in 3 seconds...")
            time.sleep(3)
            start_worker(minutes)

        time.sleep(1)


# ==========================
# CLI ENTRY
# ==========================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=5)
    args = parser.parse_args()

    start(args.minutes)


if __name__ == "__main__":
    main()