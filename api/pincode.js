// ─────────────────────────────────────────────────────────────
//  /api/pincode?pin=411001 — runs on Vercel's servers.
//  Asks Shiprocket whether we can deliver to that PIN, whether COD
//  is possible there, and roughly how many days the courier takes.
//  Results are cached on Vercel's CDN for a day per PIN.
// ─────────────────────────────────────────────────────────────
import { srConfigured, serviceability } from "./_shiprocket.js";

export default async function handler(req, res) {
  const pin = String(req.query?.pin || "").trim();
  if (!/^[1-9]\d{5}$/.test(pin)) { res.status(400).json({ error: "Enter a valid 6-digit PIN code" }); return; }
  if (!srConfigured()) { res.status(200).json({ configured: false }); return; }
  try {
    const out = await serviceability(pin);
    res.setHeader("Cache-Control", "public, s-maxage=86400, stale-while-revalidate=604800");
    res.status(200).json({ configured: true, pin, ...out });
  } catch (e) {
    // Shiprocket down/slow: tell the page to stay quiet rather than block checkout.
    res.status(200).json({ configured: true, pin, unknown: true });
  }
}
