# discord_notify.py
import requests

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1439689052918907092/DNBc4cwG9hIcvDpDQEjsl4Jwo-TtK2XC-S7ZcpxuVlKMKsoOauJTB_Nan-FlQxtQ7JlK"

def send_discord(message: str):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=5)
    except Exception as e:
        print("Discord error:", e)

