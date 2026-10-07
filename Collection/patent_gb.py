import base64
import json
import os
import re
import time

import requests

KEY = os.environ["OPS_KEY"]
SECRET = os.environ["OPS_SECRET"]
OPS = "https://ops.epo.org/3.2"
CORE = ["G06N3/02", "G06N3/08", "G06N5/00", "G06N5/02", "G06N7/00", "G06N7/02", "G06N7/04", "G06N99/00",
        "G06K9/00", "G06T1/20", "G06T3/40", "G06T7/00", "G06T7/10", "G06T7/215", "G06T7/246", "G06T9/00",
        "G06T19/20", "G05B13/02", "G05D1/00", "G06F17/27", "G06F17/28", "G10L13/00", "G10L15/00", "G10L17/00",
        "G10L25/00", "G10L99/00", "A61B34/00", "B25J9/00"]
COUNTRY = "GB"
OUT = "PATENT_GB.json"
REFS_FILE = "gb_refs.json"
DONE_FILE = "gb_done.json"
_tok = {"v": None}


def refresh_token():
    cred = base64.b64encode(("%s:%s" % (KEY, SECRET)).encode()).decode()
    r = requests.post("%s/auth/accesstoken" % OPS,
                      headers={"Authorization": "Basic %s" % cred,
                               "Content-Type": "application/x-www-form-urlencoded"},
                      data={"grant_type": "client_credentials"}, timeout=30)
    _tok["v"] = r.json()["access_token"]


def txt(n):
    if isinstance(n, dict):
        return n.get("$", "")
    if isinstance(n, list):
        return txt(n[0]) if n else ""
    return n or ""


def aslist(x):
    return x if isinstance(x, list) else ([x] if x else [])


def fmt_date(s):
    return "%s-%s-%s" % (s[:4], s[4:6], s[6:8]) if len(s) == 8 and s.isdigit() else s


def strip_country(s):
    return re.sub(r"\s*\[[A-Z]{2}\]\s*$", "", s or "").strip()


def compact_ipc(text):
    t = (text or "").replace(" ", "")
    m = re.match(r"^([A-H]\d{2}[A-Z]\d+/\d+)", t)
    return m.group(1) if m else t


def ops_get(path, params=None, retry=8):
    for _ in range(retry):
        try:
            r = requests.get("%s/rest-services/%s" % (OPS, path),
                             headers={"Authorization": "Bearer %s" % _tok["v"], "Accept": "application/json"},
                             params=params, timeout=45)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 401:
                refresh_token()
                continue
            if r.status_code in (403, 404):
                return None
            time.sleep(6)
        except Exception:
            time.sleep(6)
    return None


def search_total(cql):
    j = ops_get("published-data/search", {"q": cql, "Range": "1-1"})
    if not j:
        return 0
    return int(j["ops:world-patent-data"]["ops:biblio-search"].get("@total-result-count", 0))


def collect_refs(cql, refs):
    total = search_total(cql)
    if total == 0:
        return
    if total > 2000:
        for y in range(1970, 2027):
            collect_refs('%s and pd within "%d %d"' % (cql, y, y), refs)
        return
    frm = 1
    while frm <= total:
        j = ops_get("published-data/search", {"q": cql, "Range": "%d-%d" % (frm, min(frm + 99, total))})
        if not j:
            break
        sr = j["ops:world-patent-data"]["ops:biblio-search"].get("ops:search-result", {})
        for pr in aslist(sr.get("ops:publication-reference")):
            for d in aslist(pr.get("document-id")):
                if d.get("@document-id-type") == "docdb":
                    refs.add("%s.%s.%s" % (txt(d.get("country")), txt(d.get("doc-number")), txt(d.get("kind"))))
        frm += 100
        time.sleep(1)


def parse_biblio(ex):
    bib = ex["bibliographic-data"]
    pubs = aslist(bib["publication-reference"]["document-id"])
    pdc = next((d for d in pubs if d.get("@document-id-type") == "docdb"), pubs[0])
    pub_num = txt(pdc.get("country")) + txt(pdc.get("doc-number")) + txt(pdc.get("kind"))
    pub_date = fmt_date(txt(pdc.get("date")))
    apps = aslist(bib["application-reference"]["document-id"])
    apn = next((d for d in apps if d.get("@document-id-type") == "epodoc"), apps[0])
    titles = aslist(bib.get("invention-title"))
    title = next((txt(t) for t in titles if t.get("@lang") == "en"), txt(titles[0]) if titles else "")
    ipcr = aslist(bib.get("classifications-ipcr", {}).get("classification-ipcr"))
    ipcs = []
    for c in ipcr:
        v = compact_ipc(txt(c.get("text")))
        if v and v not in ipcs:
            ipcs.append(v)
    hit = sorted([c for c in CORE if any(ip.startswith(c) for ip in ipcs)])
    ap_p = aslist(bib.get("parties", {}).get("applicants", {}).get("applicant"))
    applicant = [strip_country(txt(a.get("applicant-name", {}).get("name")))
                 for a in ap_p if a.get("@data-format") == "epodoc"]
    inv_p = aslist(bib.get("parties", {}).get("inventors", {}).get("inventor"))
    inv = [strip_country(txt(i.get("inventor-name", {}).get("name")))
           for i in inv_p if i.get("@data-format") == "epodoc"]
    inv = list(dict.fromkeys(inv))
    return {
        "PATENT_ID": pub_num, "TITLE": title, "ABSTRACT": "",
        "APPLICANT": "; ".join(applicant), "FIRST_INVENTOR": inv[0] if inv else "",
        "INVENTORS": "; ".join(inv), "INVENTORS_COUNT": len(inv),
        "APPLICATION_NUMBER": txt(apn.get("doc-number")), "APPLICATION_DATE": fmt_date(txt(apn.get("date"))),
        "PUBLICATION_NUMBER": pub_num, "PUBLICATION_DATE": pub_date,
        "IPC_CLASSIFICATION": "; ".join(ipcs),
        "IPC_MAIN_CLASS": hit[0] if hit else (ipcs[0] if ipcs else ""),
    }


def biblio_record(ref):
    j = ops_get("published-data/publication/docdb/%s/biblio" % ref)
    if not j:
        return None
    ex = j["ops:world-patent-data"]["exchange-documents"]["exchange-document"]
    if isinstance(ex, list):
        ex = ex[0]
    return parse_biblio(ex)


def main():
    refresh_token()
    if os.path.exists(REFS_FILE):
        refs = json.load(open(REFS_FILE, encoding="utf-8"))
    else:
        rs = set()
        for cls in CORE:
            collect_refs("ic=%s and pn=%s" % (cls, COUNTRY), rs)
        refs = sorted(rs)
        json.dump(refs, open(REFS_FILE, "w", encoding="utf-8"))
    recs = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else []
    done = set(json.load(open(DONE_FILE, encoding="utf-8"))) if os.path.exists(DONE_FILE) else set()
    for i, ref in enumerate(refs, 1):
        if ref in done:
            continue
        try:
            rec = biblio_record(ref)
            if rec:
                recs.append(rec)
        except Exception:
            pass
        done.add(ref)
        if i % 50 == 0:
            json.dump(recs, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            json.dump(sorted(done), open(DONE_FILE, "w", encoding="utf-8"))
            refresh_token()
        time.sleep(0.5)
    json.dump(recs, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(sorted(done), open(DONE_FILE, "w", encoding="utf-8"))


if __name__ == "__main__":
    main()
