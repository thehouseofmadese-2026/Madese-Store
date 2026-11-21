// Cart ids for a customized item look like "productId~cz~<random>" so the
// same product can appear as multiple distinct queue entries, each with its
// own photo/note. This strips that suffix back to the real product id.
export function baseId(cartId) {
  const i = cartId.indexOf("~cz~");
  return i === -1 ? cartId : cartId.slice(0, i);
}

// Turns the customizations map the browser sends { cartId: { note, photoUrl } }
// into short text safe to store/display, capped so nothing runs away in size.
export function summarizeCustomizations(customizations) {
  if (!customizations || typeof customizations !== "object") return { note: "", photoUrl: "" };
  const notes = [], photos = [];
  for (const v of Object.values(customizations)) {
    if (v && typeof v === "object") {
      if (v.note) notes.push(String(v.note).slice(0, 400));
      if (v.photoUrl) photos.push(String(v.photoUrl).slice(0, 300));
    }
  }
  return { note: notes.join(" | ").slice(0, 1000), photoUrl: photos.join(", ").slice(0, 1000) };
}

// One structured line per cart entry, saved in orders.line_items so the
// Madese Hub "Orders & Print" page knows exactly which product, design and
// colour to print. The browser builds a customised line's note as
// "Design: X · Color: Y · <customer's own note>" (index.html addToCartFromPdp),
// so design/colour are read back from that prefix; whatever follows is the
// customer's own note (e.g. a keychain name).
export function lineItem(cartId, p, qty, customizations) {
  const cz = customizations && typeof customizations === "object" ? customizations[cartId] : null;
  const parts = String((cz && cz.note) || "").split(" · ").map(s => s.trim()).filter(Boolean);
  let design = null, color = null;
  if (parts[0] && parts[0].startsWith("Design: ")) design = parts.shift().slice(8).slice(0, 80);
  if (parts[0] && parts[0].startsWith("Color: ")) color = parts.shift().slice(7).slice(0, 80);
  const note = parts.join(" · ").slice(0, 300);
  const photo = String((cz && cz.photoUrl) || "").slice(0, 300);
  return { id: p.id, name: p.name, qty, design, color, note: note || null, photo: photo || null };
}

// Inserts one row into Supabase `orders`. Newer optional columns may not
// exist yet if their SQL migration hasn't been run; Supabase/PostgREST then
// rejects the whole insert with an unknown-column error. So we retry,
// dropping the newest optional columns first (line_items, then the
// customization_* pair), so order-saving never silently breaks while the
// store owner gets around to running the migration.
export async function insertOrder(SB_URL, SB_SERVICE, row) {
  let attempt = await insertOrderOnce(SB_URL, SB_SERVICE, row);
  if (!attempt.res.ok && row.line_items !== undefined && /column|schema cache|PGRST204/i.test(attempt.errorText || "")) {
    const { line_items, ...withoutItems } = row;
    attempt = await insertOrderOnce(SB_URL, SB_SERVICE, withoutItems);
    attempt.usedFallback = true;
  }
  return attempt;
}

async function insertOrderOnce(SB_URL, SB_SERVICE, row) {
  const post = (body) => fetch(`${SB_URL}/rest/v1/orders`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "apikey": SB_SERVICE,
      "Authorization": `Bearer ${SB_SERVICE}`,
      "Prefer": "return=minimal",
    },
    body: JSON.stringify([body]),
  });

  let res = await post(row);
  if (res.ok) return { res, usedFallback: false };
  const text = await res.text().catch(() => "");
  if (/line_items/i.test(text)) return { res, usedFallback: false, errorText: text }; // let insertOrder drop line_items first
  if ((row.customization_note !== undefined || row.customization_photo_url !== undefined) && /column|schema cache|PGRST204/i.test(text)) {
    const { customization_note, customization_photo_url, ...fallback } = row;
    res = await post(fallback);
    if (res.ok) return { res, usedFallback: true };
    return { res, usedFallback: true, errorText: await res.text().catch(() => "") };
  }
  return { res, usedFallback: false, errorText: text };
}
