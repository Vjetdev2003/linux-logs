import argparse
import threading
import time
import sys
from crawler import run_crawler

# Global flags
is_running = False
is_paused = False

def log_cli(msg):
    print(msg, flush=True)

def should_run():
    return is_running

def paused_flag():
    return is_paused


# =======================================================
# START MULTI UID
# =======================================================
def start(uids, minutes):
    global is_running, is_paused

    if is_running:
        print(">>> Old session detected. Stopping...")
        is_running = False
        time.sleep(1)

    print(f">>> START crawler for UIDs {uids} ({minutes} minutes range)")

    is_running = True
    is_paused = False

    # Khởi chạy mỗi UID 1 thread
    for uid in uids:
        print(f">>> Launching UID {uid} ...")

        threading.Thread(
            target=run_crawler,
            args=(uid, minutes, log_cli, should_run, paused_flag),
            daemon=True
        ).start()

        time.sleep(0.3)  # tránh crash Chrome headless khi mở nhiều cùng lúc

    # giữ CLI chạy
    try:
        while is_running:
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
    parser = argparse.ArgumentParser(description="Templar Log Monitor (Linux CLI)")

    parser.add_argument(
        "command",
        choices=["start", "stop", "pause", "resume"],
        help="Action to perform"
    )

    parser.add_argument(
        "--uid",
        nargs="+",
        help="Nhập 1 hoặc nhiều UID, ví dụ: --uid 178 228 10"
    )

    parser.add_argument("--minutes", type=int, default=5, help="Time range (minutes)")

    args = parser.parse_args()

    if args.command == "start":
        if not args.uid:
            print("❌ Bạn phải nhập UID:  --uid 193 hoặc --uid 193 102 228")
            return

        # Parse danh sách UID
        uids = []
        for raw in args.uid:
            raw = raw.replace(",", " ")  # hỗ trợ dạng "178,228"
            for part in raw.split():
                if part.isdigit():
                    uids.append(int(part))

        if not uids:
            print("❌ UID không hợp lệ.")
            return

        start(uids, args.minutes)

    elif args.command == "pause":
        pause()

    elif args.command == "resume":
        resume()

    elif args.command == "stop":
        stop()


if __name__ == "__main__":
    main()
