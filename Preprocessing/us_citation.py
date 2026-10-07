import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

URL = "https://api.uspto.gov/api/v1/patent/oa/enriched_cited_reference_metadata/v3/records"
KEY = os.environ["USPTO_API_KEY"]
CLEAN = "PATENT_US_clean.json"
OUT = "enriched_citations.jsonl"
PAGE = 100
WORKERS = 30


def fetch_app(appnum, retry=4):
    headers = {"x-api-key": KEY, "Accept": "application/json"}
    out = []
    start = 0
    for _ in range(retry):
        try:
            r = requests.post(URL, headers=headers,
                              data={"criteria": "patentApplicationNumber:%s" % appnum, "start": start, "rows": PAGE},
                              timeout=40)
            if r.status_code != 200:
                time.sleep(1.5)
                continue
            resp = r.json().get("response", {})
            total = resp.get("numFound", 0)
            for d in resp.get("docs", []):
                out.append({
                    "cited": d.get("citedDocumentIdentifier"),
                    "category": d.get("citationCategoryCode"),
                    "claims": d.get("relatedClaimNumberText"),
                    "oa_date": (d.get("officeActionDate") or "")[:10],
                    "examiner_cited": d.get("examinerCitedReferenceIndicator"),
                    "npl": d.get("nplIndicator"),
                })
            start += PAGE
            if start >= total:
                return out
        except Exception:
            time.sleep(1.5)
    return out if out else None


def main():
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    done.add(json.loads(line)["application_number"])
                except Exception:
                    pass
    recs = json.load(open(CLEAN, encoding="utf-8"))
    tasks = []
    for r in recs:
        app = (r.get("APPLICATION_NUMBER", "") or "").replace("US", "", 1)
        if app and app not in done:
            tasks.append((r.get("PATENT_ID", ""), app))
    with open(OUT, "a", encoding="utf-8") as out, ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(fetch_app, app): (pid, app) for pid, app in tasks}
        for fut in as_completed(futs):
            pid, app = futs[fut]
            cits = fut.result()
            if cits is None:
                rec = {"patent": pid, "application_number": app, "n_citations": 0, "citations": [], "_error": True}
            else:
                rec = {"patent": pid, "application_number": app, "n_citations": len(cits), "citations": cits}
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
