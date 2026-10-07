import os
import sys
import json
import time
import argparse
import logging
import urllib.request
import urllib.error
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
API_URL = "https://xuedingmao.top/v1/chat/completions"
MODEL = "gpt-4o"
API_KEY = os.environ.get("XDM_API_KEY", "")
ROUTE = None

DEFAULT_INPUT = os.path.join(HERE, "grants_with_pi_institution_field.jsonl")
OUTPUT = os.path.join(HERE, "grants_classified.jsonl")
AI_ONLY = os.path.join(HERE, "grants_ai_only.jsonl")
PROGRESS = os.path.join(HERE, "classification_progress.json")


def build_prompt(rec):
    abstract = (rec.get("ABSTRACT") or "").strip()
    field = (rec.get("ACADEMIC_FIELD") or "").strip()
    field_line = f"Research Field: {field}\n" if field else ""
    return f"""Please determine whether the following research project is related to Artificial Intelligence (AI). Base your judgment on the project abstract (and field, if given).

{field_line}Project Abstract: {abstract}

Criteria for judgment:
- If the project involves machine learning, deep learning, neural networks, natural language processing, computer vision, knowledge representation, expert systems, intelligent algorithms, data mining, pattern recognition, intelligent systems, automated decision-making, cognitive computing, artificial intelligence, AI, robotic intelligence, intelligent control, or other AI-related technologies or concepts, classify it as AI-related
- If the project only uses computers as tools but does not involve AI technologies, it should not be considered AI-related
- If the project description is vague or lacks sufficient information, make the best judgment based on available information

Please respond ONLY in one of the following formats (answer in English):
AI_RELATED: [brief reason in English]
NOT_AI_RELATED: [brief reason in English]
"""


def call_api(prompt, max_retries=3, timeout=30):
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
        "temperature": 0.1,
    }
    if ROUTE:
        body["provider"] = {"sort": ROUTE}
    payload = json.dumps(body).encode("utf-8")
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    delay = 1.0
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.load(r)
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"API call failed (attempt {attempt}/{max_retries}): {type(e).__name__}: {e}")
            if attempt < max_retries:
                time.sleep(delay)
                delay = min(delay * 2, 10)
    return None


def parse_answer(text):
    if not text:
        return None, "API call failed"
    t = text.strip()
    low = t.lower()
    if low.startswith("ai_related"):
        return True, t.split(":", 1)[1].strip() if ":" in t else t
    if low.startswith("not_ai_related"):
        return False, t.split(":", 1)[1].strip() if ":" in t else t
    if "not_ai_related" in low:
        return False, t
    if "ai_related" in low:
        return True, t
    return None, t


