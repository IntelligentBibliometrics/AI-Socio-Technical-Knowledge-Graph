import argparse
import json
import os
import re

import pandas as pd
from tqdm import tqdm


def normalize_doi(doi_str):
    if pd.isna(doi_str):
        return None
    doi_str = str(doi_str).strip().lower()
    doi_str = re.sub(r'^(doi:?|https?://doi\.org/|https?://dx\.doi\.org/)', '', doi_str)
    doi_str = re.sub(r'\s+', '', doi_str)
    return doi_str if doi_str else None


def load_doi_list(file_path):
    print(f"loading DOI list: {file_path}")
    try:
        df = pd.read_csv(file_path, encoding='utf-8')
        print(f"read {len(df)} rows")
        df['normalized_doi'] = df['doi'].apply(normalize_doi)
        doi_set = set(df['normalized_doi'].dropna())
        print(f"extracted {len(doi_set)} unique DOIs")
        return doi_set, df
    except Exception as e:
        print(f"read failed: {e}")
        return set(), pd.DataFrame()


def analyze_structure(file_path, sample_size=1000):
    print(f"analyzing structure: {os.path.basename(file_path)}")
    try:
        sample_df = pd.read_csv(file_path, sep='\t', nrows=sample_size, encoding='utf-8')
        print(f"sample: {len(sample_df)} rows x {len(sample_df.columns)} cols")
        print(f"columns: {list(sample_df.columns)}")
        if 'ObjectID' in sample_df.columns:
            object_ids = sample_df['ObjectID'].dropna()
            print(f"ObjectID column present, {len(object_ids)} non-null in sample")
        else:
            print("ObjectID column not found")
        return sample_df.columns.tolist()
    except Exception as e:
        print(f"analysis failed: {e}")
        return []


def find_matching_records(doi_set, scinetnews_file, chunk_size=10000):
    print(f"matching, target DOIs: {len(doi_set)}")
    matched_records = []
    total_rows = 0
    try:
        chunk_iterator = pd.read_csv(scinetnews_file, sep='\t', chunksize=chunk_size,
                                     encoding='utf-8', low_memory=False)
        for chunk in tqdm(chunk_iterator, desc="chunks"):
            if 'ObjectID' not in chunk.columns:
                print("ObjectID column missing in chunk")
                continue
            chunk['normalized_objectid'] = chunk['ObjectID'].apply(normalize_doi)
            matched_chunk = chunk[chunk['normalized_objectid'].isin(doi_set)].copy()
            if not matched_chunk.empty:
                matched_chunk = matched_chunk.drop('normalized_objectid', axis=1)
                matched_records.append(matched_chunk)
                print(f"  {len(matched_chunk)} matches")
            total_rows += len(chunk)
        if matched_records:
            final_matches = pd.concat(matched_records, ignore_index=True)
            print(f"done - scanned {total_rows:,} rows, matched {len(final_matches)}")
            return final_matches
        print(f"no matches - scanned {total_rows:,} rows")
        return pd.DataFrame()
    except Exception as e:
        print(f"matching error: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def empty_result(doi_set, matched):
    return {
        "metadata": {
            "analysis": "DOI vs SciNetNews ObjectID match",
            "doi_total": len(doi_set),
            "matched_count": matched,
            "match_rate": round(matched / len(doi_set) * 100, 4) if doi_set else 0,
            "sources": {"doi_list": "doi_list.csv", "news_data": "SciSciNet_Newsfeed_Metadata.tsv"},
        },
        "match_statistics": {},
        "matched_records": [],
    }


def create_structured_json(matched_df, doi_set):
    data = empty_result(doi_set, len(matched_df))
    matched_clean = matched_df.where(pd.notnull(matched_df), None)
    if not matched_df.empty:
        stats = {"unique_objectids": matched_df['ObjectID'].nunique() if 'ObjectID' in matched_df.columns else 0}
        for col in ['PublicationDate', 'Source', 'Category', 'Author', 'Language']:
            if col in matched_df.columns:
                vc = matched_df[col].value_counts().head(10)
                if not vc.empty:
                    stats[f"{col}_top10"] = vc.to_dict()
        data["match_statistics"] = stats
    for _, row in matched_clean.iterrows():
        data["matched_records"].append({col: value for col, value in row.items()})
    return data


def main():
    ap = argparse.ArgumentParser(description="Match DOIs against SciNetNews ObjectIDs.")
    ap.add_argument("--doi", default="doi_list.csv", help="DOI list CSV (column 'doi')")
    ap.add_argument("--scinetnews", default="SciSciNet_Newsfeed_Metadata.tsv", help="SciNetNews metadata TSV")
    ap.add_argument("--outdir", default=".", help="output directory")
    args = ap.parse_args()

    if not os.path.exists(args.doi):
        print(f"DOI file not found: {args.doi}")
        return
    if not os.path.exists(args.scinetnews):
        print(f"SciNetNews file not found: {args.scinetnews}")
        return
    os.makedirs(args.outdir, exist_ok=True)

    doi_set, _ = load_doi_list(args.doi)
    if not doi_set:
        print("empty DOI list, aborting")
        return
    if not analyze_structure(args.scinetnews):
        print("cannot analyze structure, aborting")
        return
    matched_df = find_matching_records(doi_set, args.scinetnews)

    if matched_df.empty:
        structured_data = empty_result(doi_set, 0)
    else:
        structured_data = create_structured_json(matched_df, doi_set)
        csv_out = os.path.join(args.outdir, "doi_scinetnews_matched_records.csv")
        matched_df.to_csv(csv_out, index=False, encoding='utf-8')
        print(f"matched CSV saved: {csv_out}")

    json_out = os.path.join(args.outdir, "doi_scinetnews_match_analysis.json")
    with open(json_out, 'w', encoding='utf-8') as f:
        json.dump(structured_data, f, ensure_ascii=False, indent=2)

    print(f"summary: DOI total {len(doi_set):,}, matched {len(matched_df):,}, "
          f"rate {structured_data['metadata']['match_rate']:.4f}% -> {json_out}")


if __name__ == "__main__":
    main()
