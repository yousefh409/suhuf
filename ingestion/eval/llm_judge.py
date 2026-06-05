"""LLM-as-judge accuracy eval for the Claude *annotation* layer.

The annotator is Haiku 4.5. A STRONGER model (Sonnet 4.6) independently grades a
stratified sample of its output — structural spans (isnad/matn/takhrij), block
relabels, person/qur'an spans, and poetry-block precision. Not human ground
truth, but a quantitative accuracy estimate with failure examples.

Run: PYTHONPATH=. python ingestion/eval/llm_judge.py [N_per_category]
Writes ingestion/eval/judge_results.json. Needs OPENROUTER_API_KEY.
"""
import json, os, random, sys
from ingestion._client import create_client

JUDGE_MODEL = "anthropic/claude-sonnet-4.6"
BOOKS = [
    "0676Nawawi.ArbacunaNawawiyya",
    "0751IbnQayyimJawziyya.DaWaDawa",
    "0672IbnMalik.Alfiyya",
]
random.seed(1600)


def block_text(b):
    if b["type"] == "poetry":
        return " / ".join(" ".join(t["text"] for t in h) for v in b["hemistichs"] for h in v)
    return " ".join(t["text"] for t in b["tokens"])


def span_marked(b, s):
    ids = [t["id"] for t in b["tokens"]]
    try:
        i0, i1 = ids.index(s["start_token_id"]), ids.index(s["end_token_id"])
    except ValueError:
        return None, None
    toks = b["tokens"]
    marked = " ".join(
        ("〈" + toks[i]["text"] + "〉" if i == i0 else toks[i]["text"] if not (i0 < i <= i1)
         else toks[i]["text"]) for i in range(len(toks)))
    # simpler: bracket the whole span
    span_txt = " ".join(toks[i]["text"] for i in range(i0, i1 + 1))
    full = " ".join(toks[i]["text"] for i in range(len(toks)))
    full = full.replace(span_txt, "〈 " + span_txt + " 〉", 1)
    return full, span_txt


def collect():
    cats = {k: [] for k in ["structural_span", "relabel", "person", "quran", "poetry"]}
    for uri in BOOKS:
        d = json.load(open(f"web/data/{uri}.enriched.json"))
        for p in d["pages"]:
            for b in p["content_blocks"]:
                if b.get("parser_type") and b["parser_type"] != b["type"] and b["type"] in ("matn", "takhrij", "isnad"):
                    cats["relabel"].append((uri, block_text(b), b["type"]))
                if b["type"] == "poetry":
                    hs = [" ".join(t["text"] for t in h) for v in b["hemistichs"] for h in v]
                    if len(hs) >= 2:
                        cats["poetry"].append((uri, hs[0], hs[1]))
                for s in b.get("spans", []):
                    if b["type"] == "poetry":
                        continue
                    full, span_txt = span_marked(b, s)
                    if not full:
                        continue
                    if s["label"] in ("isnad", "matn", "takhrij"):
                        cats["structural_span"].append((uri, full, span_txt, s["label"]))
                    elif s["label"] == "person":
                        cats["person"].append((uri, full, span_txt, s.get("sub_label")))
                    elif s["label"] == "quran":
                        cats["quran"].append((uri, full, span_txt, s.get("ref")))
    return cats


PROMPTS = {
 "structural_span": lambda r: f"One block of classical Arabic from a hadith work. A system tagged the 〈bracketed〉 part as «{r[3]}» (isnad=chain of narrators 'حدثنا..عن..'; matn=the reported words/content; takhrij=source attribution e.g. 'رواه البخاري'). Block:\n{r[1]}\n\nIs the «{r[3]}» label correct for the bracketed span?",
 "relabel": lambda r: f"One block of classical Arabic. A system classified its structural TYPE as «{r[2]}» (prose / isnad / matn / takhrij / heading / quran). Block:\n{r[1]}\n\nIs «{r[2]}» the correct type?",
 "person": lambda r: f"A system tagged 〈{r[2]}〉 as a PERSON with role «{r[3]}» (companion / tabii / scholar / prophet / caliph). Text:\n{r[1]}\n\nIs 〈{r[2]}〉 a person, and is the role right? (correct=person+role right; partial=person but wrong/missing role; incorrect=not a person)",
 "quran": lambda r: f"A system tagged 〈{r[2]}〉 as a QUR'AN quotation" + (f" (ref {r[3]})" if r[3] else " (no ref)") + f". Text:\n{r[1]}\n\nIs the bracketed span actually Qur'an" + (", and is the ref correct?" if r[3] else "?") + " (correct=is qur'an & ref ok/none-claimed; partial=is qur'an but wrong ref; incorrect=not qur'an)",
 "poetry": lambda r: f"Two text segments a system split as the two hemistichs of one Arabic verse (bayt). Are they genuinely a line of metrical VERSE (not prose)?\nA: {r[1]}\nB: {r[2]}\n(correct=verse; incorrect=prose)",
}

SYS = ("You are an expert in classical Arabic, hadith, and Islamic literature, grading another "
       "system's annotations. Be strict and honest. Respond ONLY with JSON: "
       '{"verdict":"correct"|"partial"|"incorrect","reason":"<= 20 words"}.')


def judge(client, prompt):
    m = client.messages.create(model=JUDGE_MODEL, max_tokens=200, system=SYS,
                               messages=[{"role": "user", "content": prompt}])
    txt = m.content[0].text.strip()
    s, e = txt.find("{"), txt.rfind("}")
    return json.loads(txt[s:e + 1])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    client = create_client()
    cats = collect()
    out = {}
    score = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}
    for cat, items in cats.items():
        random.shuffle(items)
        sample = items[:n]
        results = []
        for r in sample:
            try:
                v = judge(client, PROMPTS[cat](r))
            except Exception as ex:
                v = {"verdict": "error", "reason": str(ex)[:60]}
            results.append({"book": r[0].split(".")[-1], "verdict": v.get("verdict"),
                            "reason": v.get("reason"), "subject": r[2] if len(r) > 2 else None})
        graded = [x for x in results if x["verdict"] in score]
        acc = sum(score[x["verdict"]] for x in graded) / len(graded) if graded else 0
        out[cat] = {"n": len(graded), "accuracy": round(acc, 3),
                    "dist": {v: sum(1 for x in results if x["verdict"] == v) for v in ["correct", "partial", "incorrect", "error"]},
                    "results": results}
        print(f"{cat:<16} n={len(graded):<3} accuracy={acc:.0%}  {out[cat]['dist']}")
    json.dump(out, open("ingestion/eval/judge_results.json", "w"), ensure_ascii=False, indent=2)
    print("\nwrote ingestion/eval/judge_results.json")


if __name__ == "__main__":
    main()
