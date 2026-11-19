"""Reads /data/*.jsonl, prioritizes JSON-LD / Next.js data, extracts structured specs, and embeds paragraphs."""
import json, re, glob, sys
from app.db import conn
from app.rag import model
from app.vocab import (
    AMENITY_KEYWORDS, FIXTURE_KEYWORDS, has_term, canon_key, ALIASES,
    extract_area_display, extract_bedroom_options,
)

KNOWN_CITIES = [
    "Dubai", "Riyadh", "Jeddah", "Dammam", "Makkah", "Madinah", "Al Khobar",
    "London", "Muscat", "Abu Dhabi", "Ras Al Khaimah", "Marbella", "Mallorca",
    "Simaisma", "Doha", "Jumeirah", "Business Bay"
]

CITY_TO_COUNTRY = {
    "Dubai": "UAE", "Abu Dhabi": "UAE", "Ras Al Khaimah": "UAE",
    "Jumeirah": "UAE", "Business Bay": "UAE",
    "Riyadh": "Saudi Arabia", "Jeddah": "Saudi Arabia", "Dammam": "Saudi Arabia",
    "Makkah": "Saudi Arabia", "Madinah": "Saudi Arabia", "Al Khobar": "Saudi Arabia",
    "Simaisma": "Qatar", "Doha": "Qatar",
    "Muscat": "Oman",
    "Marbella": "Spain", "Mallorca": "Spain",
    "London": "United Kingdom",
}

BRAND_PARTNERS = [
    "Lamborghini", "Fendi Casa", "Pagani", "Aston Martin", "Trump",
    "Elie Saab", "Missoni", "Dolce & Gabbana", "W Hotels", "Marriott"
]

# Robust price regex handling both leading (SAR 340000) and trailing (340000 SAR) currencies
PRICE_RE = re.compile(
    r"(?:(AED|SAR|USD|GBP|EUR|\$|£|€)\s?([\d,]+(?:\.\d+)?))|([\d,]+(?:\.\d+)?)\s?(AED|SAR|USD|GBP|EUR|\$|£|€)",
    re.I
)
BED_RE = re.compile(r"\b(\d+)(?:\s*(?:[-–—]|to)\s*(\d+))?[\s-]*(?:bed(?:room)?s?|br)\b", re.I)
STUDIO_RE = re.compile(r"\bstudio\s+(?:apartments?|units?|flats?|residences?)\b", re.I)
STATUS_RE = re.compile(r"\bstatus\s*[:\-]?\s*(under development|completed|sold out|ready|off[- ]plan)\b", re.I)
BATH_RE = re.compile(r"(\d+)\s*(?:bath|bathroom)", re.I)
AREA_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m2|sq\.?\s*ft|sqft)", re.I)
REGA_RE = re.compile(r"(?:REGA|Licence|License)\s*(?:No\.?|Number|#|:)?\s*([A-Z0-9-]{5,25})", re.I)

CURRENCY_ALIASES = {"$": "USD", "US$": "USD", "£": "GBP", "€": "EUR", "SR": "SAR", "DH": "AED"}


def norm_currency(cur):
    """Normalize currency symbols/aliases to ISO codes so strict filters match."""
    if not cur:
        return None
    s = str(cur).strip().upper()
    return CURRENCY_ALIASES.get(s, s)


def extract_from_json_ld(json_ld_list):
    for ld in json_ld_list:
        items = ld if isinstance(ld, list) else [ld]
        for item in items:
            t = item.get("@type")
            if t in ("SingleFamilyResidence", "Product", "RealEstateListing", "Apartment", "House", "Place"):
                res = {}
                res["title"] = item.get("name")
                desc = item.get("description")
                if desc:
                    res["description"] = desc
                offers = item.get("offers")
                if isinstance(offers, dict):
                    p = offers.get("price")
                    if p:
                        try:
                            res["price"] = float(str(p).replace(",", ""))
                        except ValueError:
                            pass
                    res["currency"] = norm_currency(offers.get("priceCurrency"))
                loc = item.get("address")
                if isinstance(loc, dict):
                    res["city"] = loc.get("addressLocality")
                    res["country"] = loc.get("addressCountry")
                return res
    return {}


def _parse_amount(raw):
    try:
        return float((raw or "").replace(",", ""))
    except ValueError:
        return None


