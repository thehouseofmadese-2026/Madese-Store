"""Generate House of Madese product photos for a new product.

Reuses the Gemini wrapper AND the live instruction library from the sibling
Madese Photo Studio project instead of duplicating either here. Run with
THAT project's venv python:
  "C:\\Users\\mayan\\OneDrive\\Desktop\\Madese Photo Studio\\.venv\\Scripts\\python.exe" gen_product_photos.py <input_photo> <product_context> <output_dir> [ad_concept] [colors]

Generates (all 1:1 squares - the site shows every product image in a square frame):
- every instruction in the "Clean Listing Photos" tab of prompts.json EXCEPT the
  "Color Combo Grid" (currently: Pure White Isolated, usecase infographic, size
  comparison) -> saved as <slug>.png
- one single-colour photo per entry in `colors` -> saved as color-<slug>.png;
  add_product.py turns these into the product's Color picker so customers can
  choose a colour and add it to the cart. `colors` is a comma-separated list of
  filament colours Claude picked, e.g. "Pitch Black, Nuclear Red + Pitch Black, Ice Blue"
  ("A + B" = body in A with accents in B). Names must come from FILAMENTS below.
- the "Conceptual Print Ad" instruction from the "Lifestyle Shots" tab
  (with its own reference images, read straight from prompts.json) -> saved
  as conceptual-print-ad.png

Whichever Clean Listing instruction is titled "Pure White Isolated" (or the
first one, if that title isn't found) is also saved as main.png — this is
the plain card/thumbnail photo; everything else is gallery material.

Prints "OK <slug>" / "FAIL <slug>: <reason>" per image so the caller can
tell which succeeded without the whole batch failing over one bad call.
"""
import os
import re
import sys

PHOTO_STUDIO_DIR = r"C:\Users\mayan\OneDrive\Desktop\Madese Photo Studio"
sys.path.insert(0, PHOTO_STUDIO_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(PHOTO_STUDIO_DIR, ".env"))

from PIL import Image  # noqa: E402
import prompts_store  # noqa: E402
import gemini_client  # noqa: E402
from gemini_client import GeminiImageError, generate_variant  # noqa: E402


AD_CONCEPT_NOTE = (
    "\n\nCREATIVE CONCEPT FOR THIS PRODUCT (already decided by the art director - do NOT invent a different idea; "
    "draw exactly this, keeping the product accurate and the composition simple):\n{concept}\n\n"
    "TEXT RULES FOR THIS AD (these override the 'extremely short headline' / 'no unnecessary text' lines above): "
    "the ad is witty - a pun, a dry sarcastic jab or a smart one-liner. Render the HEADLINE exactly as written in the concept, "
    "in large clean sans-serif. If the concept gives a SUBLINE, render it exactly as written in small type beneath or beside the headline. "
    "If it gives a SCENE TEXT (a sticky note, label, tag, sign or speech bubble in the scene), render that exactly too. "
    "Those, plus a subtle 'HOUSE OF MADESE' signature, are the ONLY text in the image. Copy every word and letter exactly, "
    "with no misspellings and no extra words. Keep the text legible and well placed in the negative space, never covering the product."
)

# The filament colours Mayank owns (lowercase name -> (display name, hex)). Claude picks colour names from this list.
FILAMENTS = {
    "pitch black": ("Pitch Black", "#0E0E10"),
    "pure white": ("Pure White", "#F1ECE1"),
    "midnight gray": ("Midnight Gray", "#383F44"),
    "nuclear red": ("Nuclear Red", "#BB1E10"),
    "outrageous orange": ("Outrageous Orange", "#E25303"),
    "lemon yellow": ("Lemon Yellow", "#F9A800"),
    "rust copper": ("Rust Copper", "#8D4931"),
    "chocolate brown": ("Chocolate Brown", "#4C2B20"),
    "ice blue": ("Ice Blue", "#007CB0"),
    "sakura pink": ("Sakura Pink", "#FFB7C5"),
    "arctic": ("Arctic (Translucent)", "#7CB7A5"),
    "arctic (translucent)": ("Arctic (Translucent)", "#7CB7A5"),
    "orange (translucent)": ("Orange (Translucent)", "#FF9D5B"),
    "translucent orange": ("Orange (Translucent)", "#FF9D5B"),
    "transparent": ("Transparent (High-Speed)", "#F5F5F5"),
    "transparent (high-speed)": ("Transparent (High-Speed)", "#F5F5F5"),
}

COLOR_PROMPT = (
    "Using the uploaded product photo as the exact reference, show this SAME 3D printed product re-coloured as follows: {spec}. "
    "Keep everything else identical: same camera angle, framing, proportions, shape, surface texture and subtle PLA layer lines, "
    "pure white seamless background, bright even studio lighting, no visible shadows. Only the filament colour changes. "
    "Use the exact hex colours given; realistic matte PLA finish. One single product, centred, no text, no grid, no props."
)

# Every product image on the site is shown in a 1:1 square (.card-img / .pdp-main-img are aspect-ratio 1/1, cover-cropped),
# so ask Gemini for squares - otherwise it follows the reference photo's shape and the site crops the product.
IMAGE_ASPECT_RATIO = "1:1"


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return s or "untitled"


