"""Swap new photos into an ALREADY-LIVE product (no duplicate), leaving name/price/desc/id untouched.

Usage (any Python 3 with Pillow - the Madese Photo Studio venv has it):
  python update_product_photos.py export <product id or name> <out_dir>
  python update_product_photos.py apply  <spec.json> [--publish] [--dry-run]

export: writes the product's current photos to <out_dir> (current-img.jpg = the first image customers see,
        current-main.jpg = the white-background shot, current-gallery-N.jpg, current-color-<slug>.jpg) and
        prints "PRODUCT {json}" (id, name, collection, specs, desc, colors). Use current-main.jpg as the
        reference photo when regenerating.

apply:  spec.json = {
          "product": "<id or name>",
          "images_dir": "<folder holding the NEW images from gen_product_photos.py>",
          "colors": ["Pitch Black", "Ice Blue"]   # optional: the full ordered colour list wanted afterwards
        }
        What gets replaced, based on which files exist in images_dir:
          conceptual-print-ad*.png -> the first image (img)
          main.png                 -> the white-background shot (gallery[0])
          any other non-colour png -> the rest of the gallery is replaced by them (infographic, size comparison...)
          color-<slug>.png         -> that colour's photo (added as a new colour if it is not in the picker yet)
        Everything not present in images_dir is kept exactly as it is. If "colors" is given, the picker is
        reordered/trimmed to that list (a colour needs either an existing or a new photo).

Prints "RESULT {json}" as its last line on success; "ERROR ..." (non-zero exit) means nothing was written.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import add_product as ap  # noqa: E402  (reuses encode_image, validate, git, slugify, SITE_RE, constants)
import base64  # noqa: E402
import io  # noqa: E402

fail = ap.fail


def load_site():
    text = open(ap.INDEX, encoding="utf8", newline="").read()
    m = ap.SITE_RE.search(text)
    if not m:
        fail("SITE_DATA block not found in index.html")
    return text, m, m.group(2), json.loads(m.group(2))


def find_product(site, ref):
    ref_l = ref.strip().lower()
    hits = [p for p in site["products"] if p["id"].lower() == ref_l]
    if not hits:
        hits = [p for p in site["products"] if p["name"].strip().lower() == ref_l]
    if not hits:
        hits = [p for p in site["products"] if ref_l in p["name"].lower() or ref_l in p["id"].lower()]
    if len(hits) != 1:
        names = [p["name"] for p in (hits or site["products"])]
        fail(("ambiguous" if hits else "no such product") + f" '{ref}'; " + ("matches: " if hits else "live products: ") + str(names))
    return hits[0]


def data_uri_bytes(uri):
    return base64.b64decode(uri.split(",", 1)[1])


def cmd_export(ref, out_dir):
    _, _, _, site = load_site()
    p = find_product(site, ref)
    os.makedirs(out_dir, exist_ok=True)

    def save(name, uri):
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(data_uri_bytes(uri))

    save("current-img.jpg", p["img"])
    if p.get("gallery"):
        save("current-main.jpg", p["gallery"][0])
    else:
        save("current-main.jpg", p["img"])
    for i, g in enumerate(p.get("gallery") or []):
        save(f"current-gallery-{i}.jpg", g)
    for c in p.get("colors") or []:
        save(f"current-color-{ap.slugify(c['name'])}.jpg", c["img"])
    info = {k: p.get(k) for k in ("id", "name", "collection", "price", "specs", "desc")}
    info["colors"] = [c["name"] for c in p.get("colors") or []]
    print("PRODUCT " + json.dumps(info, ensure_ascii=False))


def element_span(site_raw, pid):
    """(start, end) of the product object with this id inside the raw SITE_DATA text (so only it is rewritten)."""
    key = '"products": ['
    pos = site_raw.index(key) + len(key)
    dec = json.JSONDecoder()
    while True:
        while site_raw[pos] in " \t\r\n,":
            pos += 1
        if site_raw[pos] == "]":
            fail(f"product '{pid}' not found in raw SITE_DATA")
        obj, rel_end = dec.raw_decode(site_raw[pos:])
        if obj.get("id") == pid:
            return pos, pos + rel_end
        pos += rel_end


def cmd_apply(spec_path, publish, dry):
    spec = json.load(open(spec_path, encoding="utf8"))
    for k in ("product", "images_dir"):
        if not spec.get(k):
            fail(f"spec missing '{k}'")

    if publish:
        if ap.git("status", "--porcelain", "--", "index.html", "products.json"):
            fail("index.html/products.json have uncommitted local changes - refusing to publish over them")
        ap.git("pull", "--rebase", "--autostash", "origin", "main")

    text, m, site_raw, site = load_site()
    old = find_product(site, spec["product"])
    prod = json.loads(json.dumps(old))  # deep copy

    d = spec["images_dir"]
    files = sorted(f for f in os.listdir(d) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")))
    ad_file = next((f for f in files if f.lower().startswith("conceptual-print-ad")), None)
    main_file = next((f for f in files if f.lower().startswith("main.")), None)
    color_files = [f for f in files if f.lower().startswith("color-")]
    rest = sorted((f for f in files if f not in (ad_file, main_file) and f not in color_files),
                  key=lambda f: ap.gallery_sort_key(f.lower()))
    if not (ad_file or main_file or rest or color_files):
        fail("images_dir has no new images")

    changed = []
    gallery = list(prod.get("gallery") or [])
    # Layout used by add_product.py: img = conceptual ad, gallery[0] = white shot, gallery[1:] = the other listing shots.
    if ad_file:
        prod["img"] = ap.encode_image(os.path.join(d, ad_file), ap.GALLERY_MAX_PX)
        changed.append("ad")
    if main_file:
        new_main = ap.encode_image(os.path.join(d, main_file), ap.GALLERY_MAX_PX)
        if gallery:
            gallery[0] = new_main
        else:
            gallery = [new_main]
        changed.append("main")
    if rest:
        keep_first = gallery[:1]
        gallery = keep_first + [ap.encode_image(os.path.join(d, f), ap.GALLERY_MAX_PX) for f in rest]
        changed.append("listing x%d" % len(rest))
    prod["gallery"] = gallery

    colors = list(prod.get("colors") or [])
    by_slug = {ap.slugify(c["name"]): c for c in colors}
    new_color_slugs = set()
    for f in color_files:
        slug = os.path.splitext(f)[0][len("color-"):].lower()
        img = ap.encode_image(os.path.join(d, f), ap.COLOR_MAX_PX)
        if slug in by_slug:
            by_slug[slug]["img"] = img
        else:
            by_slug[slug] = {"name": slug, "img": img}  # display name fixed up below from spec["colors"]
            colors.append(by_slug[slug])
        new_color_slugs.add(slug)
        changed.append("color " + by_slug[slug]["name"])
    if spec.get("colors"):
        ordered = []
        for cname in spec["colors"]:
            c = by_slug.get(ap.slugify(cname))
            if c is None:
                continue  # no photo for it: skip rather than show a broken swatch
            c["name"] = cname.strip()
            ordered.append(c)
        colors = ordered
    else:  # fix the display name of any brand-new colour that came only from a filename
        for c in colors:
            if c["name"] in new_color_slugs:
                c["name"] = c["name"].replace("-", " ").title()
    prod["colors"] = colors if len(colors) >= 2 else []
    prod["showColors"] = len(colors) >= 2
    prod["imgNote"] = "AI-generated listing photo (Madese Photo Studio) via add-product agent (photos redone)"

    item = json.dumps(prod, indent=1, ensure_ascii=False)
    item = "\n".join(" " + ln for ln in item.split("\n")).replace("</", "<\\/").replace("\n", "\r\n").lstrip(" ")
    s, e = element_span(site_raw, old["id"])
    new_site = site_raw[:s] + item + site_raw[e:]
    new_text = text[: m.start(2)] + new_site + text[m.end(2):]

    products_text = open(ap.PRODUCTS_JSON, encoding="utf8", newline="").read()
    ap.validate(new_text, products_text)
    check = json.loads(ap.SITE_RE.search(new_text).group(2))
    assert len(check["products"]) == len(site["products"])
    assert [p["id"] for p in check["products"]] == [p["id"] for p in site["products"]]
    newp = next(p for p in check["products"] if p["id"] == old["id"])
    for k in ("name", "price", "mrp", "desc", "collection", "stl", "specs"):
        assert newp.get(k) == old.get(k), f"{k} changed unexpectedly"
    assert sum(1 for p in check["products"] if p["id"] == old["id"]) == 1

    result = {"id": old["id"], "name": old["name"], "changed": changed,
              "colors": [c["name"] for c in prod["colors"]], "published": False}
    if dry:
        print("DRY RUN ok - nothing written")
        print("RESULT " + json.dumps(result))
        return
    open(ap.INDEX, "w", encoding="utf8", newline="").write(new_text)

    if publish:
        ap.git("add", "index.html")
        ap.git("commit", "-m", f"Update photos: {old['name']}\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>")
        ap.git("fetch", "origin", "main")
        push = subprocess.run(["git", "push", "origin", "main"], cwd=ap.REPO, capture_output=True, text=True)
        if push.returncode != 0:
            fail("commit made locally but push failed: " + (push.stderr or push.stdout).strip()[:400])
        result["published"] = True
        result["commit"] = ap.git("rev-parse", "--short", "HEAD")
    print("RESULT " + json.dumps(result))


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(a) == 3 and a[0] == "export":
        cmd_export(a[1], a[2])
    elif len(a) == 2 and a[0] == "apply":
        cmd_apply(a[1], "--publish" in sys.argv, "--dry-run" in sys.argv)
    else:
        fail("usage: update_product_photos.py export <product> <out_dir> | apply <spec.json> [--publish] [--dry-run]")


if __name__ == "__main__":
    main()
