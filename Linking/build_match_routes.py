import os
import sys
import re
import json
from collections import Counter
from unidecode import unidecode

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.environ.get("DATA_BASE", ".")
INST_JSON = BASE + r"/Graphdata/ai_kg_dataset/entities/INSTITUTION.json"
GRANTS_JSON = BASE + r"/ner-redo/GRANT_ner_todo.json"
MODEL_IN = BASE + r"/ner-redo/GRANT_INSTITUTION_matched_modelonly.json"
MODEL_OUT = BASE + r"/ner-redo/GRANT_INSTITUTION_model.json"
REGEX_OUT = BASE + r"/ner-redo/GRANT_INSTITUTION_regex.json"


def norm(s):
    if not s:
        return ""
    s = unidecode(str(s)).lower().strip()
    s = re.sub(r"\b(the|of|and)\b", " ", s)
    s = re.sub(r"[^a-z0-9]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    inst = json.load(open(INST_JSON, encoding="utf-8"))
    grants = json.load(open(GRANTS_JSON, encoding="utf-8"))
    model = json.load(open(MODEL_IN, encoding="utf-8"))
    src = {g["GRANT_ID"]: g.get("DATA_SOURCE") for g in grants}

    model_out = []
    for r in model:
        model_out.append({
            "GRANT_ID": r["GRANT_ID"],
            "DATA_SOURCE": src.get(r["GRANT_ID"]),
            "INSTITUTION": r["INSTITUTION"],
            "INSTITUTION_ID": r.get("INSTITUTION_ID"),
            "MATCHED_NAME": r.get("MATCHED_NAME"),
            "ROR_ID": r.get("ROR_ID"),
            "MATCH_SCORE": r.get("MATCH_SCORE"),
            "MATCH_CATEGORY": r.get("MATCH_CATEGORY"),
        })

    name2entries = {}
    for x in inst:
        nm = x.get("INSTITUTION_NAME")
        if not nm:
            continue
        key = norm(nm)
        if key:
            name2entries.setdefault(key, []).append(
                (str(x["INSTITUTION_ID"]), nm, x.get("INSTITUTION_TYPE")))

    regex_out = []
    for r in model:
        gid = r["GRANT_ID"]
        institution = r["INSTITUTION"]
        entries = name2entries.get(norm(institution))
        if entries:
            ids = sorted({e[0] for e in entries})
            ambiguous = len(ids) > 1
            chosen = entries[0]
            regex_out.append({
                "GRANT_ID": gid,
                "DATA_SOURCE": src.get(gid),
                "INSTITUTION": institution,
                "INSTITUTION_ID": chosen[0],
                "MATCHED_NAME": chosen[1],
                "REGEX_MATCH": 1,
                "AMBIGUOUS": ambiguous,
                "CANDIDATE_IDS": ids if ambiguous else None,
            })
        else:
            regex_out.append({
                "GRANT_ID": gid,
                "DATA_SOURCE": src.get(gid),
                "INSTITUTION": institution,
                "INSTITUTION_ID": None,
                "MATCHED_NAME": None,
                "REGEX_MATCH": 0,
                "AMBIGUOUS": False,
                "CANDIDATE_IDS": None,
            })

    json.dump(model_out, open(MODEL_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(regex_out, open(REGEX_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    total = len(model_out)
    m_hit = sum(1 for r in model_out if r["INSTITUTION_ID"])
    r_hit = sum(1 for r in regex_out if r["REGEX_MATCH"] == 1)
    both = sum(1 for a, b in zip(model_out, regex_out) if a["INSTITUTION_ID"] and b["INSTITUTION_ID"])
    agree = sum(1 for a, b in zip(model_out, regex_out)
                if a["INSTITUTION_ID"] and b["INSTITUTION_ID"] and a["INSTITUTION_ID"] == b["INSTITUTION_ID"])
    only_m = sum(1 for a, b in zip(model_out, regex_out) if a["INSTITUTION_ID"] and not b["INSTITUTION_ID"])
    only_r = sum(1 for a, b in zip(model_out, regex_out) if b["INSTITUTION_ID"] and not a["INSTITUTION_ID"])
    neither = sum(1 for a, b in zip(model_out, regex_out) if not a["INSTITUTION_ID"] and not b["INSTITUTION_ID"])

    print("=" * 60)
    print(f"total records: {total}")
    print(f"[route1 model] hit {m_hit} ({m_hit/total*100:.1f}%)  -> {MODEL_OUT.split('/')[-1]}")
    print(f"[route2 regex] hit {r_hit} ({r_hit/total*100:.1f}%)  -> {REGEX_OUT.split('/')[-1]}")
    print("-" * 60)
    print("comparison:")
    print(f"  both hit             : {both}")
    print(f"    - IDs agree        : {agree}")
    print(f"    - IDs differ (manual): {both - agree}")
    print(f"  model only           : {only_m}")
    print(f"  regex only           : {only_r}")
    print(f"  neither hit          : {neither}")
    print("=" * 60)


if __name__ == "__main__":
    main()
