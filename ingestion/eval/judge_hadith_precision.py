"""Precision check: does a stronger model agree the deterministic isnad/matn/
takhrij boundaries are correct? Stratified by confidence (marker vs fallback)."""
import json, os, random
from anthropic import Anthropic
random.seed(7)
d=json.load(open("web/data/0852IbnHajarCasqalani.BulughMaram.parsed.json"))
h=[b for p in d["pages"] for b in p["content_blocks"] if b.get("number")]
def seg(b,l):
    sp=[s for s in b["spans"] if s["label"]==l]
    if not sp: return ""
    ids=[t["id"] for t in b["tokens"]];tx={t["id"]:t["text"] for t in b["tokens"]}
    s=sp[0];i0=ids.index(s["start_token_id"]);i1=ids.index(s["end_token_id"])
    return " ".join(tx[ids[i]] for i in range(i0,i1+1))
def conf(b):
    s=[x for x in b["spans"] if x["label"] in("isnad","matn","takhrij")]
    return s[0].get("confidence") if s else None
hi=[b for b in h if conf(b)==0.95]; lo=[b for b in h if conf(b)==0.7]
random.shuffle(hi); random.shuffle(lo)
sample=hi[:12]+lo[:18]
client=Anthropic()
SYS=("You grade a system's segmentation of a hadith into isnad (chain of narrators), "
     "matn (the reported text), and takhrij (source attribution). Reply ONLY JSON: "
     '{"verdict":"correct|partial|incorrect","reason":"<=15 words"}.')
sc={"correct":1,"partial":0.5,"incorrect":0}; res={0.95:[],0.7:[]}
for b in sample:
    c=conf(b)
    p=f"ISNAD: {seg(b,'isnad')}\nMATN: {seg(b,'matn')}\nTAKHRIJ: {seg(b,'takhrij')}\n\nIs this segmentation correct?"
    try:
        m=client.messages.create(model="claude-sonnet-4-6",max_tokens=120,system=SYS,messages=[{"role":"user","content":p}])
        t=m.content[0].text; v=json.loads(t[t.find("{"):t.rfind("}")+1])
    except Exception as e: v={"verdict":"error","reason":str(e)[:40]}
    res[c].append(v.get("verdict"))
for c,vs in res.items():
    g=[x for x in vs if x in sc]
    acc=sum(sc[x] for x in g)/len(g) if g else 0
    from collections import Counter
    print(f"conf={c}: n={len(g)} accuracy={acc:.0%}  {dict(Counter(vs))}")
