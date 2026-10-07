import os, re, json, math
from collections import defaultdict, Counter

_KW = os.path.join(os.environ.get("AIONER_HOME", "./AIONER-main"), "keyword_matching")
D3 = os.path.join(_KW, "3model")
OUT = os.path.join(_KW, "BM25")
os.makedirs(OUT, exist_ok=True)
MODELS = ["AIONER", "BERT-Large-NER", "SciBERT-SciNERTopic"]
K1, B = 1.2, 0.75


def norm(t):
    return re.sub(r'\s+', ' ', t).strip().lower()


def wc(*parts):
    return max(1, len((' '.join(p or '' for p in parts)).split()))


print("loading paper lengths ...", flush=True)
WORK = json.load(open(f"{D3}/WORK.json", encoding="utf-8"))
work_len = {w["WORK_ID"]: wc(w.get("TITLE"), w.get("ABSTRACT")) for w in WORK}
del WORK
N = len(work_len)
avgdl = sum(work_len.values()) / N
print(f"  papers N={N:,}  avgdl={avgdl:.1f}  params k1={K1}, b={B}", flush=True)


def doc_counts(path, lenmap):
    out = {}
    for did, ents in json.load(open(path, encoding="utf-8")).items():
        if did not in lenmap:
            continue
        c = Counter(norm(e["text"]) for e in ents)
        c.pop("", None)
        if c:
            out[did] = c
    return out


def run(model):
    print(f"\n#### {model} ####", flush=True)
    work_cnt = doc_counts(f"{D3}/{model}/work_entities.json", work_len)
    news_ent = {k: set(norm(e["text"]) for e in v) - {""}
                for k, v in json.load(open(f"{D3}/{model}/news_entities.json", encoding="utf-8")).items()}
    news_ent = {k: v for k, v in news_ent.items() if v}
    print(f"  with entities work={len(work_cnt):,}  news={len(news_ent):,}", flush=True)

    df = Counter()
    for c in work_cnt.values():
        for e in c:
            df[e] += 1
    idf = {e: math.log((N - n + 0.5) / (n + 0.5) + 1) for e, n in df.items()}

    post = defaultdict(list)
    for pid, c in work_cnt.items():
        L = work_len[pid]
        norm_len = K1 * (1 - B + B * L / avgdl)
        for e, f in c.items():
            w = idf[e] * (f * (K1 + 1)) / (f + norm_len)
            post[e].append((pid, w))

    outp = f"{OUT}/{model}.json"
    fo = open(outp, "w", encoding="utf-8")
    fo.write("[")
    first = True; total = 0
    for i, (nid, ents) in enumerate(news_ent.items()):
        acc = {}
        for e in ents:
            for pid, w in post.get(e, ()):
                a = acc.get(pid)
                if a is None:
                    acc[pid] = [w, [e]]
                else:
                    a[0] += w; a[1].append(e)
        for pid, (sc, shared) in acc.items():
            rec = {"NEWS_ID": nid, "WORK_ID": pid, "LINK_METHOD": "ner", "MODEL": model,
                   "MATCHING_ENTITIES": ";".join(sorted(shared)),
                   "N_SHARED": len(shared), "BM25_SCORE": round(sc, 4)}
            fo.write(("" if first else ",") + "\n" + json.dumps(rec, ensure_ascii=False))
            first = False; total += 1
        if i % 2000 == 0:
            print(f"  news {i}/{len(news_ent)}  edges so far={total:,}", flush=True)
    fo.write("\n]\n"); fo.close()
    print(f"  [done] {outp}  edges={total:,}", flush=True)
    return total


if __name__ == "__main__":
    tot = {m: run(m) for m in MODELS}
    print("\n===== summary =====")
    for m, t in tot.items():
        print(f"  {m}: {t:,} edges")
