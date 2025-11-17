# discord_notify.py
import requests

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1439527582654533642/dPuuVPdWwO7s6J1tcYJpER_1wWAx75bgNd7dxErp6dK66JUEiVhJ-M6NkQGYUzOQkHfZ"

def send_discord(message: str):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=5)
    except Exception as e:
        print("Discord error:", e)

