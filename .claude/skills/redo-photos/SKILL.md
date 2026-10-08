---
name: redo-photos
description: Regenerate and replace the photos of an ALREADY-LIVE House of Madese product (all of them, or just the ad / white shot / listing shots / some colours) without creating a duplicate. Use when Mayank says /redo <product> <what to change>, whether typed here or relayed by the Telegram agent.
---

# Redo photos for a live product

Input: a product name (or id) + what Mayank wants changed, in his words (e.g. `Wicker Glow Retro Lamp, make the colours more vibrant`, `Bean Pod only the blue`, `new ad idea, something funnier`), optionally a NEW reference photo path. Fully automatic: never ask questions, never publish a new product. Only the photos change; name, price, description, collection and id stay as they are.

Work in `C:\Users\mayan\OneDrive\Desktop\House of Madese`. Python for every script below is `C:\Users\mayan\OneDrive\Desktop\Madese Photo Studio\.venv\Scripts\python.exe`. Work dir: `C:\Users\mayan\AppData\Local\Temp\madese-agent\redo-<slug>-<timestamp>`.

## 1. Find the product and its current photos
```
python scripts\update_product_photos.py export "<product>" "<work dir>\cur"
```
Prints `PRODUCT {...}` (id, name, specs, desc, current colour names) and saves `current-img.jpg` (ad), `current-main.jpg`, `current-gallery-N.jpg`, `current-color-<slug>.jpg`. An `ERROR` line (unknown/ambiguous product) -> stop and report it with the list it printed. Look at `current-img.jpg`, `current-main.jpg` and a colour photo with Read so you know what exists and what he is unhappy about.

## 2. Decide scope from his words
- Colours only ("colours", "variants", "the blue one") -> `--only=colors`
- Ad only ("ad", "poster", "headline") -> `--only=ad`
- White shot / listing shots -> `--only=main` / `--only=listing`
- Vague ("redo the photos") -> everything (omit `--only`)
Default to the **reference photo**: his new photo if given, else `current-main.jpg` (for ad/listing/colour redos that is the cleanest view of the product). Build `product_context` from the PRODUCT specs + desc (factual, specific, as in add-product step 3).
Colours: if he named colours, use exactly those (names from the add-product filament list); "only the blue" = just that colour (`Ice Blue`). If he is unhappy with the colour looks without naming any, regenerate the SAME colours the product has now (the PRODUCT colour names), adding a note in the context about what to fix (e.g. more saturated, truer to the filament). If the product has no colour picker yet and he asks for colours, pick 4 per add-product step 3. For a new ad, invent a NEW concept + witty headline/subline per add-product's rules, different from the current ad.

## 3. Generate
```
python scripts\gen_product_photos.py "<reference photo>" "<product_context>" "<work dir>\new" "<ad concept or empty>" "<colors or empty>" --only=<parts>
```
Prints `OK`/`FAIL` per image; retry once if everything failed. Whatever FAILs is simply left unchanged on the site. When only regenerating colours from `current-main.jpg`, the script uses that as the base because `new\main.png` doesn't exist.

## 4. Swap them in (no duplicate)
Write `<work dir>\spec.json`: `{"product": "<id>", "images_dir": "<work dir>\new"}`; add `"colors": [...]` only if he wants the picker to end up with exactly that ordered list (e.g. replacing the set); omit it to just refresh/add the colours that were generated and keep the others.
```
python scripts\update_product_photos.py apply "<work dir>\spec.json" --publish
```
It replaces only the product's images in place, validates, commits "Update photos: <name>" and pushes (Vercel redeploys in ~1 min). Last line `RESULT {...}`; `ERROR` means nothing was published. Never run add_product.py for this.

## 5. Final report (sent verbatim on Telegram; short, plain, no tables)
```
✅ Photos updated: <name>
Changed: <what was replaced, e.g. 3 colour photos (Pitch Black, Ice Blue, ...) / the ad / ...>
Kept as is: description, price, other photos
<one line on what you changed in the approach, e.g. new ad idea + headline, or "more saturated colours">
Live in ~1 min: https://www.houseofmadese.com/ (send /redo again with a note to tweak further)
```
Failure: start with `❌ NOT updated:` and the one-line reason.
