// ─────────────────────────────────────────────────────────────
//  /api/create-cod-order — runs on Vercel's servers.
//  Its job: for Cash-on-Delivery orders, there's no payment to
//  verify — but we still price the order from the SERVER'S price
//  list (never trust the browser), and save it to Supabase marked
//  "cod_pending" so the owner can confirm it before printing.
//  You never edit this file.
// ─────────────────────────────────────────────────────────────
import { readFileSync } from "fs";
import { join } from "path";
const products = JSON.parse(readFileSync(join(process.cwd(), "products.json"), "utf-8"));

export default async function handler(req, res) {
  if (req.method !== "POST") { res.status(405).json({ error: "Method not allowed" }); return; }

  try {
    const { cart, customer } = req.body || {};
    if (!cart || typeof cart !== "object" || !Object.keys(cart).length) { res.status(400).json({ error: "Empty cart" }); return; }
    if (!customer?.name || !customer?.phone || !customer?.address) { res.status(400).json({ error: "Missing customer details" }); return; }

    // Recompute the amount from SERVER-side prices — same rule as online checkout.
    let total = 0; const lineItems = [];
    for (const [id, qtyRaw] of Object.entries(cart)) {
      const qty = Math.max(1, Math.min(50, parseInt(qtyRaw, 10) || 0));
      const p = products.find(x => x.id === id);
      if (!p) { res.status(400).json({ error: `Unknown product: ${id}` }); return; }
      total += p.price * qty;
      lineItems.push(`${p.name} x${qty}`);
    }
    if (total <= 0) { res.status(400).json({ error: "Invalid order" }); return; }

    const codRef = "COD" + Date.now();

    const SB_URL = process.env.SUPABASE_URL;
    const SB_SERVICE = process.env.SUPABASE_SERVICE_KEY;
    if (SB_URL && SB_SERVICE) {
      const dbRes = await fetch(`${SB_URL}/rest/v1/orders`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "apikey": SB_SERVICE,
          "Authorization": `Bearer ${SB_SERVICE}`,
          "Prefer": "return=minimal",
        },
        body: JSON.stringify([{
          payment_id: null,
          order_id: codRef,
          payment_method: "cod",
          items_text: lineItems.join(", "),
          total,
          customer_name: String(customer.name).slice(0, 120),
          phone: String(customer.phone).slice(0, 20),
          address: String(customer.address).slice(0, 600),
          status: "cod_pending",
        }]),
      });
      if (!dbRes.ok) {
        // Order still succeeds for the customer; owner should check Supabase config.
        console.warn("COD order DB save failed:", await dbRes.text());
      }
    }

    res.status(200).json({ ok: true, ref: codRef, total });
  } catch (e) {
    res.status(500).json({ error: e.message || "Server error" });
  }
}
