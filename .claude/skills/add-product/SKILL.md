---
name: add-product
description: Add a new product to the House of Madese catalogue from a source link (MakerWorld/Printables/etc.) and a reference photo. Generates Gemini photos (incl. one per colour option), writes a witty satirical description, and publishes live. Use when Mayank sends a product link + photo (price/collection optional), whether typed here or relayed by the Telegram agent.
---

# Add a new product to House of Madese

Input (any order, in Mayank's words; often relayed by the Telegram bot as a block of text + a local photo path):
- a **source link** (usually MakerWorld / Printables)
- one or more **reference photo path(s)**
- OPTIONAL in the caption: a **price** (rupees), a **collection** name, an MRP/discount, a name override, and a **product note** (free text in his own words explaining what the product is and what it does, e.g. `99 homemaker. It's a screw-down clip that seals coffee bags, the knob twists to tighten`). Examples: `499 lamps`, `price 349, desk`, `call it Bean Pod`.
- **The product note is the source of truth.** Anything in his message that isn't the link, a price, a collection or a name is the note. If it exists, it beats what you read from the link and what you guess from the photo: use it for `product_context`, the specs bullets, the ad concept and the description, and never contradict it. Link/photo details may only ADD to it.

He wants this **fully automatic**: never stop to ask for approval before publishing. If something is wrong he fixes it in the site's Admin → Products. Only stop and ask when it is truly impossible to proceed: no photo was given at all, or the photo file doesn't exist. Everything else (unreadable link, no price, no collection) has a defined fallback below.

Work in `C:\Users\mayan\OneDrive\Desktop\House of Madese`. Don't touch the sibling Madese Photo Studio project except by running its venv Python as shown below. Don't edit `api/*`.

## Step 1 — Research the link
Work out what the product is, what it's for, size/material if stated, anything that makes the description honest. MakerWorld/Printables are JS-rendered, so a bare `WebFetch` often returns only a shell. Count the link as READ only if you got the model's real title AND its description text (what it does, dimensions, print notes); a page title alone, a login wall or a generic site blurb is NOT a read.
1. Try `WebFetch` on the link (drop the `?from=...#...` tracking tail).
2. If it isn't a real read, use the Chrome tools (load via `ToolSearch` if deferred, `mcp__claude-in-chrome__*`): open the link in a new tab, wait for it to render, then `get_page_text`; scroll/read again if the description is collapsed.
3. If still not a real read, fall back to his note + the photo, and say clearly in the report that the link could NOT be read (see step 6) so he can add a note and resend. Don't block.
When you read the link, pull out concrete facts (what it does, how it works, size, parts, print settings) and let them shape the specs and description. Do not pad the specs with generic filler like "durable plastic" or invent shapes you can't see.

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
"C:\Users\mayan\OneDrive\Desktop\Madese Photo Studio\.venv\Scripts\python.exe" "C:\Users\mayan\OneDrive\Desktop\House of Madese\scripts\gen_product_photos.py" "<photo path>" "<1-2 sentence product_context from step 1>" "<output dir>" "<ad concept>" "<colors>"
```
`<ad concept>` (4th argument) is the conceptual-ad idea YOU invent for this specific product (see below). `<colors>` (5th) is the colour options YOU pick (see below). Always pass both.

Generates (all as 1:1 squares, because the site shows every product image in a square frame, cover-cropped): every "Clean Listing Photos" instruction except the old 2x2 colour grid (currently "Pure White Isolated" → `main.png`, usecase infographic, size comparison), the "Conceptual Print Ad", and one single-colour photo per colour → `color-<slug>.png`. Prints `OK <slug>` / `FAIL <slug>: <reason>`. Run it with a generous timeout (up to 15 min). If **3 or more** images FAIL, retry the whole script once; otherwise carry on with what you have. If `main.png` is missing the publish script falls back to his original photo.

**Colour options (do this before running the script).** Customers pick a colour on the product page and add that colour to the cart, so choose colours that genuinely suit the product. Pick **4** (3 if the product has an obviously fixed look, e.g. a photo lithophane lamp; never fewer than 2) from ONLY these filaments: Pitch Black, Pure White, Midnight Gray, Nuclear Red, Outrageous Orange, Lemon Yellow, Rust Copper, Chocolate Brown, Ice Blue, Sakura Pink, Arctic (Translucent), Orange (Translucent), Transparent (High-Speed). Give them as one comma-separated string. Use "A + B" for a two-colour combo (body A, accents B) only when the product has separate parts that can take a second colour, e.g. `"Pitch Black, Nuclear Red + Pitch Black, Ice Blue, Sakura Pink"`. Mix safe bestsellers (black, white) with distinctive ones. Exact names only; an unknown name fails the colour step.

**Ad concept (do this before running the script).** The image model is poor at inventing ideas but good at drawing one it is handed, so you decide the idea. Write 2-4 sentences covering: (1) ONE simple visual metaphor rooted in what this product physically does or its shape, easily understood in a glance; (2) exactly how the product appears in the scene (it must stay clearly visible, accurate, and the hero); (3) the **witty copy** (below); (4) a background colour that complements the product. Keep it drawable: one product, at most 1-2 supporting elements, no crowds. Sanity-check: could a stranger explain the ad in one sentence? If not, simplify.

**Witty copy.** The ad must read as witty, not just pretty: the words are half the joke. Write, labelled exactly like this inside the concept text:
- `Headline:` 2-6 words, a pun, a dry sarcastic jab or a smart one-liner that plays off the visual (the picture and the words should land together). The pun must work on the first read, with no explaining needed.
- `Subline:` (optional but encouraged) one tiny deadpan or sarcastic aside, max ~8 words, that twists the headline, e.g. a fake disclaimer or a mock-modest brag.
- `Scene text:` (optional, at most one) a witty note written on something in the scene (sticky note, tag, label), max ~5 words.
Rules: nothing crude, political or mocking customers/other brands; keep every word easy to spell, since the image model must render the letters exactly; total text beyond the "HOUSE OF MADESE" signature stays under ~15 words. Don't make claims that aren't true of the product.
Example for a pen stand: "The pen stand is the skyline of a tiny city: the pens are towers rising from it against a warm cream background. Headline: 'Your Desk, Skyline.' Subline: 'Zoning approved by nobody.'" Example for a bag clip: "The clip bites a bag shut like a tiny crocodile on a deep teal background. Headline: 'Snap Judgement.' Subline: 'Stale chips filed a complaint.'"

Make `product_context` factual and specific (what it is, how it's used, rough size) so Gemini doesn't mis-identify the object. The infographic prompt says to replace example callouts with the product's real features, so put 3–4 real features in the context too.

## Step 4 — Write the spec
Create `<output dir>/spec.json`:
```json
{
  "name": "...", "collection": "...", "subcollection": "", "price": 0, "mrp": 0,
  "colors": ["Pitch Black", "Nuclear Red + Pitch Black"],
  "specs": ["2-5 short FACTUAL bullets: material, size, use"],
  "desc": "...", "stl": "<the source link>",
  "images_dir": "<output dir>", "fallback_photo": "<his original photo path>"
}
```
`colors` = the same colour names you passed to the photo script, in the same order, spelled identically (the publish script matches each to its `color-<slug>.png`; colours whose photo failed are dropped, and the Color picker only appears with 2+ left). It makes a Color picker on the product page so customers can buy the colour they want; every colour costs the same.

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
Photos: <n> generated (<list any that failed by name>)
Colors: <the colour options now live in the picker, or "none">
Ad idea: <the concept in one short sentence + headline + subline>
Link read: yes / partial / NO - <one line on what you learned from it, or "couldn't read it, used your note + photo">. If it was not a full read and he gave no note, add: "Tip: resend with a short note on what it does for a more accurate listing."
Used your note: yes/no
Live in ~1 min: https://www.houseofmadese.com/ (Admin → Products to tweak anything)
```
If the publish failed, start with `❌ NOT published:` and the reason in one line.
