#!/usr/bin/env python3
"""Generate v4 contrastive training data targeting fatha discrimination.

Eval analysis (200-sample, tashkeel-on) revealed:
  - 53 ctc_wrong misses total. Fatha audio is the hardest to detect:
    audio=fatha, label=damma: 18 misses (worst)
    audio=fatha, label=kasra: 12 misses (2nd worst)
  - 7 high-frequency function words account for 30/53 misses (57%):
    عَلَى(5x), وَلَا(4x), وَإِنْ(4x), صَلَّى(3x), إذَا(2x), لَهَا(2x), وَإِذَا(2x)
  - Post-shadda fatha→damma confusion: صَلَّى(3x), اللَّهُ(1x), أَنَّهُ(1x)
  - kasra↔damma is the strongest distinction (only 3 misses combined)

Strategy:
  1. Oversample ClArTTS entries containing high-frequency function words
     with fatha (عَلَى, هَذَا, etc.) and post-shadda fatha positions
  2. Generate TTS contrastive pairs weighted toward fatha confusion patterns
  3. Optional quality gate using v3 model to verify TTS pronunciation

Usage:
    # ClArTTS-only (no TTS, fast)
    python training/generate_v4_contrastive.py --clartts-only

    # Full pipeline with TTS
    python training/generate_v4_contrastive.py --data-dir data

    # With quality gate (requires PCD model)
    python training/generate_v4_contrastive.py --quality-gate
"""

import argparse
import asyncio
import json
import random
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

# Arabic diacritics
FATHA = "\u064E"
DAMMA = "\u064F"
KASRA = "\u0650"
FATHATAN = "\u064B"
DAMMATAN = "\u064C"
KASRATAN = "\u064D"
SUKUN = "\u0652"
SHADDA = "\u0651"

SHORT_VOWELS = [FATHA, DAMMA, KASRA]
ALL_HARAKAT = set("\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652")

VOWEL_NAMES = {FATHA: "fatha", DAMMA: "damma", KASRA: "kasra"}

ARABIC_VOICES = [
    "ar-EG-SalmaNeural", "ar-EG-ShakirNeural",
    "ar-SA-HamedNeural", "ar-SA-ZariyahNeural",
    "ar-AE-FatimaNeural", "ar-AE-HamdanNeural",
    "ar-KW-FahedNeural", "ar-KW-NouraNeural",
    "ar-QA-AmalNeural", "ar-QA-MoazNeural",
]
RATE_VARIATIONS = ["-10%", "+0%", "+10%", "+15%"]

# High-frequency function words that dominate ctc_wrong misses.
# These account for 30/53 fixable misses (57%).
# Stripped bases (no harakat) for matching.
HARD_FUNCTION_WORDS = {
    "على", "ولا", "لا", "وإن", "إن",
    "صلى", "إذا", "وإذا", "لها", "بها",
    "هذا", "فهذا", "والا", "فلم", "لم",
    "وقد", "فقد", "كان", "قال", "وأن",
    "أن", "الله", "وسلم", "تعالى",
}


def strip_harakat(text: str) -> str:
    return "".join(ch for ch in text if ch not in ALL_HARAKAT)


def strip_last_haraka(word: str) -> str:
    """Remove the case ending from a word (for sentence-final position)."""
    for i in range(len(word) - 1, -1, -1):
        if word[i] in ALL_HARAKAT and word[i] != SHADDA:
            return word[:i] + word[i + 1:]
    return word


def get_internal_vowel_positions(word: str) -> list[tuple[int, str]]:
    """Get (char_index, vowel) for internal vowel positions.

    Returns positions of short vowels that are NOT the case ending
    (not on the last base character).
    """
    base_chars = [(i, ch) for i, ch in enumerate(word) if ch not in ALL_HARAKAT]
    if len(base_chars) < 2:
        return []

    positions = []
    # Exclude the last base character (case ending position)
    for bi in range(len(base_chars) - 1):
        char_pos = base_chars[bi][0]
        # Look for vowel marks after this base character
        for j in range(char_pos + 1, len(word)):
            if word[j] == SHADDA:
                continue  # skip shadda, look for vowel after it
            if word[j] in {FATHA, DAMMA, KASRA}:
                positions.append((j, word[j]))
                break
            if word[j] not in ALL_HARAKAT:
                break  # next base char, no vowel found

    return positions