def parse_price(text):
    """Return the largest plausible currency amount found (skips stray small numbers like '2 AED')."""
    best = (None, None)
    for m in PRICE_RE.finditer(text):
        g = m.groups()
        if g[0] and g[1]:
            val, cur = _parse_amount(g[1]), norm_currency(g[0])
        elif g[2] and g[3]:
            val, cur = _parse_amount(g[2]), norm_currency(g[3])
        else:
            continue
        if val is not None and val >= 1000 and (best[0] is None or val > best[0]):
            best = (val, cur)
    return best


def extract_from_next_data(next_data):
    """Extract structured fields from Next.js __NEXT_DATA__ pageProps."""
    if not next_data:
        return {}
    props = next_data.get("props", {}).get("pageProps", {})
    res = {}
    for key in ("property", "listing", "project", "data", "item"):
        item = props.get(key) or props.get(key.capitalize())
        if isinstance(item, dict):
            res["title"] = item.get("name") or item.get("title") or item.get("project_name")
            res["price"] = item.get("price") or item.get("sale_price") or item.get("starting_price")
            raw_currency = item.get("currency") or item.get("price_currency") or item.get("priceCurrency")
            if raw_currency:
                res["currency"] = norm_currency(raw_currency)
            res["bedrooms"] = item.get("bedrooms") or item.get("beds") or item.get("bedroom_count")
            res["bathrooms"] = item.get("bathrooms") or item.get("baths")
            res["city"] = item.get("city") or item.get("location_city")
            res["country"] = item.get("country") or item.get("location_country")
            area = item.get("area") or item.get("area_sqm") or item.get("size")
            if area:
                try:
                    res["area_sqm"] = float(str(area).replace(",", ""))
                except ValueError:
                    pass
            break
    return {k: v for k, v in res.items() if v is not None}


from urllib.parse import urlparse

PROPERTY_TYPE_TERMS = ["penthouse", "duplex", "townhouse", "villa", "apartment", "residential tower", "land"]

COUNTRY_SLUGS = {
    "uae": "UAE", "uk": "United Kingdom", "spain": "Spain", "oman": "Oman",
    "qatar": "Qatar", "saudi-arabia": "Saudi Arabia", "portugal": "Portugal",
    "france": "France", "italy": "Italy", "greece": "Greece", "egypt": "Egypt",
    "bahrain": "Bahrain", "kuwait": "Kuwait", "usa": "USA",
}


def _url_slugs(url):
    return [p for p in urlparse(url).path.lower().split("/") if p]


def country_from_url(url):
    for slug in _url_slugs(url):
        if slug.startswith("properties-in-"):
            key = slug.replace("properties-in-", "")
            if key in COUNTRY_SLUGS:
                return COUNTRY_SLUGS[key]
        if slug in {v.lower() for v in COUNTRY_SLUGS.values()}:
            return slug
    return None


def _type_in(text):
    for pt in PROPERTY_TYPE_TERMS:
        if re.search(rf"\b{re.escape(pt)}s?\b", text or "", re.I):
            return pt.replace(" ", "_")
    if re.search(r"\bplots?\b", text or "", re.I):
        return "land"
    return None


def detect_property_type(url, title, specs, body):
    """URL slug / title / spec first; only then the most frequent type word in the body.
    (Scanning the whole page in priority order made any tower that mentions 'penthouse' a penthouse.)"""
    slug = " ".join(_url_slugs(url)).replace("-", " ")
    for src in (slug, title, specs.get("property type")):
        t = _type_in(src)
        if t:
            return t
        if src and re.search(r"\btowers?\b", src, re.I):
            return "residential_tower"
    counts = {pt: len(re.findall(rf"\b{re.escape(pt)}s?\b", body or "", re.I)) for pt in PROPERTY_TYPE_TERMS}
    best = max(counts, key=counts.get)
    return best.replace(" ", "_") if counts[best] else None


