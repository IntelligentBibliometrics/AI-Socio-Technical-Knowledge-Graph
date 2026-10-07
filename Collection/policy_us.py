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

API_ROOT = "https://www.federalregister.gov/api/v1"
DOCUMENTS_ENDPOINT = f"{API_ROOT}/documents.json"
TERM_PARAM = "conditions[term]"
SORT_ORDER = "newest"
MAX_PER_PAGE = 1000
REQUEST_TIMEOUT = 60

DEFAULT_OUTDIR = Path(__file__).resolve().parent / "data"
DEFAULT_MAX_PAGES = 0
DEFAULT_DELAY = 0.5

EXCLUDED_TYPE = "Uncategorized Document"
FULL_FILE = "federal_register_ai_full.json"
CORE_BASENAME = "federal_register_ai_core"

JSON_INDENT = 2
CSV_ENCODING = "utf-8-sig"
TEXT_ENCODING = "utf-8"
EXCEL_ENGINE = "openpyxl"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATEFMT = "%H:%M:%S"

logger = logging.getLogger("us")


def matches_ai(*texts):
    return any(KEYWORD_PATTERN.search(t) for t in texts if t)


def fetch_page(session, term, page, per_page):
    params = {
        TERM_PARAM: term,
        "per_page": per_page,
        "page": page,
        "order": SORT_ORDER,
    }
    try:
        response = session.get(DOCUMENTS_ENDPOINT, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None


def doc_key(doc):
    return doc.get("document_number") or doc.get("html_url")


def fetch_term(session, term, per_page, max_pages, delay, seen):
    first = fetch_page(session, term, 1, per_page)
    if not first:
        return

    total = first.get("count", 0)
    if total == 0:
        return

    pages = (total + per_page - 1) // per_page
    if max_pages:
        pages = min(pages, max_pages)

    for doc in first.get("results", []):
        seen.setdefault(doc_key(doc), doc)

    for page in range(2, pages + 1):
        response = fetch_page(session, term, page, per_page)
        if not response:
            break
        results = response.get("results", [])
        if not results:
            break
        for doc in results:
            seen.setdefault(doc_key(doc), doc)
        time.sleep(delay)


def fetch_all(terms, per_page, max_pages, delay):
    session = requests.Session()
    seen = {}
    for term in tqdm(terms, desc="keywords"):
        fetch_term(session, term, per_page, max_pages, delay, seen)
    return list(seen.values())


def to_core_fields(documents, core_filter):
    records = []
    for doc in documents:
        title = (doc.get("title") or "").strip()
        if not title:
            continue

        doc_type = doc.get("type") or ""
        if doc_type == EXCLUDED_TYPE:
            continue

        abstract = doc.get("abstract") or ""
        if core_filter and not matches_ai(title, abstract):
            continue

        agencies = [a.get("name", "") for a in doc.get("agencies") or []]
        organisations = ", ".join(filter(None, agencies)) or ", ".join(
            doc.get("agency_names") or []
        )

        records.append(
            {
                "title": title,
                "url": doc.get("html_url", ""),
                "description": abstract,
                "public_timestamp": doc.get("publication_date", ""),
                "document_type": doc_type,
                "display_type": doc_type.replace("_", " ").title(),
                "organisations": organisations,
            }
        )
    return records


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=JSON_INDENT), encoding=TEXT_ENCODING)


def save(documents, records, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    write_json(outdir / FULL_FILE, documents)
    write_json(outdir / f"{CORE_BASENAME}.json", records)

    df = pd.DataFrame(records)
    df.to_csv(outdir / f"{CORE_BASENAME}.csv", index=False, encoding=CSV_ENCODING)
    df.to_excel(outdir / f"{CORE_BASENAME}.xlsx", index=False, engine=EXCEL_ENGINE)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--term", nargs="+", default=SEARCH_QUERIES)
    parser.add_argument("--per-page", type=int, default=MAX_PER_PAGE)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--no-core-filter", action="store_true")
    args = parser.parse_args()
    args.per_page = min(args.per_page, MAX_PER_PAGE)
    return args


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATEFMT)

    documents = fetch_all(args.term, args.per_page, args.max_pages, args.delay)
    records = to_core_fields(documents, core_filter=not args.no_core_filter)

    save(documents, records, args.outdir)
    logger.info("fetched %d, kept %d -> %s", len(documents), len(records), args.outdir)


if __name__ == "__main__":
    main()
