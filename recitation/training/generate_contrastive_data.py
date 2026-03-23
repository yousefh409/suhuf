#!/usr/bin/env python3
"""Generate contrastive training data for v3 fine-tuning.

Creates minimal pairs that differ by exactly one diacritic:
  1. I3rab pairs: swap case endings (fatha/damma/kasra) on NON-FINAL words
  2. Tashkeel pairs: swap internal vowels on any word
  3. Shadda pairs: add/remove shadda

All words with swapped diacritics are placed mid-sentence so edge-tts
actually pronounces the difference. Final words get case endings stripped
from labels to avoid teaching the model to hallucinate pausal-form endings.

Output: NeMo manifest with TTS audio files.
"""

import asyncio
import json
import random
import re
import subprocess
import unicodedata
from pathlib import Path

import edge_tts
import soundfile as sf

# Arabic diacritics
FATHA = "\u064E"
DAMMA = "\u064F"
KASRA = "\u0650"
FATHATAN = "\u064B"
DAMMATAN = "\u064C"
KASRATAN = "\u064D"
SUKUN = "\u0652"
SHADDA = "\u0651"

CASE_ENDINGS = [FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SUKUN]
SHORT_VOWELS = [FATHA, DAMMA, KASRA]
ALL_HARAKAT = set("\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652")

ARABIC_VOICES = [
    "ar-EG-SalmaNeural", "ar-EG-ShakirNeural",
    "ar-SA-HamedNeural", "ar-SA-ZariyahNeural",
    "ar-AE-FatimaNeural", "ar-AE-HamdanNeural",
    "ar-KW-FahedNeural", "ar-KW-NouraNeural",
    "ar-QA-AmalNeural", "ar-QA-MoazNeural",
]
RATE_VARIATIONS = ["-10%", "+0%", "+10%", "+15%"]


def strip_harakat(text: str) -> str:
    """Remove all diacritics from text."""
    return "".join(ch for ch in text if ch not in ALL_HARAKAT)


def get_last_haraka(word: str) -> str | None:
    """Get the case ending (last haraka) of a word."""
    # Walk backwards to find last base letter's harakat
    for i in range(len(word) - 1, -1, -1):
        if word[i] in ALL_HARAKAT and word[i] != SHADDA:
            return word[i]
    return None


def replace_last_haraka(word: str, new_haraka: str) -> str:
    """Replace the last vowel diacritic (case ending) of a word."""
    # Find position of last haraka (excluding shadda)
    last_pos = -1
    for i in range(len(word) - 1, -1, -1):
        if word[i] in ALL_HARAKAT and word[i] != SHADDA:
            last_pos = i
            break
    if last_pos == -1:
        return word
    return word[:last_pos] + new_haraka + word[last_pos + 1:]


def strip_last_haraka(word: str) -> str:
    """Remove the case ending from a word (for sentence-final position)."""
    last_pos = -1
    for i in range(len(word) - 1, -1, -1):
        if word[i] in ALL_HARAKAT and word[i] != SHADDA:
            last_pos = i
            break
    if last_pos == -1:
        return word
    return word[:last_pos] + word[last_pos + 1:]


def get_internal_vowels(word: str) -> list[tuple[int, str]]:
    """Get positions and values of internal vowels (not the last one)."""
    vowels = []
    last_vowel_pos = -1
    for i in range(len(word) - 1, -1, -1):
        if word[i] in SHORT_VOWELS:
            if last_vowel_pos == -1:
                last_vowel_pos = i  # skip this one (it's the case ending)
            else:
                vowels.append((i, word[i]))
    return vowels


def swap_internal_vowel(word: str, pos: int, new_vowel: str) -> str:
    """Replace an internal vowel at a specific position."""
    return word[:pos] + new_vowel + word[pos + 1:]


def has_shadda(word: str) -> bool:
    return SHADDA in word


def add_shadda_variant(word: str) -> str | None:
    """Try to add shadda to a doubled-looking consonant, or None if not applicable."""
    # Simple: find a consonant that could plausibly take shadda
    base = strip_harakat(word)
    if len(base) < 3:
        return None
    # Pick a random consonant position (not first, not last)
    consonant_positions = []
    idx = 0
    for i, ch in enumerate(word):
        if ch not in ALL_HARAKAT:
            consonant_positions.append(i)
    if len(consonant_positions) < 3:
        return None
    # Add shadda after a mid consonant
    pos = random.choice(consonant_positions[1:-1])
    # Check if there's already a shadda nearby
    if pos + 1 < len(word) and word[pos + 1] == SHADDA:
        return None
    return word[:pos + 1] + SHADDA + word[pos + 1:]


def remove_shadda(word: str) -> str | None:
    """Remove shadda from a word that has one."""
    if SHADDA not in word:
        return None
    return word.replace(SHADDA, "", 1)


