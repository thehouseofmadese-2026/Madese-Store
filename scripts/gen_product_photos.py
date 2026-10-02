"""Generate House of Madese listing + lifestyle photos for a new product.

Reuses the Gemini wrapper from the sibling Madese Photo Studio project instead
of duplicating API/key handling here. Run with THAT project's venv python:
  "C:\\Users\\mayan\\OneDrive\\Desktop\\Madese Photo Studio\\.venv\\Scripts\\python.exe" gen_product_photos.py <input_photo> <product_context> <output_dir>

Writes <output_dir>/main.png (clean white-background listing photo) and
<output_dir>/lifestyle.png (in-use lifestyle shot). Prints "OK <name>" or
"FAIL <name>: <reason>" per image so the caller can tell which succeeded.
"""
import os
import sys

PHOTO_STUDIO_DIR = r"C:\Users\mayan\OneDrive\Desktop\Madese Photo Studio"
sys.path.insert(0, PHOTO_STUDIO_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(PHOTO_STUDIO_DIR, ".env"))

from PIL import Image  # noqa: E402
from gemini_client import GeminiImageError, generate_variant  # noqa: E402

MAIN_INSTRUCTION = (
    "Isolate this product on a pure white seamless background, bright even "
    "studio lighting, no visible shadows, straight-on e-commerce catalog style."
)
LIFESTYLE_INSTRUCTION = (
    "Show this product in a realistic everyday use setting on a real desk or "
    "surface, warm natural lighting, shallow depth of field, lifestyle product "
    "photography style."
)


def main():
    input_path, context, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    photo = Image.open(input_path)

    for name, instruction in (("main", MAIN_INSTRUCTION), ("lifestyle", LIFESTYLE_INSTRUCTION)):
        try:
            result = generate_variant(photo, instruction, product_context=context)
            result.save(os.path.join(out_dir, f"{name}.png"))
            print(f"OK {name}")
        except GeminiImageError as e:
            print(f"FAIL {name}: {e}")


if __name__ == "__main__":
    main()
