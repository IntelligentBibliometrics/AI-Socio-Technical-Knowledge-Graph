
import os
import re
import sys
import gzip
import glob
import json
import argparse
import collections
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import pycountry
except ImportError:
    pycountry = None


def is_blank(v):
    return v is None or (isinstance(v, str) and v.strip() in ("", "None"))

def nz(v):
    return None if is_blank(v) else v

def to_int(v):
    if is_blank(v):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None

def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_jsonl(path):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

def dump(rows, kg, name):
    path = os.path.join(kg, "entities", name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"  {name:<18} {len(rows):>9} rows", flush=True)


WORK_INT = {"PUBLICATION_YEAR", "CITED_BY_COUNT", "COUNTRIES_DISTINCT_COUNT",
            "INSTITUTIONS_DISTINCT_COUNT", "LOCATIONS_COUNT"}
WORK_FIELDS = ["WORK_ID", "TITLE", "ABSTRACT", "DOI", "LANGUAGE", "TYPE", "TYPE_CROSSREF",
               "PUBLICATION_YEAR", "CITED_BY_COUNT", "COUNTRIES_DISTINCT_COUNT",
               "INSTITUTIONS_DISTINCT_COUNT", "LOCATIONS_COUNT"]

def build_work_and_source(src, kg):
    w = load(os.path.join(src, "WORKS_AI_ONLY.json"))
    work, sources = [], {}
    for r in w:
        work.append({f: (to_int(r.get(f)) if f in WORK_INT else nz(r.get(f))) for f in WORK_FIELDS})
        sid = r.get("PRIMARY_LOCATION_SOURCE_ID")
        if not is_blank(sid) and sid not in sources:
            sources[str(sid)] = {"SOURCE_ID": str(sid),
                                 "SOURCE_DISPLAY_NAME": nz(r.get("PRIMARY_LOCATION_SOURCE_DISPLAY_NAME")),
                                 "SOURCE_ISSN": nz(r.get("PRIMARY_LOCATION_SOURCE_ISSN")),
                                 "SOURCE_ISSN_L": nz(r.get("PRIMARY_LOCATION_SOURCE_ISSN_L")),
                                 "SOURCE_TYPE": nz(r.get("PRIMARY_LOCATION_SOURCE_TYPE"))}
    dump(work, kg, "WORK.json")
    del w, work
    for r in load(os.path.join(src, "WORKS_ALTERNATE_SOURCES_AI.json")):
        sid = r.get("SOURCE_ID")
        if is_blank(sid) or str(sid) in sources:
            continue
        sources[str(sid)] = {"SOURCE_ID": str(sid), "SOURCE_DISPLAY_NAME": None,
                             "SOURCE_ISSN": nz(r.get("SOURCE_ISSN")),
                             "SOURCE_ISSN_L": nz(r.get("SOURCE_ISSN_L")),
                             "SOURCE_TYPE": nz(r.get("SOURCE_TYPE"))}
    order = ["SOURCE_ID", "SOURCE_DISPLAY_NAME", "SOURCE_ISSN", "SOURCE_ISSN_L", "SOURCE_TYPE"]
    dump([{k: sources[s][k] for k in order} for s in sorted(sources)], kg, "SOURCE.json")


def scan_author_names(snapshot_dir, needed):
    id_re = re.compile(rb'^\{"id":\s*"https://openalex\.org/A(\d+)"')
    need_b = {a.encode() for a in needed}
    names = {}
    files = sorted(glob.glob(os.path.join(snapshot_dir, "updated_date=*", "part_*.gz")))
    print(f"    scanning {len(files)} author snapshot shards ...", flush=True)
    for fp in files:
        try:
            with gzip.open(fp, "rb") as fh:
                for line in fh:
                    m = id_re.match(line)
                    if m and m.group(1) in need_b:
                        k = m.group(1).decode()
                        if k not in names:
                            try:
                                names[k] = json.loads(line).get("display_name")
                            except Exception:
                                pass
        except Exception as e:
            print(f"    [warn] {fp}: {e}", flush=True)
    return names

