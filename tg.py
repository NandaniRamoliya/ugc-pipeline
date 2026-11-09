import re

import requests

from config import TG_CHAT_ID, TG_TOKEN

API = f"https://api.telegram.org/bot{TG_TOKEN}"


def _call(method, files=None, **params):
    if files:
        r = requests.post(f"{API}/{method}", data=params, files=files, timeout=300)
    else:
        r = requests.post(f"{API}/{method}", json=params, timeout=60)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description')}")
    return data["result"]


def btn(text, data):
    return {"text": text, "callback_data": data}


def send(text, buttons=None):
    params = {"chat_id": TG_CHAT_ID, "disable_web_page_preview": True}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": buttons}
    if len(text) <= 4000:
        return _call("sendMessage", text=text, parse_mode="HTML", **params)
    return _call("sendMessage", text=re.sub(r"<[^>]+>", "", text)[:4000], **params)


def send_video(path, caption):
    with open(path, "rb") as f:
        return _call("sendVideo", files={"video": f}, chat_id=TG_CHAT_ID,
                     caption=caption, parse_mode="HTML", supports_streaming="true")


def updates(offset):
    return _call("getUpdates", offset=offset, timeout=0, allowed_updates=["message", "callback_query"])


def answer(cb_id, text=""):
    try:  # Telegram rejects answers to old button taps; that's harmless
        _call("answerCallbackQuery", callback_query_id=cb_id, text=text[:190])
    except Exception:
        pass


def clear_buttons(chat_id, message_id):
    try:
        _call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
              reply_markup={"inline_keyboard": []})
    except Exception:
        pass