def force_square_output():
    """Make every Gemini call from this process request a 1:1 image. gemini_client (shared with the Photo Studio app)
    is left untouched; we wrap generate_content on its cached client instead."""
    from google.genai import types
    client = gemini_client.get_client()
    orig = client.models.generate_content
    cfg = types.GenerateContentConfig(image_config=types.ImageConfig(aspect_ratio=IMAGE_ASPECT_RATIO))
    client.models.generate_content = lambda **kw: orig(config=cfg, **kw)


def color_jobs(colors_arg):
    """'Pitch Black, Nuclear Red + Pitch Black' -> [(file slug, display name, prompt spec)]; unknown names raise ValueError."""
    jobs = []
    for raw in colors_arg.split(","):
        parts = [x.strip() for x in raw.split("+") if x.strip()]
        if not parts:
            continue
        found = []
        for x in parts:
            if x.lower() not in FILAMENTS:
                raise ValueError(f"unknown filament colour '{x}'")
            found.append(FILAMENTS[x.lower()])
        name = " + ".join(n for n, _ in found)
        if len(found) == 1:
            spec = f"the whole product in {found[0][0]} ({found[0][1]})"
        else:
            spec = (f"main body in {found[0][0]} ({found[0][1]}) with the secondary/accent parts in "
                    + " and ".join(f"{n} ({h})" for n, h in found[1:]))
        jobs.append((slugify(name), name, spec))
    return jobs


def load_reference_images(rel_paths):
    images = []
    for rel in rel_paths:
        abs_path = os.path.join(PHOTO_STUDIO_DIR, rel)
        if os.path.exists(abs_path):
            images.append(Image.open(abs_path))
    return images or None


def main():
    only = next((a[7:].lower().split(",") for a in sys.argv[1:] if a.startswith("--only=")), None)
    argv = [a for a in sys.argv if not a.startswith("--only=")]
    input_path, context, out_dir = argv[1], argv[2], argv[3]
    ad_concept = argv[4].strip() if len(argv) > 4 else ""
    colors_arg = argv[5].strip() if len(argv) > 5 else ""
    os.makedirs(out_dir, exist_ok=True)
    photo = Image.open(input_path)
    force_square_output()

    data = prompts_store.load()
    # The 2x2 Color Combo Grid is replaced by one single-colour photo per colour (below), which the Color picker needs.
    clean_listing = [i for i in data.get("Clean Listing Photos", {}).get("instructions", [])
                     if "color combo" not in i.get("title", "").lower()]
    lifestyle = data.get("Lifestyle Shots", {}).get("instructions", [])

    if not clean_listing:
        print("FAIL setup: no instructions found in 'Clean Listing Photos' tab")
        return

    main_idx = next(
        (i for i, inst in enumerate(clean_listing) if "pure white" in inst.get("title", "").lower()),
        0,
    )

    conceptual_ad = next(
        (inst for inst in lifestyle if "conceptual" in inst.get("title", "").lower() and "ad" in inst.get("title", "").lower()),
        None,
    )

    AD_MODEL = "gemini-3.1-flash-image"  # mid-tier (Balanced) model, used ONLY for the conceptual ad
    jobs = [(inst, i == main_idx) for i, inst in enumerate(clean_listing)]
    if conceptual_ad is not None:
        jobs.append((conceptual_ad, False))
    else:
        print("FAIL conceptual-print-ad: no 'Conceptual Print Ad' instruction found in 'Lifestyle Shots' tab")

    for inst, is_main in jobs:
        title = inst.get("title") or inst["id"]
        slug = "main" if is_main else slugify(title)
        part = "main" if is_main else ("ad" if inst is conceptual_ad else "listing")
        if only and part not in only:
            continue
        try:
            result = generate_variant(
                photo,
                inst["text"] + (AD_CONCEPT_NOTE.format(concept=ad_concept) if (inst is conceptual_ad and ad_concept) else ""),
                reference_images=load_reference_images(inst.get("reference_images", [])),
                product_context=context,
                model=AD_MODEL if inst is conceptual_ad else None,
            )
            result.save(os.path.join(out_dir, f"{slug}.png"))
            print(f"OK {slug}" + (" (main)" if is_main else ""))
        except GeminiImageError as e:
            print(f"FAIL {slug}: {e}")

    # One single-colour photo per colour, re-coloured from the white-background shot so they all stay consistent.
    if colors_arg and (not only or "colors" in only):
        try:
            cjobs = color_jobs(colors_arg)
        except ValueError as e:
            print(f"FAIL colors: {e}")
            return
        main_path = os.path.join(out_dir, "main.png")
        base = Image.open(main_path) if os.path.exists(main_path) else photo
        for slug, name, spec in cjobs:
            try:
                result = generate_variant(base, COLOR_PROMPT.format(spec=spec), product_context=context)
                result.save(os.path.join(out_dir, f"color-{slug}.png"))
                print(f"OK color-{slug} ({name})")
            except GeminiImageError as e:
                print(f"FAIL color-{slug}: {e}")


if __name__ == "__main__":
    main()
