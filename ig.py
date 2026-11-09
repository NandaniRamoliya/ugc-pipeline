import requests

import store
from config import IG_HOST, IG_TOKEN_SEED, IG_USER_ID, IG_VERSION

BASE = f"https://{IG_HOST}/{IG_VERSION}"


def _token():
    return store.state_get("ig_token") or IG_TOKEN_SEED


def _check(r):
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError(f"Instagram API HTTP {r.status_code}: {r.text[:300]}")
    if r.status_code >= 400 or "error" in data:
        raise RuntimeError(f"Instagram API: {data.get('error', {}).get('message', r.text)[:400]}")
    return data


def _get(path, **p):
    p["access_token"] = _token()
    return _check(requests.get(f"{BASE}/{path}", params=p, timeout=60))


def _post(path, **p):
    p["access_token"] = _token()
    return _check(requests.post(f"{BASE}/{path}", data=p, timeout=120))


def create_reel(video_url, caption, cover_url=None):
    p = {"media_type": "REELS", "video_url": video_url, "caption": caption, "share_to_feed": "true"}
    if cover_url:
        p["cover_url"] = cover_url
    return _post(f"{IG_USER_ID}/media", **p)["id"]


def container_status(cid):
    return _get(cid, fields="status_code,status")


def publish(cid):
    return _post(f"{IG_USER_ID}/media_publish", creation_id=cid)["id"]


def permalink(media_id):
    return _get(media_id, fields="permalink").get("permalink", "")


def insights(media_id):
    data = _get(f"{media_id}/insights", metric="views,reach,likes,comments,saved,shares")
    return {m["name"]: (m.get("values") or [{}])[0].get("value", "") for m in data.get("data", [])}


def refresh_token():
    """Long-lived Instagram-Login tokens last ~60 days; refreshing weekly keeps them alive."""
    if "instagram.com" not in IG_HOST:
        return
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": _token()}, timeout=60)
    store.state_set("ig_token", _check(r)["access_token"])

