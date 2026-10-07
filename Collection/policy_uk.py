import argparse
import json
import logging
import re
import time
from pathlib import Path

import pandas as pd
import requests
from tqdm import tqdm

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

KEYWORD_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted(set(SEARCH_QUERIES), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

SITE_ROOT = "https://www.gov.uk"
SEARCH_API = f"{SITE_ROOT}/api/search.json"
PAGE_SIZE = 100
SORT_ORDER = "-public_timestamp"
DOC_TYPE_PARAM = "filter_content_store_document_type"
REQUEST_TIMEOUT = 30

DEFAULT_OUTDIR = Path(__file__).resolve().parent / "data"
DEFAULT_DOC_TYPES = ["policy_paper", "white_paper", "guidance"]
DEFAULT_MAX_PAGES = 30
DEFAULT_DELAY = 0.5

BACKUP_FILE = "govuk_ai_full_backup.json"
CORE_BASENAME = "govuk_core_ai_policies"
SUMMARY_BASENAME = "govuk_ai_policy_summary"

JSON_INDENT = 2
CSV_ENCODING = "utf-8-sig"
TEXT_ENCODING = "utf-8"
EXCEL_ENGINE = "openpyxl"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATEFMT = "%H:%M:%S"

logger = logging.getLogger("uk")


def matches_ai(*texts):
    return any(KEYWORD_PATTERN.search(t) for t in texts if t)


def fetch_page(session, query, start, doc_types):
    params = [
        ("q", query),
        ("count", PAGE_SIZE),
        ("start", start),
        ("order", SORT_ORDER),
    ]
    params.extend((DOC_TYPE_PARAM, t) for t in doc_types)

    try:
        response = session.get(SEARCH_API, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None


def fetch_query(session, query, doc_types, max_pages, delay, seen):
    first = fetch_page(session, query, 0, doc_types)
    if not first:
        return

    total = first.get("total", 0)
    if total == 0:
        return

    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    if max_pages:
        pages = min(pages, max_pages)

    for doc in first.get("results", []):
        seen.setdefault(doc.get("link"), doc)

    for page in range(1, pages):
        response = fetch_page(session, query, page * PAGE_SIZE, doc_types)
        if not response:
            break
        results = response.get("results", [])
        if not results:
            break
        for doc in results:
            seen.setdefault(doc.get("link"), doc)
        time.sleep(delay)


def fetch_all(queries, doc_types, max_pages, delay):
    session = requests.Session()
    seen = {}
    for query in tqdm(queries, desc="keywords"):
        fetch_query(session, query, doc_types, max_pages, delay, seen)
    return list(seen.values())


def to_core_fields(documents):
    records = []
    for doc in documents:
        organisations = []
        for org in doc.get("organisations") or []:
            organisations.append(org.get("title", "") if isinstance(org, dict) else str(org))

        link = doc.get("link") or ""
        records.append(
            {
                "title": doc.get("title"),
                "url": f"{SITE_ROOT}{link}" if link else "",
                "description": doc.get("description"),
                "public_timestamp": doc.get("public_timestamp"),
                "document_type": doc.get("format"),
                "display_type": doc.get("display_type"),
                "organisations": ", ".join(organisations),
            }
        )
    return records


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=JSON_INDENT), encoding=TEXT_ENCODING)


def save(documents, records, outdir, basename):
    outdir.mkdir(parents=True, exist_ok=True)
    write_json(outdir / BACKUP_FILE, documents)
    write_json(outdir / f"{basename}.json", records)

    df = pd.DataFrame(records)
    df.to_csv(outdir / f"{basename}.csv", index=False, encoding=CSV_ENCODING)
    df.to_excel(outdir / f"{basename}.xlsx", index=False, engine=EXCEL_ENGINE)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--query", nargs="+", default=SEARCH_QUERIES)
    parser.add_argument("--doc-types", nargs="+", default=DEFAULT_DOC_TYPES)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--no-core-filter", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATEFMT)

    documents = fetch_all(args.query, args.doc_types, args.max_pages, args.delay)
    records = to_core_fields(documents)

    if args.no_core_filter:
        basename = SUMMARY_BASENAME
    else:
        records = [r for r in records if matches_ai(r["title"], r["description"])]
        basename = CORE_BASENAME

    save(documents, records, args.outdir, basename)
    logger.info("fetched %d, kept %d -> %s", len(documents), len(records), args.outdir)


if __name__ == "__main__":
    main()
