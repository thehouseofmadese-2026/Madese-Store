# Telegram → House of Madese product agent

Send the bot a product link + photo → it generates square Gemini photos (3 Clean Listing + 1 witty Conceptual Print Ad + one photo per colour option, which become the product page Color picker),
writes a witty listing, publishes to houseofmadese.com, and replies with the result.

Pieces: `bot.py` (Telegram listener) → `claude -p` + `.claude/skills/add-product/SKILL.md` (research, collection/price
inference, description) → `scripts/gen_product_photos.py` (Gemini via Madese Photo Studio) → `scripts/add_product.py`
(encode, splice into index.html, validate, git push → Vercel).

## One-time setup
1. In Telegram, message **@BotFather** → `/newbot` → pick a name → copy the token.
2. Copy `.env.example` to `.env`, paste the token. Leave ALLOWED_USER_ID blank for now.
3. Double-click `start_agent.bat`. Message your new bot anything: it replies with your numeric Telegram ID.
4. Put that ID in `.env` as ALLOWED_USER_ID, close and reopen `start_agent.bat`. (Everyone else is ignored.)
5. First run: set `DRY_RUN=1`, send a real link + photo, check the reply, then set `DRY_RUN=0`.

## Using it
Photo + link in one message (link in caption) or as two messages. Optional hints in the same text:
`https://makerworld.com/... 499 lamps` (price + collection) or `call it Bean Pod`.
Send photos as "File" instead of "Photo" for full quality. /cancel clears a half-sent request. /undo removes the last product the agent published (repeat to go further back).

**Redo photos of a live product (no duplicate):** `/redo <product name>, <what to change>` e.g. `/redo Wicker Glow Retro Lamp, more vibrant colours`, `/redo Bean Pod only the blue`, `/redo Bean Pod new ad idea`. Attach a photo to use it as the new reference. Only the photos are replaced in place (name, price, description untouched); `.claude/skills/redo-photos` + `scripts/update_product_photos.py`. To roll one back, `git revert` its "Update photos: ..." commit.

## Notes
- Your PC must be on and `start_agent.bat` running (put a shortcut in `shell:startup` to auto-start at login).
- Uses your Claude Code login (usage counts toward your plan) and the Gemini key in Madese Photo Studio's `.env`
  (~₹15-20 per product at the default Lite model).
- Log: `agent.log` here. Anything wrong on the live site: Admin → Products, or revert the commit.
