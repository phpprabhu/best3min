import config
import requests


def send_alert(group, message):
    payload = {
        "username": "alertbot",
        "content": message
    }

    requests.post(config.DISCORD_WEBHOOK_URL[group], json=payload)
    print('Discord Msg Sent: ' + message)