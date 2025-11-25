import argparse
import threading
import time
import sys

from crawler_templar_scores import run_crawler_templar_scores

# Global flags
is_running = False
is_paused = False

# Store active crawler threads
active_threads = []


def log_cli(msg):
    print(msg, flush=True)


def should_run():
    return is_running


def paused_flag():
    return is_paused


# =======================================================
# START MULTI UID (FIXED — only 1 thread)
# =======================================================
def start(uids, minutes):
    global is_running, is_paused, active_threads

    if is_running:
        print(">>> Session already running. Restarting...")
        is_running = False
        time.sleep(1)

    print(f">>> START crawler for UIDs {uids} ({minutes} minutes range)")

    is_running = True
    is_paused = False

    # ONLY ONE THREAD — pass full UID LIST
    t = threading.Thread(
        target=run_crawler_templar_scores,
        args=(uids, minutes, log_cli, should_run, paused_flag),
        daemon=True
    )
    active_threads = [t]
    t.start()

    # Main holding loop (PM2 safe)
    try:
        while is_running:
            if not t.is_alive():
                print(">>> Crawler ended.")
                break
            time.sleep(0.5)

    except KeyboardInterrupt:
        print(">>> Ctrl + C detected. Stopping...")
        is_running = False
        time.sleep(1)


# =======================================================
# PAUSE
# =======================================================
def pause():
    global is_paused
    if not is_running:
        print("❌ Crawler is not running.")
        return
    is_paused = True
    print(">>> PAUSED.")


# =======================================================
# RESUME
# =======================================================
def resume():
    global is_paused
    if not is_running:
        print("❌ Crawler is not running.")
        return
    is_paused = False
    print(">>> RESUMED.")


# =======================================================
# STOP
# =======================================================
def stop():
    global is_running, is_paused
    if not is_running:
        print("❌ Crawler already stopped.")
        return
    is_running = False
    is_paused = False
    print(">>> STOPPING...")


# =======================================================
# MAIN
# =======================================================
def main():
    parser = argparse.ArgumentParser(description="Templar Score Monitor (Linux CLI)")

    parser.add_argument(
        "--uid", nargs="+",
        help="Nhập 1 hoặc nhiều UID, ví dụ: --uid 60 70 186",
        required=True
    )

    parser.add_argument("--minutes", type=int, default=5, help="Time range (minutes)")

    args = parser.parse_args()

    # Parse danh sách UID
    uids = []
    for raw in args.uid:
        raw = raw.replace(",", " ")
        for part in raw.split():
            if part.isdigit():
                uids.append(int(part))

    if not uids:
        print("❌ UID không hợp lệ.")
        return

    # Launch
    start(uids, args.minutes)


if __name__ == "__main__":
    main()