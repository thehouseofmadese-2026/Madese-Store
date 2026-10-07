---
name: update-site
description: Make a change to the House of Madese storefront (index.html) from a plain-language request, validate it, and publish it live. Use when Mayank describes a site change (text, price, layout, banner, colours, bug fix, etc.), typed here or relayed by the Telegram agent.
---

# Change the House of Madese site and publish it

Input: Mayank's request in plain words. He wants it **fully automatic**: make the change, publish, report. Never stop to ask for approval. Only stop without publishing if the request is genuinely impossible or too ambiguous to act on safely (say so in the report).

Work in `C:\Users\mayan\OneDrive\Desktop\House of Madese`. The site is the single file `index.html`; the catalogue/collections/content live in the `SITE_DATA` JSON block, the behaviour in the main `<script>`. Reuse existing patterns in the file. Do NOT edit `api/*` unless he explicitly asks for backend work. Do not touch the sibling projects. Never write secrets anywhere.

## Steps
1. Read the relevant part of `index.html` (grep first; it is large). Make the smallest edit that does what he asked. Don't reformat or rewrite unrelated code.
2. Publish with the script (it validates `SITE_DATA` + `products.json` JSON and `node --check` on the main script, commits ONLY index.html/products.json, rebases, pushes; Vercel deploys in ~1 min):
```
python "C:\Users\mayan\OneDrive\Desktop\House of Madese\scripts\publish_site.py" "<short summary of the change, under 80 chars>"
```
Last line is `PUBLISHED <sha> <summary>`, `NOTHING` (your edit changed nothing) or `ERROR <reason>`. If ERROR is a validation failure caused by your edit, fix it and rerun once. If the working tree already had unrelated uncommitted edits to index.html before you started, mention it in the report.
3. If the request is a destructive or risky bulk change (deleting products/collections, wiping content), don't do it; report that he should do it in Admin or confirm in a normal Claude session.

## Final report (sent to Mayank on Telegram: short, plain, no markdown tables)
```
✅ Live: <one-line description of what changed>
Where: <section/file area touched>
Live in ~1 min: https://www.houseofmadese.com/ (send /revert to undo)
```
If nothing was published start with `❌ NOT published:` + the reason in one line.
