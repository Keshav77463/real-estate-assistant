import os, re
from sentence_transformers import SentenceTransformer
from .db import conn
from .vocab import (
    AMENITY_KEYWORDS, has_term, canon_key, property_key, mentioned_property_titles,
)

model = SentenceTransformer(os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5"))
QP = "Represent this sentence for searching relevant passages: "

BEDROOM_QUERY_RE = re.compile(r"\b(\d+)\s*[- ]?\s*(?:bed(?:room)?s?|br)\b", re.I)
PRICE_UNDER_RE = re.compile(r"(?:under|below|less than|max|budget|up to)\s*(?:sar|aed|usd|\$)?\s*([\d,.]+)\s*(m|million|k|thousand)?", re.I)
PROPERTY_TYPES = ["penthouse", "duplex", "townhouse", "villa", "apartment", "residential tower", "land"]


def detect_filters(q):
    ql = q.lower()
    filters = {"source": None, "city": None, "country": None, "property_type": None,
               "bedrooms": None, "max_price": None, "currency": None, "amenities": None}

    if "dar global" in ql or "darglobal" in ql:
        filters["source"] = "darglobal"
    elif "wasalt" in ql:
        filters["source"] = "wasalt"

    for pt in PROPERTY_TYPES:
        if re.search(rf"\b{re.escape(pt)}s?\b", ql):   # word match: "land" no longer fires on "Scotland"/"island"
            filters["property_type"] = pt.replace(" ", "_")
            break

    bm = BEDROOM_QUERY_RE.search(ql)
    if bm:
        filters["bedrooms"] = int(bm.group(1))
    elif "studio" in ql:
        filters["bedrooms"] = 0

    pm = PRICE_UNDER_RE.search(ql)
    if pm:
        val = float(pm.group(1).replace(",", ""))
        mult = (pm.group(2) or "").lower()
        if mult in ("m", "million"): val *= 1_000_000
        elif mult in ("k", "thousand"): val *= 1_000
        filters["max_price"] = val

    if "sar" in ql: filters["currency"] = "SAR"
    elif "aed" in ql: filters["currency"] = "AED"
    elif "usd" in ql or "$" in ql: filters["currency"] = "USD"

    # Amenity questions ("which have a spa") become a structured filter on documents.amenities
    filters["amenities"] = [a for a in AMENITY_KEYWORDS if has_term(a, ql)] or None

    with conn() as c:
        cities = [r[0] for r in c.execute("SELECT DISTINCT city FROM documents WHERE city IS NOT NULL")]
        countries = [r[0] for r in c.execute("SELECT DISTINCT country FROM documents WHERE country IS NOT NULL")]

    filters["city"] = next((x for x in cities if x.lower() in ql), None)
    filters["country"] = next((x for x in countries if x.lower() in ql), None)
    return filters


def build_hybrid_sql(filters, pool):
    """Returns (sql, filter_params). Kept separate from execution so it can be unit-tested."""
    where, params = "", []
    for col in ("source", "city", "country", "property_type", "currency"):
        if filters.get(col):
            where += f" AND d.{col} = %s"; params.append(filters[col])
    if filters.get("bedrooms") is not None:
        where += (
            " AND (d.raw->'bedroom_options' @> jsonb_build_array(%s)"
            " OR (COALESCE(jsonb_typeof(d.raw->'bedroom_options') <> 'array', true)"
            " AND d.bedrooms <= %s"
            " AND COALESCE(NULLIF(d.raw->>'bedrooms_max', '')::int, d.bedrooms) >= %s))"
        )
        params.extend([filters["bedrooms"], filters["bedrooms"], filters["bedrooms"]])
    if filters.get("max_price") is not None:
        where += " AND d.price <= %s"; params.append(filters["max_price"])
    if filters.get("amenities"):
        where += " AND d.amenities @> %s::text[]"; params.append(filters["amenities"])

    # NOTE: 1.0/... (not 1/...). `1/(60 + ROW_NUMBER())` is integer division in Postgres and
    # evaluates to 0 for every row, which made all RRF scores tie and ranking meaningless.
    sql = f"""
    WITH vec AS (
        SELECT c.id, 1.0 / (60 + ROW_NUMBER() OVER (ORDER BY c.embedding <=> %s::vector)) AS s
        FROM chunks c JOIN documents d ON d.id = c.doc_id
        WHERE true {where}
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    ), fts AS (
        SELECT c.id, 1.0 / (60 + ROW_NUMBER() OVER (ORDER BY ts_rank_cd(c.tsv, q.query) DESC)) AS s
        FROM chunks c JOIN documents d ON d.id = c.doc_id,
             websearch_to_tsquery('english', %s) AS q(query)
        WHERE c.tsv @@ q.query {where}
        ORDER BY ts_rank_cd(c.tsv, q.query) DESC
        LIMIT %s
    )
    SELECT c.content, d.title, d.url, d.source
    FROM (SELECT COALESCE(vec.id, fts.id) AS id,
                 COALESCE(vec.s, 0) + COALESCE(fts.s, 0) AS score
          FROM vec FULL OUTER JOIN fts ON vec.id = fts.id) x
    JOIN chunks c ON c.id = x.id
    JOIN documents d ON d.id = c.doc_id
    ORDER BY x.score DESC
    LIMIT %s
    """
    return sql, params


def hybrid_search(v, q_text, filters, k=8, pool=60):
    """Vector + full-text search fused with Reciprocal Rank Fusion; returns up to k chunks."""
    v_list = v.tolist() if hasattr(v, "tolist") else list(v)
    pool = max(pool, k * 2)
    sql, params = build_hybrid_sql(filters, pool)
    args = [v_list, *params, v_list, pool, q_text, *params, pool, k]
    with conn() as c:
        return c.execute(sql, args).fetchall()


FOCUS_STOP = {
    "the", "and", "for", "with", "what", "which", "show", "tell", "about", "have",
    "has", "does", "are", "any", "all", "list", "give", "details", "detail", "price",
    "prices", "available", "offer", "offers", "like", "its", "their", "this", "that",
}


def _sig_tokens(s):
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower())
            if len(w) >= 3 and w not in FOCUS_STOP}


