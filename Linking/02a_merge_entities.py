import os, re, json, glob
from collections import defaultdict

BASE = os.environ.get("AIONER_HOME", "./AIONER-main")
OLD_STEM = os.environ.get("OLD_NEWS_STEM", "old_news_source")
KW = os.path.join(BASE, "keyword_matching")
D3 = os.path.join(KW, "3model")
PER_BATCH = 20000

NEWS = json.load(open(os.path.join(D3, "NEWS.json"), encoding="utf-8"))
WORK = json.load(open(os.path.join(D3, "WORK.json"), encoding="utf-8"))
URL2NID = {n.get("URL"): n["NEWS_ID"] for n in NEWS}
WORK_ID_BY_POS = [w["WORK_ID"] for w in WORK]
print(f"master: NEWS={len(NEWS):,}  WORK={len(WORK):,}")

OLD_SRC = json.load(open(os.path.join(BASE, f"Newsdata/{OLD_STEM}.json"), encoding="utf-8"))
OLD_ARR = OLD_SRC["articles"] if isinstance(OLD_SRC, dict) else OLD_SRC
OLD_URL_BY_POS = [a.get("url") for a in OLD_ARR]
NEW_SRC = json.load(open(os.environ.get("NEWS_JSON", "./NEWS_ner_todo.json"), encoding="utf-8"))
NEWID2URL = {a["NEWS_ID"]: a.get("URL") for a in NEW_SRC}

ENT = re.compile(r'^([^\t]+)\t(\d+)\t(\d+)\t([^\t]+)\t([^\t]+)$')
T = re.compile(r'^([^|]+)\|t\|(.*)$')
A = re.compile(r'^([^|]+)\|a\|(.*)$')


def ent_std(text, label, conf, start, end, section):
    return {"text": text, "label": label, "confidence": conf,
            "start": start, "end": end, "section": section}


def aioner_news():
    out = defaultdict(list); miss = 0; total = 0
    def parse(path, url_of):
        nonlocal miss, total
        for block in open(path, encoding="utf-8").read().split("\n\n"):
            block = block.strip("\n")
            if not block: continue
            lines = block.split("\n"); pmid = None; ents = []
            for ln in lines:
                me = ENT.match(ln); mt = T.match(ln)
                if me:
                    ents.append(ent_std(me.group(4), me.group(5), None,
                                        int(me.group(2)), int(me.group(3)), "full"))
                elif mt and "\t" not in ln:
                    pmid = mt.group(1)
            if pmid is None: continue
            total += 1
            url = url_of(pmid)
            nid = URL2NID.get(url)
            if nid is None:
                miss += 1; continue
            if ents: out[nid].extend(ents)
    parse(os.path.join(BASE, "example/output/newsdata_articles.pubtator"),
          lambda p: OLD_URL_BY_POS[int(p) - 1] if p.isdigit() and int(p) - 1 < len(OLD_URL_BY_POS) else None)
    parse(os.path.join(BASE, "example/output_news_todo/news_ner_todo.pubtator"),
          lambda p: NEWID2URL.get(p))
    return out, miss, total


def aioner_works():
    out = defaultdict(list); total = 0; miss = 0
    for f in sorted(glob.glob(os.path.join(BASE, "example/output/Works_AI_Only_*_batch_*.pubtator"))):
        b = int(re.search(r'batch_(\d+)', f).group(1))
        for block in open(f, encoding="utf-8").read().split("\n\n"):
            block = block.strip("\n")
            if not block: continue
            pmid = None; ents = []
            for ln in block.split("\n"):
                me = ENT.match(ln); mt = T.match(ln)
                if me:
                    ents.append(ent_std(me.group(4), me.group(5), None,
                                        int(me.group(2)), int(me.group(3)), "full"))
                elif mt and "\t" not in ln:
                    pmid = mt.group(1)
            if pmid is None: continue
            total += 1
            gpos = (b - 1) * PER_BATCH + (int(pmid) - 1)
            if gpos >= len(WORK_ID_BY_POS): miss += 1; continue
            if ents: out[WORK_ID_BY_POS[gpos]].extend(ents)
    return out, miss, total


