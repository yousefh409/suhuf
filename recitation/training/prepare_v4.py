#!/usr/bin/env python3
"""Prepare v4 training data: ClArTTS + v4 contrastive pairs + augmentation.

v4 strategy: fine-tune FROM v3 (not base model) with targeted data to fix
the damma bias while preserving v3's strengths.

Combines:
  1. ClArTTS (original, correct labels)
  2. v4 contrastive pairs (fatha↔damma targeted, from ClArTTS + TTS)
  3. v3 contrastive pairs (reuse existing — i3rab, tashkeel, shadda)
  4. Speed perturbation (0.9x, 1.1x)
  5. MUSAN noise augmentation

Key difference from v3: does NOT include v2 TTS data (lower quality),
focuses on ClArTTS + targeted contrastive pairs.

Run after:
  - prepare_data.py (ClArTTS)
  - generate_v4_contrastive.py (v4 contrastive pairs)
"""

import json
import random
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf


ALL_HARAKAT = set("\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652")
SHADDA = "\u0651"


def load_noise_files(musan_dir: Path) -> list[str]:
    files = []
    for subdir in ["noise", "music"]:
        d = musan_dir / subdir
        if d.exists():
            files.extend(str(f) for f in d.rglob("*.wav"))
    return files


def add_noise(audio: np.ndarray, sr: int, noise_files: list[str],
              snr_db: float) -> np.ndarray:
    noise_path = random.choice(noise_files)
    noise, noise_sr = sf.read(noise_path, dtype="float32")
    if noise_sr != sr:
        import scipy.signal
        noise = scipy.signal.resample_poly(noise, sr, noise_sr).astype(np.float32)
    if noise.ndim > 1:
        noise = noise.mean(axis=1)
    while len(noise) < len(audio):
        noise = np.concatenate([noise, noise])
    noise = noise[:len(audio)]
    signal_power = np.mean(audio ** 2) + 1e-10
    noise_power = np.mean(noise ** 2) + 1e-10
    scale = np.sqrt(signal_power / (noise_power * (10 ** (snr_db / 10))))
    return audio + scale * noise


def create_speed_perturbed(entries: list[dict], prefix: str) -> list[dict]:
    new_entries = []
    for speed in [0.9, 1.1]:
        for entry in entries:
            src = Path(entry["audio_filepath"])
            dst = src.parent / f"{src.stem}_sp{speed:.1f}_{prefix}.wav"

            if dst.exists():
                try:
                    info = sf.info(str(dst))
                    new_entries.append({
                        "audio_filepath": str(dst),
                        "duration": round(info.duration, 3),
                        "text": entry["text"],
                    })
                    continue
                except Exception:
                    pass

            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(src), "-filter:a", f"atempo={speed}",
                 "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le", str(dst)],
                capture_output=True, timeout=30,
            )
            if result.returncode == 0 and dst.exists():
                try:
                    info = sf.info(str(dst))
                    new_entries.append({
                        "audio_filepath": str(dst),
                        "duration": round(info.duration, 3),
                        "text": entry["text"],
                    })
                except Exception:
                    dst.unlink(missing_ok=True)
    return new_entries