def retrieve(q, k=10, max_chunks_per_property=2):
    """Returns one entry per property (k properties max): (merged chunk text, title, url, source)."""
    filters = detect_filters(q)
    v = model.encode(QP + q, normalize_embeddings=True)
    candidates = hybrid_search(v, q, filters, k=k * 5)

    props = {}  # (source, canonical path) -> entry; dict order == rank order of each property's best chunk
    for content, title, url, source in candidates:
        key = property_key(source, url, content)
        page_key = (source, canon_key(url))
        if key in props and props[key]["page_key"] != page_key:
            continue
        if key not in props:
            if len(props) >= k:
                continue
            props[key] = {
                "parts": [], "seen": set(), "title": title, "url": url,
                "source": source, "page_key": page_key,
            }
        p = props[key]
        norm = " ".join(content.split()).lower()
        if norm in p["seen"] or len(p["parts"]) >= max_chunks_per_property:
            continue
        p["seen"].add(norm)
        # every chunk of a document starts with the same metadata header; keep it once
        p["parts"].append(content if not p["parts"] else content.split("\n\n", 1)[-1])

    if filters.get("bedrooms") is not None:
        with conn() as c:
            titles = [row[0] for row in c.execute(
                "SELECT title FROM documents WHERE title IS NOT NULL"
            )]
        named_titles = mentioned_property_titles(q, titles)
        if named_titles:
            props = {key: prop for key, prop in props.items() if prop["title"] in named_titles}

    # When the question names a specific property (3+ significant title words), drop unrelated
    # properties that only shared the generic filters (e.g. "villa").
    qt = _sig_tokens(q)
    overlaps = {key: len(qt & _sig_tokens(p["title"])) for key, p in props.items()}
    if overlaps:
        best = max(overlaps.values())
        if best >= 3:
            cutoff = max(2, best - 1)
            props = {key: p for key, p in props.items() if overlaps[key] >= cutoff}

    return [("\n".join(p["parts"]), p["title"], p["url"], p["source"]) for p in props.values()]
