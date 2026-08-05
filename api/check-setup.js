// ─────────────────────────────────────────────────────────────
//  /api/check-setup — a diagnostic page for the owner.
//  Visit https://YOUR-SITE/api/check-setup in a browser and it
//  tells you exactly which server keys are set and whether the
//  database connection actually works. Safe: it never prints
//  your keys, only whether they look right.
// ─────────────────────────────────────────────────────────────
export default async function handler(req, res) {
  const out = { checks: [], verdict: "" };

  const add = (name, ok, detail) => out.checks.push({ name, ok, detail });

  const RZ_ID = (process.env.RAZORPAY_KEY_ID || "").trim();
  const RZ_SECRET = (process.env.RAZORPAY_KEY_SECRET || "").trim();
  const SB_URL_RAW = process.env.SUPABASE_URL || "";
  const SB_URL = SB_URL_RAW.trim().replace(/\/+$/, "");
  const SB_KEY = (process.env.SUPABASE_SERVICE_KEY || "").trim();

  add("RAZORPAY_KEY_ID set", !!RZ_ID, RZ_ID ? `starts with "${RZ_ID.slice(0, 8)}…"` : "MISSING");
  add("RAZORPAY_KEY_SECRET set", !!RZ_SECRET, RZ_SECRET ? `${RZ_SECRET.length} characters` : "MISSING");

  add("SUPABASE_URL set", !!SB_URL, SB_URL || "MISSING");
  if (SB_URL_RAW !== SB_URL) add("SUPABASE_URL clean", false, "Has a trailing slash or spaces — remove them in Vercel");
  add("SUPABASE_URL format", /^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(SB_URL),
      SB_URL ? "should look like https://xxxx.supabase.co" : "MISSING");

  add("SUPABASE_SERVICE_KEY set", !!SB_KEY, SB_KEY ? `${SB_KEY.length} characters, starts "${SB_KEY.slice(0, 4)}…"` : "MISSING");
  if (SB_KEY) {
    const isJwt = SB_KEY.startsWith("eyJ");
    add("SERVICE_KEY looks like a legacy service_role JWT", isJwt,
        isJwt ? "OK" : `starts with "${SB_KEY.slice(0, 12)}…" — use the LEGACY service_role key (starts with eyJ)`);
    add("SERVICE_KEY not duplicated", !(SB_KEY.slice(1).includes("eyJhbGciOi")),
        SB_KEY.slice(1).includes("eyJhbGciOi") ? "The key appears to be pasted TWICE — re-paste it once" : "OK");
  }

  // Live connection test
  if (SB_URL && SB_KEY) {
    try {
      const r = await fetch(`${SB_URL}/rest/v1/orders?select=id&limit=1`, {
        headers: { "apikey": SB_KEY, "Authorization": `Bearer ${SB_KEY}` },
      });
      const body = await r.text();
      add("Can reach the orders table", r.ok, r.ok ? "Connection works" : `HTTP ${r.status}: ${body.slice(0, 200)}`);
    } catch (e) {
      add("Can reach the orders table", false, "Network error: " + e.message);
    }
  }

  const failures = out.checks.filter(c => !c.ok);
  out.verdict = failures.length
    ? `${failures.length} problem(s) found — see the failing checks above.`
    : "All good. Orders should save correctly.";

  res.setHeader("Content-Type", "application/json");
  res.status(200).send(JSON.stringify(out, null, 2));
}
