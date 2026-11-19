"""Usage: python scraper/crawl.py darglobal [max_pages] | wasalt [max_pages]"""
import json, sys, pathlib
from datetime import datetime, timezone
from common import get, sitemap_urls, render, extract_page
from urlnorm import canon_key

SITES = {
    "darglobal": {
        "sitemap": "https://www.darglobal.co.uk/sitemap.xml",
        "include": ["/project", "/projects", "/properties", "/developments"],
        "default_limit": 300,
    },
    "wasalt": {
        "sitemap": "https://cdn.wasalt.sa/sitemap/product_sitemap_en_sa.xml.gz",
        "include": ["/property", "/properties", "/listing", "/en/property", "/ar/property"],
        "default_limit": 300,
    },
}

def crawl(name, limit=None, urls_file=None, append=False):
    cfg = SITES[name]
    if urls_file:
        with open(urls_file, encoding="utf-8") as fh:
            urls = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
        print(f"Using {len(urls)} URLs from {urls_file}")
    else:
        max_pages = int(limit) if limit is not None else cfg["default_limit"]
        print(f"Fetching sitemap for {name}: {cfg['sitemap']}")
        urls = sitemap_urls(cfg["sitemap"])
        if cfg["include"]:
            filtered = [u for u in urls if any(p in u.lower() for p in cfg["include"])]
            if filtered:
                urls = filtered

    out_dir = pathlib.Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(exist_ok=True)
    output = out_dir / f"{name}.jsonl"
    if append and output.exists():
        existing = set()
        with open(output, encoding="utf-8") as f:
            for line in f:
                try:
                    existing.add(canon_key(json.loads(line)["url"]))
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
        urls = [u for u in urls if canon_key(u) not in existing]
    if limit is not None:
        urls = urls[:int(limit)]
    print(f"Targeting {len(urls)} URLs for {name}")

    mode = "a" if append else "w"
    with open(output, mode, encoding="utf-8") as f:
        for idx, u in enumerate(urls, 1):
            try:
                page = extract_page(get(u), u)
                if len(page["text"]) < 250 and not page["next_data"]:
                    page = extract_page(render(u), u)
                page["source"] = name
                page["scraped_at"] = datetime.now(timezone.utc).isoformat()
                f.write(json.dumps(page, ensure_ascii=False) + "\n")
                print(f"[{idx}/{len(urls)}] ok {u}")
            except Exception as e:
                print(f"[{idx}/{len(urls)}] fail {u}: {e}")

if __name__ == "__main__":
    name = sys.argv[1]
    limit, urls_file, append = None, None, False
    for arg in sys.argv[2:]:
        if arg == "--append":
            append = True
        elif arg.lower().endswith(".txt"):
            urls_file = arg
        else:
            limit = arg
    crawl(name, limit, urls_file, append)
