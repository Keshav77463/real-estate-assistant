# What changed

## app/rag.py
- **Main bug:** `1/(60 + ROW_NUMBER() ...)` was integer division (always 0), so every RRF score tied and
  results came back in insertion order. Now `1.0/(...)`.
- FTS branch now filters with `c.tsv @@ websearch_to_tsquery(...)` (was ranking every row; `plainto_tsquery`
  ANDed every word). Both branches are capped with a candidate pool (LIMIT).
- `retrieve()` returns one entry per property (merged, de-duplicated chunks, metadata header kept once),
  keyed on (source, canonical path) so www/case/trailing-slash/alias URLs collapse. Defaults: k=10 properties, 2 chunks each.
- New amenity filter: "which have a spa" -> `d.amenities @> ARRAY['Spa']`.
- Word-boundary matching for property type ("land" vs "Scotland") and bedrooms ("3 br" vs "3 brand").

## app/ingest.py
- Amenities/fixtures: whole-word match (`Spa` no longer matches space/Spain/spacious), searched in body + spec values only.
- Skips Incapsula block pages; dedupes pages by canonical URL before inserting.
- `python -m app.ingest --prune` also deletes stale documents (old alias/case duplicates) for the loaded sources.
- Bedroom regex fixed (word boundary, ranges: min stored in `bedrooms`, max in `raw.bedrooms_max`); "Yoga Studio" no longer = studio flat.
- Property type: URL slug / title / spec first, then most frequent body term. Status: no more bare "completed" match.
- Long paragraphs are split on sentences instead of truncated to 800 chars. Header no longer prints "None" currency.

## app/vocab.py (new)
Shared amenity lists, `has_term()`, `canon_key()` and the alias map. Removed bare "Park", "School", "Security" amenities.
Verify the two entries in `ALIASES` against the live site.

## scraper/
- `urlnorm.py` (new): same canonical-URL logic; `jina_fill.py` and `wayback_fix.py` now dedupe rows by it
  (fixes `Sunrise-Haven-Luxury-Villas` vs `sunrise-haven-luxury-villas`) and use paths relative to the repo instead of `D:\downloads\...`.
- `darglobal_projects.txt`: two alias slugs commented out.
- `Dockerfile` / `requirements.txt` are unchanged (they look like the scraper's; move them if your layout differs).
- `crawl.py`, `common.py`, `app/main.py`, `app/llm.py`, `app/db.py` are unchanged.

## After copying the files in
1. `python -m app.ingest --prune`   (rebuilds chunks, so headers/embeddings lose the false "Spa")
2. Re-run the Dubai spa query.

## Local application notes (this repo)
- Files mapped as: `app/vocab.py` -> `backend/app/vocab.py`, `app/rag.py` -> `backend/app/rag.py`, `app/ingest.py` -> `backend/scraper/ingest.py` (runs as `python -m scraper.ingest`), `scraper/*` -> `scraper/*`.
- `scraper/jina_fill.py`: added `EXTRA_OVERRIDES` (`/aida-rizz-villas` -> Muscat/Oman) because it is not in the catalogue and text matching tagged it Dubai.
- `scraper/jina_fill.py`: fetch condition changed to also fetch next_data-only pages with empty text (Rayana Mansions, Trump Park Residences were skipped by both jina_fill and ingest).
- After ingest: 53 documents (43 DarGlobal + 10 Wasalt), 0 skipped, alias duplicates pruned.