# ── ClArTTS-based contrastive generation ────────────────────────────


def analyze_clartts_vowel_balance(manifest_path: Path) -> dict:
    """Analyze fatha/damma/kasra distribution in ClArTTS training data."""
    counts = Counter()
    with open(manifest_path) as f:
        for line in f:
            entry = json.loads(line)
            text = entry["text"]
            for ch in text:
                if ch in VOWEL_NAMES:
                    counts[VOWEL_NAMES[ch]] += 1

    total = sum(counts.values())
    print(f"\nClArTTS vowel distribution:")
    for v in ("fatha", "damma", "kasra"):
        n = counts[v]
        pct = n / total * 100 if total > 0 else 0
        print(f"  {v:8s}: {n:6d} ({pct:.1f}%)")
    print(f"  total:   {total}")
    return dict(counts)


def generate_clartts_balanced_copies(manifest_path: Path, max_copies: int = 2000,
                                      seed: int = 42) -> list[dict]:
    """Oversample ClArTTS entries containing hard-to-discriminate patterns.

    Scoring prioritizes (based on eval_recall analysis):
    1. Sentences with hard function words (عَلَى, وَلَا, وَإِنْ, etc.)
    2. Post-shadda fatha positions (صَلَّى, اللَّهُ, etc.)
    3. General fatha positions (fatha audio is hardest to detect)
    """
    rng = random.Random(seed)

    entries = []
    with open(manifest_path) as f:
        for line in f:
            entries.append(json.loads(line))

    scored_entries = []
    for entry in entries:
        text = entry["text"]
        words = text.split()
        score = 0

        # Check for hard function words (biggest lever — 57% of misses)
        for word in words:
            base = strip_harakat(word)
            if base in HARD_FUNCTION_WORDS:
                score += 5

        # Post-shadda fatha positions
        for i, ch in enumerate(text):
            if ch == FATHA and i > 0 and text[i - 1] == SHADDA:
                score += 4

        # General fatha — broader coverage
        fatha_count = text.count(FATHA)
        score += min(fatha_count, 5)  # cap contribution

        if score > 0:
            scored_entries.append((score, entry))

    scored_entries.sort(key=lambda x: x[0], reverse=True)
    selected = [e for _, e in scored_entries[:max_copies]]

    # Show what we selected
    func_word_count = 0
    shadda_fatha_count = 0
    for e in selected:
        text = e["text"]
        for w in text.split():
            if strip_harakat(w) in HARD_FUNCTION_WORDS:
                func_word_count += 1
        for i, ch in enumerate(text):
            if ch == FATHA and i > 0 and text[i - 1] == SHADDA:
                shadda_fatha_count += 1

    print(f"Selected {len(selected)} entries for oversampling")
    print(f"  Function word occurrences: {func_word_count}")
    print(f"  Post-shadda fatha positions: {shadda_fatha_count}")
    return selected


def generate_fatha_damma_swapped_labels(manifest_path: Path,
                                         max_pairs: int = 500,
                                         seed: int = 42) -> tuple[list[dict], list[dict]]:
    """Generate pairs where we swap fatha↔damma in labels.

    Returns (correct_entries, swapped_entries) — both use the SAME audio.
    The correct entries have the original (correct) labels.
    The swapped entries have fatha↔damma swapped on one word.

    For CTC training: use ONLY the correct entries (not swapped — wrong labels
    would confuse CTC). The swapped entries are for analysis/eval only.

    The real value: correct entries over-represent words with clear fatha/damma
    distinctions, giving the model more exposure to these patterns.
    """
    rng = random.Random(seed)

    entries = []
    with open(manifest_path) as f:
        for line in f:
            entries.append(json.loads(line))

    correct_copies = []
    swapped_copies = []  # for eval only

    rng.shuffle(entries)

    for entry in entries:
        if len(correct_copies) >= max_pairs:
            break

        text = entry["text"]
        words = text.split()
        if len(words) < 3:
            continue

        # Find non-final words with internal fatha or damma
        candidates = []
        for wi in range(len(words) - 1):  # exclude final word
            positions = get_internal_vowel_positions(words[wi])
            fd_positions = [(pos, vowel) for pos, vowel in positions
                           if vowel in (FATHA, DAMMA)]
            if fd_positions:
                candidates.append((wi, fd_positions))

        if not candidates:
            continue

        # Pick a word and position to highlight
        wi, fd_positions = rng.choice(candidates)
        pos, orig_vowel = rng.choice(fd_positions)
        swap_vowel = DAMMA if orig_vowel == FATHA else FATHA

        # Create swapped version (label only)
        swapped_word = list(words[wi])
        swapped_word[pos] = swap_vowel
        swapped_word = "".join(swapped_word)

        swapped_words = list(words)
        swapped_words[wi] = swapped_word

        correct_copies.append({
            "audio_filepath": entry["audio_filepath"],
            "duration": entry["duration"],
            "text": entry["text"],
            "meta": f"v4_fd_correct_{VOWEL_NAMES[orig_vowel]}",
        })

        swapped_copies.append({
            "audio_filepath": entry["audio_filepath"],
            "duration": entry["duration"],
            "text": " ".join(swapped_words),
            "meta": f"v4_fd_swapped_{VOWEL_NAMES[orig_vowel]}→{VOWEL_NAMES[swap_vowel]}",
        })

    print(f"Generated {len(correct_copies)} fatha↔damma highlighted pairs from ClArTTS")
    return correct_copies, swapped_copies


