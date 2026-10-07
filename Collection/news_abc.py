
import argparse
import json
import os
import re
import time
from datetime import date

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

BASE = "https://www.abc.net.au"
TOPIC_URL = "https://www.abc.net.au/news/topic/ai"
PAGE_SIZE = 20
SOURCE_DEFAULT = "abc_au"
SCRAPE_DATE = date.today().isoformat()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
}

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)


def fetch_batch(offset, retries=3, backoff=3.0):
    url = f"{TOPIC_URL}?offset={offset}"
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                m = NEXT_DATA_RE.search(resp.text)
                if not m:
                    print(f"  [warn] offset {offset}: no __NEXT_DATA__")
                    return None
                data = json.loads(m.group(1))
                return data["props"]["pageProps"]["topicstories"].get("paginated")
            print(f"  [warn] offset {offset} -> HTTP {resp.status_code} (try {attempt}/{retries})")
        except (requests.RequestException, ValueError, KeyError) as exc:
            print(f"  [warn] offset {offset} -> {exc} (try {attempt}/{retries})")
        if attempt < retries:
            time.sleep(backoff * attempt)
    return None


def extract_text(node):
    if node is None:
        return ""
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("content", "")
        return "".join(extract_text(c) for c in (node.get("children") or []))
    if isinstance(node, list):
        return "".join(extract_text(c) for c in node)
    return ""


def parse_article(item):
    link = item.get("link") or ""
    title = (item.get("title") or "").strip()
    if not link or not title:
        return None
    synopsis = item.get("synopsis") or {}
    abstract = extract_text(synopsis.get("descriptor")).strip()
    pub = ((item.get("dates") or {}).get("firstPublished") or "")[:10]
    return {
        "ABSTRACT": abstract,
        "PUBLISH_DATE": pub,
        "TITLE": title,
        "URL": BASE + link if link.startswith("/") else link,
        "_id": item.get("id", ""),
    }


def to_news_records(records, source):
    final = []
    for i, rec in enumerate(records, start=1):
        final.append({
            "NEWS_ID": f"NEWS{i:06d}",
            "ABSTRACT": rec["ABSTRACT"],
            "NEWS_NER_ID": i,
            "PAGE": rec["PAGE"],
            "POSITION": rec["POSITION"],
            "PUBLISH_DATE": rec["PUBLISH_DATE"],
            "SCRAPE_DATE": rec["SCRAPE_DATE"],
            "SOURCE": source,
            "TITLE": rec["TITLE"],
            "URL": rec["URL"],
        })
    return final


def dump(records, out, source):
    with open(out, "w", encoding="utf-8") as f:
        json.dump(to_news_records(records, source), f, ensure_ascii=False, indent=4)


def scrape(out, source, max_pages=None, delay=1.5):
    records = []
    seen = set()
    offset = 0
    page = 0
    total = None
    while True:
        page += 1
        if max_pages is not None and page > max_pages:
            break
        print(f"[batch {page}] offset={offset}")
        paginated = fetch_batch(offset)
        if not paginated:
            print(f"  [stop] no data at offset {offset} (end of listing)")
            break

        if total is None:
            total = paginated.get("pagination", {}).get("total")
            print(f"  total articles reported: {total}")

        collection = paginated.get("collection") or []
        if not collection:
            print(f"  [stop] empty batch at offset {offset}")
            break

        new_on_page = 0
        for position, item in enumerate(collection, start=1):
            rec = parse_article(item)
            if rec is None or rec["_id"] in seen:
                continue
            seen.add(rec["_id"])
            new_on_page += 1
            records.append({
                "ABSTRACT": rec["ABSTRACT"],
                "PAGE": page,
                "POSITION": position,
                "PUBLISH_DATE": rec["PUBLISH_DATE"],
                "SCRAPE_DATE": SCRAPE_DATE,
                "TITLE": rec["TITLE"],
                "URL": rec["URL"],
            })
        print(f"  -> {len(collection)} articles, {new_on_page} new")

        dump(records, out, source)
        print(f"  [saved] {len(records)} records -> {out}")

        offset += PAGE_SIZE
        if total is not None and offset >= total:
            print(f"  [done] reached total ({total})")
            break
        if new_on_page == 0:
            print(f"  [stop] no new articles at offset {offset} (all duplicates)")
            break
        time.sleep(delay)

    return to_news_records(records, source)


def main():
    ap = argparse.ArgumentParser(description="Scrape ABC News AU AI topic column.")
    ap.add_argument("--max-pages", type=int, default=None,
                    help="limit number of 20-item batches (default: until exhausted)")
    ap.add_argument("--delay", type=float, default=1.5,
                    help="seconds to wait between batch requests")
    ap.add_argument("--source", default=SOURCE_DEFAULT,
                    help='SOURCE field value (default: "abc_au")')
    ap.add_argument("--out", default="NEWS_ABC_AI.json",
                    help="output JSON path (relative paths resolve next to this script)")
    args = ap.parse_args()

    out = args.out if os.path.isabs(args.out) else os.path.join(SCRIPT_DIR, args.out)
    records = scrape(out, args.source, max_pages=args.max_pages, delay=args.delay)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=4)
    print(f"\nDone. Saved {len(records)} records -> {out}")


if __name__ == "__main__":
    main()
