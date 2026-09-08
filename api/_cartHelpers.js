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

// Inserts one row into Supabase `orders`. If the customization_* columns
// haven't been added yet (SQL migration not run), Supabase/PostgREST
// rejects the whole insert with an unknown-column error — retry once
// without those two fields so order-saving never silently breaks while
// the store owner gets around to running the migration.
export async function insertOrder(SB_URL, SB_SERVICE, row) {
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
  if (!res.ok && (row.customization_note !== undefined || row.customization_photo_url !== undefined)) {
    const text = await res.text().catch(() => "");
    if (/column|schema cache|PGRST204/i.test(text)) {
      const { customization_note, customization_photo_url, ...fallback } = row;
      res = await post(fallback);
      return { res, usedFallback: true };
    }
    return { res, usedFallback: false, errorText: text };
  }
  return { res, usedFallback: false };
}
