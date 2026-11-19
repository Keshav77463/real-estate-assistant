import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import requests

from common import extract_page
from urlnorm import dedupe_rows

DATA = Path(__file__).resolve().parent.parent / 'data' / 'darglobal.jsonl'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}


def fetch_wb(wb_url, attempts=4):
    for a in range(attempts):
        try:
            r = requests.get(wb_url, headers=HEADERS, timeout=90)
            if r.status_code == 429:
                wait = 45 * (a + 1)
                print(f'    429, waiting {wait}s')
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            print('    retry after error:', str(e)[:80])
            time.sleep(30 * (a + 1))
    return None


rows = [json.loads(l) for l in open(DATA, encoding='utf-8')]
out = []
fixed = 0
print('cooling down 90s...')
time.sleep(90)
for r in rows:
    url = r['url']
    if 'Incapsula' not in (r.get('text') or ''):
        out.append(r)
        continue
    try:
        with urllib.request.urlopen(f"http://archive.org/wayback/available?url={url}", timeout=30) as resp:
            snap = json.loads(resp.read()).get('archived_snapshots', {}).get('closest')
        if not snap or snap.get('status') != '200':
            print('no snapshot:', url.split('co.uk')[-1])
            out.append(r)
            time.sleep(3)
            continue
        wb = f"https://web.archive.org/web/{snap['timestamp']}id_/{url}"
        html = fetch_wb(wb)
        time.sleep(8)
        if not html:
            out.append(r)
            continue
        page = extract_page(html, url)
        page['source'] = 'darglobal'
        page['scraped_at'] = datetime.now(timezone.utc).isoformat()
        ok = len(page['text']) > 250 or bool(page['next_data'])
        print(('ok  ' if ok else 'thin'), url.split('co.uk')[-1], '| text:', len(page['text']), '| next:', bool(page['next_data']))
        out.append(page if ok else r)
        fixed += 1 if ok else 0
    except Exception as e:
        print('fail', url.split('co.uk')[-1], str(e)[:80])
        out.append(r)

out = dedupe_rows(out)
with open(DATA, 'w', encoding='utf-8') as f:
    for r in out:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f'recovered {fixed} pages this pass, total {len(out)}')
