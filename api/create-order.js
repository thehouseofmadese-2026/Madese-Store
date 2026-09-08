// ─────────────────────────────────────────────────────────────
//  /api/create-order  — runs on Vercel's servers (not the browser)
//  Its job: take the customer's cart, look up the REAL prices on
//  the server, create a Razorpay order for that exact amount, and
//  return the order id. This is what makes the price un-tamperable.
//  You never edit this file. It reads product prices from products.json.
// ─────────────────────────────────────────────────────────────
import { readFileSync } from "fs";
import { join } from "path";
import { baseId } from "./_cartHelpers.js";
const products = JSON.parse(readFileSync(join(process.cwd(), "products.json"), "utf-8"));
let coupons = [];
try { coupons = JSON.parse(readFileSync(join(process.cwd(), "coupons.json"), "utf-8")); } catch (e) { /* no coupons file — fine, none active */ }

export default async function handler(req, res) {
  if (req.method !== "POST") { res.status(405).json({ error: "Method not allowed" }); return; }

  const KEY_ID = process.env.RAZORPAY_KEY_ID;
  const KEY_SECRET = process.env.RAZORPAY_KEY_SECRET;
  if (!KEY_ID || !KEY_SECRET) { res.status(500).json({ error: "Razorpay keys not configured on server" }); return; }

  try {
    const { cart, customer, promoCode } = req.body || {};
    if (!cart || typeof cart !== "object" || !Object.keys(cart).length) { res.status(400).json({ error: "Empty cart" }); return; }

    // Recompute the amount from SERVER-side prices — ignore anything the browser claims.
    let amount = 0; const lineItems = [];
    for (const [id, qtyRaw] of Object.entries(cart)) {
      const qty = Math.max(1, Math.min(50, parseInt(qtyRaw, 10) || 0));
      const p = products.find(x => x.id === baseId(id));
      if (!p) { res.status(400).json({ error: `Unknown product: ${id}` }); return; }
      amount += p.price * qty;
      lineItems.push(`${p.name} x${qty}`);
    }
    if (amount <= 0) { res.status(400).json({ error: "Invalid amount" }); return; }

    // Apply a coupon ONLY if it's a real one from our own list — never trust
    // a client-supplied discount amount, only a client-supplied CODE.
    let discount = 0;
    if (promoCode) {
      const c = coupons.find(x => x.code.toUpperCase() === String(promoCode).toUpperCase());
      if (c) discount = Math.round(amount * c.percent / 100);
    }
    amount = Math.max(0, amount - discount);

    // Create the Razorpay order via their REST API (Basic auth = key:secret).
    const auth = Buffer.from(`${KEY_ID}:${KEY_SECRET}`).toString("base64");
    const rzpRes = await fetch("https://api.razorpay.com/v1/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Basic ${auth}` },
      body: JSON.stringify({
        amount: amount * 100,      // paise
        currency: "INR",
        receipt: "rcpt_" + Date.now(),
        notes: {
          items: lineItems.join(", ").slice(0, 500),
          customer: (customer?.name || "").slice(0, 100),
          phone: (customer?.phone || "").slice(0, 20),
          promo: discount ? String(promoCode) : "",
        },
      }),
    });
    const order = await rzpRes.json();
    if (!rzpRes.ok) { res.status(502).json({ error: order?.error?.description || "Razorpay order failed" }); return; }

    res.status(200).json({ orderId: order.id, amount, keyId: KEY_ID });
  } catch (e) {
    res.status(500).json({ error: e.message || "Server error" });
  }
}
