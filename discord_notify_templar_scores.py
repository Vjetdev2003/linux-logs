import requests

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1441003389734621224/XbSSPoQmNvkvO15ZFhMFgCLn4BTcvGxzwCnRtGP_nLEWTNXEmlUZCEraZAqRojf0NWej"

def send_discord1(message: str):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=5)
    except Exception as e:
        print("Discord error:", e)
