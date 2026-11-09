"""UGC pipeline. Usage: python main.py tick | weekly | ideate"""
import html
import json
import sys
import tempfile
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import ai
import cloud
import drive
import ig
import store
import tg
import video
from config import DRIVE_INBOX_FOLDER_ID, IDEAS_PER_WEEK, POST_SLOTS, TG_CHAT_ID, TZ

E = html.escape
MAX_BUILDS_PER_RUN = 2
HELP = ("<b>Commands</b>\n/status · /ideas 2\n/rewrite ID your direction\n/go ID (build with clips so far)\n"
        "/caption ID new caption\n/when ID 2026-11-20 19:00\n/retry ID (failed publish)")


def now():
    return datetime.now(TZ)


def parse_dt(s):
    dt = datetime.fromisoformat(s.strip())
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def find(pid):
    for r in store.content().all():
        if r["id"] == pid:
            return r
    raise ValueError(f"{pid} not found in Content sheet")


def next_id(rows):
    nums = [int(r["id"][4:]) for r in rows if r["id"].startswith("UGC-") and r["id"][4:].isdigit()]
    return f"UGC-{max(nums, default=0) + 1:04d}"


def active_products():
    return [p for p in store.products().all()
            if p["name"].strip() and p["status"].strip().lower() != "inactive"]


def strip_row(rec):
    return {k: v for k, v in rec.items() if k not in ("_row", "status")}


# ---------- scripts ----------
def script_text(r):
    shots = json.loads(r["shots_json"])
    total = sum(float(s.get("seconds") or 0) for s in shots)
    out = [f"<b>{r['id']} · {E(r['product_name'])}</b>  (~{total:.0f}s)",
           f"Angle: {E(r['angle'])}", f"🎣 <b>{E(r['hook'])}</b>", "", "🎬 <b>Shot list</b>"]
    for i, s in enumerate(shots, 1):
        out.append(f"<b>{i}.</b> ({s.get('seconds', '?')}s) {E(s.get('visual', ''))}")
        if s.get("on_screen_text"):
            out.append(f"   📝 {E(s['on_screen_text'])}")
        if s.get("voiceover"):
            out.append(f"   🎙 {E(s['voiceover'])}")
    out += ["", "<b>Caption</b>", E(r["caption"]), E(r["hashtags"])]
    return "\n".join(out)


def send_script(r):
    pid = r["id"]
    tg.send(script_text(r), [[tg.btn("✅ Approve", f"sa:{pid}"), tg.btn("🔁 Rewrite", f"sr:{pid}"),
                              tg.btn("❌ Drop", f"sx:{pid}")]])


def ideate(n=IDEAS_PER_WEEK):
    prods = active_products()
    if not prods:
        tg.send("📦 No products yet. Add products you own to the <b>Products</b> tab, then send /ideas")
        return
    tbl = store.content()
    rows = tbl.all()
    payload = [{k: p[k] for k in ("product_id", "name", "brand", "category", "key_benefits", "notes")}
               for p in prods]
    ideas = ai.generate_ideas(payload, n, store.state_get("learnings"), [r["hook"] for r in rows[-20:]])
    by_id = {str(p["product_id"]): p for p in prods}
    made = 0
    for idea in ideas:
        p = by_id.get(idea["product_id"])
        if not p:
            continue
        rec = {"id": next_id(rows), "created_at": now().isoformat(timespec="minutes"),
               "status": "SCRIPT_REVIEW", "product_id": p["product_id"], "product_name": p["name"],
               "angle": idea["angle"], "hook": idea["hook"],
               "shots_json": json.dumps(idea["shots"], ensure_ascii=False),
               "caption": idea["caption"], "hashtags": " ".join(idea["hashtags"])}
        tbl.append(rec)
        rows.append(rec)
        send_script(rec)
        made += 1
    tg.send(f"🗓 {made} new UGC scripts ready for review.")


