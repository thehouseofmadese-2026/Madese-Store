"""Telegram front door for the House of Madese add-product agent.

Mayank sends a product link + photo (+ optional "499 lamps" style caption) to a
private Telegram bot. This process, running on his PC, downloads the photo and
runs Claude Code headlessly with the repo's add-product skill, which generates
the Gemini photos (incl. colour options), writes the description, publishes to the live site, and
replies with the result here.

Standard library only - no pip install. Config comes from .env next to this file:
  TELEGRAM_BOT_TOKEN=...      (from @BotFather)
  ALLOWED_USER_ID=...         (your numeric Telegram id - the bot ignores everyone else)
  DRY_RUN=1                   (optional: do everything except publish, for testing)
"""
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
WORK_ROOT = os.path.join(os.environ.get("TEMP", HERE), "madese-agent")
JOB_TIMEOUT_S = 40 * 60
SETTLE_S = 4          # wait this long after the last message before acting (multi-photo albums, link sent after photo)
PENDING_TTL_S = 15 * 60

URL_RE = re.compile(r"https?://\S+")


def load_env():
    env = {}
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env()
TOKEN = ENV.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED = ENV.get("ALLOWED_USER_ID") or os.environ.get("ALLOWED_USER_ID")
DRY_RUN = (ENV.get("DRY_RUN") or "").strip() in ("1", "true", "yes")
API = f"https://api.telegram.org/bot{TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{TOKEN}"
CLAUDE = shutil.which("claude") or shutil.which("claude.exe")

LOG = open(os.path.join(HERE, "agent.log"), "a", encoding="utf8", buffering=1)


def log(*a):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} " + " ".join(str(x) for x in a)
    print(line)
    LOG.write(line + "\n")


def tg(method, **params):
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(f"{API}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=70) as r:
        return json.load(r)


def say(chat_id, text):
    for i in range(0, len(text), 3900):
        try:
            tg("sendMessage", chat_id=chat_id, text=text[i:i + 3900], disable_web_page_preview="true")
        except Exception as e:
            log("sendMessage failed:", e)


def download(file_id, dest_dir):
    info = tg("getFile", file_id=file_id)["result"]
    ext = os.path.splitext(info["file_path"])[1] or ".jpg"
    path = os.path.join(dest_dir, f"photo{len(os.listdir(dest_dir)) + 1}{ext}")
    with urllib.request.urlopen(f"{FILE_API}/{info['file_path']}", timeout=120) as r, open(path, "wb") as f:
        shutil.copyfileobj(r, f)
    return path


# ---- job running -----------------------------------------------------------

def build_redo_prompt(photos, text):
    lines = [
        "You are running headlessly as Mayank's House of Madese product-listing agent, triggered from Telegram with /redo.",
        f"Read {os.path.join(REPO, '.claude', 'skills', 'redo-photos', 'SKILL.md')} and follow it exactly, start to finish, without asking questions.",
        "This replaces photos on an ALREADY-LIVE product in place. Never add a new product.",
        "",
        "New reference photo path(s) (optional; if none, use the product's current main photo):",
        *([f"  {p}" for p in photos] or ["  (none)"]),
        "",
        "Mayank's message (the product name + what he wants changed):",
        text or "(no text)",
    ]
    if DRY_RUN:
        lines += ["", "TEST MODE: in step 4 run update_product_photos.py with --dry-run instead of --publish, and begin your final report with '🧪 TEST - not published'."]
    lines += ["", "Your final output is sent to him verbatim on Telegram, so end with the short report described in step 5."]
    return "\n".join(lines)


def build_prompt(photos, text):
    lines = [
        "You are running headlessly as Mayank's House of Madese product-listing agent, triggered from Telegram.",
        f"Read {os.path.join(REPO, '.claude', 'skills', 'add-product', 'SKILL.md')} and follow it exactly, start to finish, without asking questions.",
        "",
        "Reference photo path(s) (use the first as the primary; the rest are extra angles):",
        *[f"  {p}" for p in photos],
        "",
        "Mayank's message (contains the source link and optionally a price/collection/name hint and a note explaining what the product is/does; the note is the source of truth):",
        text or "(no text)",
    ]
    if DRY_RUN:
        lines += ["", "TEST MODE: in step 5 run add_product.py with --dry-run instead of --publish, and begin your final report with '🧪 TEST - not published'."]
    lines += ["", "Your final output is sent to him verbatim on Telegram, so end with the short report described in step 6."]
    return "\n".join(lines)


def run_job(chat_id, photos, text, redo=False):
    if not CLAUDE:
        say(chat_id, "❌ Can't find the `claude` command on this PC's PATH.")
        return
    if redo:
        say(chat_id, "⏳ On it. Regenerating the photos and swapping them into the live listing (no duplicate). Usually 3-10 minutes.")
    else:
        say(chat_id, "⏳ On it. Reading the link, generating the photos and colour options, writing the description. Usually 5-12 minutes.")
    cmd = [
        CLAUDE, "-p", (build_redo_prompt if redo else build_prompt)(photos, text),
        "--permission-mode", "dontAsk",
        "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep", "Bash", "WebFetch", "WebSearch", "mcp__claude-in-chrome__*",
        "--add-dir", os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive", "Desktop", "Madese Photo Studio"),
        "--add-dir", WORK_ROOT,
    ]
    log("job start:", text[:120].replace("\n", " "), "| photos:", len(photos))
    stop = threading.Event()

    def typing():
        while not stop.wait(4.5):
            try:
                tg("sendChatAction", chat_id=chat_id, action="upload_photo")
            except Exception:
                pass
    threading.Thread(target=typing, daemon=True).start()
    try:
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding="utf8", timeout=JOB_TIMEOUT_S)
        out = (r.stdout or "").strip()
        log("job exit", r.returncode, "| stderr:", (r.stderr or "")[-300:].replace("\n", " "))
        if r.returncode == 0 and out:
            say(chat_id, out)
        else:
            say(chat_id, ("❌ NOT updated" if redo else "❌ NOT published") + ": the agent run failed.\n" + ((out or r.stderr or "no output")[-800:]))
    except subprocess.TimeoutExpired:
        say(chat_id, "❌ NOT published: timed out after 40 minutes. Check the site before resending, in case it half-finished.")
    except Exception as e:
        say(chat_id, f"❌ NOT published: {e}")
    finally:
        stop.set()


