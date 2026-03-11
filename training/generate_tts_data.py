#!/usr/bin/env python3
"""Generate TTS training data from diacritized Arabic text (Tashkeela corpus).

Uses edge-tts (free, multiple Arabic voices) to synthesize diacritized text.
Produces NeMo-format manifest with 16kHz WAV files.
"""

import asyncio
import json
import random
import re
import sys
from pathlib import Path

import edge_tts
import soundfile as sf
import numpy as np

# Arabic voices available in edge-tts
ARABIC_VOICES = [
    "ar-EG-SalmaNeural",   # Egyptian female
    "ar-EG-ShakirNeural",  # Egyptian male
    "ar-SA-HamedNeural",   # Saudi male
    "ar-SA-ZariyahNeural", # Saudi female
    "ar-AE-FatimaNeural",  # UAE female
    "ar-AE-HamdanNeural",  # UAE male
    "ar-KW-FahedNeural",   # Kuwaiti male
    "ar-KW-NouraNeural",   # Kuwaiti female
    "ar-QA-AmalNeural",    # Qatari female
    "ar-QA-MoazNeural",    # Qatari male
]

# Speed variations for more diversity
RATE_VARIATIONS = ["-10%", "+0%", "+10%", "+15%"]


def load_tashkeela(data_dir: Path, max_samples: int = 12000) -> list[str]:
    """Load diacritized Arabic text from Tashkeela dataset."""
    from datasets import load_dataset

    print("Downloading Tashkeela corpus...")
    ds = load_dataset("tashkeela", split="train", trust_remote_code=True)

    sentences = []
    for item in ds:
        text = item.get("text", "")
        if not text:
            continue
        # Split into sentences on period, newline, etc.
        for sent in re.split(r'[.\n؟!،]', text):
            sent = sent.strip()
            # Filter: must have diacritics, reasonable length
            if not sent:
                continue
            has_diac = any("\u064B" <= ch <= "\u0652" for ch in sent)
            word_count = len(sent.split())
            if has_diac and 4 <= word_count <= 25:
                sentences.append(sent)

    # Deduplicate and shuffle
    sentences = list(set(sentences))
    random.shuffle(sentences)
    sentences = sentences[:max_samples]
    print(f"Extracted {len(sentences)} diacritized sentences")
    return sentences


async def synthesize_one(text: str, voice: str, rate: str, output_path: Path) -> float | None:
    """Synthesize one utterance and return duration, or None on failure."""
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        # Save as mp3 first, then convert
        mp3_path = output_path.with_suffix(".mp3")
        await communicate.save(str(mp3_path))

        # Convert to 16kHz WAV
        import subprocess
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp3_path), "-ar", "16000", "-ac", "1",
             "-acodec", "pcm_s16le", str(output_path)],
            capture_output=True, timeout=30,
        )
        mp3_path.unlink(missing_ok=True)

        if result.returncode != 0 or not output_path.exists():
            return None

        info = sf.info(str(output_path))
        if info.duration < 1.0 or info.duration > 30.0:
            output_path.unlink(missing_ok=True)
            return None
        return info.duration
    except Exception as e:
        return None


async def generate_batch(sentences: list[str], wav_dir: Path, batch_start: int,
                         concurrent: int = 5) -> list[dict]:
    """Generate TTS for a batch of sentences with concurrency control."""
    sem = asyncio.Semaphore(concurrent)
    entries = []

    async def process_one(idx: int, text: str):
        async with sem:
            voice = random.choice(ARABIC_VOICES)
            rate = random.choice(RATE_VARIATIONS)
            wav_path = wav_dir / f"tts_{batch_start + idx:06d}.wav"
            duration = await synthesize_one(text, voice, rate, wav_path)
            if duration:
                return {
                    "audio_filepath": str(wav_path),
                    "duration": round(duration, 3),
                    "text": text,
                }
            return None

    tasks = [process_one(i, s) for i, s in enumerate(sentences)]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


def create_speed_perturbations(manifest_path: Path, wav_dir: Path) -> Path:
    """Create 0.9x and 1.1x speed-perturbed copies of all audio."""
    import subprocess

    sp_manifest = manifest_path.parent / "tts_manifest_sp.json"
    entries = []

    with open(manifest_path) as f:
        originals = [json.loads(line) for line in f]

    # Include originals
    entries.extend(originals)

    for speed in [0.9, 1.1]:
        suffix = f"_sp{speed:.1f}"
        for entry in originals:
            src = Path(entry["audio_filepath"])
            dst = wav_dir / f"{src.stem}{suffix}.wav"

            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(src), "-filter:a", f"atempo={speed}",
                 "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le", str(dst)],
                capture_output=True, timeout=30,
            )
            if result.returncode == 0 and dst.exists():
                info = sf.info(str(dst))
                entries.append({
                    "audio_filepath": str(dst),
                    "duration": round(info.duration, 3),
                    "text": entry["text"],
                })

    with open(sp_manifest, "w") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"Speed perturbation: {len(originals)} → {len(entries)} samples")
    return sp_manifest


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--max-samples", type=int, default=10000,
                        help="Max TTS utterances to generate")
    parser.add_argument("--concurrent", type=int, default=8,
                        help="Concurrent TTS requests")
    parser.add_argument("--speed-perturb", action="store_true",
                        help="Generate speed perturbations (0.9x, 1.1x)")
    parser.add_argument("--batch-size", type=int, default=200,
                        help="Process in batches to save progress")
    args = parser.parse_args()

    tts_dir = args.data_dir / "tts"
    wav_dir = tts_dir / "wavs"
    wav_dir.mkdir(parents=True, exist_ok=True)

    # Check for resume
    manifest_path = tts_dir / "tts_manifest.json"
    existing_count = 0
    if manifest_path.exists():
        with open(manifest_path) as f:
            existing_count = sum(1 for _ in f)
        print(f"Resuming: {existing_count} samples already generated")

    # Load text
    sentences = load_tashkeela(args.data_dir, args.max_samples)
    if existing_count > 0:
        sentences = sentences[existing_count:]
    print(f"Generating TTS for {len(sentences)} sentences...")

    # Install ffmpeg if needed
    import subprocess
    subprocess.run(["apt-get", "install", "-y", "-qq", "ffmpeg"],
                   capture_output=True)

    # Generate in batches
    total_generated = existing_count
    total_duration = 0.0
    for batch_start in range(0, len(sentences), args.batch_size):
        batch = sentences[batch_start:batch_start + args.batch_size]
        entries = await generate_batch(batch, wav_dir, total_generated, args.concurrent)

        # Append to manifest
        with open(manifest_path, "a") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
                total_duration += e["duration"]

        total_generated += len(entries)
        hours = total_duration / 3600
        print(f"  Progress: {total_generated} samples ({hours:.1f}h), "
              f"batch {batch_start // args.batch_size + 1}")

    # Final stats
    with open(manifest_path) as f:
        all_entries = [json.loads(line) for line in f]
    total_dur = sum(e["duration"] for e in all_entries) / 3600
    print(f"\nTTS generation complete: {len(all_entries)} samples ({total_dur:.1f}h)")

    # Speed perturbation
    if args.speed_perturb:
        print("\nGenerating speed perturbations...")
        create_speed_perturbations(manifest_path, wav_dir)

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