def classify(rec, dry_run=False):
    if dry_run:
        ai_related, reason = None, "[dry-run] API not called"
    else:
        ai_related, reason = parse_answer(call_api(build_prompt(rec)))
    out = {}
    for k, v in rec.items():
        if k == "AI_CLASSIFICATION_REASON":
            out["AI_RELATED"] = ai_related
            out["AI_CLASSIFICATION_REASON"] = reason
        else:
            out[k] = v
    if "AI_CLASSIFICATION_REASON" not in rec:
        out["AI_RELATED"] = ai_related
        out["AI_CLASSIFICATION_REASON"] = reason
    out["CLASSIFIED_AT"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return out


def load_done_ids(path):
    done = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    done.add(json.loads(line)["GRANT_ID"])
                except (json.JSONDecodeError, KeyError):
                    continue
    return done


def read_input(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def save_progress(stats):
    stats["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(PROGRESS, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def write_ai_only():
    if not os.path.exists(OUTPUT):
        return
    n = 0
    with open(OUTPUT, encoding="utf-8") as fin, open(AI_ONLY, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            if json.loads(line).get("AI_RELATED") is True:
                fout.write(line + "\n")
                n += 1
    logger.info(f"AI-related subset {n} -> {AI_ONLY}")


def run(input_path, workers, dry_run, limit):
    done = load_done_ids(OUTPUT)
    todo = []
    for rec in read_input(input_path):
        if rec.get("GRANT_ID") in done:
            continue
        todo.append(rec)
        if limit and len(todo) >= limit:
            break
    logger.info(f"input {input_path}")
    logger.info(f"done {len(done)}, to process {len(todo)}, workers {workers}"
                + ("  [DRY-RUN]" if dry_run else ""))

    if dry_run:
        for rec in todo:
            out = classify(rec, dry_run=True)
            print(json.dumps({k: out[k] for k in
                              ("GRANT_ID", "DATA_SOURCE", "ACADEMIC_FIELD", "AI_RELATED")},
                             ensure_ascii=False))
            print("  prompt preview:", build_prompt(rec)[:150].replace("\n", " "), "...\n")
        return

    stats = {"total": 0, "ai_related": 0, "not_ai_related": 0, "errors": 0,
             "done_before": len(done), "todo": len(todo)}
    t0 = time.monotonic()
    with open(OUTPUT, "a", encoding="utf-8") as out, \
            ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(classify, r) for r in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            stats["total"] += 1
            if rec["AI_RELATED"] is True:
                stats["ai_related"] += 1
            elif rec["AI_RELATED"] is False:
                stats["not_ai_related"] += 1
            else:
                stats["errors"] += 1
            if i % 50 == 0:
                out.flush()
                save_progress(stats)
                rate = i / (time.monotonic() - t0)
                eta = (len(todo) - i) / rate / 3600 if rate else 0
                logger.info(f"progress {i}/{len(todo)}  {rate:.1f} req/s  ETA {eta:.1f}h  "
                            f"AI {stats['ai_related']} | non-AI {stats['not_ai_related']} | errors {stats['errors']}")
    save_progress(stats)
    logger.info(f"done: {stats['total']} processed, AI-related {stats['ai_related']}, "
                f"non-AI {stats['not_ai_related']}, errors {stats['errors']}")
    write_ai_only()


def bench(input_path, tiers, per):
    recs = []
    for rec in read_input(input_path):
        recs.append(rec)
        if len(recs) >= per * len(tiers) + 1:
            break
    logger.info(f"endpoint {API_URL} | model {MODEL} | route {ROUTE or 'default'}")
    print("connectivity check...", end=" ", flush=True)
    if not call_api(build_prompt(recs[0])):
        print("API unreachable, check key / network / endpoint")
        return
    print("")
    print(f"\n{'workers':>8} | {'time_s':>7} | {'req/s':>6} | {'err%':>6}")
    best = None
    for i, w in enumerate(tiers):
        batch = recs[1 + i * per: 1 + (i + 1) * per]
        t = time.monotonic()
        err = 0
        with ThreadPoolExecutor(max_workers=w) as ex:
            for out in ex.map(classify, batch):
                if out["AI_RELATED"] is None:
                    err += 1
        dt = time.monotonic() - t
        rate = len(batch) / dt if dt else 0
        er = err / len(batch) if batch else 1
        print(f"{w:>8} | {dt:>7.1f} | {rate:>6.2f} | {er:>5.0%}")
        if er < 0.1 and (best is None or rate > best[1]):
            best = (w, rate)
    if best:
        print(f"\nsuggestion: workers={best[0]} (~{best[1]:.1f} req/s) "
              f"-> full 61,117 records ~{61117 / best[1] / 3600:.1f} h")
    else:
        print("\nall tiers have high error rates; reduce concurrency or check API limits")


def main():
    global API_URL, MODEL, ROUTE
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0, help="process only the first N records (for testing)")
    ap.add_argument("--dry-run", action="store_true", help="dry run: check data flow and prompt without calling the API")
    ap.add_argument("--bench", action="store_true", help="benchmark concurrency tiers and suggest one")
    ap.add_argument("--bench-tiers", default="5,10,20,30", help="concurrency tiers for --bench")
    ap.add_argument("--bench-per", type=int, default=20, help="records per tier for --bench")
    ap.add_argument("--route", choices=["price", "speed", "success_rate"], help="provider.sort route")
    ap.add_argument("--api-url", default=API_URL)
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()
    API_URL, MODEL, ROUTE = args.api_url, args.model, args.route
    if not args.dry_run and not API_KEY:
        sys.exit("set the XDM_API_KEY environment variable first")
    if args.bench:
        bench(args.input, [int(x) for x in args.bench_tiers.split(",")], args.bench_per)
    else:
        run(args.input, args.workers, args.dry_run, args.limit)


if __name__ == "__main__":
    main()