def rewrite(r, note=""):
    product = next((strip_row(p) for p in active_products() if p["product_id"] == r["product_id"]),
                   {"name": r["product_name"]})
    idea = ai.rewrite_idea(product, r["hook"], r["angle"], note)
    store.content().update(r, angle=idea["angle"], hook=idea["hook"], caption=idea["caption"],
                           shots_json=json.dumps(idea["shots"], ensure_ascii=False),
                           hashtags=" ".join(idea["hashtags"]))
    send_script(r)


def next_slot():
    taken = {r["scheduled_at"] for r in store.content().all()
             if r["status"] in ("SCHEDULED", "PUBLISHING", "PUBLISHED") and r["scheduled_at"]}
    t = now()
    for d in range(28):
        day = (t + timedelta(days=d)).date()
        for wd, hm in sorted(POST_SLOTS, key=lambda s: s[1]):
            if day.weekday() != wd:
                continue
            h, m = map(int, hm.split(":"))
            slot = datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)
            if slot > t + timedelta(minutes=40) and slot.isoformat(timespec="minutes") not in taken:
                return slot
    return t + timedelta(hours=2)


# ---------- Telegram handling ----------
def on_callback(cb):
    action, pid = cb["data"].split(":", 1)
    tbl, r = store.content(), find(pid)
    st = r["status"]

    if action == "sa" and st == "SCRIPT_REVIEW":
        folder_id = ""
        try:
            folder_id = drive.create_folder(f"{pid} · {r['product_name']}", DRIVE_INBOX_FOLDER_ID)
            where = f'<a href="https://drive.google.com/drive/folders/{folder_id}">this Drive folder</a>'
        except Exception:
            where = f"a new folder named <b>{pid}</b> inside your UGC Inbox"
        tbl.update(r, status="AWAITING_CLIPS", folder_id=folder_id)
        n = len(json.loads(r["shots_json"]))
        tg.send(f"🎥 <b>{pid}</b> approved. Film {n} clips (one per shot, vertical) and upload them to "
                f"{where}.\nOrder = file names A→Z (phone names like IMG_1234 already work).\n"
                f"I'll build the reel automatically once {n} clips are there. Fewer clips? /go {pid}")
        return "Approved"
    if action == "sr" and st == "SCRIPT_REVIEW":
        rewrite(r)
        return "Rewritten"
    if action == "sx" and st in ("SCRIPT_REVIEW", "FINAL_REVIEW"):
        tbl.update(r, status="DROPPED")
        return "Dropped"
    if action == "fa" and st == "FINAL_REVIEW":
        when = next_slot()
        tbl.update(r, status="SCHEDULED", scheduled_at=when.isoformat(timespec="minutes"))
        tg.send(f"📅 <b>{pid}</b> scheduled for {when:%a %d %b, %I:%M %p}.\n"
                f"Change it: /when {pid} {when:%Y-%m-%d %H:%M}")
        return "Scheduled"
    if action == "fr" and st == "FINAL_REVIEW":
        tbl.update(r, status="WAITING_REFILM")
        tg.send(f"🔁 Replace the clips in <b>{pid}</b>'s Drive folder, then send /go {pid}")
        return "OK"
    return f"Already handled ({st})"


