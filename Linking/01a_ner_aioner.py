import json, re, os, sys, subprocess

GPU = sys.argv[1] if len(sys.argv) > 1 else "0"
ENV = os.environ.get("AIONER_ENV", "")
AIONER = os.environ.get("AIONER_HOME", "./AIONER-main")
NEWS_JSON = os.environ.get("NEWS_JSON", "./NEWS_ner_todo.json")
IN_DIR = f"{AIONER}/example/input_news_todo"
OUT_DIR = f"{AIONER}/example/output_news_todo"
MODEL = f"{AIONER}/pretrained_models/AIONER/PubmedBERT-CRF-AIONER.h5"
VOCAB = f"{AIONER}/vocab/AIO_label.vocab"
PUBTATOR = f"{IN_DIR}/news_ner_todo.pubtator"


def clean(t):
    if not t:
        return ""
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def json_to_pubtator(src, dst):
    papers = json.load(open(src, encoding='utf-8'))
    n = 0
    with open(dst, 'w', encoding='utf-8') as f:
        for i, p in enumerate(papers):
            pmid = str(p.get('NEWS_ID') or (i + 1)).strip()
            title, abstract = clean(p.get('TITLE', '')), clean(p.get('TEXT', ''))
            if not title and not abstract:
                continue
            f.write(f"{pmid}|t|{title}\n{pmid}|a|{abstract}\n\n")
            n += 1
    return n


def main():
    os.makedirs(IN_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"[1/2] converting {NEWS_JSON} -> PubTator ...")
    n = json_to_pubtator(NEWS_JSON, PUBTATOR)
    print(f"      wrote {n} docs -> {PUBTATOR}")

    print(f"[2/2] AIONER (PubmedBERT-CRF) tagging (GPU={GPU}) ...")
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = f"{ENV}/lib:" + env.get("LD_LIBRARY_PATH", "")
    env["CUDA_VISIBLE_DEVICES"] = str(GPU)
    subprocess.run(
        [f"{ENV}/bin/python", "AIONER_Run.py",
         "-i", f"{IN_DIR}/", "-m", MODEL, "-v", VOCAB, "-e", "ALL", "-o", f"{OUT_DIR}/"],
        cwd=f"{AIONER}/src", env=env, check=True,
    )
    print(f"[done] AIONER output: {OUT_DIR}/news_ner_todo.pubtator")


if __name__ == "__main__":
    main()
