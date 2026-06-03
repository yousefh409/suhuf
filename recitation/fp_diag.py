#!/usr/bin/env python3
"""Diagnostic: dump corpus false positives (correct text flagged) with the
triggering tier (error_detail) and key signals. Read-only; no eval changes."""
import sys, argparse, torch
sys.path.insert(0, ".")
from engine import RecitationEngine
from eval import _score_phrase_with_whisper, iter_corpus_items, iter_session_items, MODEL_PATH

ap = argparse.ArgumentParser()
ap.add_argument("--source", choices=["corpus", "sessions"], default="corpus")
ap.add_argument("--limit", type=int, default=8)
args = ap.parse_args()

eng = RecitationEngine(str(MODEL_PATH))
it = (iter_corpus_items(eng, limit=args.limit) if args.source == "corpus"
      else iter_session_items(eng, max_items=args.limit))

nfp = ntot = 0
by_tier = {}
for (_lbl, uid, audio, text, ww) in it:
    model_out = eng.get_model_outputs(torch.from_numpy(audio), output_hidden_states=True)
    cls = _score_phrase_with_whisper(eng, audio, text, ww, model_out=model_out)
    for cw in cls:
        ntot += 1
        if cw["status"] != "correct":
            nfp += 1
            d = cw["debug"]
            det = cw.get("error_detail")
            by_tier[det] = by_tier.get(det, 0) + 1
            print(f"FP {uid:18s} '{cw['word']}' type={cw['error_type']:8s} tier={det} "
                  f"eff={d.get('eff')} i3d={d.get('i3rab_delta')} td={d.get('tash_delta')} "
                  f"sukd={d.get('sukoon_delta')} pc={d.get('pc')} gfm={d.get('gfm')} gdm={d.get('gdm')}")
print(f"\nFP {nfp}/{ntot} = {100*nfp/ntot:.2f}%")
print("by tier:", by_tier)