def on_text(text):
    parts = text.strip().split(maxsplit=2)
    cmd = parts[0].lower().split("@")[0]
    tbl = store.content()

    if cmd == "/status":
        c = Counter(r["status"] for r in tbl.all())
        tg.send("<b>Pipeline</b>\n" + ("\n".join(f"{k}: {v}" for k, v in sorted(c.items())) or "Empty"))
        return
    if cmd == "/ideas":
        ideate(int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2)
        return
    if cmd not in ("/caption", "/when", "/go", "/retry", "/rewrite") or len(parts) < 2:
        tg.send(HELP)
        return

    r = find(parts[1].upper())
    arg = parts[2] if len(parts) > 2 else ""
    if cmd == "/caption" and arg:
        tbl.update(r, caption=arg)
        tg.send(f"✏️ Caption updated for {r['id']}")
    elif cmd == "/when" and arg:
        dt = datetime.strptime(arg, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        tbl.update(r, scheduled_at=dt.isoformat(timespec="minutes"))
        tg.send(f"📅 {r['id']} moved to {dt:%a %d %b, %I:%M %p}")
    elif cmd == "/go" and r["status"] in ("AWAITING_CLIPS", "WAITING_REFILM", "BUILD_FAILED", "BUILDING"):
        tbl.update(r, status="READY_TO_BUILD")
        tg.send(f"⚙️ {r['id']} will be built on the next run (≤30 min).")
    elif cmd == "/retry" and r["status"] == "FAILED":
        tbl.update(r, status="SCHEDULED", container_id="", scheduled_at=now().isoformat(timespec="minutes"))
        tg.send(f"🔁 {r['id']} will retry publishing on the next run.")
    elif cmd == "/rewrite" and r["status"] == "SCRIPT_REVIEW":
        rewrite(r, arg)
    else:
        tg.send(f"Can't do {cmd} while {r['id']} is {r['status']}.")


def poll():
    offset = int(store.state_get("tg_offset") or 0)
    for u in tg.updates(offset):
        offset = u["update_id"] + 1
        store.state_set("tg_offset", offset)  # saved first, so an action never runs twice
        try:
            if "callback_query" in u:
                cb = u["callback_query"]
                chat = cb["message"]["chat"]["id"]
                if str(chat) != TG_CHAT_ID:
                    continue
                result = on_callback(cb)
                tg.answer(cb["id"], result)
                tg.clear_buttons(chat, cb["message"]["message_id"])
            elif "text" in u.get("message", {}):
                if str(u["message"]["chat"]["id"]) == TG_CHAT_ID:
                    on_text(u["message"]["text"])
        except Exception as e:
            traceback.print_exc()
            tg.send(f"⚠️ {E(str(e))[:500]}")


# ---------- building ----------
def build_ready():
    tbl, built = store.content(), 0
    for r in tbl.all():
        if r["status"] not in ("AWAITING_CLIPS", "READY_TO_BUILD") or built >= MAX_BUILDS_PER_RUN:
            continue
        folder = r["folder_id"] or drive.find_folder(r["id"], DRIVE_INBOX_FOLDER_ID)
        if not folder:
            continue
        files = drive.list_media(folder)
        shots = json.loads(r["shots_json"])
        if not files or (r["status"] == "AWAITING_CLIPS" and len(files) < len(shots)):
            continue
        built += 1
        tbl.update(r, status="BUILDING", folder_id=folder)
        try:
            build_one(r, shots, files)
        except Exception as e:
            traceback.print_exc()
            tbl.update(r, status="BUILD_FAILED", error=str(e)[:500])
            tg.send(f"⚠️ Build failed for <b>{r['id']}</b>: {E(str(e)[:300])}\nFix clips, then /go {r['id']}")


def build_one(r, shots, files):
    with tempfile.TemporaryDirectory() as tmp:
        work, local, pairs = Path(tmp), {}, []
        for i, shot in enumerate(shots):
            f = files[i % len(files)]  # fewer clips than shots → clips are reused in order
            is_img = f["mimeType"].startswith("image/")
            if f["id"] not in local:
                ext = Path(f["name"]).suffix or (".jpg" if is_img else ".mp4")
                local[f["id"]] = drive.download(f["id"], work / f"src_{len(local):02d}{ext}")
            pairs.append((shot, local[f["id"]], is_img))

        final, cover = video.assemble(pairs, r["hook"], work)
        vurl = cloud.upload(final, r["id"], "video")
        curl = cloud.upload(cover, f"{r['id']}_cover", "image")
        store.content().update(r, status="FINAL_REVIEW", video_url=vurl, cover_url=curl, error="")

        secs = video.duration(final)
        try:
            if final.stat().st_size > 48 * 1024 * 1024:
                raise ValueError("too big for Telegram")
            tg.send_video(final, f"<b>{r['id']}</b> · {secs:.0f}s")
        except Exception:
            tg.send(f'🎬 <a href="{vurl}">Watch {r["id"]}</a> ({secs:.0f}s)')
        pid = r["id"]
        tg.send(f"<b>Caption</b>\n{E(r['caption'])}\n{E(r['hashtags'])}",
                [[tg.btn("✅ Approve & schedule", f"fa:{pid}"), tg.btn("🎥 Re-film", f"fr:{pid}"),
                  tg.btn("❌ Drop", f"sx:{pid}")]])


# ---------- publishing ----------
def wait_container(cid, max_wait=240):
    waited = 0
    while True:
        status = ig.container_status(cid).get("status_code", "")
        if status != "IN_PROGRESS" or waited >= max_wait:
            return status
        time.sleep(15)
        waited += 15


def publish_due():
    tbl = store.content()
    for r in tbl.all():
        if r["status"] not in ("SCHEDULED", "PUBLISHING") or not r["scheduled_at"]:
            continue
        if r["status"] == "SCHEDULED" and parse_dt(r["scheduled_at"]) > now():
            continue
        try:
            cid = r["container_id"]
            if not cid:
                caption = f"{r['caption']}\n\n{r['hashtags']}".strip()
                cid = ig.create_reel(r["video_url"], caption, r["cover_url"] or None)
                tbl.update(r, status="PUBLISHING", container_id=cid)
            status = wait_container(cid)
            if status == "FINISHED":
                mid = ig.publish(cid)
                link = ig.permalink(mid)
                tbl.update(r, status="PUBLISHED", ig_media_id=mid, permalink=link, error="")
                tg.send(f"🚀 <b>{r['id']}</b> is live: {link}")
            elif status in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Instagram processing {status}: {ig.container_status(cid).get('status')}")
            # IN_PROGRESS → checked again next run
        except Exception as e:
            traceback.print_exc()
            tbl.update(r, status="FAILED", error=str(e)[:500])
            tg.send(f"❌ Publishing failed for <b>{r['id']}</b>: {E(str(e)[:300])}\nRetry: /retry {r['id']}")


# ---------- weekly ----------
def weekly():
    try:
        ig.refresh_token()
    except Exception as e:
        tg.send(f"⚠️ Instagram token refresh failed: {E(str(e))[:300]}")

    tbl, posts = store.content(), []
    for r in [x for x in tbl.all() if x["status"] == "PUBLISHED" and x["ig_media_id"]][-15:]:
        try:
            m = ig.insights(r["ig_media_id"])
        except Exception:
            continue
        tbl.update(r, views=m.get("views", ""), reach=m.get("reach", ""), likes=m.get("likes", ""),
                   comments=m.get("comments", ""), saves=m.get("saved", ""), shares=m.get("shares", ""))
        posts.append({k: r[k] for k in ("id", "product_name", "angle", "hook", "views", "reach",
                                        "likes", "comments", "saves", "shares")})
    if posts:
        s = ai.weekly_learnings(posts)
        learnings = "\n".join(f"- {x}" for x in s.get("learnings", []))
        store.state_set("learnings", learnings)
        tg.send(f"📊 <b>Weekly UGC report</b>\n{E(s.get('report', ''))}\n\n<b>Next week</b>\n{E(learnings)}")
    ideate()


def tick():
    for step in (poll, build_ready, publish_due):
        try:
            step()
        except Exception as e:
            traceback.print_exc()
            try:
                tg.send(f"⚠️ {step.__name__} crashed: {E(str(e))[:400]}")
            except Exception:
                pass


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "tick"
    {"tick": tick, "weekly": weekly, "ideate": ideate}[task]()