def json_news(old_file, new_file):
    out = defaultdict(list); miss = 0; total = 0
    for f in (old_file, new_file):
        for r in json.load(open(f, encoding="utf-8")):
            total += 1
            nid = URL2NID.get(r.get("url"))
            if nid is None: miss += 1; continue
            ents = []
            for sec in ("title", "abstract"):
                for e in r.get("entities", {}).get(sec, []):
                    ents.append(ent_std(e["text"], e["label"], e.get("confidence"),
                                        e.get("start"), e.get("end"), sec))
            if ents: out[nid].extend(ents)
    return out, miss, total


def json_works(pattern):
    out = defaultdict(list); miss = 0; total = 0
    for f in sorted(glob.glob(pattern)):
        part = int(re.search(r'part_(\d+)', f).group(1))
        for r in json.load(open(f, encoding="utf-8")):
            total += 1
            gpos = (part - 1) * PER_BATCH + int(r["id"])
            if gpos >= len(WORK_ID_BY_POS): miss += 1; continue
            wid = WORK_ID_BY_POS[gpos]
            ents = []
            for sec in ("title", "abstract"):
                for e in r.get("entities", {}).get(sec, []):
                    ents.append(ent_std(e["text"], e["label"], e.get("confidence"),
                                        e.get("start"), e.get("end"), sec))
            if ents: out[wid].extend(ents)
    return out, miss, total


def save(model, news_map, work_map):
    d = os.path.join(D3, model); os.makedirs(d, exist_ok=True)
    for name, m in (("news_entities.json", news_map), ("work_entities.json", work_map)):
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=2)
    ne = sum(len(v) for v in news_map.values()); we = sum(len(v) for v in work_map.values())
    print(f"  [{model}] news docs={len(news_map):,} entities={ne:,} | work docs={len(work_map):,} entities={we:,}")


def main():
    print("\n== AIONER ==")
    nn, nmiss, ntot = aioner_news();  print(f"  news aligned: {ntot-nmiss}/{ntot} (missed {nmiss})")
    ww, wmiss, wtot = aioner_works(); print(f"  work aligned: {wtot-wmiss}/{wtot} (missed {wmiss})")
    save("AIONER", nn, ww)

    print("\n== BERT-Large-NER ==")
    nn, nmiss, ntot = json_news(
        os.path.join(KW, f"data/news/{OLD_STEM}_BERT-Large-NER_results.json"),
        os.path.join(KW, "data/news/NEWS_ner_todo_BERT-Large-NER_results.json"))
    print(f"  news aligned: {ntot-nmiss}/{ntot} (missed {nmiss})")
    ww, wmiss, wtot = json_works(os.path.join(KW, "data/papers/ner_results/*BERT-Large-NER_results.json"))
    print(f"  work aligned: {wtot-wmiss}/{wtot} (missed {wmiss})")
    save("BERT-Large-NER", nn, ww)

    print("\n== SciBERT-SciNERTopic ==")
    nn, nmiss, ntot = json_news(
        os.path.join(KW, f"data/news/{OLD_STEM}_SciBERT-SciNERTopic_results.json"),
        os.path.join(KW, "data/news/NEWS_ner_todo_SciBERT-SciNERTopic_results.json"))
    print(f"  news aligned: {ntot-nmiss}/{ntot} (missed {nmiss})")
    ww, wmiss, wtot = json_works(os.path.join(KW, "data/papers/ner_results/*SciBERT-SciNERTopic_results.json"))
    print(f"  work aligned: {wtot-wmiss}/{wtot} (missed {wmiss})")
    save("SciBERT-SciNERTopic", nn, ww)


if __name__ == "__main__":
    main()