def load_tashkeela_sentences(max_samples: int = 15000) -> list[str]:
    """Load diacritized Arabic sentences from Tashkeela."""
    from datasets import load_dataset
    print("Loading Tashkeela corpus...")
    ds = load_dataset("tashkeela", split="train", trust_remote_code=True)

    sentences = []
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
            # Need at least 5 words so swapped word is never final
            if has_diac and 5 <= len(words) <= 20:
                sentences.append(sent)

    sentences = list(set(sentences))
    random.shuffle(sentences)
    return sentences[:max_samples]


def generate_irab_pairs(sentences: list[str], max_pairs: int = 8000) -> list[dict]:
    """Generate i3rab contrastive pairs: same sentence, different case ending on one word."""
    pairs = []

    for sent in sentences:
        if len(pairs) >= max_pairs:
            break

        words = sent.split()
        if len(words) < 5:
            continue

        # Pick a non-final word (indices 1 to len-2 to avoid first and last)
        candidates = []
        for idx in range(1, len(words) - 1):
            haraka = get_last_haraka(words[idx])
            if haraka and haraka in SHORT_VOWELS:
                candidates.append(idx)

        if not candidates:
            continue

        word_idx = random.choice(candidates)
        original_haraka = get_last_haraka(words[word_idx])
        original_word = words[word_idx]

        # Create variants with other case endings
        for new_haraka in SHORT_VOWELS:
            if new_haraka == original_haraka:
                continue
            new_word = replace_last_haraka(original_word, new_haraka)
            new_words = words.copy()
            new_words[word_idx] = new_word
            # Strip case ending from FINAL word in label (TTS won't pronounce it)
            new_words[-1] = strip_last_haraka(new_words[-1])
            new_sent = " ".join(new_words)

            pairs.append({
                "text": new_sent,
                "type": "irab_wrong",
                "changed_word_idx": word_idx,
                "original_haraka": original_haraka,
                "new_haraka": new_haraka,
            })

        # Also add correct version with final word label fixed
        correct_words = words.copy()
        correct_words[-1] = strip_last_haraka(correct_words[-1])
        pairs.append({
            "text": " ".join(correct_words),
            "type": "irab_correct",
            "changed_word_idx": word_idx,
            "original_haraka": original_haraka,
            "new_haraka": original_haraka,
        })

    random.shuffle(pairs)
    print(f"Generated {len(pairs)} i3rab contrastive pairs")
    return pairs


def generate_tashkeel_pairs(sentences: list[str], max_pairs: int = 8000) -> list[dict]:
    """Generate internal tashkeel pairs: swap an internal vowel."""
    pairs = []

    for sent in sentences:
        if len(pairs) >= max_pairs:
            break

        words = sent.split()
        if len(words) < 5:
            continue

        # Pick a non-final word with internal vowels
        candidates = []
        for idx in range(len(words) - 1):  # exclude final word
            ivowels = get_internal_vowels(words[idx])
            if ivowels:
                candidates.append((idx, ivowels))

        if not candidates:
            continue

        word_idx, ivowels = random.choice(candidates)
        vowel_pos, original_vowel = random.choice(ivowels)

        for new_vowel in SHORT_VOWELS:
            if new_vowel == original_vowel:
                continue
            new_word = swap_internal_vowel(words[word_idx], vowel_pos, new_vowel)
            new_words = words.copy()
            new_words[word_idx] = new_word
            # Strip final word case ending
            new_words[-1] = strip_last_haraka(new_words[-1])

            pairs.append({
                "text": " ".join(new_words),
                "type": "tashkeel_wrong",
                "changed_word_idx": word_idx,
            })

        # Correct version
        correct_words = words.copy()
        correct_words[-1] = strip_last_haraka(correct_words[-1])
        pairs.append({
            "text": " ".join(correct_words),
            "type": "tashkeel_correct",
        })

    random.shuffle(pairs)
    print(f"Generated {len(pairs)} tashkeel contrastive pairs")
    return pairs


def generate_shadda_pairs(sentences: list[str], max_pairs: int = 4000) -> list[dict]:
    """Generate shadda contrastive pairs."""
    pairs = []

    for sent in sentences:
        if len(pairs) >= max_pairs:
            break

        words = sent.split()
        if len(words) < 5:
            continue

        # Find non-final words with shadda
        for idx in range(len(words) - 1):
            if has_shadda(words[idx]):
                # Create version without shadda
                no_shadda = remove_shadda(words[idx])
                if no_shadda and no_shadda != words[idx]:
                    new_words = words.copy()
                    new_words[idx] = no_shadda
                    new_words[-1] = strip_last_haraka(new_words[-1])
                    pairs.append({
                        "text": " ".join(new_words),
                        "type": "shadda_removed",
                        "changed_word_idx": idx,
                    })

                    # Also add correct with fixed final
                    correct_words = words.copy()
                    correct_words[-1] = strip_last_haraka(correct_words[-1])
                    pairs.append({
                        "text": " ".join(correct_words),
                        "type": "shadda_correct",
                    })
                    break

    random.shuffle(pairs)
    print(f"Generated {len(pairs)} shadda contrastive pairs")
    return pairs


