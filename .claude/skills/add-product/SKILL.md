---
name: add-product
description: Add a new product to the House of Madese catalogue from a source link (MakerWorld/Printables/etc.) and a reference photo. Generates 5 Gemini photos, writes a witty satirical description, and publishes live. Use when Mayank sends a product link + photo (price/collection optional), whether typed here or relayed by the Telegram agent.
---

# Add a new product to House of Madese

Input (any order, in Mayank's words; often relayed by the Telegram bot as a block of text + a local photo path):
- a **source link** (usually MakerWorld / Printables)
- one or more **reference photo path(s)**
- OPTIONAL in the caption: a **price** (rupees), a **collection** name, an MRP/discount, a name override, a note. Examples: `499 lamps`, `price 349, desk`, `call it Bean Pod`.

He wants this **fully automatic**: never stop to ask for approval before publishing. If something is wrong he fixes it in the site's Admin → Products. Only stop and ask when it is truly impossible to proceed: no photo was given at all, or the photo file doesn't exist. Everything else (unreadable link, no price, no collection) has a defined fallback below.

Work in `C:\Users\mayan\OneDrive\Desktop\House of Madese`. Don't touch the sibling Madese Photo Studio project except by running its venv Python as shown below. Don't edit `api/*`.

## Step 1 — Research the link
Work out what the product is, what it's for, size/material if stated, anything that makes the description honest. MakerWorld/Printables are JS-rendered:
1. Try `WebFetch` first.
2. If empty/unusable, use the Chrome tools (load via `ToolSearch` if deferred): navigate, then `get_page_text`.
3. If still unreadable, infer from the photo + caption and say so in the final report. Don't block.

## Step 2 — Collection + price (infer unless Mayank gave them)
Read the live data (never trust a memorised list). This prints collections and each product's collection/price/mrp:
```
python -c "import re,json;d=json.loads(re.search(r'id=\"SITE_DATA\">(.*?)</script>',open('index.html',encoding='utf8').read(),re.S).group(1));print([c['name'] for c in d['collections']]);[print(p['collection'],p['price'],p['mrp'],p['name']) for p in d['products']]"
```
- **Collection**: if he named one, match it to the closest live name (case-insensitive, typos OK). If not, pick the closest-fit existing collection for what the product *is* (lamps → Lamps, pen stands/phone stands/desk gear → Desktop Needs, personalised/figures/keychains → Custom, etc.). Only if truly nothing fits, use the least-wrong one and flag it in the report.
- **Price**: if he gave one, use it exactly. Otherwise suggest one from comparable live products (same collection, similar size/complexity; this is a small-batch 3D-print shop, typical range ₹399–₹1299). Round to a price ending in 9. **MRP** = price × ~1.3 rounded to end in 9 (or his MRP if given). In the report, state clearly that the price was inferred so he can override it.

## Step 3 — Generate the photos (Gemini via Madese Photo Studio)
Output dir: `C:\Users\mayan\AppData\Local\Temp\madese-agent\<slug>-<timestamp>` (create it).
```
"C:\Users\mayan\OneDrive\Desktop\Madese Photo Studio\.venv\Scripts\python.exe" "C:\Users\mayan\OneDrive\Desktop\House of Madese\scripts\gen_product_photos.py" "<photo path>" "<1-2 sentence product_context from step 1>" "<output dir>" "<ad concept>"
```
`<ad concept>` is the 4th argument: the conceptual-ad idea YOU invent for this specific product (see below). Always pass it.

Generates every "Clean Listing Photos" instruction (4 currently; "Pure White Isolated" → `main.png`) plus the "Conceptual Print Ad" → 5 images. Prints `OK <slug>` / `FAIL <slug>: <reason>`. Run it with a generous timeout (up to 10 min). If an image FAILs, retry that whole script once only if **3 or more** failed; otherwise carry on with what you have. If `main.png` is missing the publish script falls back to his original photo.

**Ad concept (do this before running the script).** The image model is poor at inventing ideas but good at drawing one it is handed, so you decide the idea. Write 2-4 sentences covering: (1) ONE simple visual metaphor rooted in what this product physically does or its shape, easily understood in a glance; (2) exactly how the product appears in the scene (it must stay clearly visible, accurate, and the hero); (3) a headline of 2-6 words that is clever but plainly readable, no puns that need explaining; (4) a background colour that complements the product. Keep it drawable: one product, at most 1-2 supporting elements, no crowds, no tiny text beyond the headline. Sanity-check: could a stranger explain the ad in one sentence? If not, simplify. Example for a pen stand: "The pen stand is the skyline of a tiny city: the pens are towers rising from it against a warm cream background. Headline: 'Your Desk, Skyline.'"

Make `product_context` factual and specific (what it is, how it's used, rough size) so Gemini doesn't mis-identify the object. The infographic prompt says to replace example callouts with the product's real features, so put 3–4 real features in the context too.

## Step 4 — Write the spec
Create `<output dir>/spec.json`:
```json
{
  "name": "...", "collection": "...", "subcollection": "", "price": 0, "mrp": 0,
  "specs": ["2-5 short FACTUAL bullets: material, size, use"],
  "desc": "...", "stl": "<the source link>",
  "images_dir": "<output dir>", "fallback_photo": "<his original photo path>"
}
```
**Name**: his override, else a short, brandable name (existing style: "Desk Rebel Pen Stand", "Cumulis Table Lamp", "Grip Halo MagSafe Stand" — a catchy first word + plain product noun). Don't copy a third-party's trademarked name.

**Description voice (witty, a little satirical, funny) — rules:**
- Structure: a one-line funny hook → 2–3 short paragraphs of deadpan, self-aware humour about the problem the product solves or the person who needs it → then a plain, honest facts list (4–6 lines, each its own line, no markdown symbols) covering material, size, how it's used, anything included.
- Humour comes from observation (desk chaos, cable spaghetti, "your keys deserve better"), not insults, nothing crude, nothing political, no mocking customers or other brands.
- **Honesty over jokes**: never invent specs, certifications, dimensions, safety claims or "included" items that you didn't read from the link or see in the photo. Jokes can exaggerate the *situation*, never the *product*. Mention it's 3D printed in Ichalkaranji layer by layer where it fits naturally.
- Length ~90–150 words. Skim 2 existing `desc` fields first so it still sounds like House of Madese. Use real newlines (`\n\n`) between paragraphs.

## Step 5 — Publish (script does everything mechanical)
```
"C:\Users\mayan\OneDrive\Desktop\Madese Photo Studio\.venv\Scripts\python.exe" "C:\Users\mayan\OneDrive\Desktop\House of Madese\scripts\add_product.py" "<output dir>\spec.json" --publish
```
It compresses + base64-encodes the images, splices the product into `SITE_DATA` in `index.html` (leaving the rest of the file untouched), appends to `products.json` (needed so checkout accepts the price), validates (`JSON.parse` + `node --check`), does `git pull --rebase`, commits only `index.html` + `products.json`, and pushes to `main` (Vercel auto-deploys in ~1 min). Last line is `RESULT {...}`; `ERROR ...` means nothing was published. If it fails on a fixable cause (bad collection name, etc.), fix the spec and rerun once.

## Step 6 — Final report (this text is sent to Mayank on Telegram, so keep it short and plain)
Exactly this shape, no markdown tables:
```
✅ Live: <name>
Collection: <collection> · ₹<price> (MRP ₹<mrp>) [say "price inferred" if you chose it]
Photos: <n>/5 generated (<list any that failed by name>)
Ad idea: <the concept in one short sentence + headline>
Link read: yes/no
Live in ~1 min: https://www.houseofmadese.com/ (Admin → Products to tweak anything)
```
If the publish failed, start with `❌ NOT published:` and the reason in one line.
