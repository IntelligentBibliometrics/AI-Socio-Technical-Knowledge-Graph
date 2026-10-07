
import argparse
import json
import os
import time
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

BASE = "https://theconversation.com"
TOPIC_URL = "https://theconversation.com/topics/artificial-intelligence-ai-90"
SOURCE = "the_conversation_au"
SCRAPE_DATE = date.today().isoformat()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
}


def fetch(url, retries=3, backoff=3.0):
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                resp.encoding = resp.apparent_encoding or "utf-8"
                return resp.text
            print(f"  [warn] {url} -> HTTP {resp.status_code} (try {attempt}/{retries})")
        except requests.RequestException as exc:
            print(f"  [warn] {url} -> {exc} (try {attempt}/{retries})")
        if attempt < retries:
            time.sleep(backoff * attempt)
    return None


def text_of(node):
    return node.get_text(strip=True) if node is not None else ""


def parse_publish_date(article):
    t = article.find("time")
    if t is None:
        return ""
    dt = t.get("datetime", "")
    if dt:
        return dt[:10]
    return text_of(t)


def parse_article(article):
    link = article.select_one("header h2 a") or article.select_one("a.article-link")
    if link is None:
        return None
    title = text_of(link) or link.get("aria-label", "").strip()
    href = link.get("href", "")
    if not title or not href:
        return None
    url = urljoin(BASE, href)

    abstract = text_of(article.select_one("div.content span") or article.select_one("div.content"))

    return {
        "ABSTRACT": abstract,
        "PUBLISH_DATE": parse_publish_date(article),
        "TITLE": title,
        "URL": url,
        "_data_id": article.get("data-id", ""),
    }


def to_news_records(records):
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
            "SOURCE": rec["SOURCE"],
            "TITLE": rec["TITLE"],
            "URL": rec["URL"],
        })
    return final


def dump(records, out):
    with open(out, "w", encoding="utf-8") as f:
        json.dump(to_news_records(records), f, ensure_ascii=False, indent=4)


def scrape(out, max_pages=None, delay=1.5):
    records = []
    seen = set()
    page = 1
    while True:
        if max_pages is not None and page > max_pages:
            break
        url = TOPIC_URL if page == 1 else f"{TOPIC_URL}?page={page}"
        print(f"[page {page}] {url}")
        html = fetch(url)
        if html is None:
            print(f"  [stop] could not fetch page {page}")
            break

        soup = BeautifulSoup(html, "html.parser")
        articles = soup.find_all("article")
        if not articles:
            print(f"  [stop] no <article> on page {page} (end of listing)")
            break

        new_on_page = 0
        for position, art in enumerate(articles, start=1):
            rec = parse_article(art)
            if rec is None:
                continue
            key = rec["URL"]
            if key in seen:
                continue
            seen.add(key)
            new_on_page += 1
            records.append({
                "ABSTRACT": rec["ABSTRACT"],
                "PAGE": page,
                "POSITION": position,
                "PUBLISH_DATE": rec["PUBLISH_DATE"],
                "SCRAPE_DATE": SCRAPE_DATE,
                "SOURCE": SOURCE,
                "TITLE": rec["TITLE"],
                "URL": rec["URL"],
            })
        print(f"  -> {len(articles)} articles, {new_on_page} new")

        if new_on_page == 0:
            print(f"  [stop] no new articles on page {page} (all duplicates)")
            break

        dump(records, out)
        print(f"  [saved] {len(records)} records -> {out}")

        page += 1
        time.sleep(delay)

    return to_news_records(records)


def main():
    ap = argparse.ArgumentParser(description="Scrape The Conversation AI topic column.")
    ap.add_argument("--max-pages", type=int, default=None,
                    help="limit number of listing pages (default: until exhausted)")
    ap.add_argument("--delay", type=float, default=1.5,
                    help="seconds to wait between page requests")
    ap.add_argument("--out", default="NEWS_CONVERSATION_AI.json",
                    help="output JSON path (relative paths resolve next to this script)")
    args = ap.parse_args()

    out = args.out if os.path.isabs(args.out) else os.path.join(SCRIPT_DIR, args.out)
    records = scrape(out, max_pages=args.max_pages, delay=args.delay)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=4)
    print(f"\nDone. Saved {len(records)} records -> {out}")


if __name__ == "__main__":
    main()
