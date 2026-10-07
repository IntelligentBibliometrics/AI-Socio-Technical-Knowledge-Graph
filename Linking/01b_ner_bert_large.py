import json, os, torch
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

BASE = os.path.join(os.environ.get("AIONER_HOME", "./AIONER-main"), "keyword_matching")
NEWS_JSON = os.environ.get("NEWS_JSON", "./NEWS_ner_todo.json")
STEM = "NEWS_ner_todo"
MODEL_NAME = "BERT-Large-NER"
MODEL_PATH = os.path.join(BASE, "models/bert-large-NER")
AGG = "simple"
WIN, OVERLAP = 1500, 200


def make_windows(text):
    if not text:
        return []
    if len(text) <= WIN:
        return [(0, text)]
    step = WIN - OVERLAP; out = []; i = 0
    while i < len(text):
        out.append((i, text[i:i + WIN]))
        if i + WIN >= len(text):
            break
        i += step
    return out


def ner_field(pipe, text):
    ents, seen = [], set()
    for off, chunk in make_windows(text):
        try:
            res = pipe(chunk)
        except Exception:
            res = []
        for e in res:
            s, en = int(e["start"]) + off, int(e["end"]) + off
            k = (s, en, e["entity_group"])
            if k in seen:
                continue
            seen.add(k)
            ents.append({"text": e["word"], "label": e["entity_group"],
                         "confidence": float(e["score"]), "start": s, "end": en})
    ents.sort(key=lambda x: x["start"])
    return ents


def main():
    news = json.load(open(NEWS_JSON, encoding="utf-8"))
    out_dir = os.path.join(BASE, "data/news"); os.makedirs(out_dir, exist_ok=True)
    device = 0 if torch.cuda.is_available() else -1
    print(f"{MODEL_NAME}: {len(news)} docs, device={'GPU' if device==0 else 'CPU'}")
    tok = AutoTokenizer.from_pretrained(MODEL_PATH)
    mdl = AutoModelForTokenClassification.from_pretrained(MODEL_PATH)
    pipe = pipeline("ner", model=mdl, tokenizer=tok, aggregation_strategy=AGG, device=device)

    results = []
    for i, art in enumerate(news):
        if i % 500 == 0:
            print(f"  {i}/{len(news)}", flush=True)
        title = art.get("TITLE", "") or ""; abstract = art.get("TEXT", "") or ""
        t, a = ner_field(pipe, title), ner_field(pipe, abstract)
        results.append({
            "id": art.get("NEWS_ID", i), "title": title, "abstract": abstract,
            "url": art.get("URL", ""), "source": art.get("SOURCE", ""),
            "publish_date": art.get("PUBLISH_DATE", ""),
            "entities": {"title": t, "abstract": a},
            "statistics": {"title_entities": len(t), "abstract_entities": len(a),
                           "total_entities": len(t) + len(a)},
        })
    out = os.path.join(out_dir, f"{STEM}_{MODEL_NAME}_results.json")
    json.dump(results, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[done] {out}  total entities={sum(r['statistics']['total_entities'] for r in results):,}")


if __name__ == "__main__":
    main()
