import argparse, json, os, random, sys, threading, time, urllib.request, urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from tqdm import tqdm

GRAPH = "https://api.openaire.eu/graph/v1/researchProducts"
SCHOLIX = "https://api.scholexplorer.openaire.eu/v3/Links"
OPENAIRE_TOKEN = ""   # API token goes here
# (key, DOI parameter, type-filter parameter, type, side of the link holding the dataset/software)
QUERIES = (("dataset_out", "sourcePid", "targetType", "dataset", "target"),
           ("dataset_in", "targetPid", "sourceType", "dataset", "source"),
           ("software_out", "sourcePid", "targetType", "software", "target"),
           ("software_in", "targetPid", "sourceType", "software", "source"))
SIMILARITY_MARK = "similar"   # matches hasAmongTopNSimilarDocuments, isAmongTopNSimilarDocuments, isSimilarTo


class RateLimiter:
    """At most `rate` requests per second across all threads."""
    def __init__(self, rate):
        self.interval, self.lock, self.next = 1.0 / rate, threading.Lock(), 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            slot = max(now, self.next)
            self.next = slot + self.interval
        if slot > now:
            time.sleep(slot - now)


LIMITER = None


def get_json(url, params, auth=False):
    global OPENAIRE_TOKEN
    full = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        token = OPENAIRE_TOKEN if auth else ""
        req = urllib.request.Request(full, headers={
            "Accept": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
        LIMITER.wait()
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403) and token and attempt < 4:
                if OPENAIRE_TOKEN:
                    print("[auth] token rejected or expired - continuing anonymously", flush=True)
                OPENAIRE_TOKEN = ""
                continue
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(3 * (attempt + 1)); continue
            return None
        except Exception:
            if attempt < 4:
                time.sleep(3 * (attempt + 1)); continue
            return None


def norm_doi(d):
    d = (d or "").strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if d.startswith(p):
            d = d[len(p):]
    return d


def compact(link, side):
    o = link.get(side) or {}
    rel = link.get("RelationshipType") or {}
    ids = o.get("Identifier") or []
    return {"relation": rel.get("Name"), "subtype": rel.get("SubType"),
            "provider": [x.get("name") for x in (link.get("LinkProvider") or [])],
            "title": o.get("Title"),
            "doi": next((x.get("ID") for x in ids if x.get("IDScheme") == "doi"), None),
            "openaire_id": next((x.get("ID") for x in ids if x.get("IDScheme") == "openaireIdentifier"), None),
            "publisher": [x.get("name") for x in (o.get("Publisher") or [])],
            "date": o.get("PublicationDate")}


def process(paper, skip_match):
    doi = norm_doi(paper.get("DOI"))
    rec = {"PAPER_ID": paper["PAPER_ID"], "DOI": doi, "YEAR": paper.get("PUBLICATION_YEAR"),
           "in_openaire": None, "links": {}, "ok": True}
    if not doi:
        rec["in_openaire"] = False
        return rec
    if not skip_match:
        d = get_json(GRAPH, {"pid": doi, "pageSize": 1}, auth=True)
        if d is None:
            rec["ok"] = False; return rec
        rec["in_openaire"] = (d.get("header") or {}).get("numFound", 0) > 0
    for key, pid_param, type_param, typ, side in QUERIES:
        links, page = [], 0
        while True:
            d = get_json(SCHOLIX, {pid_param: doi, type_param: typ, "page": page})
            if d is None:
                rec["ok"] = False; return rec
            res = d.get("result") or []
            links += [compact(L, side) for L in res]
            page += 1
            if not res or page >= (d.get("totalPages") or 0):
                break
        if links:
            rec["links"][key] = links
    return rec


def is_similarity(link):
    return SIMILARITY_MARK in (link.get("subtype") or "").lower() or SIMILARITY_MARK in (link.get("relation") or "").lower()


def kept_links(rec, key, keep_similarity):
    L = rec["links"].get(key, [])
    return L if keep_similarity else [x for x in L if not is_similarity(x)]


def load_checkpoint(path):
    done = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue   # partially written last line of an interrupted run
                if r.get("ok"):
                    done[r["PAPER_ID"]] = r
    return done


def select_papers(args):
    P = json.load(open(args.paper, encoding="utf-8"))
    if args.ids:
        want = {l.strip() for l in open(args.ids, encoding="utf-8") if l.strip()}
        P = [p for p in P if str(p["PAPER_ID"]) in want]
    if args.year_from is not None:
        P = [p for p in P if (p.get("PUBLICATION_YEAR") or 0) >= args.year_from]
    if args.year_to is not None:
        P = [p for p in P if (p.get("PUBLICATION_YEAR") or 9999) <= args.year_to]
    if args.sample and args.sample < len(P):
        random.seed(args.seed)
        P = random.sample(P, args.sample)
    return P


def bucket(y):
    if not y: return "unknown"
    return "<2000" if y < 2000 else "2000-2009" if y < 2010 else "2010-2019" if y < 2020 else "2020+"


def finalize(papers, done, args):
    rows = [done[p["PAPER_ID"]] for p in papers if p["PAPER_ID"] in done]
    n = len(rows)
    if not n:
        print("nothing finished yet"); return
    keep = args.keep_similarity
    edges = {"dataset": [], "software": []}
    flags = {}
    dropped = 0
    for r in rows:
        f = {"dataset": False, "software": False}
        for key, _, _, typ, _ in QUERIES:
            dropped += len(r["links"].get(key, [])) - len(kept_links(r, key, keep))
            for L in kept_links(r, key, keep):
                f[typ] = True
                edges[typ].append({"PAPER_ID": r["PAPER_ID"], "PAPER_DOI": r["DOI"],
                                   f"{typ.upper()}_DOI": L["doi"], f"{typ.upper()}_OPENAIRE_ID": L["openaire_id"],
                                   f"{typ.upper()}_TITLE": L["title"], "PUBLISHER": "; ".join(L["publisher"] or []) or None,
                                   "DIRECTION": "paper_to_" + typ if key.endswith("_out") else typ + "_to_paper",
                                   "RELATION": L["relation"], "RELATION_SUBTYPE": L["subtype"],
                                   "LINK_PROVIDER": "; ".join(L["provider"] or []) or None})
        flags[r["PAPER_ID"]] = f
    for typ in edges:   # the same link can be reported from both directions / pages
        seen, uniq = set(), []
        for e in edges[typ]:
            k = (e["PAPER_ID"], e[f"{typ.upper()}_DOI"] or e[f"{typ.upper()}_OPENAIRE_ID"], e["DIRECTION"], e["RELATION_SUBTYPE"])
            if k not in seen:
                seen.add(k); uniq.append(e)
        edges[typ] = uniq
        with open(os.path.join(args.out, f"PAPER_{typ.upper()}.json"), "w", encoding="utf-8") as fo:
            json.dump(uniq, fo, ensure_ascii=False, indent=2)

    n_ds = sum(f["dataset"] for f in flags.values())
    n_sw = sum(f["software"] for f in flags.values())
    n_any = sum(f["dataset"] or f["software"] for f in flags.values())
    checked = [r for r in rows if r["in_openaire"] is not None]
    matched = sum(1 for r in checked if r["in_openaire"])
    pct = lambda a, b: f"{a/b:.1%}" if b else "n/a"
    lines = [f"papers processed: {n} of {len(papers)} selected",
             f"similarity-based relations: {'kept' if keep else f'dropped ({dropped} links)'}",
             f"[r] DOIs found in the OpenAIRE Graph: {matched} / {len(checked)} = {pct(matched, len(checked))}",
             f"[c] papers with >=1 dataset OR software: {n_any} / {n} = {pct(n_any, n)}",
             f"    papers with >=1 dataset : {n_ds} = {pct(n_ds, n)}",
             f"    papers with >=1 software: {n_sw} = {pct(n_sw, n)}",
             f"    PAPER_DATASET links: {len(edges['dataset'])} (distinct datasets "
             f"{len({e['DATASET_DOI'] or e['DATASET_OPENAIRE_ID'] for e in edges['dataset']})})",
             f"    PAPER_SOFTWARE links: {len(edges['software'])} (distinct software "
             f"{len({e['SOFTWARE_DOI'] or e['SOFTWARE_OPENAIRE_ID'] for e in edges['software']})})",
             "", "by publication period (papers / dataset or software / dataset / software):"]
    for b in ("<2000", "2000-2009", "2010-2019", "2020+", "unknown"):
        g = [r for r in rows if bucket(r["YEAR"]) == b]
        if g:
            a = sum(flags[r["PAPER_ID"]]["dataset"] or flags[r["PAPER_ID"]]["software"] for r in g)
            d = sum(flags[r["PAPER_ID"]]["dataset"] for r in g); s = sum(flags[r["PAPER_ID"]]["software"] for r in g)
            lines.append(f"    {b:10s} {len(g):6d}  {a:5d} ({pct(a, len(g)):>5})  {d:5d} ({pct(d, len(g)):>5})  {s:5d} ({pct(s, len(g)):>5})")
    for typ in ("dataset", "software"):
        if edges[typ]:
            lines += ["", f"{typ} links:",
                      f"    relation subtype: {Counter(e['RELATION_SUBTYPE'] for e in edges[typ]).most_common(6)}",
                      f"    direction       : {Counter(e['DIRECTION'] for e in edges[typ]).most_common()}",
                      f"    publisher       : {Counter(p for e in edges[typ] for p in (e['PUBLISHER'] or '(none)').split('; ')).most_common(6)}"]
    text = "\n".join(lines)
    with open(os.path.join(args.out, "openaire_summary.txt"), "w", encoding="utf-8") as fo:
        fo.write(text + "\n")
    enc = sys.stdout.encoding or "utf-8"
    print(("\n" + "=" * 72 + "\n" + text + "\n" + "=" * 72).encode(enc, "replace").decode(enc))


def main():
    global LIMITER
    ap = argparse.ArgumentParser(description="Datasets and software linked to papers, from the OpenAIRE Graph (join by DOI).")
    ap.add_argument("--paper", required=True, help="PAPER.json of the knowledge graph")
    ap.add_argument("--out", required=True, help="output directory (also holds the checkpoint)")
    ap.add_argument("--ids", help="text file with one PAPER_ID per line (subset to process)")
    ap.add_argument("--year-from", type=int); ap.add_argument("--year-to", type=int)
    ap.add_argument("--sample", type=int, help="random sample size taken from the selected papers")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--rate", type=float, default=8.0, help="max requests per second (all threads)")
    ap.add_argument("--keep-similarity", action="store_true", help="keep OpenAIRE similarity-based relations")
    ap.add_argument("--skip-match", action="store_true", help="skip the Graph API presence check")
    ap.add_argument("--summary-only", action="store_true", help="rebuild outputs from the checkpoint, no requests")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    LIMITER = RateLimiter(args.rate)
    ckpt = os.path.join(args.out, "openaire_checkpoint.jsonl")
    papers = select_papers(args)
    done = load_checkpoint(ckpt)
    todo = [p for p in papers if p["PAPER_ID"] not in done]
    print(f"selected {len(papers):,} papers | done {len(papers) - len(todo):,} | to do {len(todo):,} | "
          f"rate <= {args.rate}/s | token: {'yes' if OPENAIRE_TOKEN else 'no'} | checkpoint {ckpt}", flush=True)
    if args.summary_only or not todo:
        finalize(papers, done, args); return

    plain = not sys.stderr.isatty()   # redirected to a log: print plain progress lines instead of a bar
    n_done0 = len(papers) - len(todo)
    bar = tqdm(total=len(papers), initial=n_done0, desc="OpenAIRE", unit="paper", dynamic_ncols=True, disable=plain)
    n_link = n_err = 0
    t0 = time.time()
    try:
        with open(ckpt, "a", encoding="utf-8") as fo, ThreadPoolExecutor(args.workers) as pool:
            futs = [pool.submit(process, p, args.skip_match) for p in todo]
            for k, fut in enumerate(as_completed(futs), 1):
                r = fut.result()
                if r["ok"]:
                    fo.write(json.dumps(r, ensure_ascii=False) + "\n"); fo.flush()
                    done[r["PAPER_ID"]] = r
                    n_link += bool(r["links"])
                    bar.update(1)
                else:
                    n_err += 1
                bar.set_postfix(linked=n_link, errors=n_err)
                if plain and (k % 25 == 0 or k == len(futs)):
                    el = time.time() - t0
                    cur = n_done0 + k - n_err
                    filled = int(30 * cur / len(papers))
                    print(f"[{'#' * filled}{'.' * (30 - filled)}] {cur}/{len(papers)} linked={n_link} errors={n_err} "
                          f"elapsed={el/60:.1f}m eta={el/k*(len(futs)-k)/60:.1f}m", flush=True)
    except KeyboardInterrupt:
        print("\ninterrupted - progress saved; run the same command again to resume", flush=True)
    finally:
        bar.close()
    if n_err:
        print(f"{n_err} papers failed and were not saved; run the same command again to retry them", flush=True)
    finalize(papers, done, args)


if __name__ == "__main__":
    main()
