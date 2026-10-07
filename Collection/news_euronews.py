
import argparse
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TAG_URL = "https://www.euronews.com/tag/artificial-intelligence"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def make_driver(headed=False):
    opts = Options()
    if not headed:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--window-size=1366,900")
    opts.add_argument("--no-sandbox")
    opts.add_argument(f"--user-agent={UA}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
    )
    return driver


def page_has_cards(driver):
    return len(driver.find_elements(By.CSS_SELECTOR, "div.b-listing__main article")) > 0


def main():
    ap = argparse.ArgumentParser(description="Selenium downloader for Euronews AI tag.")
    ap.add_argument("--start", type=int, default=1, help="first page (default 1)")
    ap.add_argument("--end", type=int, default=None, help="last page (default: until list ends)")
    ap.add_argument("--delay", type=float, default=4.0, help="seconds between pages")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--html-dir", default="raw_html", help="output folder for page source")
    args = ap.parse_args()

    html_dir = args.html_dir if os.path.isabs(args.html_dir) else os.path.join(SCRIPT_DIR, args.html_dir)
    os.makedirs(html_dir, exist_ok=True)

    print("launching Chrome ...")
    driver = make_driver(headed=args.headed)
    saved = skipped = 0
    try:
        page = args.start
        while args.end is None or page <= args.end:
            dest = os.path.join(html_dir, f"p{page}.html")
            if os.path.exists(dest):
                print(f"[p{page}] already saved, skip")
                skipped += 1
                page += 1
                continue

            print(f"[p{page}] loading {TAG_URL}?p={page}")
            driver.get(f"{TAG_URL}?p={page}")
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.b-listing__main")))
            except Exception:
                pass
            time.sleep(1.5)

            if not page_has_cards(driver):
                print(f"  [end] page {page} has no article cards — end of listing")
                break

            with open(dest, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            saved += 1
            print(f"  [saved] {dest}")
            page += 1
            time.sleep(args.delay)
    finally:
        driver.quit()

    print(f"\nDone. saved {saved} new page(s), skipped {skipped} existing -> {html_dir}")
    print("Next: python preprocess_euronews_html.py")


if __name__ == "__main__":
    main()