def fix_v2_tts_labels(tts_manifest: Path, output_manifest: Path):
    """Fix v2 TTS labels: strip case endings from final words.

    The TTS doesn't pronounce case endings on final words (pausal form),
    so the label shouldn't have them either.
    """
    entries = []
    fixed = 0
    with open(tts_manifest) as f:
        for line in f:
            entry = json.loads(line)
            words = entry["text"].split()
            if words:
                original_last = words[-1]
                words[-1] = strip_last_haraka(words[-1])
                if words[-1] != original_last:
                    fixed += 1
                entry["text"] = " ".join(words)
            entries.append(entry)

    with open(output_manifest, "w") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"Fixed {fixed}/{len(entries)} final-word labels in TTS data")
    return entries


async def synthesize_one(text: str, voice: str, rate: str, output_path: Path) -> float | None:
    """Synthesize one utterance via edge-tts, return duration or None."""
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
                except:
                    pass

            duration = await synthesize_one(pair["text"], voice, rate, wav_path)
            if duration:
                return {
                    "audio_filepath": str(wav_path),
                    "duration": round(duration, 3),
                    "text": pair["text"],
                }
            return None

    # Process in batches
    batch_size = 200
    for batch_start in range(0, len(pairs), batch_size):
        batch = pairs[batch_start:batch_start + batch_size]
        tasks = [process_one(batch_start + i, p) for i, p in enumerate(batch)]
        results = await asyncio.gather(*tasks)
        good = [r for r in results if r is not None]
        manifest_entries.extend(good)
        print(f"  {prefix}: {len(manifest_entries)}/{batch_start + len(batch)} synthesized")

    return manifest_entries


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--max-irab-pairs", type=int, default=8000)
    parser.add_argument("--max-tashkeel-pairs", type=int, default=8000)
    parser.add_argument("--max-shadda-pairs", type=int, default=4000)
    parser.add_argument("--max-sentences", type=int, default=15000)
    parser.add_argument("--concurrent", type=int, default=8)
    parser.add_argument("--fix-v2-labels", action="store_true",
                        help="Also fix sentence-final labels in existing v2 TTS data")
    args = parser.parse_args()

    contrastive_dir = args.data_dir / "contrastive"
    wav_dir = contrastive_dir / "wavs"
    wav_dir.mkdir(parents=True, exist_ok=True)

    # Fix v2 TTS labels if requested
    if args.fix_v2_labels:
        v2_manifest = args.data_dir / "tts" / "tts_manifest.json"
        if v2_manifest.exists():
            fixed_manifest = args.data_dir / "tts" / "tts_manifest_fixed.json"
            fix_v2_tts_labels(v2_manifest, fixed_manifest)

    # Load sentences
    sentences = load_tashkeela_sentences(args.max_sentences)
    print(f"Loaded {len(sentences)} sentences from Tashkeela\n")

    # Split sentences for different pair types (avoid overlap)
    n = len(sentences)
    irab_sents = sentences[:n // 3]
    tashkeel_sents = sentences[n // 3: 2 * n // 3]
    shadda_sents = sentences[2 * n // 3:]

    # Generate pairs
    irab_pairs = generate_irab_pairs(irab_sents, args.max_irab_pairs)
    tashkeel_pairs = generate_tashkeel_pairs(tashkeel_sents, args.max_tashkeel_pairs)
    shadda_pairs = generate_shadda_pairs(shadda_sents, args.max_shadda_pairs)

    # Synthesize
    print("\nSynthesizing i3rab pairs...")
    irab_entries = await synthesize_pairs(irab_pairs, wav_dir, "irab", args.concurrent)

    print("\nSynthesizing tashkeel pairs...")
    tashkeel_entries = await synthesize_pairs(tashkeel_pairs, wav_dir, "tashkeel", args.concurrent)

    print("\nSynthesizing shadda pairs...")
    shadda_entries = await synthesize_pairs(shadda_pairs, wav_dir, "shadda", args.concurrent)

    # Write manifests
    all_entries = irab_entries + tashkeel_entries + shadda_entries
    random.shuffle(all_entries)

    manifest_path = contrastive_dir / "contrastive_manifest.json"
    with open(manifest_path, "w") as f:
        for e in all_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    total_dur = sum(e["duration"] for e in all_entries) / 3600
    print(f"\nContrastive data generation complete:")
    print(f"  I3rab pairs:    {len(irab_entries)}")
    print(f"  Tashkeel pairs: {len(tashkeel_entries)}")
    print(f"  Shadda pairs:   {len(shadda_entries)}")
    print(f"  Total:          {len(all_entries)} samples ({total_dur:.1f}h)")
    print(f"  Manifest:       {manifest_path}")


if __name__ == "__main__":
    asyncio.run(main())
