// Shipping + COD fee rules, read from shipping.json at the repo root.
// The browser shows the same numbers (it fetches /shipping.json), but the
// server is what actually charges, so the amount can't be tampered with.
import { readFileSync } from "fs";
import { join } from "path";
import { baseId } from "./_cartHelpers.js";

const DEFAULTS = { flat: 79, freeAbove: 999, codFee: 49, bulkyExtra: {} };
let cfg = DEFAULTS;
try { cfg = { ...DEFAULTS, ...JSON.parse(readFileSync(join(process.cwd(), "shipping.json"), "utf-8")) }; } catch (e) { /* missing file: use defaults */ }

const num = v => Math.max(0, Math.round(Number(v) || 0));

// subtotal = item total BEFORE any promo discount (that's what the
// free-shipping threshold is measured against). cart = { cartId: qty }.
export function shippingCharges(cart, subtotal, isCod) {
  const freeAbove = num(cfg.freeAbove);
  let shipping = 0;
  if (!(freeAbove > 0 && subtotal >= freeAbove)) {
    shipping = num(cfg.flat);
    const extra = cfg.bulkyExtra || {};
    for (const [id, qtyRaw] of Object.entries(cart || {})) {
      const qty = Math.max(1, Math.min(50, parseInt(qtyRaw, 10) || 0));
      shipping += num(extra[baseId(id)]) * qty;
    }
  }
  const codFee = isCod ? num(cfg.codFee) : 0;
  return { shipping, codFee };
}
