import argparse
import json
import logging
import re
import time
import urllib.parse
from pathlib import Path

AI_KEYWORDS = {
    "Core AI terms": ["artificial intelligence", "artificial-intelligence", "AI"],
    "Learning paradigms": ["machine learning", "deep learning", "reinforcement learning",
                           "supervised learning", "unsupervised learning",
                           "self-supervised learning", "transfer learning"],
    "Model architectures": ["neural network", "artificial neural network", "attention mechanism",
                            "self-attention", "convolutional neural network",
                            "recurrent neural network", "generative adversarial network",
                            "diffusion model", "graph neural network", "autoencoder"],
    "Generative AI and large language models": [
        "large language model", "LLM", "generative AI", "generative artificial intelligence",
        "vision-language model", "artificial general intelligence", "prompt engineering",
        "retrieval-augmented generation", "conversational AI", "chatbot", "AI agent",
        "agentic AI"],
    "Landmark AI systems": ["GPT", "ChatGPT", "DALL-E", "Stable Diffusion", "Midjourney",
                            "AlphaFold", "AlphaGo", "AlphaZero"],
    "AI organizations": ["OpenAI", "Google DeepMind", "Anthropic", "Meta AI", "Hugging Face",
                         "Mistral AI", "Stability AI", "xAI", "NVIDIA"],
}

SEARCH_QUERIES = [word for group in AI_KEYWORDS.values() for word in group]

SITE_ROOT = "https://apo.org.au"
GEO_FACET = "apo-facets%5B0%5D=geographic_coverage%3A1"
SEARCH_URL = SITE_ROOT + "/search-apo/{query}?" + GEO_FACET + "&page={page}"

NODE_ID_PATTERN = re.compile(r"/node/(\d+)")
DCTERMS_PATTERN = re.compile(r'<meta[^>]+name="(dcterms\.[^"]+)"[^>]+content="([^"]*)"')
WHITESPACE_PATTERN = re.compile(r"\s+")

NODE_LINK_SELECTOR = "a[href*='/node/']"
RESULT_SELECTOR = "h1 a[href*='/node/'], h2 a[href*='/node/'], h3 a[href*='/node/']"
LABEL_SELECTOR = ".label-box"
ABSTRACT_SELECTOR = ".resource__body"
ORG_SELECTORS = [".party a", ".publisher a"]
TIME_TAG = "time"
TIME_ATTR = "datetime"
PARENT_XPATH = ".."
CONTAINER_LEVELS = 4
READ_MORE_TEXT = "Read more"

CHROME_ARGS = ["--disable-blink-features=AutomationControlled", "--window-size=1280,1000"]
CHROME_EXCLUDE_SWITCHES = ["enable-automation"]
WEBDRIVER_MASK_JS = "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
PAGE_LOAD_TIMEOUT = 60
CHALLENGE_MAX_WAIT = 50
CHALLENGE_POLL = 2
CHALLENGE_MARKER = "moment"
SITE_TITLE_MARKER = "apo"

DEFAULT_OUTDIR = Path(__file__).resolve().parent / "data"
DEFAULT_MAX_PAGES = 80
DEFAULT_DELAY = 2.5
DEFAULT_LIMIT = 0
OUTPUT_FILE = "apo_policy.jsonl"
SAVE_LOG_EVERY = 50

JURISDICTION = "AU"
SOURCE = "APO"
URL_KEY = "URL"
TEXT_ENCODING = "utf-8"
APPEND_MODE = "a"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATEFMT = "%H:%M:%S"

logger = logging.getLogger("au")


def node_id(url):
    match = NODE_ID_PATTERN.search(url or "")
    return match.group(1) if match else None


def search_url(query, page):
    return SEARCH_URL.format(query=urllib.parse.quote(query), page=page)


def make_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    for argument in CHROME_ARGS:
        options.add_argument(argument)
    options.add_experimental_option("excludeSwitches", CHROME_EXCLUDE_SWITCHES)

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument", {"source": WEBDRIVER_MASK_JS}
    )
    return driver


def get_page(driver, url):
    from selenium.webdriver.common.by import By

    try:
        driver.get(url)
    except Exception:
        pass

    deadline = time.time() + CHALLENGE_MAX_WAIT
    while time.time() < deadline:
        title = (driver.title or "").lower()
        if CHALLENGE_MARKER not in title:
            if driver.find_elements(By.CSS_SELECTOR, NODE_LINK_SELECTOR) or SITE_TITLE_MARKER in title:
                return True
        time.sleep(CHALLENGE_POLL)
    return False


