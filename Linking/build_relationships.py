
import os
import re
import sys
import json
import argparse
import collections

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def is_blank(v):
    return v is None or (isinstance(v, str) and v.strip() in ("", "None"))

def nz(v):
    return None if is_blank(v) else v

def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None

def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def dump(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"  wrote {os.path.basename(path):<28} {len(rows):>9} rows", flush=True)

def entity_ids(kg, name, key):
    return {str(r[key]) for r in load(os.path.join(kg, "entities", name))}


GRANT_SRC_CC = {"NSF": "US", "UKRI": "GB", "ARC": "AU", "CORDIS": "EU"}
POLICY_SRC_CC = {"GOV.UK": "GB", "Federal Register": "US", "EUR-Lex": "EU", "APO": "AU"}
NEWS_SRC_CC = {
    "bbc": "GB",
    "cnn": "US", "mit": "US", "sciencedaily": "US",
    "abc_au": "AU", "the_conversation_au": "AU",
    "euronews": "EU",
}
PATENT_SRC_CC = {"US (USPTO)": "US", "EP (EPO)": "EU", "GB (EPO)": "GB", "AU (IP Australia)": "AU"}


def norm_doi(v):
    if is_blank(v):
        return None
    s = str(v).strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "doi.org/"):
        s = s.replace(p, "")
    return s.lstrip("/") or None

def norm_patnum(v):
    if is_blank(v):
        return None
    return re.sub(r"[^A-Za-z0-9]", "", str(v)).upper() or None


def build_work_source(src, rel):
    # One WORK_SOURCE edge per work, pointing at its primary_location source
    # (the version of record). Non-primary locations are not linked, so
    # IS_PRIMARY is always 1; the column is kept for schema compatibility.
    pair = {}
    for r in load(os.path.join(src, "WORKS_AI_ONLY.json")):
        wid, sid = nz(r.get("WORK_ID")), nz(r.get("PRIMARY_LOCATION_SOURCE_ID"))
        if wid and sid:
            pair[(str(wid), str(sid))] = 1
    dump([{"WORK_ID": w, "SOURCE_ID": s, "IS_PRIMARY": p} for (w, s), p in pair.items()],
         os.path.join(rel, "WORK_SOURCE.json"))

def build_work_author_institution(src, rel):
    out = []
    for r in load(os.path.join(src, "WORKS_AUTHORS_INSTITUTIONS_AI.json")):
        wid, aid = nz(r.get("WORK_ID")), nz(r.get("AUTHOR_ID"))
        if not wid or not aid:
            continue
        out.append({"WORK_ID": str(wid), "AUTHOR_ID": str(aid),
                    "INSTITUTION_ID": nz(r.get("INSTITUTION_ID")),
                    "AUTHOR_POSITION": nz(r.get("AUTHOR_POSITION"))})
    dump(out, os.path.join(rel, "WORK_AUTHOR_INSTITUTION.json"))

def build_grant_institution(src, rel, grant_ids):
    out = []
    for r in load(os.path.join(src, "GRANT_CONNECTION.json")):
        gid = str(r["GRANT_ID"])
        if gid not in grant_ids:
            continue
        out.append({"GRANT_ID": gid, "INSTITUTION_ID": str(r["INSTITUTION_ID"]),
                    "MATCH_SCORE": to_float(r.get("MATCH_SCORE")),
                    "REGEX_MATCH": to_int(r.get("REGEX_MATCH"))})
    dump(out, os.path.join(rel, "GRANT_INSTITUTION.json"))

