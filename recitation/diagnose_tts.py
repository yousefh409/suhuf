#!/usr/bin/env python3
"""Diagnose why full-passage TTS tashkeel detection is low.

For each phrase in ajrumiyyah, for each word with swappable internal diacritics:
  - Generate TTS audio for the modified phrase (one diacritic swapped)
  - Score directly through the engine (no WebSocket)
  - Print per-word signals: eff, greedy_diac_mismatches, greedy_segment,
    best_tashkeel_score, and whether each signal would fire

At the end, summarize: how many words have gdm >= 1 at various eff gates,
and what detection rate each gate would yield.

Usage:
    python diagnose_tts.py          # first 5 phrases only
    python diagnose_tts.py --all    # all phrases
    python diagnose_tts.py -v       # verbose (print per-word details even for non-swapped)
"""

import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

CACHE_DIR = BASE / ".tts_cache"
CACHE_DIR.mkdir(exist_ok=True)
MODEL_PATH = BASE / "models" / "ssl_xls_r_v5"
TTS_VOICE = "ar-SA-HamedNeural"

# Diacritics
FATHA = '\u064e'
DAMMA = '\u064f'
KASRA = '\u0650'
FATHATAN = '\u064b'
DAMMATAN = '\u064c'
KASRATAN = '\u064d'
SUKOON = '\u0652'
SHADDA = '\u0651'
HARAKAT = frozenset({FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SUKOON, SHADDA})
SHORT_VOWELS = {FATHA, DAMMA, KASRA}


# ── Swap logic (same as measure_tashkeel.py) ──

def find_internal_diacritics(word):
    """Find swappable internal diacritics in a word.
    Returns list of (index, char, consonant_before, is_first_cons).
    Skips the final diacritic (that's i3rab).
    """
    chars = list(word)
    consonants = [i for i, c in enumerate(chars) if c not in HARAKAT]
    if len(consonants) < 2:
        return []

    results = []
    last_cons_idx = consonants[-1]

    for i, ch in enumerate(chars):
        if ch not in SHORT_VOWELS:
            continue
        cons_idx = None
        for ci in range(i - 1, -1, -1):
            if chars[ci] not in HARAKAT:
                cons_idx = ci
                break
        if cons_idx is None:
            continue
        if cons_idx == last_cons_idx:
            continue
        is_first = (cons_idx == consonants[0])
        results.append((i, ch, chars[cons_idx], is_first))

    return results


def swap_diacritic(word, idx, original, replacement):
    chars = list(word)
    assert chars[idx] == original
    chars[idx] = replacement
    return ''.join(chars)


def pick_swap(original_diac):
    swaps = {
        FATHA: KASRA,
        KASRA: DAMMA,
        DAMMA: FATHA,
    }
    return swaps[original_diac]


# ── TTS generation (same caching as measure_tashkeel.py) ──

async def tts_generate(text: str, voice: str = TTS_VOICE) -> Path:
    """Generate TTS audio, cache by text hash. Returns path to raw f32le PCM."""
    import edge_tts

    key = hashlib.sha256(f"{voice}:{text}".encode()).hexdigest()[:16]
    raw_path = CACHE_DIR / f"{key}.raw"
    if raw_path.exists():
        return raw_path

    mp3_path = CACHE_DIR / f"{key}.mp3"
    comm = edge_tts.Communicate(text, voice)
    await comm.save(str(mp3_path))

    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(mp3_path),
        "-f", "f32le", "-acodec", "pcm_f32le",
        "-ac", "1", "-ar", "16000",
        "-v", "quiet", str(raw_path),
    ], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr.decode()}")
    mp3_path.unlink(missing_ok=True)
    return raw_path


def load_pcm(path: Path) -> torch.Tensor:
    """Load raw f32le PCM file into a torch tensor."""
    audio = np.fromfile(str(path), dtype=np.float32)
    return torch.from_numpy(audio.copy())


# ── Threshold constants from server.py ──

# Batch thresholds
BATCH_I3RAB = 0.08
BATCH_TASHKEEL = 0.12
BATCH_PC_TIER1_DELTA = -4.5
BATCH_PC_TIER1_EFF = -0.7
BATCH_PC_TIER2_DELTA = -2.5
BATCH_PC_TIER2_EFF = -0.3