# ── TTS-based contrastive generation ────────────────────────────────


def load_tashkeela_sentences(max_samples: int = 10000,
                             clartts_manifest: Path | None = None) -> list[str]:
    """Load diacritized Arabic sentences from ClArTTS manifest or Tashkeela."""
    sentences = []

    # Prefer ClArTTS manifest (available on RunPod, high-quality diacritization)
    if clartts_manifest and clartts_manifest.exists():
        print(f"Loading sentences from ClArTTS manifest: {clartts_manifest}")
        with open(clartts_manifest) as f:
            for line in f:
                entry = json.loads(line)
                text = entry.get("text", "").strip()
                if not text:
                    continue
                has_diac = any("\u064B" <= ch <= "\u0652" for ch in text)
                words = text.split()
                if has_diac and 5 <= len(words) <= 20:
                    sentences.append(text)
        print(f"  Loaded {len(sentences)} sentences from ClArTTS")
    else:
        # Fallback: try Tashkeela from HuggingFace
        try:
            from datasets import load_dataset
            print("Loading Tashkeela corpus...")
            ds = load_dataset("tashkeela", split="train")

            for item in ds:
                text = item.get("text", "")
                if not text:
                    continue
                for sent in re.split(r'[.\n؟!]', text):
                    sent = sent.strip()
                    if not sent:
                        continue
                    has_diac = any("\u064B" <= ch <= "\u0652" for ch in sent)
                    words = sent.split()
                    if has_diac and 5 <= len(words) <= 20:
                        sentences.append(sent)
        except Exception as e:
            print(f"WARNING: Could not load Tashkeela: {e}")
            print("Provide --data-dir with ClArTTS manifest for TTS generation")

    sentences = list(set(sentences))
    random.shuffle(sentences)
    return sentences[:max_samples]


