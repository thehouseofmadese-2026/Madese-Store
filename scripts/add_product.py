"""Deterministically add one product to the House of Madese catalogue.

The /add-product skill does the thinking (research, naming, description) and
hands the result to this script as a JSON spec; this script does everything
mechanical so it can't be fumbled: image compression + base64 encoding,
splicing the product into index.html's SITE_DATA block WITHOUT re-serialising
the other ~7.5MB, updating products.json, validating, and (optionally)
committing + pushing to main so Vercel deploys.

Usage (any Python 3 with Pillow - the Madese Photo Studio venv has it):
  python add_product.py <spec.json> [--publish] [--dry-run]

spec.json:
{
  "name": "Cumulis Table Lamp",
  "collection": "Lamps",            # must match a live collection name (case-insensitive)
  "subcollection": "",              # optional
  "price": 899,
  "mrp": 1169,                      # optional, defaults to price
  "specs": ["PLA", "160mm x 200mm"],
  "desc": "Funny but honest description...",
  "stl": "https://makerworld.com/...",   # source link, admin-only field
  "images_dir": "C:/.../out",       # folder with main.png + other generated *.png
  "fallback_photo": "C:/.../ref.jpg" # used for img if main.png is missing
}

Prints "RESULT {json}" as its last line on success; exits non-zero with a
"ERROR ..." line on any failure (nothing is written unless every check passes).
"""
import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(REPO, "index.html")
PRODUCTS_JSON = os.path.join(REPO, "products.json")

MAIN_MAX_PX, GALLERY_MAX_PX, JPEG_QUALITY = 1000, 1400, 82
GALLERY_ORDER = ["conceptual-print-ad", "usecase", "size-comparison", "color-combo"]

SITE_RE = re.compile(r'(<script type="application/json" id="SITE_DATA">)(.*?)(</script>)', re.S)


def fail(msg):
    print(f"ERROR {msg}")
    sys.exit(1)


