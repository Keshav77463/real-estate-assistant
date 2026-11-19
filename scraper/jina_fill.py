import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from urlnorm import canon_key, dedupe_rows

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / 'data' / 'darglobal.jsonl'
CATALOGUE = HERE / 'jina_projects.md'

COUNTRY_MAP = {
    'uae': 'UAE', 'united arab emirates': 'UAE',
    'ksa': 'Saudi Arabia', 'saudi arabia': 'Saudi Arabia',
    'qatar': 'Qatar', 'oman': 'Oman', 'spain': 'Spain',
    'united kingdom': 'United Kingdom', 'england': 'United Kingdom',
}

CITY_ALIASES = {
    'al marjan island': 'Ras Al Khaimah', 'rak': 'Ras Al Khaimah',
    'aida': 'Muscat', 'amaya': 'Jeddah', 'rayana': 'Riyadh',
    'benahavis': 'Benahavis', 'cortesin': 'Cortesin', 'simaisma': 'Simaisma',
}

KNOWN_CITIES = ['Dubai', 'Jeddah', 'Riyadh', 'London', 'Doha', 'Muscat',
                'Simaisma', 'Benahavis', 'Cortesin', 'Marbella', 'Mallorca']


def parse_label(label):
    parts = [p.strip(' |') for p in re.split(r'[,|]', label) if p.strip(' |')]
    city = country = None
    for p in reversed(parts):
        low = p.lower()
        if low in COUNTRY_MAP and country is None:
            country = COUNTRY_MAP[low]
        elif p in KNOWN_CITIES and city is None:
            city = p
        elif low in CITY_ALIASES and city is None:
            city = CITY_ALIASES[low]
    return city, country


text = CATALOGUE.read_text(encoding='utf-8')
entries = re.findall(r'\[!\[Image \d+: [^\]]*\]\([^)]+\)\s*(.*?)\s*###\s*(.*?)\]\((https://darglobal\.co\.uk/[^)\s"]+)', text)
catalogue = {}
for loc, title, url in entries:
    catalogue[url] = {'label': loc.strip(), 'title': title.strip()}
print('catalogue entries:', len(catalogue))

rows = dedupe_rows([json.loads(l) for l in open(DATA, encoding='utf-8')])

EXTRA_OVERRIDES = {
    '/aida-rizz-villas': {'city_override': 'Muscat', 'country_override': 'Oman', 'location_label': 'AIDA, Muscat, Oman'},
}
for r in rows:
    o = EXTRA_OVERRIDES.get(canon_key(r['url']))
    if o:
        r.update(o)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}


def jina_page(url):
    r = requests.get('https://r.jina.ai/' + url, headers=HEADERS, timeout=120)
    r.raise_for_status()
    body = r.text
    title = ''
    m = re.search(r'^Title:\s*(.+)$', body, re.M)
    if m:
        title = m.group(1).strip()
    mi = body.find('Markdown Content:')
    content = body[mi + len('Markdown Content:'):] if mi >= 0 else body
    content = re.sub(r'!\[Image \d+:[^\]]*\]\([^)]*\)', '', content)
    content = re.sub(r'\]\((https?://[^)\s]+)[^)]*\)', ']', content)
    content = re.sub(r'\[([^\]]*)\]', r'\1', content)
    content = re.sub(r'\n{2,}', '\n', content)
    paragraphs = [p.strip() for p in content.split('\n') if len(p.strip()) >= 60]
    return {
        'url': url,
        'title': title,
        'meta_description': None,
        'next_data': None,
        'json_ld': [],
        'specs': {},
        'paragraphs': paragraphs,
        'text': content.strip(),
    }


def is_blocked(r):
    return 'Incapsula' in (r.get('text') or '')


by_key = {canon_key(r['url']): r for r in rows}  # case/alias-insensitive

for url, info in catalogue.items():
    city, country = parse_label(info['label'])
    row = by_key.get(canon_key(url))
    if row is None:
        row = {'url': url}
        rows.append(row)
        by_key[canon_key(url)] = row
    row['city_override'] = city
    row['country_override'] = country
    row['location_label'] = info['label']
    if not row.get('title'):
        row['title'] = info['title']

need_fetch = [r for r in rows if is_blocked(r) or len(r.get('text') or '') < 250]
print('pages needing jina fetch:', len(need_fetch))
for i, row in enumerate(need_fetch, 1):
    url = row['url']
    try:
        page = jina_page(url)
        page['source'] = 'darglobal'
        page['scraped_at'] = datetime.now(timezone.utc).isoformat()
        page['city_override'] = row.get('city_override')
        page['country_override'] = row.get('country_override')
        page['location_label'] = row.get('location_label')
        if not page['title']:
            page['title'] = row.get('title', '')
        ok = len(page['text']) > 250
        print(f"[{i}/{len(need_fetch)}] {'ok  ' if ok else 'thin'} {url.split('co.uk')[-1]} text={len(page['text'])}")
        if ok:
            row.update(page)
        time.sleep(4)
    except Exception as e:
        print(f"[{i}/{len(need_fetch)}] fail {url.split('co.uk')[-1]}: {str(e)[:90]}")
        time.sleep(4)

rows = dedupe_rows(rows)
with open(DATA, 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print('saved', len(rows), 'rows')
