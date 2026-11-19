import json, re, time, gzip, requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RealEstateResearchBot/2.0)"
}

def get(url, delay=1.0):
    time.sleep(delay)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    if r.content[:2] == b"\x1f\x8b":
        return gzip.decompress(r.content).decode("utf-8", "replace")
    return r.text

def sitemap_urls(url, limit=None):
    soup = BeautifulSoup(get(url), "xml")
    out = []
    for loc in soup.find_all("loc"):
        u = loc.text.strip()
        if u.endswith(".xml"):
            out.extend(sitemap_urls(u, limit=limit))
        else:
            out.append(u)
        if limit and len(out) >= limit:
            return out[:limit]
    return out

def render(url):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        page = b.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2000)
        html = page.content()
        b.close()
    return html

def _extract_spec_pairs(soup):
    specs = {}
    known_labels = {
        "property type", "area (sqm)", "area (sq. ft.)", "area", "size",
        "built-up area", "plot area", "unit types",
        "location", "status", "completion", "completion date", "starting price",
        "price", "bedrooms", "bathrooms", "furnishing", "developer", "brand", "last updated"
    }
    for el in soup.find_all(["div", "li", "td", "dt", "span", "p", "h3", "h4", "h5", "h6"]):
        txt = el.get_text(" ", strip=True)
        if not txt or len(txt) > 40:
            continue
        norm = txt.lower().rstrip(":")
        if norm in known_labels:
            nxt = el.find_next_sibling()
            if nxt:
                val = nxt.get_text(" ", strip=True)
                if val and val.lower().rstrip(":") not in known_labels and len(val) < 160:
                    specs[norm] = val

    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            k = dt.get_text(" ", strip=True).lower().rstrip(":")
            v = dd.get_text(" ", strip=True)
            if k and v and len(k) < 50 and len(v) < 200:
                specs[k] = v
    return specs

def extract_page(html, url):
    soup = BeautifulSoup(html, "lxml")
    data = {
        "url": url,
        "title": soup.title.get_text(strip=True) if soup.title else None,
        "meta_description": None,
        "next_data": None,
        "json_ld": [],
        "specs": {},
        "paragraphs": [],
        "text": "",
    }

    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        data["meta_description"] = meta_desc["content"].strip()

    nd = soup.find("script", id="__NEXT_DATA__")
    try:
        nd_str = nd.string.strip() if nd and nd.string else None
        data["next_data"] = json.loads(nd_str) if nd_str else None
    except Exception:
        data["next_data"] = None

    for s in soup.find_all("script", type="application/ld+json"):
        try:
            raw = s.string.lstrip("\ufeff").strip() if s.string else ""
            if not raw:
                continue
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                data["json_ld"].extend(parsed)
            else:
                data["json_ld"].append(parsed)
        except Exception:
            pass

    for t in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        t.decompose()

    main = soup.find("main") or soup.body
    if main:
        data["specs"] = _extract_spec_pairs(main)
        paragraphs = []
        seen_p = set()
        for p in main.find_all(["p", "article", "section"]):
            if p.name in ("article", "section") and len(p.find_all("p")) > 0:
                continue
            ptxt = re.sub(r"\s+", " ", p.get_text(" ", strip=True)).strip()
            if len(ptxt) >= 60 and ptxt not in seen_p:
                seen_p.add(ptxt)
                paragraphs.append(ptxt)
        data["paragraphs"] = paragraphs
        text = main.get_text("\n", strip=True)
        data["text"] = re.sub(r"\n{2,}", "\n", text)

    return data