def build_author_institution_country(src, kg, snapshot_dir):
    d = load(os.path.join(src, "WORKS_AUTHORS_INSTITUTIONS_AI.json"))
    author_ids = sorted({str(r["AUTHOR_ID"]) for r in d if not is_blank(r.get("AUTHOR_ID"))})
    names = scan_author_names(snapshot_dir, set(author_ids)) if snapshot_dir else {}
    dump([{"AUTHOR_ID": to_int(a), "AUTHOR_NAME": names.get(a)} for a in author_ids], kg, "AUTHOR.json")
    inst = {}
    for r in d:
        iid = r.get("INSTITUTION_ID")
        if is_blank(iid):
            continue
        iid = str(iid)
        cur = inst.setdefault(iid, {"INSTITUTION_ID": to_int(iid), "INSTITUTION_NAME": None, "INSTITUTION_TYPE": None})
        if cur["INSTITUTION_NAME"] is None and not is_blank(r.get("INSTITUTION_NAME")):
            cur["INSTITUTION_NAME"] = r["INSTITUTION_NAME"]
        if cur["INSTITUTION_TYPE"] is None and not is_blank(r.get("INSTITUTION_TYPE")):
            cur["INSTITUTION_TYPE"] = r["INSTITUTION_TYPE"]
    dump([inst[k] for k in sorted(inst)], kg, "INSTITUTION.json")
    inst_codes = {str(r["INSTITUTION_COUNTRY"]) for r in d if not is_blank(r.get("INSTITUTION_COUNTRY"))}
    return inst_codes

CODE_NAME_SPECIAL = {"EU": "European Union", "DD": "German Democratic Republic (East Germany)",
                     "SU": "Soviet Union", "YU": "Yugoslavia", "XK": "Kosovo"}

def code_to_name(code):
    if code in CODE_NAME_SPECIAL:
        return CODE_NAME_SPECIAL[code]
    if pycountry:
        c = pycountry.countries.get(alpha_2=code)
        if c:
            return c.name
    return code

def build_country(kg, inst_codes):
    codes = sorted(inst_codes | {"US", "GB", "AU", "EU"})
    dump([{"COUNTRY_CODE": c, "COUNTRY_NAME": code_to_name(c)} for c in codes], kg, "COUNTRY.json")


GRANT_FIELDS = ["GRANT_ID", "ABSTRACT", "ACADEMIC_FIELD", "DATA_SOURCE", "FUNDING", "CURRENCY",
                "INSTITUTION", "PI_NAME", "PROGRAM", "START_YEAR", "AI_CLASSIFICATION_REASON"]

def build_grant(grant_detail, kg):
    g = load(grant_detail)
    dump([{f: r.get(f) for f in GRANT_FIELDS} for r in g], kg, "GRANT.json")


POLICY_FIELDS = ["POLICY_ID", "TITLE", "URL", "DESCRIPTION", "DISPLAY_TYPE",
                 "ORGANISATIONS", "PUBLIC_TIMESTAMP", "SOURCE"]
DOMAIN_SOURCE = {"www.federalregister.gov": "Federal Register", "www.gov.uk": "GOV.UK",
                 "data.europa.eu": "EUR-Lex"}

def _date10(v):
    return None if is_blank(v) else str(v)[:10]

def build_policy(src, apo, kg):
    import urllib.parse
    def source_of(url):
        dom = urllib.parse.urlparse(url or "").netloc
        return DOMAIN_SOURCE.get(dom, dom or None)
    out = []
    for r in load(os.path.join(src, "POLICY.json")):
        out.append({"POLICY_ID": r["POLICY_ID"], "TITLE": nz(r.get("TITLE")), "URL": nz(r.get("URL")),
                    "DESCRIPTION": nz(r.get("DESCRIPTION")), "DISPLAY_TYPE": nz(r.get("DISPLAY_TYPE")),
                    "ORGANISATIONS": nz(r.get("ORGANISATIONS")),
                    "PUBLIC_TIMESTAMP": _date10(r.get("PUBLIC_TIMESTAMP")),
                    "SOURCE": source_of(r.get("URL"))})
    if apo and os.path.exists(apo):
        maxn = max((int(str(r["POLICY_ID"])[2:]) for r in out if str(r["POLICY_ID"]).startswith("pc")), default=0)
        for i, r in enumerate(load_jsonl(apo), start=1):
            out.append({"POLICY_ID": f"pc{maxn + i:05d}", "TITLE": nz(r.get("TITLE")),
                        "URL": nz(r.get("URL")), "DESCRIPTION": nz(r.get("DESCRIPTION")),
                        "DISPLAY_TYPE": nz(r.get("DOCUMENT_TYPE")),
                        "ORGANISATIONS": nz(r.get("ORGANISATIONS")),
                        "PUBLIC_TIMESTAMP": _date10(r.get("PUBLIC_TIMESTAMP")),
                        "SOURCE": nz(r.get("SOURCE"))})
    dump([{f: r[f] for f in POLICY_FIELDS} for r in out], kg, "POLICY.json")


