"""Deterministic parser-vs-source reconciliation.

The parser is a deterministic transform of OpenITI markup, so the SOURCE file
is the ground truth. For each book we recompute, straight from the raw markup,
what the output SHOULD contain, and compare to what parse.py emitted. Exact for
unambiguous markup (item numbers, pages, sheet refs, qur'an citations); counts +
deltas for the heuristic categories (poetry).
"""
import json, re, sys, glob
from pathlib import Path

CORPUS = Path("RELEASE")
BOOKS = {
    "0676Nawawi.ArbacunaNawawiyya": "0676Nawawi/0676Nawawi.ArbacunaNawawiyya/0676Nawawi.ArbacunaNawawiyya.Shamela0012836-ara1.mARkdown",
    "0672IbnMalik.Alfiyya": "0672IbnMalik/0672IbnMalik.Alfiyya/0672IbnMalik.Alfiyya.Shamela0008522-ara1",
    "0852IbnHajarCasqalani.BulughMaram": "0852IbnHajarCasqalani/0852IbnHajarCasqalani.BulughMaram/0852IbnHajarCasqalani.BulughMaram.Shamela0009111-ara1",
    "0751IbnQayyimJawziyya.DaWaDawa": "0751IbnQayyimJawziyya/0751IbnQayyimJawziyya.DaWaDawa/0751IbnQayyimJawziyya.DaWaDawa.Shamela0000158-ara1",
}

ORD_ONLY = re.compile(r"^###\s+\|+\s+[\d٠-٩]+\s*-\s*$")
SHEET    = re.compile(r"^###\s+\|+\s+\[\s*ص\s*:\s*[\d٠-٩]+\s*\]\s*$")
PAGE     = re.compile(r"PageV(\d+)P(\d+)")
ELLIP    = re.compile(r"(?:^|\s)(\.\.\.|…)(?:\s|$)")
# {ayah}[sura: ayah] citation pattern in source
QURAN_CIT= re.compile(r"\{[^}]*\}\s*\[[^\]]*:[^\]]*\]")

def body(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    start = next((i+1 for i,l in enumerate(lines) if l.strip()=="#META#Header#End#"), 0)
    return lines[start:]

def src_expect(lines):
    text = "\n".join(lines)
    ord_only = sum(1 for l in lines if ORD_ONLY.match(l.strip()))
    sheet    = sum(1 for l in lines if SHEET.match(l.strip()))
    pages    = {(int(m.group(1)),int(m.group(2))) for m in PAGE.finditer(text) if int(m.group(2))>0}
    quran    = len(QURAN_CIT.findall(text))
    # standalone-ellipsis content lines (raw verse signal, before balance guard)
    ellip = sum(1 for l in lines if l.startswith(("# ","~~")) and ELLIP.search(l))
    return dict(ord_only=ord_only, sheet=sheet, pages=len(pages), quran_cit=quran, ellipsis_lines=ellip)

def out_actual(uri):
    d = json.load(open(f"web/data/{uri}.parsed.json"))
    numbered = sum(1 for p in d["pages"] for b in p["content_blocks"] if b.get("number"))
    nums = [b["number"] for p in d["pages"] for b in p["content_blocks"] if b.get("number")]
    poetry = sum(1 for p in d["pages"] for b in p["content_blocks"] if b["type"]=="poetry")
    quran  = sum(1 for p in d["pages"] for b in p["content_blocks"] for s in b.get("spans",[]) if s["label"]=="quran")
    chapters = len(d["chapters"])
    return dict(pages=len(d["pages"]), numbered=numbered, nums=nums, poetry=poetry, quran=quran, chapters=chapters)

def seq_report(nums):
    ints=[]
    for n in nums:
        try: ints.append(int(str(n).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩","0123456789"))))
        except: pass
    if not ints: return "n/a"
    asc = sum(1 for a,b in zip(ints,ints[1:]) if b==a+1)
    return f"{len(ints)} nums, range {min(ints)}–{max(ints)}, {asc}/{len(ints)-1} consecutive-steps, dups={len(ints)-len(set(ints))}"

print(f"{'book':<22} {'metric':<16} {'source':>8} {'parsed':>8}  match")
print("-"*70)
for uri, rel in BOOKS.items():
    e = src_expect(body(CORPUS/"data"/rel)); a = out_actual(uri)
    short = uri.split(".")[-1][:20]
    rows = [
        ("item-numbers", e["ord_only"], a["numbered"]),
        ("real-pages",   e["pages"],    a["pages"]),
        ("quran-citations", e["quran_cit"], a["quran"]),
        ("ellipsis-lines→poetry", e["ellipsis_lines"], a["poetry"]),
    ]
    for name,s,o in rows:
        mark = "EXACT" if s==o else ("~" if abs(s-o)<=max(2,0.05*s) else "DIFF")
        print(f"{short:<22} {name:<16} {s:>8} {o:>8}  {mark}")
    print(f"{short:<22} {'sheet-refs':<16} {e['sheet']:>8} {'(dropped)':>8}")
    print(f"{short:<22} {'number-seq':<16} {seq_report(a['nums'])}")
    print()
