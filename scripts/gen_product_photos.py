"""Generate House of Madese product photos for a new product.

Reuses the Gemini wrapper AND the live instruction library from the sibling
Madese Photo Studio project instead of duplicating either here. Run with
THAT project's venv python:
  "C:\\Users\\mayan\\OneDrive\\Desktop\\Madese Photo Studio\\.venv\\Scripts\\python.exe" gen_product_photos.py <input_photo> <product_context> <output_dir>

Generates:
- every instruction in the "Clean Listing Photos" tab of prompts.json
  (currently: Pure White Isolated, usecase infographic, size comparison,
  Color Combo Grid) -> saved as <slug>.png
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
from gemini_client import GeminiImageError, generate_variant  # noqa: E402


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return s or "untitled"


def load_reference_images(rel_paths):
    images = []
    for rel in rel_paths:
        abs_path = os.path.join(PHOTO_STUDIO_DIR, rel)
        if os.path.exists(abs_path):
            images.append(Image.open(abs_path))
    return images or None


def main():
    input_path, context, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    photo = Image.open(input_path)

    data = prompts_store.load()
    clean_listing = data.get("Clean Listing Photos", {}).get("instructions", [])
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

    AD_MODEL = "gemini-3-pro-image"  # best-quality model, used ONLY for the conceptual ad
    jobs = [(inst, i == main_idx) for i, inst in enumerate(clean_listing)]
    if conceptual_ad is not None:
        jobs.append((conceptual_ad, False))
    else:
        print("FAIL conceptual-print-ad: no 'Conceptual Print Ad' instruction found in 'Lifestyle Shots' tab")

    for inst, is_main in jobs:
        title = inst.get("title") or inst["id"]
        slug = "main" if is_main else slugify(title)
        try:
            result = generate_variant(
                photo,
                inst["text"],
                reference_images=load_reference_images(inst.get("reference_images", [])),
                product_context=context,
                model=AD_MODEL if inst is conceptual_ad else None,
            )
            result.save(os.path.join(out_dir, f"{slug}.png"))
            print(f"OK {slug}" + (" (main)" if is_main else ""))
        except GeminiImageError as e:
            print(f"FAIL {slug}: {e}")


if __name__ == "__main__":
    main()