def encode_image(path, max_px):
    img = Image.open(path)
    if img.mode not in ("RGB", "L"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    img.thumbnail((max_px, max_px), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def gallery_sort_key(name):
    for i, prefix in enumerate(GALLERY_ORDER):
        if name.startswith(prefix):
            return (i, name)
    return (len(GALLERY_ORDER), name)


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "product"


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if check and r.returncode != 0:
        fail(f"git {' '.join(args)} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def validate(index_text, products_text):
    """JSON-parse SITE_DATA + products.json, and `node --check` the main script."""
    m = SITE_RE.search(index_text)
    json.loads(m.group(2))
    json.loads(products_text)
    node = shutil.which("node")
    if not node:
        print("WARN node not found - skipped script syntax check")
        return
    scripts = [
        s for attrs, s in re.findall(r"<script([^>]*)>(.*?)</script>", index_text, re.S)
        if "src=" not in attrs and "application/json" not in attrs and len(s) > 5000
    ]
    for s in scripts:
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf8") as f:
            f.write(s)
        r = subprocess.run([node, "--check", f.name], capture_output=True, text=True)
        os.unlink(f.name)
        if r.returncode != 0:
            fail(f"node --check failed: {r.stderr.strip()[:400]}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    publish, dry = "--publish" in sys.argv, "--dry-run" in sys.argv
    if len(args) != 1:
        fail("usage: add_product.py <spec.json> [--publish] [--dry-run]")
    spec = json.load(open(args[0], encoding="utf8"))

    for k in ("name", "collection", "price", "desc", "images_dir"):
        if not spec.get(k) and spec.get(k) != 0:
            fail(f"spec missing '{k}'")

    # Starting from a clean, up-to-date main so the push can't clobber anything.
    if publish:
        dirty = git("status", "--porcelain", "--", "index.html", "products.json")
        if dirty:
            fail("index.html/products.json have uncommitted local changes - refusing to publish over them")
        git("pull", "--rebase", "--autostash", "origin", "main")

    text = open(INDEX, encoding="utf8", newline="").read()
    m = SITE_RE.search(text)
    if not m:
        fail("SITE_DATA block not found in index.html")
    site_raw = m.group(2)
    site = json.loads(site_raw)

    # Collection must match something that actually exists on the live site.
    wanted = spec["collection"].strip().lower()
    coll = next((c for c in site["collections"] if c["name"].lower() == wanted), None)
    if coll is None:
        fail("collection '%s' not found; live collections: %s" % (spec["collection"], [c["name"] for c in site["collections"]]))

    existing_ids = {p["id"] for p in site["products"]}
    base = slugify(spec["name"])
    pid, n = base, 2
    while pid in existing_ids:
        pid, n = f"{base}-{n}", n + 1

    # Images.
    d = spec["images_dir"]
    pngs = sorted(f for f in os.listdir(d) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
    main_file = next((f for f in pngs if f.lower().startswith("main.")), None)
    if main_file:
        img = encode_image(os.path.join(d, main_file), MAIN_MAX_PX)
    elif spec.get("fallback_photo") and os.path.exists(spec["fallback_photo"]):
        img = encode_image(spec["fallback_photo"], MAIN_MAX_PX)
    else:
        fail("no main image and no fallback_photo")
    gallery_files = sorted((f for f in pngs if f != main_file), key=lambda f: gallery_sort_key(f.lower()))
    gallery = [encode_image(os.path.join(d, f), GALLERY_MAX_PX) for f in gallery_files]

    price = spec["price"]
    sub = (spec.get("subcollection") or "").strip()
    product = {
        "id": pid,
        "name": spec["name"].strip(),
        "collection": coll["name"],
        "subcollection": sub,
        "price": price,
        "mrp": spec.get("mrp") or price,
        "specs": spec.get("specs") or [],
        "img": img,
        "imgNote": "AI-generated listing photo (Madese Photo Studio) via add-product agent",
        "desc": spec["desc"].strip(),
        "gallery": gallery,
        "variants": [],
        "showVariants": False,
        "colors": [],
        "showColors": False,
        "stl": spec.get("stl", ""),
    }

    # Splice the new product onto the end of site["products"] without touching the rest.
    key = '"products": ['
    kpos = site_raw.index(key)
    arr_start = kpos + len(key) - 1
    _, rel_end = json.JSONDecoder().raw_decode(site_raw[arr_start:])
    arr_close = arr_start + rel_end - 1  # index of the closing ']'
    assert site_raw[arr_close] == "]"

    item = json.dumps(product, indent=1, ensure_ascii=False)
    item = "\n".join(" " + ln for ln in item.split("\n")).replace("</", "<\\/").replace("\n", "\r\n")
    before = site_raw[:arr_close].rstrip()
    new_site = before + ",\r\n" + item + "\r\n " + site_raw[arr_close:]
    new_text = text[: m.start(2)] + new_site + text[m.end(2):]

    products_text = open(PRODUCTS_JSON, encoding="utf8", newline="").read()
    plist = json.loads(products_text)
    plist.append({"id": pid, "name": product["name"], "price": price})
    nl = "\r\n" if "\r\n" in products_text else "\n"
    new_products_text = json.dumps(plist, indent=2, ensure_ascii=False).replace("\n", nl)
    if products_text.endswith(("\n", "\r\n")):
        new_products_text += nl

    validate(new_text, new_products_text)
    check = json.loads(SITE_RE.search(new_text).group(2))
    assert check["products"][-1]["id"] == pid and len(check["products"]) == len(site["products"]) + 1

    result = {
        "id": pid, "name": product["name"], "collection": coll["name"], "price": price,
        "mrp": product["mrp"], "gallery_count": len(gallery), "main": main_file or "fallback_photo",
        "gallery_files": gallery_files, "published": False,
    }
    if dry:
        print("DRY RUN ok - nothing written")
        print("RESULT " + json.dumps(result))
        return

    open(INDEX, "w", encoding="utf8", newline="").write(new_text)
    open(PRODUCTS_JSON, "w", encoding="utf8", newline="").write(new_products_text)

    if publish:
        git("add", "index.html", "products.json")
        git("commit", "-m", f"Add product: {product['name']}\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>")
        git("fetch", "origin", "main")
        push = subprocess.run(["git", "push", "origin", "main"], cwd=REPO, capture_output=True, text=True)
        if push.returncode != 0:
            fail("commit made locally but push failed: " + (push.stderr or push.stdout).strip()[:400])
        result["published"] = True
        result["commit"] = git("rev-parse", "--short", "HEAD")

    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()
