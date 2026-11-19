// Shiprocket API helper (server only). Login comes from Vercel env vars
// SHIPROCKET_EMAIL / SHIPROCKET_PASSWORD (an "API user" made in Shiprocket →
// Settings → API Users). Pickup PIN / location name / box size live in shipping.json.
// Everything here fails soft: if Shiprocket is down or not set up, checkout
// still works and the order is still saved; it just isn't auto-pushed.
import { readFileSync } from "fs";
import { join } from "path";

const BASE = "https://apiv2.shiprocket.in/v1/external";
let ship = {};
try { ship = JSON.parse(readFileSync(join(process.cwd(), "shipping.json"), "utf-8")); } catch (e) {}
export const SR = {
  pickupPincode: String(ship.pickupPincode || "416115"),
  pickupLocation: String(ship.pickupLocation || "Primary"),
  box: { length: 15, breadth: 15, height: 10, weight: 0.4, ...(ship.defaultBox || {}) },
  storeEmail: String(ship.storeEmail || "thehouseofmadese@gmail.com"),
};

export const srConfigured = () => !!(process.env.SHIPROCKET_EMAIL && process.env.SHIPROCKET_PASSWORD);

// Shiprocket tokens last ~10 days; keep one per warm function instance.
let token = null, tokenAt = 0;
async function getToken(force) {
  if (!force && token && Date.now() - tokenAt < 8 * 864e5) return token;
  const r = await timed(`${BASE}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: process.env.SHIPROCKET_EMAIL, password: process.env.SHIPROCKET_PASSWORD }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.token) throw new Error("Shiprocket login failed: " + (j.message || r.status));
  token = j.token; tokenAt = Date.now();
  return token;
}

function timed(url, opts = {}, ms = 8000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  return fetch(url, { ...opts, signal: ctrl.signal }).finally(() => clearTimeout(t));
}

export async function srFetch(path, opts = {}) {
  const go = async force => timed(BASE + path, {
    ...opts, headers: { "Content-Type": "application/json", ...(opts.headers || {}), Authorization: `Bearer ${await getToken(force)}` },
  });
  let r = await go(false);
  if (r.status === 401) r = await go(true); // stale token: log in again once
  const j = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, data: j };
}

// Can couriers reach this PIN from our pickup PIN? Is COD possible? How many days?
export async function serviceability(pin) {
  const q = new URLSearchParams({ pickup_postcode: SR.pickupPincode, delivery_postcode: pin, weight: String(SR.box.weight), cod: "1" });
  const { ok, data } = await srFetch(`/courier/serviceability/?${q}`);
  const list = (ok && data?.data?.available_courier_companies) || [];
  if (!list.length) return { serviceable: false };
  const days = list.map(c => parseInt(c.estimated_delivery_days, 10)).filter(n => n > 0);
  const c0 = list[0] || {};
  return {
    serviceable: true,
    cod: list.some(c => Number(c.cod) === 1),
    minDays: days.length ? Math.min(...days) : null,
    maxDays: days.length ? Math.max(...days) : null,
    city: c0.city || "", state: c0.state || "",
  };
}

async function cityStateFor(pin) {
  try {
    const { ok, data } = await srFetch(`/open/postcode/details?postcode=${pin}`);
    const d = ok && data?.postcode_details;
    if (d && d.city && d.state) return { city: d.city, state: d.state };
  } catch (e) {}
  try { // fallback: India Post's public PIN directory
    const r = await timed(`https://api.postalpincode.in/pincode/${pin}`, {}, 5000);
    const po = (await r.json())?.[0]?.PostOffice?.[0];
    if (po) return { city: po.District || po.Block || po.Name, state: po.State };
  } catch (e) {}
  return { city: "", state: "" };
}

// One line per product (Shiprocket wants unique SKUs; customized copies of the same product merge).
export function addSrItem(list, p, qty) {
  const hit = list.find(i => i.sku === p.id);
  if (hit) hit.units += qty; else list.push({ name: String(p.name).slice(0, 100), sku: p.id, units: qty, price: p.price });
}

export const pinFrom = c => {
  const p = String(c?.pincode || "").trim();
  if (/^[1-9]\d{5}$/.test(p)) return p;
  const m = /PIN\s*([1-9]\d{5})/i.exec(String(c?.address || ""));
  return m ? m[1] : "";
};

// Creates the order in Shiprocket's "New" list. Nothing is booked or charged
// until you click Ship there. Never throws: returns { pushed, error }.
export async function pushOrder({ orderId, customer, items, paymentMethod, subTotal, shipping = 0, discount = 0, codFee = 0 }) {
  if (!srConfigured()) return { pushed: false, error: "Shiprocket not configured" };
  try {
    const pin = pinFrom(customer);
    if (!pin) return { pushed: false, error: "No valid PIN code on order" };
    const { city, state } = await cityStateFor(pin);
    const now = new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 16).replace("T", " "); // IST
    const [first, ...rest] = String(customer.name || "Customer").trim().split(/\s+/);
    const { ok, data } = await srFetch("/orders/create/adhoc", {
      method: "POST",
      body: JSON.stringify({
        order_id: String(orderId).slice(0, 50),
        order_date: now,
        pickup_location: SR.pickupLocation,
        billing_customer_name: first,
        billing_last_name: rest.join(" "),
        billing_address: String(customer.address || "").replace(/\s*—\s*PIN\s*\d{6}\s*$/i, "").slice(0, 190),
        billing_city: city || "NA",
        billing_pincode: pin,
        billing_state: state || "NA",
        billing_country: "India",
        billing_email: customer.email || SR.storeEmail,
        billing_phone: String(customer.phone || "").replace(/\D/g, "").slice(-10),
        shipping_is_billing: true,
        order_items: items.map(i => ({ name: i.name, sku: i.sku, units: i.units, selling_price: i.price })),
        payment_method: paymentMethod === "cod" ? "COD" : "Prepaid",
        shipping_charges: shipping,
        transaction_charges: codFee,
        total_discount: discount,
        sub_total: subTotal,
        length: SR.box.length, breadth: SR.box.breadth, height: SR.box.height, weight: SR.box.weight,
      }),
    });
    if (ok && (data.order_id || data.shipment_id)) return { pushed: true, srOrderId: data.order_id, shipmentId: data.shipment_id };
    return { pushed: false, error: (data.message || "Shiprocket rejected the order") + (data.errors ? " " + JSON.stringify(data.errors).slice(0, 300) : "") };
  } catch (e) {
    return { pushed: false, error: e.name === "AbortError" ? "Shiprocket timed out" : e.message };
  }
}
