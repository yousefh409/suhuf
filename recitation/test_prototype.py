#!/usr/bin/env python3
"""Quick prototype: load model, decode a few recordings, validate scoring."""

import sys, json
from pathlib import Path

# Run from recitation/ dir
BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from engine import RecitationEngine

MODEL_PATH = BASE / "models" / "ssl_xls_r_v5"
PASSAGES_FILE = BASE / "passage.json"
MANIFEST_FILE = BASE / "test_data" / "manifest.jsonl"
TEST_DIR = BASE / "test_data"


def load_passages():
    with open(PASSAGES_FILE) as f:
        data = json.load(f)
    # For now, only ajrumiyyah has phrases
    for p in data["passages"]:
        if p["id"] == "ajrumiyyah" and "phrases" in p:
            return p["phrases"]
    return []


def load_manifest():
    entries = []
    with open(MANIFEST_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def main():
    phrases = load_passages()
    manifest = load_manifest()
    engine = RecitationEngine(str(MODEL_PATH))

    print(f"\n{'='*80}")
    print(f"Loaded {len(phrases)} phrases, {len(manifest)} recordings")
    print(f"{'='*80}\n")

    # Test a few recordings: 2 correct, 2 with errors
    test_indices = [1, 2, 8, 14]  # correct, correct, sukoon+kasra, no tanween
    if len(sys.argv) > 1:
        test_indices = [int(x) for x in sys.argv[1:]]

    for idx in test_indices:
        if idx >= len(manifest):
            continue
        entry = manifest[idx]
        audio_path = TEST_DIR / entry["file"]
        phrase_idx = entry["phrase_idx"]
        notes = entry["notes"]

        if phrase_idx >= len(phrases):
            print(f"[SKIP] phrase_idx {phrase_idx} out of range")
            continue

        phrase_text = phrases[phrase_idx]
        print(f"\n{'─'*80}")
        print(f"Recording: {entry['file']}")
        print(f"Notes: {notes}")
        print(f"Phrase {phrase_idx}: {phrase_text}")
        print()

        # Load audio
        waveform = engine.load_audio(str(audio_path))
        print(f"Audio: {waveform.shape[0]} samples = {waveform.shape[0]/16000:.2f}s")

        # Get log probs and greedy decode
        log_probs = engine.get_log_probs(waveform)
        greedy = engine.greedy_decode(log_probs)
        print(f"Greedy: {greedy}")

        # Full phrase score
        T = log_probs.shape[0]
        tokens = engine.text_to_tokens(phrase_text)
        full_score = engine.ctc_log_prob(log_probs, tokens) / T
        print(f"Full phrase score: {full_score:.4f}")

        # Forced alignment + word scoring
        try:
            results, _, _ = engine.score_phrase(waveform, phrase_text)
            print(f"\nWord-by-word:")
            for r in results:
                word = r["word"]
                es = r["expected_score"]
                ss = r["sukoon_score"]
                eff = r["effective_score"]
                alt_name = r["best_alt_name"] or "-"
                alt_score = r["best_alt_score"]
                delta = eff - alt_score if alt_score > -900 else 0

                status = "OK"
                if alt_score > eff + 0.1:
                    status = f"ALT_BETTER({alt_name})"

                print(f"  {word:>30s}  exp={es:+.3f}  suk={ss:+.3f}  "
                      f"eff={eff:+.3f}  alt={alt_score:+.3f}({alt_name})  "
                      f"Δ={delta:+.3f}  {status}")
        except Exception as e:
            print(f"  ERROR in scoring: {e}")


if __name__ == "__main__":
    main()
