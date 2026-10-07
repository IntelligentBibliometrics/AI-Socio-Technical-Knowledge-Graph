"""Build PAPER_CITES_PAPER from the OpenAlex works snapshot.

Scans every works shard, keeps the records whose work id is in PAPER.json and
emits one edge (citing -> cited) for each entry of `referenced_works` that is
also in PAPER.json. References to papers outside the corpus, and self
references, are dropped; the result is the citation network *within* the
selected AI papers, not the full reference lists.

Usage:
    python 04_paper_citations.py --snapshot <openalex-snapshot>/data/works \
        --paper <kg>/entities/PAPER.json --out <kg>/relationships/PAPER_CITES_PAPER.json
"""
import argparse, glob, gzip, json, os, re, time
from multiprocessing import Pool

ID_RE = re.compile(rb'"id":\s*"https://openalex\.org/W(\d+)"')
REF_RE = re.compile(rb'"referenced_works":\s*\[(.*?)\]', re.S)
W_RE = re.compile(rb'https://openalex\.org/W(\d+)')
IDS = None


def init(paper_path):
    global IDS
    IDS = {str(p["PAPER_ID"]).encode() for p in json.load(open(paper_path, encoding="utf-8"))}


def scan(fp):
    n = hit = 0
    edges = []
    with gzip.open(fp, "rb") as fh:
        for line in fh:
            n += 1
            m = ID_RE.search(line, 0, 120)
            if not m or m.group(1) not in IDS:
                continue
            hit += 1
            r = REF_RE.search(line)
            if not r:
                continue
            src = m.group(1)
            for x in W_RE.findall(r.group(1)):
                if x in IDS and x != src:
                    edges.append((src.decode(), x.decode()))
    return fp, n, hit, edges


def main():
    ap = argparse.ArgumentParser(description="Citations among the selected papers (OpenAlex referenced_works).")
    ap.add_argument("--snapshot", required=True, help="OpenAlex snapshot works dir (contains updated_date=*/part_*.gz)")
    ap.add_argument("--paper", required=True, help="PAPER.json of the knowledge graph")
    ap.add_argument("--out", required=True, help="output PAPER_CITES_PAPER.json")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.snapshot, "updated_date=*", "part_*.gz")),
                   key=os.path.getsize, reverse=True)
    t0 = time.time()
    tot_n = tot_hit = 0
    pairs = set()
    with Pool(args.workers, initializer=init, initargs=(args.paper,)) as pool:
        for i, (fp, n, hit, edges) in enumerate(pool.imap_unordered(scan, files), 1):
            tot_n += n; tot_hit += hit
            pairs.update(edges)
            if i % 25 == 0 or i == len(files):
                print(f"[{i}/{len(files)}] records={tot_n:,} papers={tot_hit:,} edges={len(pairs):,} "
                      f"{(time.time()-t0)/60:.1f} min", flush=True)

    rows = [{"CITING_PAPER_ID": s, "CITED_PAPER_ID": d} for s, d in sorted(pairs)]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"[done] {args.out}  papers found={tot_hit:,}  edges={len(rows):,}  "
          f"citing={len({s for s, _ in pairs}):,}  cited={len({d for _, d in pairs}):,}")


if __name__ == "__main__":
    main()