def generate_targeted_vowel_pairs(sentences: list[str],
                                   max_pairs: int = 4000,
                                   seed: int = 42) -> list[dict]:
    """Generate TTS contrastive pairs targeting fatha discrimination.

    Eval analysis shows the model's CTC weaknesses (ctc_wrong misses):
      audio=fatha, label=damma: 18 misses (34%)
      audio=fatha, label=kasra: 12 misses (23%)
      audio=kasra, label=fatha:  7 misses (13%)
      audio=damma, label=fatha:  6 misses (11%)
      audio=damma, label=kasra:  5 misses (9%)
      audio=kasra, label=damma:  2 misses (4%)

    Strategy:
      - 40% fatha→damma pairs (biggest gap)
      - 25% fatha→kasra pairs (2nd biggest gap)
      - 15% kasra→fatha + damma→fatha pairs
      - 10% damma→kasra pairs
      - 10% kasra→damma pairs (model already good here)
      - Weight toward function words and post-shadda positions
    """
    rng = random.Random(seed)
    pairs = []

    for sent in sentences:
        if len(pairs) >= max_pairs:
            break

        words = sent.split()
        if len(words) < 5:
            continue

        # Find non-final words with internal vowels
        candidates = []
        for wi in range(len(words) - 1):
            word = words[wi]
            base = strip_harakat(word)
            positions = get_internal_vowel_positions(word)
            if positions:
                for pos, vowel in positions:
                    weight = 1
                    # Hard function words: 6x weight
                    if base in HARD_FUNCTION_WORDS:
                        weight = 6
                    # Post-shadda: 5x weight
                    elif pos > 0 and word[pos - 1] == SHADDA:
                        weight = 5
                    # First vowel in word: 3x weight
                    elif pos < 3:
                        weight = 3
                    candidates.append((wi, pos, vowel, weight))

        if not candidates:
            continue

        # Weighted random selection
        weights = [w for _, _, _, w in candidates]
        total_weight = sum(weights)
        probs = [w / total_weight for w in weights]
        idx = rng.choices(range(len(candidates)), weights=probs, k=1)[0]
        wi, vowel_pos, orig_vowel, _ = candidates[idx]

        # Choose swap vowel based on actual confusion patterns
        if orig_vowel == FATHA:
            # Fatha is hardest — 40% damma, 25% kasra (matches eval ratios)
            swap_vowel = DAMMA if rng.random() < 0.62 else KASRA
        elif orig_vowel == DAMMA:
            # 55% fatha, 45% kasra
            swap_vowel = FATHA if rng.random() < 0.55 else KASRA
        else:  # kasra
            # 70% fatha (bigger gap), 30% damma
            swap_vowel = FATHA if rng.random() < 0.70 else DAMMA

        # Create swapped sentence
        swapped_word = list(words[wi])
        swapped_word[vowel_pos] = swap_vowel
        swapped_word = "".join(swapped_word)

        new_words = list(words)
        new_words[wi] = swapped_word
        # Strip final word case ending (TTS won't pronounce it)
        new_words[-1] = strip_last_haraka(new_words[-1])
        swapped_sent = " ".join(new_words)

        pairs.append({
            "text": swapped_sent,
            "type": f"v4_tashkeel_{VOWEL_NAMES[orig_vowel]}→{VOWEL_NAMES[swap_vowel]}",
            "changed_word_idx": wi,
            "orig_vowel": VOWEL_NAMES[orig_vowel],
            "swap_vowel": VOWEL_NAMES[swap_vowel],
        })

        # Also add correct version with fixed final
        correct_words = list(words)
        correct_words[-1] = strip_last_haraka(correct_words[-1])
        pairs.append({
            "text": " ".join(correct_words),
            "type": "v4_tashkeel_correct",
        })

    # Also generate i3rab contrastive pairs (same as v3 but fewer)
    irab_pairs = generate_irab_pairs(sentences[len(sentences)//2:], max_pairs=max_pairs // 4)
    pairs.extend(irab_pairs)

    rng.shuffle(pairs)
    print(f"Generated {len(pairs)} v4 targeted vowel pairs")

    # Show distribution
    type_counts = Counter(p.get("type", "?").split("_")[2] if "tashkeel" in p.get("type", "") else p.get("type", "?")
                         for p in pairs)
    for t, c in type_counts.most_common():
        print(f"  {t}: {c}")

    return pairs


def generate_irab_pairs(sentences: list[str], max_pairs: int = 1000) -> list[dict]:
    """Generate i3rab contrastive pairs (same as v3, focused on fatha↔damma)."""
    rng = random.Random(99)
    pairs = []

    for sent in sentences:
        if len(pairs) >= max_pairs:
            break

        words = sent.split()
        if len(words) < 5:
            continue

        candidates = []
        for idx in range(1, len(words) - 1):
            # Get last haraka
            for i in range(len(words[idx]) - 1, -1, -1):
                if words[idx][i] in ALL_HARAKAT and words[idx][i] != SHADDA:
                    if words[idx][i] in {FATHA, DAMMA, KASRA}:
                        candidates.append((idx, words[idx][i]))
                    break

        if not candidates:
            continue

        word_idx, orig_haraka = rng.choice(candidates)

        # Bias toward fatha↔damma swaps
        if orig_haraka == FATHA:
            target = DAMMA if rng.random() < 0.7 else KASRA
        elif orig_haraka == DAMMA:
            target = FATHA if rng.random() < 0.7 else KASRA
        else:
            target = rng.choice([FATHA, DAMMA])

        # Swap the last haraka
        word = words[word_idx]
        for i in range(len(word) - 1, -1, -1):
            if word[i] == orig_haraka:
                word = word[:i] + target + word[i + 1:]
                break

        new_words = list(words)
        new_words[word_idx] = word
        new_words[-1] = strip_last_haraka(new_words[-1])

        pairs.append({
            "text": " ".join(new_words),
            "type": "v4_irab_wrong",
            "changed_word_idx": word_idx,
        })

        # Correct version
        correct_words = list(words)
        correct_words[-1] = strip_last_haraka(correct_words[-1])
        pairs.append({
            "text": " ".join(correct_words),
            "type": "v4_irab_correct",
        })

    print(f"Generated {len(pairs)} i3rab pairs")
    return pairs


async def synthesize_one(text: str, voice: str, rate: str, output_path: Path) -> float | None:
    """Synthesize one utterance via edge-tts, return duration or None."""
    import edge_tts
    import soundfile as sf
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        mp3_path = output_path.with_suffix(".mp3")
        await communicate.save(str(mp3_path))

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "16000", "-ac", "1",
             "-acodec", "pcm_s16le", str(output_path)],
            capture_output=True, timeout=30,
        )
        mp3_path.unlink(missing_ok=True)

        if result.returncode != 0 or not output_path.exists():
            return None
        import soundfile as sf
        info = sf.info(str(output_path))
        if info.duration < 0.5 or info.duration > 30.0:
            output_path.unlink(missing_ok=True)
            return None
        return info.duration
    except Exception:
        return None


