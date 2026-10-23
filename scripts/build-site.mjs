// Build step run by Vercel on every deploy (see vercel.json). No dependencies.
//
// index.html in the repo stays the single source of truth (images embedded as base64, exactly as the
// admin panel and the Telegram agent write it). This script turns it into the deployable site in dist/:
//   1. every embedded image becomes a real, cacheable file in dist/img/p/<hash>.<ext>
//      (index.html drops from several MB to a few hundred KB)
//   2. every product gets its own page at /product/<id> with its own title, description, social-share
//      image and Product structured data, so Google and WhatsApp see it as a real page
//   3. sitemap.xml lists the home page and every product
// Run locally:  node scripts/build-site.mjs   (then serve dist/)

import { readFileSync, writeFileSync, mkdirSync, rmSync, copyFileSync, existsSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(ROOT, "dist");
const SITE_URL = "https://www.houseofmadese.com";
const BRAND = "House of Madese";

rmSync(OUT, { recursive: true, force: true });
mkdirSync(join(OUT, "img", "p"), { recursive: true });

/* ── 1. pull embedded images out into files ── */
let html = readFileSync(join(ROOT, "index.html"), "utf8");
const inBytes = Buffer.byteLength(html);
const seen = new Map();
let imageCount = 0;
html = html.replace(/data:image\/(jpeg|jpg|png|webp);base64,([A-Za-z0-9+/=]+)/g, (whole, type, b64) => {
  if (seen.has(whole)) return seen.get(whole);
  const buf = Buffer.from(b64, "base64");
  const ext = type === "jpeg" ? "jpg" : type;
  const name = createHash("sha1").update(buf).digest("hex").slice(0, 12) + "." + ext;
  writeFileSync(join(OUT, "img", "p", name), buf);
  const url = "/img/p/" + name;
  seen.set(whole, url);
  imageCount++;
  return url;
});

/* ── 2. read the site data ── */
const dataMatch = /<script type="application\/json" id="SITE_DATA">([\s\S]*?)<\/script>/.exec(html);
if (!dataMatch) throw new Error("SITE_DATA block not found in index.html");
const SITE = JSON.parse(dataMatch[1]);
const products = (SITE.products || []).filter(p => p && p.id && p.name);

/* ── 3. copy the plain static files ── */
for (const f of ["favicon-256.png", "favicon.ico", "og-image.png", "robots.txt"]) {
  if (existsSync(join(ROOT, f))) copyFileSync(join(ROOT, f), join(OUT, f));
}
writeFileSync(join(OUT, "index.html"), html);

/* ── 4. one page per product ── */
const esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const abs = u => (!u ? "" : /^https?:/.test(u) ? u : SITE_URL + u);
const clip = (s, n) => { s = String(s || "").replace(/\s+/g, " ").trim(); return s.length <= n ? s : s.slice(0, n - 1).replace(/\s+\S*$/, "") + "…"; };
const setTag = (src, re, tag) => { if (!re.test(src)) throw new Error("template tag missing: " + re); return src.replace(re, () => tag); };

function productPage(p) {
  const url = `${SITE_URL}/product/${encodeURIComponent(p.id)}`;
  const title = clip(`${p.name} | ${BRAND}`, 70);
  const desc = clip(p.desc || `${p.name}. ${(p.specs || []).join(". ")}. Designed and 3D-printed in Ichalkaranji, India.`, 158);
  const images = [p.img, ...(p.gallery || [])].filter(Boolean).map(abs);
  const ogImg = images[0] || SITE_URL + "/og-image.png";

  let page = html;
  page = setTag(page, /<title>[\s\S]*?<\/title>/, `<title>${esc(title)}</title>`);
  page = setTag(page, /<meta name="description" content="[^"]*">/, `<meta name="description" content="${esc(desc)}">`);
  page = setTag(page, /<link rel="canonical" href="[^"]*">/, `<link rel="canonical" href="${esc(url)}">`);
  page = setTag(page, /<meta property="og:type" content="[^"]*">/, `<meta property="og:type" content="product">`);
  page = setTag(page, /<meta property="og:title" content="[^"]*">/, `<meta property="og:title" content="${esc(title)}">`);
  page = setTag(page, /<meta property="og:description" content="[^"]*">/, `<meta property="og:description" content="${esc(desc)}">`);
  page = setTag(page, /<meta property="og:url" content="[^"]*">/, `<meta property="og:url" content="${esc(url)}">`);
  page = setTag(page, /<meta property="og:image" content="[^"]*">/, `<meta property="og:image" content="${esc(ogImg)}">`);
  page = page.replace(/<meta property="og:image:(width|height)" content="[^"]*">\s*/g, "");
  page = setTag(page, /<meta name="twitter:title" content="[^"]*">/, `<meta name="twitter:title" content="${esc(title)}">`);
  page = setTag(page, /<meta name="twitter:description" content="[^"]*">/, `<meta name="twitter:description" content="${esc(desc)}">`);
  page = setTag(page, /<meta name="twitter:image" content="[^"]*">/, `<meta name="twitter:image" content="${esc(ogImg)}">`);

  const ld = [{
    "@context": "https://schema.org",
    "@type": "Product",
    name: p.name,
    image: images,
    description: desc,
    sku: p.id,
    category: p.collection || undefined,
    brand: { "@type": "Brand", name: BRAND },
    offers: {
      "@type": "Offer",
      url,
      priceCurrency: "INR",
      price: String(p.price),
      availability: "https://schema.org/InStock",
      itemCondition: "https://schema.org/NewCondition",
      seller: { "@type": "Organization", name: BRAND }
    }
  }, {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: SITE_URL + "/" },
      ...(p.collection ? [{ "@type": "ListItem", position: 2, name: p.collection, item: SITE_URL + "/" }] : []),
      { "@type": "ListItem", position: p.collection ? 3 : 2, name: p.name, item: url }
    ]
  }];
  const ldTag = `<script type="application/ld+json">${JSON.stringify(ld).replace(/</g, "\\u003c")}</script>\n`;
  page = page.replace("</head>", () => ldTag + "</head>");

  // Plain-HTML copy of what the product view shows, for crawlers and link previews. The page script
  // removes it once the real product view has opened.
  const price = p.mrp > p.price ? `Rs ${p.price} (was Rs ${p.mrp})` : `Rs ${p.price}`;
  const ssr = `<div id="ssrProduct" style="position:absolute;left:-9999px;top:0;width:1px;height:1px;overflow:hidden">` +
    `<h1>${esc(p.name)}</h1><p>${esc(p.collection || "")}</p><p>${esc(price)}</p>` +
    (p.img ? `<img src="${esc(p.img)}" alt="${esc(p.name)}" width="600" height="600">` : "") +
    `<p>${esc(p.desc || "")}</p>` +
    ((p.specs || []).length ? `<ul>${p.specs.map(s => `<li>${esc(s)}</li>`).join("")}</ul>` : "") +
    `<p>Made in India. Ships in 48 hours. Cash on delivery and UPI available.</p></div>\n`;
  page = page.replace(/<body[^>]*>/, m => m + "\n" + ssr);
  return page;
}

for (const p of products) {
  const dir = join(OUT, "product", p.id);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "index.html"), productPage(p));
}

/* ── 5. sitemap ── */
const day = new Date().toISOString().slice(0, 10);
const urls = [{ loc: SITE_URL + "/", pri: "1.0" }, ...products.map(p => ({ loc: `${SITE_URL}/product/${encodeURIComponent(p.id)}`, pri: "0.8" }))];
writeFileSync(join(OUT, "sitemap.xml"),
  `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
  urls.map(u => `  <url>\n    <loc>${esc(u.loc)}</loc>\n    <lastmod>${day}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>${u.pri}</priority>\n  </url>`).join("\n") +
  `\n</urlset>\n`);

const outBytes = Buffer.byteLength(html);
console.log(`build-site: ${products.length} product pages, ${imageCount} images extracted, index.html ${(inBytes / 1e6).toFixed(2)} MB -> ${(outBytes / 1e6).toFixed(2)} MB`);