def extract_search(driver):
    from selenium.webdriver.common.by import By

    rows = []
    anchors = [a for a in driver.find_elements(By.CSS_SELECTOR, RESULT_SELECTOR) if a.text.strip()]

    for anchor in anchors:
        try:
            container = anchor
            for _ in range(CONTAINER_LEVELS):
                container = container.find_element(By.XPATH, PARENT_XPATH)
                if container.find_elements(By.TAG_NAME, TIME_TAG):
                    break

            def field(css, attr=None):
                elements = container.find_elements(By.CSS_SELECTOR, css)
                if not elements:
                    return None
                return elements[0].get_attribute(attr) if attr else elements[0].text.strip()

            abstract = field(ABSTRACT_SELECTOR)
            if abstract:
                abstract = WHITESPACE_PATTERN.sub(" ", abstract.replace(READ_MORE_TEXT, "")).strip()

            organisation = None
            for css in ORG_SELECTORS:
                organisation = field(css)
                if organisation:
                    break

            rows.append(
                {
                    "url": anchor.get_attribute("href"),
                    "title": anchor.text.strip(),
                    "display_type": field(LABEL_SELECTOR),
                    "description": abstract,
                    "public_timestamp": field(TIME_TAG, TIME_ATTR),
                    "org": organisation,
                }
            )
        except Exception:
            continue

    return rows


def fetch_dcterms(driver, url):
    if not get_page(driver, url):
        return {}
    meta = {}
    for name, content in DCTERMS_PATTERN.findall(driver.page_source):
        meta.setdefault(name, content.strip())
    return meta


def load_done(raw_file):
    done = set()
    if not raw_file.exists():
        return done
    with raw_file.open(encoding=TEXT_ENCODING) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)[URL_KEY])
            except (ValueError, KeyError):
                continue
    return done


def search_all(driver, queries, max_pages, delay, limit, done_count):
    seen = {}
    for query in queries:
        for page in range(max_pages):
            if not get_page(driver, search_url(query, page)):
                break

            rows = extract_search(driver)
            if not rows:
                break

            fresh = sum(1 for r in rows if r["url"] not in seen)
            for row in rows:
                seen.setdefault(row["url"], row)

            if fresh == 0:
                break
            time.sleep(delay)
            if limit and len(seen) >= limit + done_count:
                return seen
        logger.info("query '%s' done, %d unique so far", query, len(seen))
        if limit and len(seen) >= limit + done_count:
            break
    return seen


def build_record(row, meta):
    return {
        "POLICY_ID": node_id(row["url"]),
        "TITLE": meta.get("dcterms.title") or row["title"],
        URL_KEY: row["url"],
        "DESCRIPTION": row["description"] or meta.get("dcterms.description"),
        "DISPLAY_TYPE": row["display_type"],
        "DOCUMENT_TYPE": meta.get("dcterms.type"),
        "ORGANISATIONS": meta.get("dcterms.publisher") or row["org"],
        "PUBLIC_TIMESTAMP": meta.get("dcterms.date") or row["public_timestamp"],
        "LICENSE": meta.get("dcterms.license"),
        "JURISDICTION": JURISDICTION,
        "SOURCE": SOURCE,
    }


def crawl(args):
    args.outdir.mkdir(parents=True, exist_ok=True)
    raw_file = args.outdir / OUTPUT_FILE
    done = load_done(raw_file)

    driver = make_driver()
    try:
        logger.info("waiting for Cloudflare (first run ~30-60s; keep the browser window visible)")
        if not get_page(driver, search_url(args.query[0], 0)):
            return

        seen = search_all(driver, args.query, args.max_pages, args.delay, args.limit, len(done))

        todo = [row for url, row in seen.items() if url not in done]
        if args.limit:
            todo = todo[: args.limit]

        saved = 0
        with raw_file.open(APPEND_MODE, encoding=TEXT_ENCODING) as out:
            for row in todo:
                record = build_record(row, fetch_dcterms(driver, row["url"]))
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                saved += 1
                if saved % SAVE_LOG_EVERY == 0:
                    logger.info("saved %d/%d", saved, len(todo))
                time.sleep(args.delay)

        logger.info("added %d, total %d -> %s", saved, len(done) + saved, raw_file)
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--crawl", action="store_true")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--query", nargs="+", default=SEARCH_QUERIES)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATEFMT)

    if args.crawl:
        crawl(args)


if __name__ == "__main__":
    main()