def extract_structured_fields(page):
    source = page.get("source", "unknown")
    url = page["url"]
    text = page.get("text") or ""
    specs = {k.lower(): v for k, v in (page.get("specs") or {}).items()}
    
    # Priority 1: JSON-LD structured data
    ld_data = extract_from_json_ld(page.get("json_ld") or [])

    # Priority 2: Next.js __NEXT_DATA__
    nd_data = extract_from_next_data(page.get("next_data"))

    title = ld_data.get("title") or nd_data.get("title") or page.get("title") or ""
    full_blob = f"{title}\n{page.get('meta_description') or ''}\n{json.dumps(specs)}\n{text}"
    
    doc_type = "project" if source == "darglobal" or "/project" in url.lower() else "listing"
    developer = "DarGlobal" if source == "darglobal" else specs.get("developer")
    # Brand only from title / URL slug / specs. Scanning the whole body matched partner logos
    # and footer links (e.g. every DarGlobal page mentions Trump), mislabelling projects.
    brand_src = f"{title} {' '.join(_url_slugs(url))} {json.dumps(specs)}"
    brand = next((b for b in BRAND_PARTNERS
                  if re.search(rf"\b{re.escape(b)}s?\b", brand_src, re.I)), None)

    loc_str = specs.get("location", "")
    url_country = country_from_url(url)
    text_city = next((c for c in KNOWN_CITIES if c.lower() in f"{loc_str} {full_blob}".lower()), None)
    city = ld_data.get("city") or nd_data.get("city")
    if not city and not url_country:
        city = text_city
    country = (ld_data.get("country") or nd_data.get("country") or url_country
               or CITY_TO_COUNTRY.get(city) or CITY_TO_COUNTRY.get(text_city))
    if not country and "," in loc_str:
        country = loc_str.split(",")[-1].strip()

    district = None
    if "," in loc_str:
        parts = [p.strip() for p in loc_str.split(",")]
        if len(parts) >= 2 and parts[1].lower() == (city or "").lower():
            district = parts[0]

    if page.get("city_override"):
        city = page["city_override"]
    if page.get("country_override"):
        country = page["country_override"]

    property_type = detect_property_type(url, title, specs, text)

    status = specs.get("status")
    if not status:
        sm = STATUS_RE.search(text)
        if sm:
            status = sm.group(1).title()
        elif re.search(r"\bunder development\b", full_blob, re.I):
            status = "Under Development"
        # bare "completed" anywhere in the page is NOT treated as a status (matched marketing copy)

    transaction_type = "off_plan" if source == "darglobal" else "sale"
    if "rent" in url.lower() or "for rent" in full_blob.lower():
        transaction_type = "rent"

    price, currency = ld_data.get("price"), ld_data.get("currency")
    if price is None and nd_data.get("price") is not None:
        price = nd_data["price"]
        currency = currency or nd_data.get("currency")
    if price is None:
        price, currency = parse_price(full_blob)
    if not currency:
        currency = nd_data.get("currency")
    currency = norm_currency(currency)
    # Do NOT guess currency — leave NULL if not found in page content
    # currency remains as extracted or None

    area_sqm = nd_data.get("area_sqm")
    am = AREA_RE.search(full_blob)
    if am and area_sqm is None:
        val = float(am.group(1).replace(",", ""))
        if "ft" in am.group(0).lower():
            val = round(val * 0.092903, 2)
        area_sqm = val
    area_display = extract_area_display(specs, text)

    bm = BED_RE.search(full_blob)
    bedroom_options = extract_bedroom_options(full_blob)
    bedrooms = nd_data.get("bedrooms")
    bedrooms_max = None
    if bedroom_options:
        bedrooms = bedroom_options[0]
        bedrooms_max = bedroom_options[-1]
    elif bedrooms is None:
        if bm:
            bedrooms = int(bm.group(1))  # for a range like "2-4 bedroom" this is the minimum
            bedrooms_max = int(bm.group(2)) if bm.group(2) else None
        elif STUDIO_RE.search(full_blob):  # "Yoga Studio" no longer makes a property a studio flat
            bedrooms = 0

    bath_m = BATH_RE.search(full_blob)
    bathrooms = nd_data.get("bathrooms")
    if bathrooms is None:
        bathrooms = int(bath_m.group(1)) if bath_m else None

    furnishing = specs.get("furnishing")
    if not furnishing:
        if "unfurnished" in full_blob.lower():
            furnishing = "Unfurnished"
        elif "furnished" in full_blob.lower():
            furnishing = "Furnished"

    # whole-word match on body text + spec values (not the title: "Trump Park Residences" is not a park)
    amenity_src = " ".join(str(v) for v in specs.values()) + "\n" + text
    amenities = [a for a in AMENITY_KEYWORDS if has_term(a, amenity_src)]
    fixtures = [fx for fx in FIXTURE_KEYWORDS if has_term(fx, amenity_src)]
    rega_m = REGA_RE.search(full_blob)
    rega_license = rega_m.group(1) if rega_m else None

    # Last updated: NULL if not found on page (scraped_at column tracks crawl time)
    last_updated = specs.get("last updated") or specs.get("last_updated") or None

    return {
        "source": source,
        "url": url,
        "doc_type": doc_type,
        "title": title,
        "developer": developer,
        "brand_partner": brand,
        "city": city,
        "district": district,
        "country": country,
        "transaction_type": transaction_type,
        "property_type": property_type,
        "unit_types": None,
        "status": status,
        "completion_date": specs.get("completion"),
        "price": price,
        "currency": currency,
        "area_sqm": area_sqm,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "furnishing": furnishing,
        "amenities": amenities or None,
        "fixtures": fixtures or None,
        "rega_license": rega_license,
        "last_updated": last_updated,
        "raw": json.dumps({
            "specs": specs, "json_ld": page.get("json_ld"),
            "bedrooms_max": bedrooms_max, "bedroom_options": bedroom_options or None,
            "area_display": area_display,
        }),
    }


