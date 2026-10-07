import json
import os
import re
import time

import requests

BASE = "https://api.uspto.gov/api/v1/patent/applications/search"
KEY = os.environ["USPTO_API_KEY"]
CORE = ["G06N3/02", "G06N3/08", "G06N5/00", "G06N5/02", "G06N7/00", "G06N7/02", "G06N7/04", "G06N99/00",
        "G06K9/00", "G06T1/20", "G06T3/40", "G06T7/00", "G06T7/10", "G06T7/215", "G06T7/246", "G06T9/00",
        "G06T19/20", "G05B13/02", "G05D1/00", "G06F17/27", "G06F17/28", "G10L13/00", "G10L15/00", "G10L17/00",
        "G10L25/00", "G10L99/00", "A61B34/00", "B25J9/00"]


def to_query(cpc):
    m = re.match(r"^([A-HY]\d{2}[A-Z])(.*)$", cpc)
    s, rest = m.group(1), m.group(2)
    return "%s*" % s if not rest else "%s*%s*" % (s, rest.replace("/", chr(92) + "/"))


QUERY = "applicationMetaData.cpcClassificationBag:(" + " OR ".join(to_query(c) for c in CORE) + ")"
FIELDS = ["applicationNumberText", "applicationMetaData.inventionTitle",
          "applicationMetaData.cpcClassificationBag", "applicationMetaData.inventorBag",
          "applicationMetaData.applicantBag", "applicationMetaData.firstApplicantName",
          "applicationMetaData.filingDate", "applicationMetaData.patentNumber",
          "applicationMetaData.earliestPublicationNumber", "applicationMetaData.grantDate",
          "applicationMetaData.earliestPublicationDate", "applicationMetaData.applicationNumberText"]
OUT = "PATENT_US.json"
PROG = "us_progress.json"
SIZE = 100
S = requests.Session()
S.headers.update({"X-API-Key": KEY, "Accept": "application/json", "Content-Type": "application/json"})


def compact(c):
    return "".join(c.split())


def parse(w):
    md = w.get("applicationMetaData", {})
    cpcs = [compact(c) for c in (md.get("cpcClassificationBag") or [])]
    hit = [p for p in CORE if any(cc.startswith(p) for cc in cpcs)]
    if not hit:
        return None, None
    inv = [(i.get("inventorNameText") or (i.get("firstName", "") + " " + i.get("lastName", "")).strip())
           for i in (md.get("inventorBag") or [])]
    inv = [x for x in inv if x]
    app = [a.get("applicantNameText") for a in (md.get("applicantBag") or []) if a.get("applicantNameText")]
    if not app and md.get("firstApplicantName"):
        app = [md["firstApplicantName"]]
    pnum = md.get("patentNumber")
    pubnum = md.get("earliestPublicationNumber")
    appnum = w.get("applicationNumberText") or md.get("applicationNumberText") or ""
    pub = ("US%s" % pnum) if pnum else (pubnum or (("US%s" % appnum) if appnum else ""))
    rec = {
        "PATENT_ID": pub, "TITLE": md.get("inventionTitle") or "", "ABSTRACT": "",
        "APPLICANT": "; ".join(app), "FIRST_INVENTOR": inv[0] if inv else "",
        "INVENTORS": "; ".join(inv), "INVENTORS_COUNT": len(inv),
        "APPLICATION_NUMBER": ("US%s" % appnum) if appnum else "",
        "APPLICATION_DATE": md.get("filingDate") or "",
        "PUBLICATION_NUMBER": pub,
        "PUBLICATION_DATE": md.get("grantDate") or md.get("earliestPublicationDate") or "",
        "IPC_CLASSIFICATION": "; ".join(sorted(hit)), "IPC_MAIN_CLASS": sorted(hit)[0],
    }
    return pub, (rec, hit)


def fetch(offset, size, retry=5):
    body = {"q": QUERY, "fields": FIELDS, "pagination": {"offset": offset, "limit": size},
            "sort": [{"field": "applicationNumberText", "order": "asc"}]}
    for _ in range(retry):
        try:
            r = S.post(BASE, data=json.dumps(body), timeout=90)
            if r.status_code == 200:
                return r.json()
            time.sleep(3)
        except Exception:
            time.sleep(3)
    return None


def dump_output(records):
    out = []
    for pub, r in records.items():
        hit = r.get("_hit", [])
        rec = {k: v for k, v in r.items() if k != "_hit"}
        rec["IPC_CLASSIFICATION"] = "; ".join(hit)
        rec["IPC_MAIN_CLASS"] = hit[0] if hit else ""
        out.append(rec)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def main():
    prog = json.load(open(PROG, encoding="utf-8")) if os.path.exists(PROG) else {"offset": 0, "records": {}}
    records = prog["records"]
    first = fetch(0, SIZE)
    if not first:
        return
    total = first.get("count", 0)

    def ingest(data):
        for w in data.get("patentFileWrapperDataBag", []):
            pub, val = parse(w)
            if not pub:
                continue
            rec, hit = val
            if pub in records:
                s = set(records[pub].get("_hit", []))
                s.update(hit)
                records[pub]["_hit"] = sorted(s)
            else:
                rec["_hit"] = sorted(hit)
                records[pub] = rec

    if prog["offset"] == 0:
        ingest(first)
        prog["offset"] = SIZE
    for i, off in enumerate(range(prog["offset"], total, SIZE), 1):
        data = fetch(off, SIZE)
        if not data:
            break
        ingest(data)
        prog["offset"] = off + SIZE
        if i % 100 == 0:
            prog["records"] = records
            json.dump(prog, open(PROG, "w", encoding="utf-8"), ensure_ascii=False)
            dump_output(records)
        time.sleep(0.25)
    prog["records"] = records
    json.dump(prog, open(PROG, "w", encoding="utf-8"), ensure_ascii=False)
    dump_output(records)


if __name__ == "__main__":
    main()
