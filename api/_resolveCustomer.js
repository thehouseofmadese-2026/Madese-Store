// ─────────────────────────────────────────────────────────────
//  _resolveCustomer.js — shared helper, not an API route itself.
//  Takes the access_token a logged-in customer's browser sends,
//  and asks Supabase to confirm it's real. Never trust a customer
//  ID sent directly from the browser — always verify the token.
//  If anything about this fails (no token, guest checkout, bad
//  token), it just returns null — checkout must NEVER fail because
//  of an account-linking hiccup. This is a bonus feature, not a
//  requirement to buy.
// ─────────────────────────────────────────────────────────────
export async function resolveCustomerId(access_token) {
  if (!access_token) return null;
  const SB_URL = (process.env.SUPABASE_URL || "").trim().replace(/\/+$/, "");
  const SB_SERVICE = (process.env.SUPABASE_SERVICE_KEY || "").trim();
  if (!SB_URL || !SB_SERVICE) return null;
  try {
    const r = await fetch(`${SB_URL}/auth/v1/user`, {
      headers: { "apikey": SB_SERVICE, "Authorization": `Bearer ${access_token}` },
    });
    if (!r.ok) return null;
    const user = await r.json();
    return user?.id || null;
  } catch (e) {
    return null;
  }
}