jobs = queue.Queue()


def worker():
    while True:
        chat_id, photos, text, redo = jobs.get()
        try:
            run_job(chat_id, photos, text, redo)
        except Exception as e:  # never let the worker die
            log("worker error:", e)
            say(chat_id, f"❌ Agent error: {e}")
        jobs.task_done()


# ---- message collection ----------------------------------------------------
# Each product becomes its own job as soon as it is complete:
#   - photo + link in one message (caption)            -> job right away
#   - photo(s) then link, or link then photo           -> job when the second half arrives
#   - an album (several photos sent together)          -> one job, after a short wait for all its photos
# Products sent back-to-back are queued and processed one at a time.

units = {}  # key -> {"chat", "photos", "text", "last", "nudged", "album"}


def new_unit(chat_id, album=False):
    return {"chat": chat_id, "photos": [], "text": [], "last": time.time(), "nudged": False, "album": album,
            "dir": os.path.join(WORK_ROOT, "incoming", datetime.now().strftime("%Y%m%d-%H%M%S-%f"))}


def enqueue(unit):
    chat_id = unit["chat"]
    jobs.put((chat_id, unit["photos"], "\n".join(unit["text"]), False))
    n = jobs.unfinished_tasks
    if n > 1:
        say(chat_id, f"Queued (#{n}): I'll start it as soon as the one before it finishes.")