def build_chunks(page, meta, max_chars=800):
    header_parts = [f"Source: {meta['source'].upper()}"]
    if meta["title"]: header_parts.append(f"Title: {meta['title']}")
    if meta["developer"]: header_parts.append(f"Developer: {meta['developer']}")
    if meta["brand_partner"]: header_parts.append(f"Brand: {meta['brand_partner']}")
    loc = ", ".join(x for x in [meta["district"], meta["city"], meta["country"]] if x)
    if loc: header_parts.append(f"Location: {loc}")
    if meta["property_type"]: header_parts.append(f"Type: {meta['property_type']}")
    raw = json.loads(meta["raw"])
    area = raw.get("area_display")
    if not area and meta["area_sqm"] is not None:
        area = f"{meta['area_sqm']:,.0f} SQM"
    if area: header_parts.append(f"Area: {area}")
    if meta["bedrooms"] is not None:
        bedrooms = str(meta["bedrooms"])
        bedroom_options = raw.get("bedroom_options")
        bedrooms_max = raw.get("bedrooms_max")
        if bedroom_options:
            bedrooms = ", ".join(str(value) for value in bedroom_options)
        elif bedrooms_max is not None:
            bedrooms = f"{bedrooms}-{bedrooms_max}"
        header_parts.append(f"Bedrooms: {bedrooms}")
    if meta["price"] is not None:
        header_parts.append(f"Price: {meta['price']:,.0f}" + (f" {meta['currency']}" if meta["currency"] else ""))
    if meta["status"]: header_parts.append(f"Status: {meta['status']}")
    if meta["amenities"]: header_parts.append(f"Amenities: {', '.join(meta['amenities'])}")
    header = " | ".join(header_parts)

    paragraphs = page.get("paragraphs") or [page.get("text") or ""]
    chunks, buf = [], ""
    for para in paragraphs:
        for p in _wrap(para, max_chars):
            if len(buf) + len(p) + 1 <= max_chars:
                buf = f"{buf}\n{p}".strip()
            else:
                if buf: chunks.append(f"{header}\n\n{buf}")
                buf = p
    if buf: chunks.append(f"{header}\n\n{buf}")
    return chunks or [header]


def _wrap(p, n):
    """Split a long paragraph on sentence boundaries (hard-cut only if one sentence exceeds n).
    The old code did `p[:max_chars]`, silently dropping the rest of long paragraphs."""
    if len(p) <= n:
        return [p]
    out, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", p):
        while len(sent) > n:
            if cur: out.append(cur); cur = ""
            out.append(sent[:n]); sent = sent[n:]
        if len(cur) + len(sent) + 1 <= n:
            cur = f"{cur} {sent}".strip()
        else:
            if cur: out.append(cur)
            cur = sent
    if cur: out.append(cur)
    return out


def _canon_links(p):
    """Rewrite legacy alias paths inside page text so the LLM cites canonical URLs."""
    def fix(s):
        for old, new in ALIASES.items():
            s = s.replace(old, new)
        return s
    p["text"] = fix(p.get("text") or "")
    if p.get("paragraphs"):
        p["paragraphs"] = [fix(x) for x in p["paragraphs"]]
    if p.get("url"):
        p["url"] = fix(p["url"])
    return p


def is_junk(p):
    text = p.get("text") or ""
    if "Incapsula" in text:          # anti-bot block page, not real content
        return True
    return len(text) < 80 and not p.get("specs")