# Streaming thresholds
STREAM_I3RAB = 0.15
STREAM_TASHKEEL = 0.20
STREAM_PC_TIER1_DELTA = -6.0
STREAM_PC_TIER1_EFF = -0.7
STREAM_PC_TIER2_DELTA = -3.5
STREAM_PC_TIER2_EFF = -0.3


def would_flag(wr, streaming=False):
    """Replicate classify_words logic. Returns (flagged: bool, signal: str|None)."""
    eff = wr["effective_score"]

    # Signal 1: CTC i3rab
    i3rab_t = STREAM_I3RAB if streaming else BATCH_I3RAB
    alt = wr["best_alt_score"]
    if alt > -900 and alt > eff + i3rab_t:
        return True, "S1_i3rab"

    # Signal 2: CTC tashkeel
    tash_t = STREAM_TASHKEEL if streaming else BATCH_TASHKEEL
    tash = wr.get("best_tashkeel_score", -999.0)
    if tash > -900 and tash > eff + tash_t:
        return True, "S2_tashkeel"

    # Signal 3: Per-char diacritic confidence (two-tier)
    if streaming:
        pc1_d, pc1_e = STREAM_PC_TIER1_DELTA, STREAM_PC_TIER1_EFF
        pc2_d, pc2_e = STREAM_PC_TIER2_DELTA, STREAM_PC_TIER2_EFF
    else:
        pc1_d, pc1_e = BATCH_PC_TIER1_DELTA, BATCH_PC_TIER1_EFF
        pc2_d, pc2_e = BATCH_PC_TIER2_DELTA, BATCH_PC_TIER2_EFF
    pc = wr.get("pc_worst_delta", 999.0)
    if (pc < pc1_d and eff > pc1_e) or (pc < pc2_d and eff > pc2_e):
        return True, "S3_perchar"

    # Signal 4: Shadda-position diacritic scoring
    shadda_score = wr.get("best_shadda_score", -999.0)
    shadda_thresh = 0.30 if streaming else 0.25
    if shadda_score > -900 and shadda_score > eff + shadda_thresh:
        return True, "S4_shadda"

    # Signal 5: Greedy internal diacritic mismatch
    greedy_eff_gate = -1.5 if streaming else -0.5
    gdm_count = wr.get("greedy_diac_mismatches", 0)
    if gdm_count >= 1 and eff > greedy_eff_gate:
        return True, "S5_greedy"

    # Signal 6: Greedy final diacritic mismatch + per-char confirmation
    gfm = wr.get("greedy_final_mismatch", False)
    if gfm and pc < -2.0 and eff > -1.0:
        return True, "S6_greedy_final"

    return False, None


DIAC_NAMES = {FATHA: "fatha", DAMMA: "damma", KASRA: "kasra"}