async def synthesize_pairs(pairs: list[dict], wav_dir: Path, prefix: str,
                            concurrent: int = 8) -> list[dict]:
    """Synthesize all pairs via edge-tts with concurrency control."""
    import soundfile as sf
    sem = asyncio.Semaphore(concurrent)
    manifest_entries = []

    async def process_one(idx: int, pair: dict):
        async with sem:
            voice = random.choice(ARABIC_VOICES)
            rate = random.choice(RATE_VARIATIONS)
            wav_path = wav_dir / f"{prefix}_{idx:06d}.wav"

            if wav_path.exists():
                try:
                    info = sf.info(str(wav_path))
                    return {
                        "audio_filepath": str(wav_path),
                        "duration": round(info.duration, 3),
                        "text": pair["text"],
                    }
                except Exception:
                    pass

            duration = await synthesize_one(pair["text"], voice, rate, wav_path)
            if duration:
                return {
                    "audio_filepath": str(wav_path),
                    "duration": round(duration, 3),
                    "text": pair["text"],
                }
            return None

    batch_size = 200
    for batch_start in range(0, len(pairs), batch_size):
        batch = pairs[batch_start:batch_start + batch_size]
        tasks = [process_one(batch_start + i, p) for i, p in enumerate(batch)]
        results = await asyncio.gather(*tasks)
        good = [r for r in results if r is not None]
        manifest_entries.extend(good)
        print(f"  {prefix}: {len(manifest_entries)}/{batch_start + len(batch)} synthesized")

    return manifest_entries


# ── Quality gate ────────────────────────────────────────────────────


