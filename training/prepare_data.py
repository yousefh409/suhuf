#!/usr/bin/env python3
"""Prepare ClArTTS + noise data for NeMo ASR fine-tuning.

Downloads:
  1. ClArTTS (12h diacritized Classical Arabic) from HuggingFace
  2. MUSAN noise corpus (for noise augmentation)

Outputs:
  data/clartts/train_manifest.json   — NeMo manifest for training
  data/clartts/test_manifest.json    — NeMo manifest for validation
  data/clartts/wavs/                 — Resampled 16kHz WAV files
  data/musan/                        — Noise files for augmentation
  data/musan/noise_manifest.json     — NeMo manifest for noise files

NeMo manifest format:
  {"audio_filepath": "path/to/audio.wav", "duration": 3.5, "text": "diacritized text"}
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf


def prepare_clartts(output_dir: Path, max_samples: int = 0):
    """Download ClArTTS and convert to NeMo manifest format."""
    from datasets import load_dataset

    wavs_dir = output_dir / "clartts" / "wavs"
    wavs_dir.mkdir(parents=True, exist_ok=True)

    print("Downloading ClArTTS from HuggingFace...")
    dataset = load_dataset("MBZUAI/ClArTTS")

    target_sr = 16000

    for split in ["train", "test"]:
        ds = dataset[split]
        if max_samples > 0 and split == "train":
            ds = ds.select(range(min(max_samples, len(ds))))

        manifest_path = output_dir / "clartts" / f"{split}_manifest.json"
        entries = []
        skipped = 0

        print(f"\nProcessing {split} split ({len(ds)} samples)...")

        for i, sample in enumerate(ds):
            text = sample["text"].strip()
            if not text:
                skipped += 1
                continue

            # Check if text has diacritics
            has_harakat = any(
                "\u064B" <= ch <= "\u0652" for ch in text
            )
            if not has_harakat:
                skipped += 1
                continue

            # Get audio
            audio_data = np.array(sample["audio"], dtype=np.float32)
            orig_sr = sample["sampling_rate"]

            # Resample to 16kHz if needed
            if orig_sr != target_sr:
                from scipy.signal import resample as scipy_resample
                num_samples = int(len(audio_data) * target_sr / orig_sr)
                audio_data = scipy_resample(audio_data, num_samples).astype(np.float32)

            # Normalize
            peak = np.abs(audio_data).max()
            if peak > 0:
                audio_data = audio_data / peak * 0.95

            duration = len(audio_data) / target_sr

            # Skip very short or very long clips
            if duration < 0.5 or duration > 20.0:
                skipped += 1
                continue

            # Save WAV
            filename = f"clartts_{split}_{i:05d}.wav"
            wav_path = wavs_dir / filename
            sf.write(str(wav_path), audio_data, target_sr)

            entries.append({
                "audio_filepath": str(wav_path.resolve()),
                "duration": round(duration, 3),
                "text": text,
            })

            if (i + 1) % 500 == 0:
                print(f"  {i + 1}/{len(ds)} processed...")

        # Write manifest
        with open(manifest_path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        total_hours = sum(e["duration"] for e in entries) / 3600
        print(f"  {split}: {len(entries)} samples ({total_hours:.1f}h), skipped {skipped}")
        print(f"  Manifest: {manifest_path}")


def prepare_musan(output_dir: Path):
    """Download MUSAN noise corpus for augmentation.

    MUSAN contains:
      - noise/   — ambient noise, technical noise (930 files)
      - speech/  — speech from various sources (used as babble noise)
      - music/   — music recordings
    """
    musan_dir = output_dir / "musan"

    if (musan_dir / "noise").exists():
        print("MUSAN already downloaded, skipping.")
        return

    musan_dir.mkdir(parents=True, exist_ok=True)

    print("\nDownloading MUSAN noise corpus...")
    print("  (This is ~11GB, may take a while)")

    import subprocess
    # Download from OpenSLR
    url = "https://www.openslr.org/resources/17/musan.tar.gz"
    tar_path = musan_dir / "musan.tar.gz"

    subprocess.run(
        ["wget", "-q", "--show-progress", "-O", str(tar_path), url],
        check=True,
    )

    print("Extracting...")
    subprocess.run(
        ["tar", "-xzf", str(tar_path), "-C", str(musan_dir), "--strip-components=1"],
        check=True,
    )
    tar_path.unlink()  # Remove tar after extraction

    # Create noise manifest for NeMo
    noise_manifest_path = musan_dir / "noise_manifest.json"
    entries = []

    for wav_path in sorted(musan_dir.rglob("*.wav")):
        try:
            info = sf.info(str(wav_path))
            entries.append({
                "audio_filepath": str(wav_path.resolve()),
                "duration": round(info.duration, 3),
                "offset": 0,
            })
        except Exception:
            continue

    with open(noise_manifest_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    print(f"  MUSAN: {len(entries)} noise files")
    print(f"  Manifest: {noise_manifest_path}")


def prepare_speed_perturbed(output_dir: Path):
    """Create speed-perturbed copies of ClArTTS (0.9x and 1.1x).

    This 3x's the training data and adds speaking rate diversity
    (ClArTTS is single-speaker, so this helps generalization).
    """
    clartts_dir = output_dir / "clartts"
    train_manifest = clartts_dir / "train_manifest.json"

    if not train_manifest.exists():
        print("Train manifest not found, run prepare_clartts first.")
        return

    perturbed_dir = clartts_dir / "wavs_perturbed"
    perturbed_dir.mkdir(exist_ok=True)

    entries_original = []
    with open(train_manifest, "r", encoding="utf-8") as f:
        for line in f:
            entries_original.append(json.loads(line))

    speeds = [0.9, 1.1]
    all_entries = list(entries_original)  # start with originals

    print(f"\nCreating speed-perturbed copies ({speeds})...")

    for speed in speeds:
        print(f"  Speed {speed}x...")
        for i, entry in enumerate(entries_original):
            audio_data, sr = sf.read(entry["audio_filepath"])

            # Resample to simulate speed change
            from scipy.signal import resample as scipy_resample
            new_len = int(len(audio_data) / speed)
            audio_perturbed = scipy_resample(audio_data, new_len).astype(np.float32)

            duration = len(audio_perturbed) / sr
            if duration < 0.5 or duration > 25.0:
                continue

            filename = f"sp{speed}_{Path(entry['audio_filepath']).name}"
            wav_path = perturbed_dir / filename
            sf.write(str(wav_path), audio_perturbed, sr)

            all_entries.append({
                "audio_filepath": str(wav_path.resolve()),
                "duration": round(duration, 3),
                "text": entry["text"],
            })

            if (i + 1) % 1000 == 0:
                print(f"    {i + 1}/{len(entries_original)}")

    # Write combined manifest
    combined_manifest = clartts_dir / "train_manifest_sp.json"
    with open(combined_manifest, "w", encoding="utf-8") as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    total_hours = sum(e["duration"] for e in all_entries) / 3600
    print(f"  Combined: {len(all_entries)} samples ({total_hours:.1f}h)")
    print(f"  Manifest: {combined_manifest}")


def main():
    parser = argparse.ArgumentParser(description="Prepare data for PCD fine-tuning")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data"),
        help="Output directory for prepared data",
    )
    parser.add_argument(
        "--max-samples", type=int, default=0,
        help="Max training samples (0 = all). Use for quick testing.",
    )
    parser.add_argument(
        "--skip-musan", action="store_true",
        help="Skip MUSAN download (if already have noise data or don't want augmentation)",
    )
    parser.add_argument(
        "--skip-speed", action="store_true",
        help="Skip speed perturbation (saves disk space, less data diversity)",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: ClArTTS
    prepare_clartts(args.output_dir, args.max_samples)

    # Step 2: MUSAN noise
    if not args.skip_musan:
        prepare_musan(args.output_dir)

    # Step 3: Speed perturbation
    if not args.skip_speed:
        prepare_speed_perturbed(args.output_dir)

    print("\n" + "=" * 60)
    print("Data preparation complete!")
    print("=" * 60)
    print(f"\nTo fine-tune, run:")
    print(f"  python training/finetune_pcd.py --data-dir {args.output_dir}")


if __name__ == "__main__":
    main()
