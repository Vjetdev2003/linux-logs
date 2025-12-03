import argparse
import threading
import time
import subprocess
from crawler_templar_scores import run_crawler_templar_scores

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

is_running = False
is_paused = False

active_thread = None


def log_cli(msg):
    print(msg, flush=True)


def should_run():
    return is_running


def paused_flag():
    return is_paused


def start(uids, minutes):
    global is_running, is_paused, active_thread

    if is_running:
        print("Restarting...")
        is_running = False
        time.sleep(1)

    print(f">>> START for UIDs {uids}")

    is_running = True
    is_paused = False

    active_thread = threading.Thread(
        target=run_crawler_templar_scores,
        args=(uids, minutes, log_cli, should_run, paused_flag),
        daemon=True
    )
    active_thread.start()

    # keep alive
    while is_running:
        if not active_thread.is_alive():
            print(">>> END")
            break
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--uid", nargs="+", required=True)
    parser.add_argument("--minutes", type=int, default=5)

    args = parser.parse_args()

    uids = []
    for raw in args.uid:
        for part in raw.replace(",", " ").split():
            if part.isdigit():
                uids.append(int(part))

    start(uids, args.minutes)


if __name__ == "__main__":
    main()