def quality_gate_filter(manifest_entries: list[dict], model_path: str) -> list[dict]:
    """Filter TTS entries using PCD model to verify vowel pronunciation.

    Transcribes each audio with the PCD model and checks if the
    diacritics in the transcription match the intended label.
    Rejects entries where the TTS didn't actually pronounce the
    intended vowel.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from i3rab.pcd_transcriber import PCDTranscriber
    import soundfile as sf

    print(f"\nQuality gate: verifying {len(manifest_entries)} TTS entries...")
    pcd = PCDTranscriber(model_path)

    passed = []
    rejected = 0

    for entry in manifest_entries:
        try:
            audio, sr = sf.read(entry["audio_filepath"], dtype="float32")
            if sr != 16000:
                continue

            # Transcribe
            log_probs, encoded_len, _ = pcd.encode(audio)
            decoded = pcd.greedy_decode(log_probs, encoded_len)
            if not decoded:
                rejected += 1
                continue

            # Check if transcription has diacritics matching the label
            label_text = entry["text"]
            # Simple check: do the short vowels in the decoded text
            # roughly match the label?
            label_vowels = [ch for ch in label_text if ch in {FATHA, DAMMA, KASRA}]
            dec_vowels = [ch for ch in decoded if ch in {FATHA, DAMMA, KASRA}]

            if not label_vowels or not dec_vowels:
                rejected += 1
                continue

            # Calculate vowel match rate
            min_len = min(len(label_vowels), len(dec_vowels))
            matches = sum(1 for a, b in zip(label_vowels[:min_len], dec_vowels[:min_len])
                         if a == b)
            match_rate = matches / min_len if min_len > 0 else 0

            if match_rate >= 0.6:  # at least 60% of vowels match
                passed.append(entry)
            else:
                rejected += 1

        except Exception:
            rejected += 1

    print(f"  Quality gate: {len(passed)} passed, {rejected} rejected")
    return passed


# ── Main ────────────────────────────────────────────────────────────


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--clartts-only", action="store_true",
                        help="Only generate ClArTTS-based pairs (no TTS)")
    parser.add_argument("--max-clartts-pairs", type=int, default=500)
    parser.add_argument("--max-tts-pairs", type=int, default=4000)
    parser.add_argument("--max-sentences", type=int, default=10000)
    parser.add_argument("--concurrent", type=int, default=8)
    parser.add_argument("--quality-gate", action="store_true",
                        help="Filter TTS entries using PCD model")
    parser.add_argument("--model", type=str, default="models/pcd_clartts_v3.nemo",
                        help="PCD model path for quality gate")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    v4_dir = args.data_dir / "contrastive_v4"
    v4_dir.mkdir(parents=True, exist_ok=True)

    all_entries = []

    # ── 1. ClArTTS-based: analyze vowel balance ────────────────────
    clartts_manifest = args.data_dir / "clartts" / "train_manifest.json"
    if clartts_manifest.exists():
        analyze_clartts_vowel_balance(clartts_manifest)

        # Generate oversampled fatha entries from ClArTTS
        oversampled = generate_clartts_balanced_copies(
            clartts_manifest, max_copies=args.max_clartts_pairs, seed=args.seed
        )
        all_entries.extend(oversampled)

        # Generate fatha↔damma highlighted pairs (correct labels, same audio)
        correct_pairs, swapped_pairs = generate_fatha_damma_swapped_labels(
            clartts_manifest, max_pairs=args.max_clartts_pairs, seed=args.seed
        )
        all_entries.extend(correct_pairs)

        # Save swapped pairs for analysis (NOT for CTC training)
        analysis_path = v4_dir / "fd_swapped_analysis.json"
        with open(analysis_path, "w") as f:
            for e in swapped_pairs:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"  Saved {len(swapped_pairs)} swapped pairs for analysis to {analysis_path}")
    else:
        print(f"WARNING: ClArTTS manifest not found at {clartts_manifest}")

    # ── 2. TTS-based contrastive pairs ──────────────────────────────
    if not args.clartts_only:
        sentences = load_tashkeela_sentences(args.max_sentences,
                                                    clartts_manifest=clartts_manifest)
        print(f"Loaded {len(sentences)} sentences\n")

        tts_pairs = generate_targeted_vowel_pairs(
            sentences, max_pairs=args.max_tts_pairs, seed=args.seed
        )

        wav_dir = v4_dir / "wavs"
        wav_dir.mkdir(parents=True, exist_ok=True)

        print("\nSynthesizing v4 contrastive pairs...")
        tts_entries = await synthesize_pairs(tts_pairs, wav_dir, "v4", args.concurrent)

        # Quality gate
        if args.quality_gate and tts_entries:
            tts_entries = quality_gate_filter(tts_entries, args.model)

        all_entries.extend(tts_entries)

    # ── 3. Write manifest ───────────────────────────────────────────
    random.shuffle(all_entries)

    # Remove meta field before writing (used internally)
    for e in all_entries:
        e.pop("meta", None)

    manifest_path = v4_dir / "contrastive_v4_manifest.json"
    with open(manifest_path, "w") as f:
        for e in all_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    total_dur = sum(e["duration"] for e in all_entries) / 3600

    print(f"\n{'='*60}")
    print(f"v4 contrastive data generation complete:")
    print(f"  Total:     {len(all_entries)} samples ({total_dur:.1f}h)")
    print(f"  Manifest:  {manifest_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
