"""Deterministic check: does each parsed qur'an span's text match the ayah it
cites, per the bundled index? Validates citation→text consistency and measures
ref-resolution coverage. Run: python ingestion/eval/check_quran_refs.py <uri>...
"""
import json, sys
from ingestion import quran as Q

IDX = {(s,a): Q.normalize(t) for s,a,t in json.load(open("ingestion/data/quran.json"))["ayat"]}

def ayahs_for_ref(ref):
    """Yield normalized texts for a ref like '2:255' or '103:1-3'."""
    sura, rest = ref.split(":"); sura=int(sura)
    if "-" in rest:
        a,b = rest.split("-"); rng=range(int(a),int(b)+1)
    else: rng=[int(rest)]
    return " ".join(IDX.get((sura,a),"") for a in rng).strip()

def run(uri):
    d=json.load(open(f"web/data/{uri}.parsed.json"))
    total=withref=match=partial=miss=noref=0
    for p in d["pages"]:
        for b in p["content_blocks"]:
            order=[t["id"] for t in b.get("tokens",[])]
            tok={t["id"]:t["text"] for t in b.get("tokens",[])}
            for s in b.get("spans",[]):
                if s["label"]!="quran": continue
                total+=1
                ref=s.get("ref")
                if not ref: noref+=1; continue
                withref+=1
                gold=Q.normalize(ayahs_for_ref(ref))
                i0=order.index(s["start_token_id"]); i1=order.index(s["end_token_id"])
                sw=Q.normalize(" ".join(tok[order[i]] for i in range(i0,i1+1))).split()
                gw=set(gold.split())
                hit=sum(1 for w in sw if w in gw)/max(1,len(sw))
                match+=hit>=0.8; partial+=0.4<=hit<0.8; miss+=hit<0.4
    print(f"{uri}: spans={total} ref-coverage={withref}/{total} ({withref/max(1,total):.0%}) "
          f"| of-ref: exact={match} partial={partial} miss={miss}")

for uri in (sys.argv[1:] or ["0751IbnQayyimJawziyya.DaWaDawa"]): run(uri)