def build_news(src, refetch_dir, news_date_map, kg):
    dm = load(news_date_map) if (news_date_map and os.path.exists(news_date_map)) else {}
    out = []
    for r in load(os.path.join(src, "NEWS_NER.json")):
        out.append({"NEWS_ID": r.get("NEWS_ID"), "TITLE": nz(r.get("TITLE")), "TEXT": nz(r.get("ABSTRACT")),
                    "SOURCE": nz(r.get("SOURCE")), "URL": nz(r.get("URL")),
                    "PUBLISH_DATE": nz(r.get("PUBLISH_DATE")), "SCRAPE_DATE": nz(r.get("SCRAPE_DATE"))})
    for r in load(os.path.join(src, "NEWS_DOI.json")):
        out.append({"NEWS_ID": r.get("NEWS_DOI_ID"), "TITLE": nz(r.get("NEWS_DOI_TITLE")),
                    "TEXT": nz(r.get("NEWS_TEXT")), "SOURCE": nz(r.get("SOURCE")),
                    "URL": nz(r.get("NEW_DOI_URL")), "PUBLISH_DATE": None, "SCRAPE_DATE": None})
    if refetch_dir and os.path.isdir(refetch_dir):
        maxn = max((int(re.match(r"NEWS(\d+)$", r["NEWS_ID"]).group(1)) for r in out
                    if re.match(r"NEWS(\d+)$", str(r["NEWS_ID"]))), default=0)
        n = maxn
        for fn in ("NEWS_ABC_AI.json", "NEWS_EURONEWS_AI.json", "NEWS_CONVERSATION_AI.json"):
            p = os.path.join(refetch_dir, fn)
            if not os.path.exists(p):
                continue
            for r in load(p):
                n += 1
                out.append({"NEWS_ID": f"NEWS{n:06d}", "TITLE": nz(r.get("TITLE")), "TEXT": nz(r.get("ABSTRACT")),
                            "SOURCE": nz(r.get("SOURCE")), "URL": nz(r.get("URL")),
                            "PUBLISH_DATE": nz(r.get("PUBLISH_DATE")), "SCRAPE_DATE": nz(r.get("SCRAPE_DATE"))})
    for r in out:
        if is_blank(r["SCRAPE_DATE"]):
            r["SCRAPE_DATE"] = "2025-09-19"
        if is_blank(r["PUBLISH_DATE"]) and r["NEWS_ID"] in dm:
            r["PUBLISH_DATE"] = dm[r["NEWS_ID"]]
    dump(out, kg, "NEWS.json")


def build_tweet(src, kg):
    t = load(os.path.join(src, "TWEETS.json"))
    dump([{"TWEET_ID": r.get("TWEET_ID"), "TWEET_LINK": nz(r.get("TWEETS_LINK")),
           "PUBLISHED_TIME": nz(r.get("PUBLISHED_TIME")), "DOI": nz(r.get("DOI"))} for r in t], kg, "TWEET.json")


def main():
    ap = argparse.ArgumentParser(description="build knowledge-graph entity tables (entities/)")
    ap.add_argument("--src", required=True, help="source data directory")
    ap.add_argument("--grant-detail", required=True, help="path to GRANT_DETAIL.json")
    ap.add_argument("--kg", required=True, help="ai_kg_dataset output directory")
    ap.add_argument("--apo", default=None, help="apo_policy.jsonl (optional)")
    ap.add_argument("--refetch-dir", default=None, help="supplementary news directory (optional)")
    ap.add_argument("--author-snapshot", default=None, help="OpenAlex authors snapshot dir (optional; fills author names)")
    ap.add_argument("--news-date-map", default=None, help="JSON {NEWS_ID: date}, fills missing publish dates (optional)")
    args = ap.parse_args()
    os.makedirs(os.path.join(args.kg, "entities"), exist_ok=True)

    print("WORK / SOURCE ...", flush=True)
    build_work_and_source(args.src, args.kg)
    print("AUTHOR / INSTITUTION ...", flush=True)
    inst_codes = build_author_institution_country(args.src, args.kg, args.author_snapshot)
    print("COUNTRY (master) ...", flush=True)
    build_country(args.kg, inst_codes)
    print("GRANT ...", flush=True)
    build_grant(args.grant_detail, args.kg)
    print("POLICY ...", flush=True)
    build_policy(args.src, args.apo, args.kg)
    print("NEWS ...", flush=True)
    build_news(args.src, args.refetch_dir, args.news_date_map, args.kg)
    print("TWEET ...", flush=True)
    build_tweet(args.src, args.kg)
    print("done.", flush=True)


if __name__ == "__main__":
    main()
