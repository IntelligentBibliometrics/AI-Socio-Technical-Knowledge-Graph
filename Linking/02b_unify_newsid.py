import json, re, os, sys

D3 = os.path.join(os.environ.get("AIONER_HOME", "./AIONER-main"), "keyword_matching", "3model")
MODELS = ["AIONER", "BERT-Large-NER", "SciBERT-SciNERTopic"]


def build_map():
    news = json.load(open(f"{D3}/NEWS.json", encoding="utf-8"))
    nd = sorted([n for n in news if n["NEWS_ID"].startswith("newsdoi")],
                key=lambda n: int(re.sub(r"\D", "", n["NEWS_ID"])))
    maxn = max(int(re.sub(r"\D", "", n["NEWS_ID"]))
               for n in news if n["NEWS_ID"].startswith("NEWS"))
    mp = {}
    for i, n in enumerate(nd, 1):
        mp[n["NEWS_ID"]] = f"NEWS{maxn + i:06d}"
    return news, mp


def main():
    news, mp = build_map()
    print(f"newsdoi to rename: {len(mp)}  e.g. {list(mp.items())[:2]} .. {list(mp.items())[-1]}")

    mapping = []
    for n in news:
        old = n["NEWS_ID"]
        if old in mp:
            mapping.append({"NEWS_ID": mp[old], "OLD_ID": old, "URL": n.get("URL"),
                            "SOURCE": n.get("SOURCE"), "TITLE": n.get("TITLE"),
                            "PUBLISH_DATE": n.get("PUBLISH_DATE"), "DOI": None})
            n["NEWS_ID"] = mp[old]
    json.dump(news, open(f"{D3}/NEWS.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(mapping, open(f"{D3}/newsdoi_unify_map.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"  master updated; map newsdoi_unify_map.json ({len(mapping)} entries, DOI placeholder)")

    for m in MODELS:
        f = f"{D3}/{m}/news_entities.json"
        d = json.load(open(f, encoding="utf-8"))
        d2 = {mp.get(k, k): v for k, v in d.items()}
        json.dump(d2, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  {m}/news_entities.json re-keyed (docs {len(d2)})")

    news2 = json.load(open(f"{D3}/NEWS.json", encoding="utf-8"))
    ids = [n["NEWS_ID"] for n in news2]
    nums = sorted(int(re.sub(r"\D", "", x)) for x in ids)
    print("\n== verify master ==")
    print(f"  total={len(ids)}  remaining newsdoi={sum(1 for x in ids if x.startswith('newsdoi'))}")
    print(f"  id min={nums[0]} max={nums[-1]} contiguous={nums == list(range(1, len(ids)+1))} unique={len(set(ids))==len(ids)}")
    for m in MODELS:
        d = json.load(open(f"{D3}/{m}/news_entities.json", encoding="utf-8"))
        left = sum(1 for k in d if k.startswith("newsdoi"))
        print(f"  {m}/news_entities: remaining newsdoi keys={left}")


if __name__ == "__main__":
    main()
