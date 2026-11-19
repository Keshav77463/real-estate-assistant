"""Same canonical-URL logic as app/vocab.py (duplicated because scraper/ runs standalone)."""
from urllib.parse import urlparse

ALIASES = {
    "/trump-international-hotel-tower-dubai": "/trump-international-hotel-and-tower-dubai",
    "/dg-villas-at-jge": "/d-villas-at-jge",
}
CARRY = ("city_override", "country_override", "location_label")


def canon_key(url):
    path = urlparse(url or "").path.rstrip("/").lower()
    return ALIASES.get(path, path)


def _quality(r):
    text = r.get("text") or ""
    return (0 if "Incapsula" in text else 1, 1 if r.get("next_data") else 0, len(text))


def dedupe_rows(rows):
    """One row per canonical page: keep the best-quality row, carry over catalogue overrides."""
    best, order = {}, []
    for r in rows:
        k = canon_key(r["url"])
        if k not in best:
            best[k] = r
            order.append(k)
            continue
        cur = best[k]
        win, lose = (r, cur) if _quality(r) > _quality(cur) else (cur, r)
        for f in CARRY:
            if not win.get(f) and lose.get(f):
                win[f] = lose[f]
        best[k] = win
    return [best[k] for k in order]
