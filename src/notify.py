"""Varslingslaget - bytebart.

Set NOTIFIER i .env til telegram, twilio_sms eller stdout.
Telegram kostar 0 kr og er standard. Twilio SMS kostar ca. 0,70 kr
per melding pluss ca. 15 kr/mnd for nummeret.
"""

import requests

from .config import env


def _send_twilio_sms(text):
    sid = env("TWILIO_ACCOUNT_SID")
    token = env("TWILIO_AUTH_TOKEN")
    from_number = env("TWILIO_FROM_NUMBER")
    to_number = env("ALERT_PHONE_NUMBER")

    missing = [
        name for name, value in [
            ("TWILIO_ACCOUNT_SID", sid),
            ("TWILIO_AUTH_TOKEN", token),
            ("TWILIO_FROM_NUMBER", from_number),
            ("ALERT_PHONE_NUMBER", to_number),
        ] if not value
    ]
    if missing:
        print("[notify] manglar: %s" % ", ".join(missing))
        return False

    url = "https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json" % sid
    try:
        resp = requests.post(
            url,
            auth=(sid, token),
            data={"From": from_number, "To": to_number, "Body": text[:320]},
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        print("[notify] Twilio feila: %s" % exc)
        return False
    return True


def _send_telegram(text):
    token = env("TELEGRAM_BOT_TOKEN")
    chat_id = env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[notify] manglar TELEGRAM_BOT_TOKEN eller TELEGRAM_CHAT_ID")
        return False

    try:
        resp = requests.post(
            "https://api.telegram.org/bot%s/sendMessage" % token,
            data={"chat_id": chat_id, "text": text},
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        print("[notify] Telegram feila: %s" % exc)
        return False
    return True


def _send_stdout(text):
    print("=" * 60)
    print("VARSEL:")
    print(text)
    print("=" * 60)
    return True


BACKENDS = {
    "telegram": _send_telegram,
    "twilio_sms": _send_twilio_sms,
    "stdout": _send_stdout,
}


def send(text):
    name = env("NOTIFIER", "telegram")
    backend = BACKENDS.get(name)
    if backend is None:
        print("[notify] ukjend NOTIFIER '%s' - fell tilbake til stdout" % name)
        backend = _send_stdout
    return backend(text)