def iter_jsonl(path):
    """Read JSON objects from JSONL, also accepting legacy raw newlines inside string values."""
    text = open(path, encoding="utf-8").read()
    buf, depth, in_string, escaped, line_no, start_line = [], 0, False, False, 1, 1
    record_no = 0
    for char in text:
        if depth == 0:
            if char.isspace():
                line_no += char == "\n"
                continue
            if char != "{":
                raise ValueError(f"{path}:{line_no}: expected a JSON object")
            buf = ["{"]
            depth, in_string, escaped, start_line = 1, False, False, line_no
            continue

        if char in "\r\n":
            if in_string:
                buf.append("\\r" if char == "\r" else "\\n")
            else:
                buf.append(char)
            line_no += char == "\n"
            continue

        buf.append(char)
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                record_no += 1
                try:
                    yield json.loads("".join(buf))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{start_line}: invalid JSON record {record_no}: {exc}") from exc
                buf = []

    if depth:
        raise ValueError(f"{path}:{start_line}: incomplete JSON record at end of file")


def load_pages():
    """Read all jsonl files; one page per (source, canonical path), best-quality row wins."""
    best, skipped = {}, 0
    for path in sorted(glob.glob("/data/*.jsonl")):
        for p in iter_jsonl(path):
            if is_junk(p):
                skipped += 1
                continue
            key = (p.get("source", "unknown"), canon_key(p["url"]))
            cur = best.get(key)
            if cur is None or len(p.get("text") or "") > len(cur.get("text") or ""):
                best[key] = p
    return list(best.values()), skipped


def main(prune=False):
    pages, skipped = load_pages()
    n, urls = 0, []
    with conn() as c, c.cursor() as cur:
        for p in pages:
            p = _canon_links(p)
            meta = extract_structured_fields(p)
            cur.execute(
                """INSERT INTO documents (
                       source, url, doc_type, title, developer, brand_partner,
                       city, district, country, transaction_type, property_type,
                       status, completion_date, price, currency, area_sqm, bedrooms,
                       bathrooms, furnishing, amenities, fixtures, rega_license,
                       last_updated, raw
                   ) VALUES (
                       %(source)s, %(url)s, %(doc_type)s, %(title)s, %(developer)s, %(brand_partner)s,
                       %(city)s, %(district)s, %(country)s, %(transaction_type)s, %(property_type)s,
                       %(status)s, %(completion_date)s, %(price)s, %(currency)s, %(area_sqm)s, %(bedrooms)s,
                       %(bathrooms)s, %(furnishing)s, %(amenities)s, %(fixtures)s, %(rega_license)s,
                       %(last_updated)s, %(raw)s
                   )
                   ON CONFLICT (url) DO UPDATE SET
                       doc_type = EXCLUDED.doc_type, title = EXCLUDED.title,
                       developer = EXCLUDED.developer, brand_partner = EXCLUDED.brand_partner,
                       city = EXCLUDED.city, district = EXCLUDED.district, country = EXCLUDED.country,
                       transaction_type = EXCLUDED.transaction_type, property_type = EXCLUDED.property_type,
                       status = EXCLUDED.status, completion_date = EXCLUDED.completion_date,
                       price = EXCLUDED.price, currency = EXCLUDED.currency, area_sqm = EXCLUDED.area_sqm,
                       bedrooms = EXCLUDED.bedrooms, bathrooms = EXCLUDED.bathrooms,
                       furnishing = EXCLUDED.furnishing, amenities = EXCLUDED.amenities,
                       fixtures = EXCLUDED.fixtures, rega_license = EXCLUDED.rega_license,
                       last_updated = EXCLUDED.last_updated, raw = EXCLUDED.raw,
                       scraped_at = now()
                   RETURNING id""",
                meta,
            )
            doc_id = cur.fetchone()[0]
            cur.execute("DELETE FROM chunks WHERE doc_id = %s", (doc_id,))
            parts = build_chunks(p, meta)
            embs = model.encode(parts, normalize_embeddings=True, batch_size=32)
            for part, e in zip(parts, embs):
                cur.execute("INSERT INTO chunks (doc_id, content, embedding) VALUES (%s, %s, %s)", (doc_id, part, e))
            urls.append(p["url"])
            n += 1

        pruned = 0
        if prune and urls:
            # remove stale rows (old alias / blocked-page documents) for the sources we just loaded
            sources = sorted({p.get("source", "unknown") for p in pages})
            cur.execute("DELETE FROM chunks WHERE doc_id IN "
                        "(SELECT id FROM documents WHERE source = ANY(%s) AND url <> ALL(%s))", (sources, urls))
            cur.execute("DELETE FROM documents WHERE source = ANY(%s) AND url <> ALL(%s)", (sources, urls))
            pruned = cur.rowcount
        c.commit()
    print(f"Successfully ingested {n} documents (skipped {skipped} blocked/empty rows, pruned {pruned} stale documents).")


if __name__ == "__main__":
    main(prune="--prune" in sys.argv)