async def main():
    process_all = "--all" in sys.argv

    # Load engine
    from engine import RecitationEngine
    engine = RecitationEngine(str(MODEL_PATH))

    # Load passage
    with open(BASE / "passage.json") as f:
        data = json.load(f)

    passage = next(p for p in data["passages"] if p["id"] == "ajrumiyyah")
    phrases = passage["phrases"]
    full_text = " ".join(phrases)

    if not process_all:
        phrases = phrases[:5]
        print(f"Processing first 5 phrases (use --all for all {len(passage['phrases'])})")
    else:
        print(f"Processing all {len(phrases)} phrases")

    # ── Collect results ──
    all_results = []  # list of dicts per swapped word

    for pi, phrase in enumerate(phrases):
        words = phrase.split()
        print(f"\n{'='*70}")
        print(f"Phrase {pi}: {phrase[:80]}...")
        print(f"{'='*70}")

        if len(words) > 15:
            print(f"  SKIP (too long: {len(words)} words)")
            continue

        for wi, word in enumerate(words):
            internals = find_internal_diacritics(word)
            if not internals:
                continue

            # Pick swap target (prefer non-first-consonant)
            non_first = [d for d in internals if not d[3]]
            target = non_first[0] if non_first else internals[0]
            idx, orig_diac, cons, is_first = target
            new_diac = pick_swap(orig_diac)
            modified_word = swap_diacritic(word, idx, orig_diac, new_diac)

            # Build modified phrase
            mod_words = list(words)
            mod_words[wi] = modified_word
            modified_phrase = " ".join(mod_words)

            # Generate TTS
            raw_path = await tts_generate(modified_phrase)
            waveform = load_pcm(raw_path)

            # Score through engine directly
            word_results, greedy, matched_phrase_idx, match_sim = \
                engine.locate_and_score(waveform, full_text, passage["phrases"])

            # Find the target word in results
            # We need to compute the global word index for phrase pi, word wi
            global_offset = 0
            for pj in range(pi):
                global_offset += len(passage["phrases"][pj].split())
            target_global_idx = global_offset + wi

            target_wr = None
            for wr in word_results:
                if wr["word_idx"] == target_global_idx:
                    target_wr = wr
                    break

            if target_wr is None:
                print(f"  [{pi}] w{wi} {word} -> {modified_word}: NOT FOUND in results "
                      f"(matched phrase {matched_phrase_idx}, sim={match_sim:.2f})")
                all_results.append({
                    "phrase_idx": pi, "word_idx": wi,
                    "word": word, "modified": modified_word,
                    "found": False,
                })
                continue

            eff = target_wr["effective_score"]
            gdm = target_wr.get("greedy_diac_mismatches", 0)
            greedy_seg = target_wr.get("greedy_segment", "")
            tash_score = target_wr.get("best_tashkeel_score", -999.0)
            pc_delta = target_wr.get("pc_worst_delta", 999.0)
            shadda_score = target_wr.get("best_shadda_score", -999.0)
            alt_score = target_wr["best_alt_score"]

            batch_flagged, batch_signal = would_flag(target_wr, streaming=False)
            stream_flagged, stream_signal = would_flag(target_wr, streaming=True)

            swap_desc = f"{cons}:{DIAC_NAMES[orig_diac]}->{DIAC_NAMES[new_diac]}"

            result = {
                "phrase_idx": pi, "word_idx": wi,
                "word": word, "modified": modified_word,
                "swap": swap_desc,
                "found": True,
                "eff": eff,
                "gdm": gdm,
                "greedy_seg": greedy_seg,
                "tash_score": tash_score,
                "alt_score": alt_score,
                "pc_delta": pc_delta,
                "shadda_score": shadda_score,
                "batch_flagged": batch_flagged,
                "batch_signal": batch_signal,
                "stream_flagged": stream_flagged,
                "stream_signal": stream_signal,
            }
            all_results.append(result)

            # Print per-word detail
            flag_b = "FLAGGED" if batch_flagged else "missed"
            flag_s = "FLAGGED" if stream_flagged else "missed"
            print(f"  [{pi}] w{wi} {word} -> {modified_word} ({swap_desc})")
            print(f"       eff={eff:.3f}  gdm={gdm}  tash={tash_score:.3f}  "
                  f"alt={alt_score:.3f}  pc={pc_delta:.2f}  "
                  f"shadda={shadda_score:.3f}")
            print(f"       greedy_seg: {greedy_seg}")
            print(f"       batch: {flag_b} ({batch_signal})  "
                  f"stream: {flag_s} ({stream_signal})")

    # ── Summary ──
    found = [r for r in all_results if r.get("found", False)]
    total = len(found)

    if total == 0:
        print("\nNo swappable words found!")
        return

    print(f"\n{'='*70}")
    print(f"SUMMARY ({total} swapped words)")
    print(f"{'='*70}")

    # Batch vs streaming detection
    batch_detected = sum(1 for r in found if r["batch_flagged"])
    stream_detected = sum(1 for r in found if r["stream_flagged"])
    print(f"  Batch detection:     {batch_detected}/{total} = {batch_detected/total*100:.1f}%")
    print(f"  Streaming detection: {stream_detected}/{total} = {stream_detected/total*100:.1f}%")

    # Signal breakdown (batch)
    print(f"\n  Signal breakdown (batch, flagged words):")
    signal_counts = {}
    for r in found:
        if r["batch_flagged"]:
            sig = r["batch_signal"]
            signal_counts[sig] = signal_counts.get(sig, 0) + 1
    for sig, cnt in sorted(signal_counts.items(), key=lambda x: -x[1]):
        print(f"    {sig}: {cnt}")

    # Signal breakdown (streaming)
    print(f"\n  Signal breakdown (streaming, flagged words):")
    signal_counts = {}
    for r in found:
        if r["stream_flagged"]:
            sig = r["stream_signal"]
            signal_counts[sig] = signal_counts.get(sig, 0) + 1
    for sig, cnt in sorted(signal_counts.items(), key=lambda x: -x[1]):
        print(f"    {sig}: {cnt}")

    # GDM distribution
    gdm_ge1 = sum(1 for r in found if r["gdm"] >= 1)
    gdm_ge2 = sum(1 for r in found if r["gdm"] >= 2)
    print(f"\n  Greedy diacritic mismatches:")
    print(f"    gdm >= 1: {gdm_ge1}/{total} = {gdm_ge1/total*100:.1f}%")
    print(f"    gdm >= 2: {gdm_ge2}/{total} = {gdm_ge2/total*100:.1f}%")

    # Eff distribution
    eff_values = [r["eff"] for r in found]
    print(f"\n  Effective score distribution:")
    print(f"    min={min(eff_values):.3f}  max={max(eff_values):.3f}  "
          f"mean={sum(eff_values)/len(eff_values):.3f}  "
          f"median={sorted(eff_values)[len(eff_values)//2]:.3f}")

    # Eff gate analysis for Signal 5 (greedy diac mismatch)
    print(f"\n  Signal 5 (greedy mismatch) at various eff gates:")
    print(f"  (words with gdm>=1 AND eff > gate)")
    for gate in [-0.3, -0.5, -0.7, -1.0, -1.5, -2.0, -3.0, -999.0]:
        count = sum(1 for r in found if r["gdm"] >= 1 and r["eff"] > gate)
        pct = count / total * 100
        label = "batch=-0.5" if gate == -0.5 else ("stream=-1.5" if gate == -1.5 else "")
        marker = " <-- " + label if label else ""
        print(f"    eff > {gate:6.1f}: {count:3d}/{total} = {pct:5.1f}%{marker}")

    # Words with gdm>=1 but gated out by eff > -0.5
    print(f"\n  Words with gdm>=1 but BLOCKED by batch eff gate (eff <= -0.5):")
    blocked = [r for r in found if r["gdm"] >= 1 and r["eff"] <= -0.5]
    for r in blocked:
        print(f"    [{r['phrase_idx']}] w{r['word_idx']} {r['word']} -> {r['modified']} "
              f"eff={r['eff']:.3f} gdm={r['gdm']} greedy={r['greedy_seg']}")

    # Words with gdm==0 (greedy didn't catch the mismatch)
    print(f"\n  Words with gdm==0 (greedy didn't detect mismatch):")
    no_gdm = [r for r in found if r["gdm"] == 0]
    for r in no_gdm:
        print(f"    [{r['phrase_idx']}] w{r['word_idx']} {r['word']} -> {r['modified']} "
              f"eff={r['eff']:.3f} greedy={r['greedy_seg']}")

    # What signals COULD detect words that batch misses?
    print(f"\n  Words MISSED by batch -- why?")
    missed = [r for r in found if not r["batch_flagged"]]
    for r in missed:
        reasons = []
        if r["gdm"] >= 1 and r["eff"] <= -0.5:
            reasons.append(f"S5: gdm={r['gdm']} but eff={r['eff']:.3f} <= -0.5")
        if r["gdm"] == 0:
            reasons.append(f"S5: gdm=0 (greedy didnt see it)")
        tash = r["tash_score"]
        if tash > -900 and tash <= r["eff"] + BATCH_TASHKEEL:
            reasons.append(f"S2: tash={tash:.3f} <= eff+0.12={r['eff']+BATCH_TASHKEEL:.3f}")
        elif tash <= -900:
            reasons.append(f"S2: tash_score not computed (skipped)")
        alt = r["alt_score"]
        if alt > -900 and alt <= r["eff"] + BATCH_I3RAB:
            pass  # not relevant for tashkeel
        pc = r["pc_delta"]
        if pc >= BATCH_PC_TIER1_DELTA:
            reasons.append(f"S3: pc={pc:.2f} >= {BATCH_PC_TIER1_DELTA}")
        if not reasons:
            reasons.append("no signal triggered")
        print(f"    [{r['phrase_idx']}] w{r['word_idx']} {r['word']} -> {r['modified']}  "
              f"eff={r['eff']:.3f}  " + " | ".join(reasons))


if __name__ == "__main__":
    asyncio.run(main())
