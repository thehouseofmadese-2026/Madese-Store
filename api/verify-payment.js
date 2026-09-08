// ─────────────────────────────────────────────────────────────
//  /api/verify-payment — runs on Vercel's servers.
//  Its job: after the customer pays, confirm the payment is REAL
//  by checking Razorpay's cryptographic signature. Only if it's
//  genuine does it record the order (to Supabase, if configured).
//  A faked "success" from the browser fails this check and is
//  rejected. You never edit this file.
// ─────────────────────────────────────────────────────────────
import crypto from "crypto";
import { readFileSync } from "fs";
import { join } from "path";
import { resolveCustomerId } from "./_resolveCustomer.js";
import { baseId, summarizeCustomizations, insertOrder } from "./_cartHelpers.js";
const products = JSON.parse(readFileSync(join(process.cwd(), "products.json"), "utf-8"));
let coupons = [];
try { coupons = JSON.parse(readFileSync(join(process.cwd(), "coupons.json"), "utf-8")); } catch (e) {}

export default async function handler(req, res) {
  if (req.method !== "POST") { res.status(405).json({ error: "Method not allowed" }); return; }

  const KEY_SECRET = process.env.RAZORPAY_KEY_SECRET;
  if (!KEY_SECRET) { res.status(500).json({ error: "Razorpay secret not configured" }); return; }

  try {
    const { razorpay_order_id, razorpay_payment_id, razorpay_signature, cart, customer, access_token, promoCode, customizations } = req.body || {};
    if (!razorpay_order_id || !razorpay_payment_id || !razorpay_signature) { res.status(400).json({ error: "Missing payment fields" }); return; }

    // The signature check: HMAC-SHA256 of "orderId|paymentId" with your secret must match.
    const expected = crypto.createHmac("sha256", KEY_SECRET)
      .update(`${razorpay_order_id}|${razorpay_payment_id}`)
      .digest("hex");
    if (expected !== razorpay_signature) { res.status(400).json({ verified: false, error: "Signature mismatch — payment not verified" }); return; }

    // Recompute the trustworthy total again from server prices for the record —
    // and apply the same coupon logic used at order-creation time, so the
    // total we SAVE matches the amount that was actually CHARGED.
    let total = 0; const lineItems = [];
    for (const [id, qtyRaw] of Object.entries(cart || {})) {
      const qty = Math.max(1, parseInt(qtyRaw, 10) || 0);
      const p = products.find(x => x.id === baseId(id));
      if (p) { total += p.price * qty; lineItems.push(`${p.name} x${qty}`); }
    }
    const { note: customization_note, photoUrl: customization_photo_url } = summarizeCustomizations(customizations);
    if (promoCode) {
      const c = coupons.find(x => x.code.toUpperCase() === String(promoCode).toUpperCase());
      if (c) total = Math.max(0, total - Math.round(total * c.percent / 100));
    }

    // If the customer was logged in, link this order to their account.
    // Never lets an account-linking problem block the actual order.
    const customer_id = await resolveCustomerId(access_token);

    // Optionally store the order in Supabase (only if the env vars are set).
    const SB_URL = process.env.SUPABASE_URL;
    const SB_SERVICE = process.env.SUPABASE_SERVICE_KEY;
    if (SB_URL && SB_SERVICE) {
      await insertOrder(SB_URL, SB_SERVICE, {
        payment_id: razorpay_payment_id,
        order_id: razorpay_order_id,
        customer_id,
        items_text: lineItems.join(", "),
        total,
        customer_name: (customer?.name || "").slice(0, 120),
        phone: (customer?.phone || "").slice(0, 20),
        address: (customer?.address || "").slice(0, 600),
        status: "paid",
        customization_note,
        customization_photo_url,
      }).catch(() => {}); // payment already verified; a DB hiccup shouldn't fail the customer
    }

    res.status(200).json({ verified: true, payment_id: razorpay_payment_id });
  } catch (e) {
    res.status(500).json({ error: e.message || "Server error" });
  }
}
