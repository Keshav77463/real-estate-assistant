"""Shared vocab + helpers used by ingest.py and rag.py (kept free of heavy imports)."""
import re
from decimal import Decimal
from urllib.parse import urlparse

# NOTE: bare "Park", "School" and "Security" were removed on purpose: they collide with
# project names ("Trump Park Residences", "Old Park Lane") and site navigation.
AMENITY_KEYWORDS = [
    "Swimming Pool", "Infinity Pool", "Private Pool", "Gym", "Fitness Center", "Spa",
    "Sky Garden", "Yoga Studio", "Private Beach", "Beach Access", "Golf Course", "Parking",
    "Indoor Parking", "Valet Parking", "Concierge", "24/7 Security", "Mosque",
    "Health Centre", "Garden", "Jacuzzi", "Sauna", "Steam Room", "Tennis Court",
    "Padel Court", "Kids Club", "Children's Play Area", "BBQ Area", "Clubhouse",
    "Business Center", "Co-working Space", "Cinema", "Library", "Restaurant",
]

BEDROOM_OPTIONS_RE = re.compile(
    r"\b(\d+(?:(?:\s*(?:,|/|&|\band\b|[-\u2013\u2014])\s*)\d+)+)"
    r"\s*[- ]*(?:bed(?:room)?s?|br)\b",
    re.I,
)
AREA_UNITS_RE = re.compile(r"sq\.?\s*ft|sqft|sq\.?\s*m|sqm|m²", re.I)
AREA_VALUE_RE = re.compile(
    r"(?P<start>\d[\d,]*(?:\.\d+)?)"
    r"(?:\s*(?:to|[-\u2013\u2014])\s*(?P<end>\d[\d,]*(?:\.\d+)?))?"
    r"\s*(?P<unit>sq\.?\s*ft|sqft|sq\.?\s*m|sqm|m²)?",
    re.I,
)
AREA_LABEL_RE = re.compile(
    r"\barea(?:\s+bau)?\s*(?:\(\s*(?P<label_unit>sq\.?\s*ft|sqft|sq\.?\s*m|sqm|m²)\s*\))?"
    r"\s*:?\s*(?P<value>\d[\d,]*(?:\.\d+)?"
    r"(?:\s*(?:to|[-\u2013\u2014])\s*\d[\d,]*(?:\.\d+)?))"
    r"\s*(?P<value_unit>sq\.?\s*ft|sqft|sq\.?\s*m|sqm|m²)?",
    re.I,
)
PROPERTY_QUERY_NOISE = {
    "available", "bed", "bedroom", "bedrooms", "br", "apartment", "apartments",
    "villa", "villas", "townhouse", "townhouses", "penthouse", "penthouses",
    "duplex", "land", "property", "properties", "listing", "listings", "unit",
    "units", "layout", "layouts", "show", "find", "give", "tell", "what", "which",
    "does", "have", "has", "with", "for", "from", "under", "below", "max", "budget",
    "price", "prices", "sar", "aed", "usd", "million", "thousand", "luxury",
}


FIXTURE_KEYWORDS = [
    "Smart Home", "Split AC", "Central AC", "Elevator", "CCTV", "Balcony", "Maid's Room",
]


def has_term(term, text):
    """Whole-word match (plural 's' allowed). 'Spa' no longer matches 'space', 'Spain', 'spacious'."""
    return re.search(rf"(?<!\w){re.escape(term)}s?(?!\w)", text or "", re.I) is not None


def extract_bedroom_options(text):
    """Find explicit multi-layout bedroom lists such as '1, 2 & 3-bedrooms'."""
    for match in BEDROOM_OPTIONS_RE.finditer(text or ""):
        values = [int(value) for value in re.findall(r"\d+", match.group(1))]
        separators = match.group(1)
        if (len(values) == 2 and re.search(r"[-\u2013\u2014]|\bto\b", separators, re.I)
                and not re.search(r"[,/&]|\band\b", separators, re.I)):
            continue
        if len(values) > 1:
            return sorted(set(values))
    return []


def _format_area_value(value, unit=None):
    match = AREA_VALUE_RE.search(str(value or ""))
    if not match:
        return None

    def format_number(number):
        parsed = Decimal(number.replace(",", ""))
        return f"{parsed:,.2f}".rstrip("0").rstrip(".") if parsed % 1 else f"{int(parsed):,}"

    unit = match.group("unit") or unit
    normalized_unit = ""
    if unit:
        normalized_unit = "SQFT" if "ft" in unit.lower() else "SQM"
    area = format_number(match.group("start"))
    if match.group("end"):
        area += f" to {format_number(match.group('end'))}"
    return f"{area} {normalized_unit}".strip()


def extract_area_display(specs, text):
    """Prefer a labeled area range and preserve its source unit for display."""
    for key, value in (specs or {}).items():
        if "area" in key.lower():
            unit = AREA_UNITS_RE.search(key)
            display = _format_area_value(value, unit.group(0) if unit else None)
            if display:
                return display

    for match in AREA_LABEL_RE.finditer(text or ""):
        unit = match.group("value_unit") or match.group("label_unit")
        display = _format_area_value(match.group("value"), unit)
        if display:
            return display
    return None


def mentioned_property_titles(query, titles):
    """Match explicitly named properties without mistaking search filters for names."""
    query_tokens = {
        word for word in re.findall(r"[a-z0-9]+", query.lower())
        if len(word) >= 3 and word not in PROPERTY_QUERY_NOISE
    }
    if len(query_tokens) < 2:
        return set()

    scores = []
    for title in titles:
        title_tokens = {
            word for word in re.findall(r"[a-z0-9]+", (title or "").lower())
            if len(word) >= 3 and word not in PROPERTY_QUERY_NOISE
        }
        score = len(query_tokens & title_tokens)
        if score >= 2:
            scores.append((score, title))
    if not scores:
        return set()
    best = max(score for score, _ in scores)
    return {title for score, title in scores if score >= max(2, best - 1)}


# Different slugs that point at the same project. Verify against the live site.
ALIASES = {
    "/trump-international-hotel-tower-dubai": "/trump-international-hotel-and-tower-dubai",
    "/dg-villas-at-jge": "/d-villas-at-jge",
}


def canon_key(url):
    """Identity of a page: path only, lower-cased, no trailing slash, aliases merged.
    Compare together with `source` — different sites can share a path."""
    path = urlparse(url or "").path.rstrip("/").lower()
    return ALIASES.get(path, path)


def property_key(source, url, content):
    """Collapse duplicate Wasalt ads when their indexed property facts are identical."""
    page_key = (source, canon_key(url))
    if (source or "").lower() != "wasalt":
        return page_key

    lines = (content or "").split("\n\n", 1)[0].splitlines()
    header = lines[0].strip().lower() if lines else ""
    required = ("title:", "location:", "type:", "bedrooms:", "price:")
    if all(field in header for field in required):
        return ("wasalt", " ".join(header.split()))
    return page_key