def on_message(msg):
    chat_id = msg["chat"]["id"]
    uid = str(msg.get("from", {}).get("id", ""))
    if not ALLOWED:
        say(chat_id, f"Your Telegram ID is {uid}. Put ALLOWED_USER_ID={uid} in scripts/telegram_agent/.env and restart me.")
        return
    if uid != str(ALLOWED):
        log("ignored message from", uid)
        return

    text = (msg.get("text") or msg.get("caption") or "").strip()
    if text.lower() in ("/start", "/help"):
        say(chat_id, "Send me a product link + a photo of it (link in the caption or as a separate message). "
                     "Optionally add a price and collection, e.g. '499 lamps', and a note in your own words about what the product is and does "
                     "(e.g. '99 homemaker. Screw-down clip that seals coffee bags'), which I treat as the truth over the link. "
                     "You can send several products in a row; "
                     "I'll queue them and do them one by one. Send /undo to remove the last product I published. "
                     "To redo photos of a product that's already live (no duplicate): /redo <product name> <what to change>, "
                     "e.g. '/redo Wicker Glow Retro Lamp, more vibrant colours' or '/redo Bean Pod new ad idea'. "
                     "Attach a photo to use it as the new reference.")
        return
    if text.lower() in ("/cancel", "cancel"):
        had = units.pop(("partial", chat_id), None)
        say(chat_id, "Cleared the half-sent request." if had else "Nothing half-sent. (Jobs already queued can't be cancelled.)")
        return

    if text.lower() in ("/undo", "undo"):
        if jobs.unfinished_tasks > 0:
            say(chat_id, "A product is still being processed. Wait for it to finish, then send /undo.")
            return
        say(chat_id, "Undoing the last product I published...")
        r = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "undo_product.py")],
                           capture_output=True, text=True, encoding="utf8", timeout=300)
        out = (r.stdout or "").strip().splitlines()
        last = out[-1] if out else (r.stderr or "no output").strip()[-300:]
        log("undo:", last)
        say(chat_id, ("↩️ Removed: " + last[len("UNDONE "):] + ". Gone from the site in about a minute. Send /undo again to remove the one before it.")
            if last.startswith("UNDONE") else "❌ " + last)
        return

    if text.lower().startswith("/redo"):
        body = text[5:].strip()
        if not body:
            say(chat_id, "Tell me which product and what to change, e.g. /redo Wicker Glow Retro Lamp, more vibrant colours")
            return
        unit = new_unit(chat_id)
        os.makedirs(unit["dir"], exist_ok=True)
        try:
            if msg.get("photo"):
                unit["photos"].append(download(msg["photo"][-1]["file_id"], unit["dir"]))
            elif (msg.get("document") or {}).get("mime_type", "").startswith("image/"):
                unit["photos"].append(download(msg["document"]["file_id"], unit["dir"]))
        except Exception as e:
            say(chat_id, f"❌ Couldn't download that photo: {e}")
            return
        jobs.put((chat_id, unit["photos"], body, True))
        if jobs.unfinished_tasks > 1:
            say(chat_id, f"Queued (#{jobs.unfinished_tasks}): I'll start it as soon as the one before it finishes.")
        return

    has_photo = bool(msg.get("photo")) or (msg.get("document") or {}).get("mime_type", "").startswith("image/")
    has_link = bool(URL_RE.search(text))
    mg = msg.get("media_group_id")

    if mg:                                    # part of an album: gather everything with the same id
        key = ("album", mg)
        unit = units.setdefault(key, new_unit(chat_id, album=True))
    elif has_photo and has_link:              # self-contained product message
        key = ("msg", msg["message_id"])
        unit = units.setdefault(key, new_unit(chat_id))
    else:                                     # half a product: park it until the other half arrives
        key = ("partial", chat_id)
        unit = units.setdefault(key, new_unit(chat_id))

    os.makedirs(unit["dir"], exist_ok=True)
    try:
        if msg.get("photo"):
            unit["photos"].append(download(msg["photo"][-1]["file_id"], unit["dir"]))
        elif has_photo:
            unit["photos"].append(download(msg["document"]["file_id"], unit["dir"]))
    except Exception as e:
        say(chat_id, f"❌ Couldn't download that photo: {e}")
        return
    if text:
        unit["text"].append(text)
    unit["last"] = time.time()
    unit["nudged"] = False


def flush_pending():
    now = time.time()
    for key, u in list(units.items()):
        idle = now - u["last"]
        complete = bool(u["photos"]) and bool(URL_RE.search("\n".join(u["text"])))
        if complete and (not u["album"] or idle >= SETTLE_S):
            del units[key]
            enqueue(u)
        elif idle >= SETTLE_S and not u["nudged"] and (u["photos"] or u["text"]):
            u["nudged"] = True
            if u["photos"]:
                say(u["chat"], "Got the photo. Now send the product link (or /cancel).")
            else:
                say(u["chat"], "Got the link. Now send a photo of the product (or /cancel).")
        elif idle > PENDING_TTL_S:
            del units[key]


def main():
    if not TOKEN:
        sys.exit("Missing TELEGRAM_BOT_TOKEN in scripts/telegram_agent/.env (see README.md)")
    os.makedirs(WORK_ROOT, exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    me = tg("getMe")["result"]
    log(f"bot @{me['username']} online | allowed user: {ALLOWED or '(not set)'} | dry-run: {DRY_RUN} | claude: {CLAUDE}")
    offset = None
    while True:
        try:
            res = tg("getUpdates", offset=offset, timeout=3)["result"]
            for u in res:
                offset = u["update_id"] + 1
                if "message" in u:
                    on_message(u["message"])
            flush_pending()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log("poll error:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