def build_patent_cites_patent(citations_path, kg, rel):
    pats = load(os.path.join(kg, "entities", "PATENT.json"))
    pat_ids = {str(r["PATENT_ID"]) for r in pats}
    num2id = {}
    for r in pats:
        pid = str(r["PATENT_ID"])
        for k in ("PUBLICATION_NUMBER", "APPLICATION_NUMBER"):
            n = norm_patnum(r.get(k))
            if n:
                num2id.setdefault(n, pid)
    edges = set()
    with open(citations_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            citing = str(rec.get("patent") or "")
            if citing not in pat_ids:
                continue
            for c in rec.get("citations", []) or []:
                cid = num2id.get(norm_patnum(c.get("cited")))
                if cid and cid != citing:
                    edges.add((citing, cid))
    dump([{"CITING_PATENT_ID": a, "CITED_PATENT_ID": b} for a, b in edges],
         os.path.join(rel, "PATENT_CITES_PATENT.json"))


def build_institution_country(src, rel, inst_ids):
    m = collections.defaultdict(collections.Counter)
    for r in load(os.path.join(src, "WORKS_AUTHORS_INSTITUTIONS_AI.json")):
        iid, cc = r.get("INSTITUTION_ID"), r.get("INSTITUTION_COUNTRY")
        if not is_blank(iid) and not is_blank(cc):
            m[str(iid)][cc] += 1
    out = [{"INSTITUTION_ID": iid, "COUNTRY_CODE": cnt.most_common(1)[0][0]}
           for iid, cnt in m.items() if iid in inst_ids]
    dump(out, os.path.join(rel, "INSTITUTION_COUNTRY.json"))

def build_country_from_field(kg, rel, ent_file, id_key, field, code_map, out_file):
    out = []
    for r in load(os.path.join(kg, "entities", ent_file)):
        cc = code_map.get(r.get(field))
        if cc:
            out.append({id_key: r[id_key], "COUNTRY_CODE": cc})
    dump(out, os.path.join(rel, out_file))


def build_doi_links(src, kg, rel):
    doi2work = {}
    for w in load(os.path.join(kg, "entities", "WORK.json")):
        dk = norm_doi(w.get("DOI"))
        if dk and dk not in doi2work:
            doi2work[dk] = str(w["WORK_ID"])
    nw = [{"NEWS_ID": str(r["NEWS_DOI_ID"]), "WORK_ID": doi2work[norm_doi(r.get("DOI"))],
           "LINK_METHOD": "doi", "MODEL": None, "MATCHING_ENTITIES": None}
          for r in load(os.path.join(src, "NEWS_DOI.json")) if norm_doi(r.get("DOI")) in doi2work]
    dump(nw, os.path.join(rel, "NEWS_WORK.json"))
    tweet_ids = entity_ids(kg, "TWEET.json", "TWEET_ID")
    tw, seen = [], set()
    for r in load(os.path.join(src, "TWEETS.json")):
        wid = doi2work.get(norm_doi(r.get("DOI")))
        tid = str(r.get("TWEET_ID"))
        if wid and tid in tweet_ids and (tid, wid) not in seen:
            seen.add((tid, wid))
            tw.append({"TWEET_ID": tid, "WORK_ID": wid})
    dump(tw, os.path.join(rel, "TWEET_WORK.json"))


def main():
    ap = argparse.ArgumentParser(description="build knowledge-graph relationship tables (relationships/)")
    ap.add_argument("--src", required=True, help="source data directory")
    ap.add_argument("--kg", required=True, help="ai_kg_dataset directory (must already have entities/)")
    ap.add_argument("--citations", default=None, help="enriched_citations.jsonl from us_citation.py (optional)")
    args = ap.parse_args()
    src, kg = args.src, args.kg
    rel = os.path.join(kg, "relationships")
    os.makedirs(rel, exist_ok=True)

    grant_ids = entity_ids(kg, "GRANT.json", "GRANT_ID")
    inst_ids = entity_ids(kg, "INSTITUTION.json", "INSTITUTION_ID")

    print("direct relations ...", flush=True)
    build_work_source(src, rel)
    build_work_author_institution(src, rel)
    build_grant_institution(src, rel, grant_ids)
    if args.citations:
        build_patent_cites_patent(args.citations, kg, rel)
    else:
        print("  [skip] PATENT_CITES_PATENT: no --citations", flush=True)

    print("country relations ...", flush=True)
    build_institution_country(src, rel, inst_ids)
    build_country_from_field(kg, rel, "POLICY.json", "POLICY_ID", "SOURCE", POLICY_SRC_CC, "POLICY_COUNTRY.json")
    build_country_from_field(kg, rel, "GRANT.json", "GRANT_ID", "DATA_SOURCE", GRANT_SRC_CC, "GRANT_COUNTRY.json")
    build_country_from_field(kg, rel, "NEWS.json", "NEWS_ID", "SOURCE", NEWS_SRC_CC, "NEWS_COUNTRY.json")
    build_country_from_field(kg, rel, "PATENT.json", "PATENT_ID", "source", PATENT_SRC_CC, "PATENT_COUNTRY.json")

    print("DOI relations ...", flush=True)
    build_doi_links(src, kg, rel)

    print("done. (PATENT entities / PATENT_INSTITUTION from the Collection + Linking pipeline)", flush=True)


if __name__ == "__main__":
    main()