def create_noisy_copies(entries: list[dict], noisy_dir: Path,
                        noise_files: list[str], fraction: float = 0.3) -> list[dict]:
    noisy_dir.mkdir(parents=True, exist_ok=True)
    noisy_entries = []
    to_augment = random.sample(entries, int(len(entries) * fraction))

    for entry in to_augment:
        src = Path(entry["audio_filepath"])
        snr = random.uniform(5, 25)
        dst = noisy_dir / f"{src.stem}_noisy_v4.wav"

        try:
            audio, sr = sf.read(str(src), dtype="float32")
            noisy = add_noise(audio, sr, noise_files, snr)
            peak = np.max(np.abs(noisy))
            if peak > 0.95:
                noisy = noisy * (0.95 / peak)
            sf.write(str(dst), noisy, sr)
            noisy_entries.append({
                "audio_filepath": str(dst),
                "duration": entry["duration"],
                "text": entry["text"],
            })
        except Exception:
            continue

    return noisy_entries


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--noise-fraction", type=float, default=0.3)
    parser.add_argument("--no-speed-perturb", action="store_true")
    parser.add_argument("--no-noise", action="store_true")
    parser.add_argument("--include-v3-contrastive", action="store_true",
                        help="Also include v3 contrastive pairs")
    parser.add_argument("--include-v2-tts", action="store_true",
                        help="Also include v2 TTS data (not recommended)")
    args = parser.parse_args()

    all_entries = []

    # 1. ClArTTS (original — correct labels, including final words)
    clartts_manifest = args.data_dir / "clartts" / "train_manifest.json"
    if clartts_manifest.exists():
        with open(clartts_manifest) as f:
            clartts = [json.loads(line) for line in f]
        dur = sum(e["duration"] for e in clartts) / 3600
        print(f"1. ClArTTS: {len(clartts)} samples ({dur:.1f}h)")
        all_entries.extend(clartts)
    else:
        print("WARNING: ClArTTS manifest not found!")

    # 2. v4 contrastive pairs (fatha↔damma targeted)
    v4_manifest = args.data_dir / "contrastive_v4" / "contrastive_v4_manifest.json"
    if v4_manifest.exists():
        with open(v4_manifest) as f:
            v4_contrastive = [json.loads(line) for line in f]
        dur = sum(e["duration"] for e in v4_contrastive) / 3600
        print(f"2. v4 contrastive: {len(v4_contrastive)} samples ({dur:.1f}h)")
        all_entries.extend(v4_contrastive)
    else:
        print("WARNING: v4 contrastive manifest not found! Run generate_v4_contrastive.py first")

    # 3. v3 contrastive pairs (optional — reuse existing)
    if args.include_v3_contrastive:
        v3_manifest = args.data_dir / "contrastive" / "contrastive_manifest.json"
        if v3_manifest.exists():
            with open(v3_manifest) as f:
                v3_contrastive = [json.loads(line) for line in f]
            dur = sum(e["duration"] for e in v3_contrastive) / 3600
            print(f"3. v3 contrastive: {len(v3_contrastive)} samples ({dur:.1f}h)")
            all_entries.extend(v3_contrastive)

    # 4. v2 TTS data (optional, not recommended)
    if args.include_v2_tts:
        tts_manifest = args.data_dir / "tts" / "tts_manifest.json"
        if tts_manifest.exists():
            with open(tts_manifest) as f:
                tts = [json.loads(line) for line in f]
            dur = sum(e["duration"] for e in tts) / 3600
            print(f"4. v2 TTS: {len(tts)} samples ({dur:.1f}h)")
            all_entries.extend(tts)

    if not all_entries:
        print("ERROR: No training data found!")
        return

    total_dur = sum(e["duration"] for e in all_entries) / 3600
    print(f"\nBase data: {len(all_entries)} samples ({total_dur:.1f}h)")

    # 5. Speed perturbation
    if not args.no_speed_perturb:
        print("\n5. Creating speed perturbations...")
        sp_entries = create_speed_perturbed(all_entries, "v4")
        print(f"   Speed perturbed: +{len(sp_entries)} samples")
        all_entries.extend(sp_entries)

    # 6. Noise augmentation
    if not args.no_noise:
        musan_dir = args.data_dir / "musan"
        if musan_dir.exists():
            noise_files = load_noise_files(musan_dir)
            if noise_files:
                print(f"\n6. Adding noise to {args.noise_fraction*100:.0f}% ({len(noise_files)} noise files)...")
                noisy_dir = args.data_dir / "augmented" / "noisy_v4"
                noisy_entries = create_noisy_copies(all_entries, noisy_dir, noise_files, args.noise_fraction)
                print(f"   Noisy copies: +{len(noisy_entries)} samples")
                all_entries.extend(noisy_entries)
        else:
            print("  MUSAN not found, skipping noise augmentation")

    # Write combined manifest
    random.shuffle(all_entries)
    combined = args.data_dir / "train_v4_combined.json"
    with open(combined, "w") as f:
        for e in all_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    total_dur = sum(e["duration"] for e in all_entries) / 3600
    print(f"\n{'='*60}")
    print(f"v4 combined manifest: {combined}")
    print(f"Total: {len(all_entries)} samples ({total_dur:.1f}h)")
    print(f"{'='*60}")

    print(f"\nTo train v4:")
    print(f"  python training/finetune_pcd.py \\")
    print(f"    --from-nemo models/pcd_clartts_v3.nemo \\")
    print(f"    --train-manifest {combined} \\")
    print(f"    --epochs 12 --lr 1e-5 \\")
    print(f"    --freeze-encoder-epochs 3 \\")
    print(f"    --output-dir checkpoints/v4")


if __name__ == "__main__":
    main()
