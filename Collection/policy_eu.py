import argparse
import csv
import json
import logging
import re
from pathlib import Path

import pandas as pd

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

QUERY_JOINER = " OR "
QUERY_QUOTE = '"'

CORE_FIELDS = [
    "Collection of the document",
    "Date of document",
    "Author",
    "Form",
    "Title",
    "Document sector",
    "Document year",
]
IMPORTANT_FIELDS = [
    "CELEX number",
    "Document type",
    "Subtitle",
    "Legal basis",
    "Treaty",
    "Publication Reference",
    "Date of publication",
]
OPTIONAL_FIELDS = [
    "Related document(s)",
    "ELI",
    "Date of effect",
]
RETAINED_FIELDS = CORE_FIELDS + IMPORTANT_FIELDS + OPTIONAL_FIELDS
REQUIRED_FIELDS = ["CELEX number", "ELI"]

FIELD_CATEGORY = {
    **{f: "核心字段" for f in CORE_FIELDS},
    **{f: "重要字段" for f in IMPORTANT_FIELDS},
    **{f: "可选字段" for f in OPTIONAL_FIELDS},
}

FIELD_TITLE = "Title"
FIELD_SUBTITLE = "Subtitle"
FIELD_CELEX = "CELEX number"
FIELD_ELI = "ELI"
FIELD_DOC_TYPE = "Document type"
FIELD_FORM = "Form"
FIELD_AUTHOR = "Author"
FIELD_DATE_PUBLICATION = "Date of publication"
FIELD_DATE_DOCUMENT = "Date of document"

CELEX_URL = "https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX:{celex}"

DEFAULT_OUTDIR = Path(__file__).resolve().parent / "data"
FILTERED_BASENAME = "euro_policy_filtered"
CORE_BASENAME = "euro_policy_core"

SHEET_DATA = "筛选数据"
SHEET_FIELDS = "字段说明"
SHEET_FIELD_WIDTHS = {"A": 8, "B": 45, "C": 12, "D": 12, "E": 12, "F": 12}

READ_ENCODING = "utf-8"
READ_QUOTING = csv.QUOTE_ALL
BAD_LINES_ACTION = "skip"
JSON_INDENT = 2
CSV_ENCODING = "utf-8-sig"
TEXT_ENCODING = "utf-8"
EXCEL_ENGINE = "openpyxl"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATEFMT = "%H:%M:%S"

logger = logging.getLogger("euro")


def matches_ai(*texts):
    return any(KEYWORD_PATTERN.search(t) for t in texts if t)


def select_fields(df):
    return [f for f in RETAINED_FIELDS if f in df.columns]


def apply_required(df):
    mask = pd.Series(True, index=df.index)
    for field in REQUIRED_FIELDS:
        if field in df.columns:
            mask &= df[field].notna() & (df[field].astype(str).str.strip() != "")
    return df[mask].copy()


def apply_ai_filter(df):
    empty = pd.Series("", index=df.index)
    title = df[FIELD_TITLE] if FIELD_TITLE in df.columns else empty
    subtitle = df[FIELD_SUBTITLE] if FIELD_SUBTITLE in df.columns else empty
    mask = [
        matches_ai(str(t) if pd.notna(t) else "", str(s) if pd.notna(s) else "")
        for t, s in zip(title, subtitle)
    ]
    return df[mask].copy()


def build_field_summary(df, fields):
    rows = []
    for i, field in enumerate(fields, 1):
        valid = int(df[field].notna().sum())
        rows.append(
            {
                "序号": i,
                "字段名称": field,
                "字段分类": FIELD_CATEGORY.get(field, ""),
                "有效数量": valid,
                "有效率(%)": round(valid / len(df) * 100, 2) if len(df) else 0.0,
                "唯一值数": int(df[field].nunique(dropna=True)),
            }
        )
    return pd.DataFrame(rows)


def to_core_fields(df):
    records = []
    for row in df.where(df.notna(), "").to_dict(orient="records"):
        title = str(row.get(FIELD_TITLE) or "").strip()
        if not title:
            continue

        eli = str(row.get(FIELD_ELI) or "").strip()
        celex = str(row.get(FIELD_CELEX) or "").strip()
        if eli:
            url = eli
        elif celex:
            url = CELEX_URL.format(celex=celex)
        else:
            url = ""

        records.append(
            {
                "title": title,
                "url": url,
                "description": "",
                "public_timestamp": row.get(FIELD_DATE_PUBLICATION) or row.get(FIELD_DATE_DOCUMENT) or "",
                "document_type": row.get(FIELD_DOC_TYPE) or "",
                "display_type": row.get(FIELD_FORM) or "",
                "organisations": row.get(FIELD_AUTHOR) or "",
            }
        )
    return records


def save(df, fields, records, outdir):
    outdir.mkdir(parents=True, exist_ok=True)

    df.to_csv(outdir / f"{FILTERED_BASENAME}.csv", index=False, encoding=CSV_ENCODING)
    with pd.ExcelWriter(outdir / f"{FILTERED_BASENAME}.xlsx", engine=EXCEL_ENGINE) as writer:
        df.to_excel(writer, sheet_name=SHEET_DATA, index=False)
        build_field_summary(df, fields).to_excel(writer, sheet_name=SHEET_FIELDS, index=False)
        sheet = writer.sheets[SHEET_FIELDS]
        for column, width in SHEET_FIELD_WIDTHS.items():
            sheet.column_dimensions[column].width = width

    (outdir / f"{CORE_BASENAME}.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=JSON_INDENT), encoding=TEXT_ENCODING
    )
    core_df = pd.DataFrame(records)
    core_df.to_csv(outdir / f"{CORE_BASENAME}.csv", index=False, encoding=CSV_ENCODING)
    core_df.to_excel(outdir / f"{CORE_BASENAME}.xlsx", index=False, engine=EXCEL_ENGINE)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--ai-filter", action="store_true")
    parser.add_argument("--print-queries", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATEFMT)

    if args.print_queries:
        print(QUERY_JOINER.join(f"{QUERY_QUOTE}{w}{QUERY_QUOTE}" for w in SEARCH_QUERIES))
        return

    df_raw = pd.read_csv(
        args.input, on_bad_lines=BAD_LINES_ACTION, encoding=READ_ENCODING, quoting=READ_QUOTING
    )

    fields = select_fields(df_raw)
    df = apply_required(df_raw[fields].copy())
    if args.ai_filter:
        df = apply_ai_filter(df)

    records = to_core_fields(df)
    save(df, fields, records, args.outdir)
    logger.info("raw %d, kept %d -> %s", len(df_raw), len(records), args.outdir)


if __name__ == "__main__":
    main()
