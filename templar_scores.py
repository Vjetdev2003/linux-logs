import json
import os
import time
import threading
from crawler_templar_scores import run_crawler_templar_scores

COMMAND_FILE = "commands.json"

is_running = False
is_paused = False
running_threads = []
start_lock = threading.Lock()


def log(msg):
    print(msg, flush=True)


def should_run():
    return is_running


def paused_flag():
    return is_paused


def start_crawlers(uids, minutes):
    global is_running, is_paused, running_threads

    with start_lock:
        if is_running:
            log(">>> Stopping old session...")
            is_running = False
            time.sleep(1)

        log(f">>> START session for UIDs {uids} ({minutes} min)")
        is_running = True
        is_paused = False

        running_threads = []

        for uid in uids:
            log(f">>> Launch UID {uid}")
            t = threading.Thread(
                target=run_crawler_templar_scores,
                args=(uid, minutes, log, should_run, paused_flag),
                daemon=True
            )
            running_threads.append(t)
            t.start()
            time.sleep(0.2)


def pause():
    global is_paused
    if not is_running:
        log("❌ Not running.")
        return
    is_paused = True
    log(">>> PAUSED.")


def resume():
    global is_paused
    if not is_running:
        log("❌ Not running.")
        return
    is_paused = False
    log(">>> RESUMED.")


def stop():
    global is_running, is_paused
    if not is_running:
        log("❌ Already stopped.")
        return
    is_running = False
    is_paused = False
    log(">>> STOPPING session...")


def read_command():
    if not os.path.exists(COMMAND_FILE):
        return None

    try:
        with open(COMMAND_FILE, "r") as f:
            data = json.load(f)
        os.remove(COMMAND_FILE)
        return data
    except:
        return None


def main_loop():
    log("=== Templar Scores Daemon Started ===")
    log("Waiting for commands (start / stop / pause / resume)...")

    while True:
        cmd = read_command()
        if cmd:
            action = cmd.get("cmd")

            if action == "start":
                uids = cmd.get("uid", [])
                minutes = cmd.get("minutes", 5)

                if not uids:
                    log("❌ Missing UID list")
                else:
                    start_crawlers(uids, minutes)

            elif action == "pause":
                pause()

            elif action == "resume":
                resume()

            elif action == "stop":
                stop()

            else:
                log(f"❌ Unknown command: {action}")

        # keep daemon alive
        time.sleep(0.5)


if __name__ == "__main__":
    main_loop()
