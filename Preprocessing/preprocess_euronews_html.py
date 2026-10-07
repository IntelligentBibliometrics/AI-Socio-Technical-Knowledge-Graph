
import argparse
import glob
import json
import os
import re
from datetime import date

from bs4 import BeautifulSoup

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE = "https://www.euronews.com"
SOURCE_DEFAULT = "euronews"
SCRAPE_DATE = date.today().isoformat()

DATE_IN_URL = re.compile(r"/(20\d\d)/(\d\d)/(\d\d)/")
PAGENO_IN_NAME = re.compile(r"(\d+)")


def parse_date(article, href):
    el = article.select_one(".the-media-object__date time[datetime]")
    if el and el.get("datetime"):
        return el["datetime"][:10]
    m = DATE_IN_URL.search(href)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def parse_html(html):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("div.b-listing__main")
    if not main:
        return []
    rows = []
    for art in main.find_all("article"):
        link = art.select_one("a.the-media-object__link[href]")
        if not link:
            continue
        href = link["href"]
        url = href if href.startswith("http") else BASE + href
        url = url.replace("http://", "https://")
        title_el = art.select_one(".the-media-object__title")
        title = (title_el.get_text(strip=True) if title_el
                 else link.get("aria-label", "").strip())
        if not title:
            continue
        desc_el = art.select_one(".the-media-object__description")
        abstract = desc_el.get_text(strip=True) if desc_el else ""
        rows.append((title, url, abstract, parse_date(art, href)))
    return rows


def page_number(path):
    name = os.path.splitext(os.path.basename(path))[0]
    m = PAGENO_IN_NAME.search(name)
    return int(m.group(1)) if m else 10**9


def main():
    ap = argparse.ArgumentParser(description="Preprocess locally saved Euronews AI pages.")
    ap.add_argument("--html-dir", default="raw_html",
                    help="folder with saved page source (default: raw_html, next to this script)")
    ap.add_argument("--source", default=SOURCE_DEFAULT, help='SOURCE value (default: "euronews")')
    ap.add_argument("--out", default="NEWS_EURONEWS_AI.json",
                    help="output JSON path (relative paths resolve next to this script)")
    args = ap.parse_args()

    html_dir = args.html_dir if os.path.isabs(args.html_dir) else os.path.join(SCRIPT_DIR, args.html_dir)
    out = args.out if os.path.isabs(args.out) else os.path.join(SCRIPT_DIR, args.out)

    files = sorted(glob.glob(os.path.join(html_dir, "*.html")), key=page_number)
    if not files:
        print(f"[!] no .html files in {html_dir}")
        print("    Save each listing page's source as raw_html/p1.html, p2.html, ... first.")
        return

    seen = set()
    records = []
    for path in files:
        pg = page_number(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            rows = parse_html(f.read())
        new = 0
        for position, (title, url, abstract, pub) in enumerate(rows, start=1):
            if url in seen:
                continue
            seen.add(url)
            new += 1
            records.append({
                "ABSTRACT": abstract, "PAGE": pg, "POSITION": position,
                "PUBLISH_DATE": pub, "SCRAPE_DATE": SCRAPE_DATE,
                "TITLE": title, "URL": url,
            })
        print(f"  {os.path.basename(path)} (page {pg}): {len(rows)} cards, {new} new "
              f"(cumulative {len(records)})")

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
            "SOURCE": args.source,
            "TITLE": rec["TITLE"],
            "URL": rec["URL"],
        })
    with open(out, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=4)
    print(f"\nDone. {len(files)} page(s) -> {len(final)} unique records -> {out}")


if __name__ == "__main__":
    main()
