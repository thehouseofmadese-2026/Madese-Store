---
name: add-product
description: Add a new product to the House of Madese catalogue from a source link (MakerWorld/Printables/etc.), a reference photo, a price, and a collection. Use when Mayank gives a product link + photo + price + collection and wants it added to the live site.
---

# Add a new product to House of Madese

Mayank will give you, in any order, in his own words:
- a **source link** (usually MakerWorld or Printables — the 3D model page for the product)
- one or more **reference photo(s)** of the actual printed object
- a **price** (rupees)
- a **collection** name it belongs in (e.g. Custom, Lamps, Desktop Needs, Girlies, Homemaker, Adult Money — but always confirm against the live list in step 2, don't assume this list is current)
- optionally: a name override, a short note, a subcollection, a discount/MRP

He wants this fully automatic — do not stop to ask him to approve the draft before publishing. He already knows that if anything comes out wrong, he can fix it afterward in the site's own Admin → Products panel (it's just editing the same SITE_DATA this skill writes). Only stop and ask him directly if something is genuinely ambiguous and guessing wrong would be a real content error (e.g. no collection name he gave matches anything on the live site, or no photo was provided at all).

Work in this project (`C:\Users\mayan\OneDrive\Desktop\House of Madese`). Do not touch the sibling Madese Photo Studio project's files except to read `gemini_client.py`'s public function (already wired for you — see step 3).

## Step 1 — Research the source link

Figure out what the product actually is: what it's for, how it's used, rough size/material if stated, anything that would help write an honest product description. MakerWorld/Printables pages are JS-rendered, so:
1. Try `WebFetch` on the link first.
2. If that comes back empty/unusable, use the Chrome tools instead (load them via `ToolSearch` if deferred): navigate to the link, then `get_page_text` or `read_page` to pull the title, description, and any print/use details.

If the link can't be read at all, don't block — fall back to inferring from the photo + whatever Mayank told you in his message, and mention in your final summary that the link couldn't be read.

## Step 2 — Confirm the collection

Read the live collection list out of `index.html`'s embedded data so you're matching against what's actually on the site right now, not a memorized list:

```
grep -n '"collections"' index.html
```

Then read that JSON region (it's inside the `<script type="application/json" id="SITE_DATA">` block starting around line 801) to get the real `collections` array (each has a `name`, and possibly `hasSubcollections`/`subcollections`). Match what Mayank said to the closest existing `collection.name` (case-insensitive, minor typos OK). If nothing matches at all, that's the one case worth asking him directly rather than guessing — getting the collection wrong misfiles the product on the storefront.

If the matched collection has `hasSubcollections: true` and Mayank mentioned a subcollection, match it the same way; otherwise leave `subcollection` as `""`.

## Step 3 — Generate photos with Gemini (via Madese Photo Studio)

Don't reimplement Gemini calls here — this project has no Gemini key of its own by design. Reuse the wrapper already built in the sibling project by running `scripts/gen_product_photos.py` with **that project's venv Python**:

```
"C:\Users\mayan\OneDrive\Desktop\Madese Photo Studio\.venv\Scripts\python.exe" "C:\Users\mayan\OneDrive\Desktop\House of Madese\scripts\gen_product_photos.py" "<path to Mayank's reference photo>" "<one or two sentence product_context from step 1>" "<scratchpad output dir>"
```

This writes `main.png` (clean white-background listing photo) and `lifestyle.png` (in-use lifestyle shot) into the output dir, and prints `OK <name>` / `FAIL <name>: <reason>` per image. Use the scratchpad directory for `<output dir>`.

- If `main.png` succeeds, that becomes the product's `img`.
- If it fails, fall back to using Mayank's original reference photo as `img` instead (don't block the whole task over one failed generation — note the failure in your final summary).
- If `lifestyle.png` succeeds, add it to `gallery`; if it fails, just skip it (gallery can be shorter, that's fine).

## Step 4 — Build the product object

Base64-encode each final image as a data URL (`data:image/png;base64,<...>`) — that's how every existing product photo is stored (no external image hosting in this project). Then build an object matching the existing schema exactly (see any entry in `SITE_DATA.products` for the live shape):

```json
{
  "id": "<kebab-case slug of the name, deduped against existing ids by appending -2, -3, ... if it collides>",
  "name": "<product name — from Mayank's override if he gave one, else the best name from your research>",
  "collection": "<matched collection.name from step 2>",
  "subcollection": "<matched subcollection or \"\">",
  "price": <the number Mayank gave>,
  "mrp": <same as price unless Mayank told you a discount/MRP>,
  "specs": ["<2-5 short factual bullets from your research — material, size, use case, etc.>"],
  "img": "<base64 data URL from step 3>",
  "imgNote": "<short internal note, doesn't show to customers once img is set>",
  "desc": "<1-3 sentence description in the site's existing voice — skim a couple of existing products' desc fields first to match tone>",
  "gallery": ["<base64 data URL(s), e.g. the lifestyle shot, if any>"],
  "variants": [],
  "showVariants": false,
  "colors": [],
  "showColors": false,
  "stl": "<the source link Mayank gave — reuses the existing admin-only STL-link field for exactly this purpose>"
}
```

## Step 5 — Write it into the site

1. Read the `products.json` file at the repo root and the relevant region of `index.html` around `id="SITE_DATA"` (don't read the whole 1.7MB file — it's mostly base64 image data; use `grep -n` to find line ranges first, then targeted `Read` with `offset`/`limit`, or `Edit` with a unique anchor string near the end of the `products` array).
2. Append the new product object to the `products` array inside the `SITE_DATA` JSON block in `index.html`.
3. Append `{ "id": "...", "name": "...", "price": ... }` to `products.json` (this is what the backend uses to verify prices server-side — skipping this means checkout will reject orders for the new product).

## Step 6 — Validate before publishing

Both of these must pass before you commit anything:
```
node --check <extracted main <script> block>
```
and parse the `SITE_DATA` JSON text with `JSON.parse` (e.g. via a quick `node -e`) — same for `products.json`. This matches how every other edit to this file is validated; don't skip it.

## Step 7 — Publish

```
git add index.html products.json
git status --short
git fetch origin main
git commit -m "Add product: <name>"
git push origin main
```
Vercel auto-deploys on push, live in ~1 minute.

## Step 8 — Report back

Tell Mayank, briefly: product name, collection (+ subcollection if any), price, whether both photos generated successfully or one fell back, whether the link could be read, and that it's live. Remind him Admin → Products is there if anything needs a tweak.
