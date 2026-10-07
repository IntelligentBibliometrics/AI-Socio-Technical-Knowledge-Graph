
import argparse
import os

import pandas as pd

DEFAULT_JCR_FILE = "JCR.xlsx"
AI_CATEGORY_KEYWORD = "COMPUTER SCIENCE, ARTIFICIAL INTELLIGENCE"

_INVALID_ISSN = {'', 'N/A', 'NA', 'NULL', 'NONE', '-'}


def find_category_column(df):
    for col in df.columns:
        if 'category' in col.lower() or 'categories' in col.lower():
            return col
    return None


def find_issn_columns(df):
    return [col for col in df.columns if 'issn' in col.lower()]


def normalize_issn(value):
    if value is None:
        return None
    text = str(value).strip()
    if text.upper() in _INVALID_ISSN or text.lower() == 'nan':
        return None
    return text


def load_ai_journal_issns(jcr_file_path=DEFAULT_JCR_FILE, keyword=AI_CATEGORY_KEYWORD, verbose=True):
    if not os.path.exists(jcr_file_path):
        print(f"error: JCR file not found: {jcr_file_path}")
        return set()

    try:
        jcr_df = pd.read_excel(jcr_file_path)
    except Exception as e:
        print(f"error reading JCR file: {e}")
        return set()

    category_column = find_category_column(jcr_df)
    if category_column is None:
        print("no category column found; check column names")
        print(f"available columns: {list(jcr_df.columns)}")
        return set()

    ai_journals = jcr_df[
        jcr_df[category_column].astype(str).str.contains(keyword, case=False, na=False)
    ]

    issn_columns = find_issn_columns(jcr_df)
    if not issn_columns:
        print("no ISSN column found; check column names")
        return set()

    issn_set = set()
    for col in issn_columns:
        for raw in ai_journals[col].dropna():
            issn = normalize_issn(raw)
            if issn:
                issn_set.add(issn)

    if verbose:
        print(f"JCR file: {jcr_file_path}")
        print(f"category column: {category_column}, ISSN columns: {issn_columns}")
        print(f"loaded {len(ai_journals)} AI journals, {len(issn_set)} ISSN/eISSN")

    return issn_set


def main():
    parser = argparse.ArgumentParser(description='load AI-journal ISSNs from JCR')
    parser.add_argument('--jcr-file', default=DEFAULT_JCR_FILE, help='path to JCR.xlsx')
    parser.add_argument('--keyword', default=AI_CATEGORY_KEYWORD, help='category keyword')
    parser.add_argument('--dump', help='write the ISSN set to this file (one per line)')
    args = parser.parse_args()

    issn_set = load_ai_journal_issns(args.jcr_file, args.keyword)
    if not issn_set:
        print("no ISSNs found; check the file and column names")
        return

    if args.dump:
        with open(args.dump, 'w', encoding='utf-8') as f:
            for issn in sorted(issn_set):
                f.write(issn + '\n')
        print(f"wrote {len(issn_set)} ISSNs to: {args.dump}")
    else:
        for issn in sorted(issn_set)[:20]:
            print(f"  {issn}")
        if len(issn_set) > 20:
            print(f"  ... {len(issn_set)} total")


if __name__ == '__main__':
    main()
