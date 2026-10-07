import io
import json
import os
import re
import time

import requests
from pypdf import PdfReader

BASE = "https://production.api.ipaustralia.gov.au/public/ipright-search-api/v1"
CORE_IPC = ["G06N3/02", "G06N3/08", "G06N5/00", "G06N5/02", "G06N7/00", "G06N7/02", "G06N7/04", "G06N99/00",
            "G06K9/00", "G06T1/20", "G06T3/40", "G06T7/00", "G06T7/10", "G06T7/215", "G06T7/246", "G06T9/00",
            "G06T19/20", "G05B13/02", "G05D1/00", "G06F17/27", "G06F17/28", "G10L13/00", "G10L15/00", "G10L17/00",
            "G10L25/00", "G10L99/00", "A61B34/00", "B25J9/00"]
NUMBERS_FILE = "core_numbers.json"
OUT = "PATENT_AU.json"
S = requests.Session()
S.headers.update({"Accept": "application/json"})


def search_numbers(prefix, pause=0.3):
    q = "%s* IN IPC" % prefix
    out, offset, limit = [], 0, 100
    while True:
        j = S.get("%s/patents" % BASE, params={"query": q, "offset": offset, "limit": limit}, timeout=30).json()
        res = j.get("results") or []
        out.extend(x["auApplicationNumber"] for x in res)
        total = j.get("count", 0)
        offset += limit
        if offset >= total or not res:
            break
        time.sleep(pause)
    return out


def norm_ipc(mark):
    return " ".join(mark.split())


def clean_abstract(t):
    t = " ".join(t.split())
    t = re.sub(r"This data,.*$", "", t).strip()
    m = re.search(r"\bABSTRACT\b", t, re.I)
    if m:
        t = t[m.end():]
    t = re.sub(r"\b\d{9,10}\s+\d{1,2}\s+[A-Za-z]{3,}\s+\d{4}.*$", "", t)
    return t.strip(" 0123456789\t\n")


def get_abstract(num, docs, pause=0.3):
    absdocs = [d for d in docs
               if "abstract" in ((d.get("documentName") or "") + (d.get("documentType") or "")).lower()]
    absdocs.sort(key=lambda d: 0 if "accept" in (d.get("documentName") or "").lower() else 1)
    for d in absdocs:
        try:
            r = S.get("%s/patents/%s/documents/content" % (BASE, num),
                      params={"documents": d["documentId"]},
                      headers={"Accept": "application/pdf"}, timeout=30)
            if "pdf" in r.headers.get("content-type", ""):
                txt = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(r.content)).pages)
                c = clean_abstract(txt)
                if len(c) > 40:
                    return c
        except Exception:
            pass
        time.sleep(pause)
    return ""


def fetch_record(num, pause=0.3):
    d = S.get("%s/patents/%s" % (BASE, num), timeout=30).json()
    inv = [i.get("name", "") for i in (d.get("inventors") or []) if i.get("name")]
    ap = d.get("applicants")
    apps = [a.get("name", "") for a in ap] if isinstance(ap, list) else ([ap] if ap else [])
    ipcs = [norm_ipc(m["IPCMark"]) for m in (d.get("IPCMarks") or []) if m.get("IPCMark")]
    main = [norm_ipc(m["IPCMark"]) for m in (d.get("IPCMarks") or [])
            if m.get("firstMarkIndicator") and m.get("IPCMark")]
    specs = d.get("specifications") or []
    kind = specs[-1].get("kind", "") if specs else ""
    aunum = d.get("auApplicationNumber") or str(num)
    return {
        "PATENT_ID": "AU%s" % aunum,
        "TITLE": d.get("inventionTitle") or "",
        "ABSTRACT": get_abstract(num, d.get("documents") or [], pause),
        "APPLICANT": "; ".join(a for a in apps if a),
        "FIRST_INVENTOR": inv[0] if inv else "",
        "INVENTORS": "; ".join(inv),
        "INVENTORS_COUNT": len(inv),
        "APPLICATION_NUMBER": "AU%s" % aunum,
        "APPLICATION_DATE": d.get("filingDate") or "",
        "PUBLICATION_NUMBER": "AU%s%s" % (aunum, kind),
        "PUBLICATION_DATE": d.get("opiDate") or d.get("wipoPublicationDate") or "",
        "IPC_CLASSIFICATION": "; ".join(ipcs),
        "IPC_MAIN_CLASS": main[0] if main else (ipcs[0] if ipcs else ""),
    }


def main():
    if os.path.exists(NUMBERS_FILE):
        nums = json.load(open(NUMBERS_FILE, encoding="utf-8"))
    else:
        seen = set()
        for p in CORE_IPC:
            seen.update(search_numbers(p))
        nums = sorted(seen)
        json.dump(nums, open(NUMBERS_FILE, "w", encoding="utf-8"))
    recs = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else []
    done = {r["PATENT_ID"] for r in recs}
    todo = [n for n in nums if "AU%s" % n not in done]
    for i, n in enumerate(todo, 1):
        try:
            recs.append(fetch_record(n))
        except Exception:
            pass
        if i % 20 == 0:
            json.dump(recs, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        time.sleep(0.25)
    json.dump(recs, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
