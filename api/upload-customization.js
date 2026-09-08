// ─────────────────────────────────────────────────────────────
//  /api/upload-customization — runs on Vercel's servers.
//  Its job: take a customer's reference photo (sent as base64 from
//  the browser) and store it in Supabase Storage using the SERVICE
//  key, so the bucket itself never has to be writable by the public.
//  Returns a public URL the browser then attaches to the cart item.
//  You never edit this file.
// ─────────────────────────────────────────────────────────────
const MAX_BYTES = 8 * 1024 * 1024; // 8MB, matches the bucket's own limit
const ALLOWED = { "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/heic": "heic", "image/heif": "heif" };

export default async function handler(req, res) {
  if (req.method !== "POST") { res.status(405).json({ error: "Method not allowed" }); return; }

  const SB_URL = (process.env.SUPABASE_URL || "").trim().replace(/\/+$/, "");
  const SB_SERVICE = (process.env.SUPABASE_SERVICE_KEY || "").trim();
  if (!SB_URL || !SB_SERVICE) { res.status(500).json({ error: "Storage not configured on server" }); return; }

  try {
    const { productId, imageBase64, imageType } = req.body || {};
    if (!productId || typeof productId !== "string") { res.status(400).json({ error: "Missing productId" }); return; }
    if (!imageBase64 || typeof imageBase64 !== "string") { res.status(400).json({ error: "Missing image" }); return; }
    const ext = ALLOWED[imageType];
    if (!ext) { res.status(400).json({ error: "Unsupported image type — use JPEG, PNG, WEBP or HEIC" }); return; }

    const raw = Buffer.from(imageBase64.replace(/^data:[^,]+,/, ""), "base64");
    if (raw.length > MAX_BYTES) { res.status(400).json({ error: "Image too large (max 8MB)" }); return; }

    const safeProductId = productId.replace(/[^a-z0-9-]/gi, "").slice(0, 60) || "product";
    const path = `${safeProductId}/${Date.now()}-${Math.random().toString(36).slice(2, 8)}.${ext}`;

    const upRes = await fetch(`${SB_URL}/storage/v1/object/customizations/${path}`, {
      method: "POST",
      headers: {
        "apikey": SB_SERVICE,
        "Authorization": `Bearer ${SB_SERVICE}`,
        "Content-Type": imageType,
        "x-upsert": "false",
      },
      body: raw,
    });
    if (!upRes.ok) {
      const t = await upRes.text().catch(() => "");
      res.status(502).json({ error: "Upload failed: " + t.slice(0, 300) });
      return;
    }

    const url = `${SB_URL}/storage/v1/object/public/customizations/${path}`;
    res.status(200).json({ url });
  } catch (e) {
    res.status(500).json({ error: e.message || "Server error" });
  }
}
