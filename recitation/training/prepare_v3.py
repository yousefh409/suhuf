#!/usr/bin/env python3
"""Prepare v3 training data: ClArTTS + fixed TTS + contrastive pairs + augmentation.

Combines:
  1. ClArTTS (original, correct labels)
  2. v2 TTS data with FIXED final-word labels (strip case endings from last word)
  3. Contrastive pairs (i3rab + tashkeel + shadda)
  4. Speed perturbation (0.9x, 1.1x)
  5. MUSAN noise augmentation

Run after:
  - prepare_data.py (ClArTTS)
  - generate_tts_data.py (v2 TTS)
  - generate_contrastive_data.py (contrastive pairs)
"""

import json
import random
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf


ALL_HARAKAT = set("\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652")
SHADDA = "\u0651"


def strip_last_haraka(word: str) -> str:
    """Remove the case ending from a word."""
    for i in range(len(word) - 1, -1, -1):
        if word[i] in ALL_HARAKAT and word[i] != SHADDA:
            return word[:i] + word[i + 1:]
    return word


def fix_tts_final_labels(manifest_path: Path) -> list[dict]:
    """Load TTS manifest and fix final-word case endings in labels."""
    entries = []
    fixed = 0
    with open(manifest_path) as f:
        for line in f:
            entry = json.loads(line)
            words = entry["text"].split()
            if words:
                original = words[-1]
                words[-1] = strip_last_haraka(words[-1])
                if words[-1] != original:
                    fixed += 1
                entry["text"] = " ".join(words)
            entries.append(entry)
    print(f"  Fixed {fixed}/{len(entries)} TTS final-word labels")
    return entries


def download_musan(data_dir: Path) -> Path:
    """Download MUSAN noise corpus if not present."""
    musan_dir = data_dir / "musan"
    if musan_dir.exists() and any(musan_dir.rglob("*.wav")):
        return musan_dir
    print("Downloading MUSAN noise corpus...")
    musan_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["wget", "-q", "https://www.openslr.org/resources/17/musan.tar.gz",
         "-O", str(data_dir / "musan.tar.gz")],
        check=True, timeout=600,
    )
    subprocess.run(
        ["tar", "-xzf", str(data_dir / "musan.tar.gz"), "-C", str(data_dir)],
        check=True, timeout=1200,
    )
    (data_dir / "musan.tar.gz").unlink(missing_ok=True)
    return musan_dir


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
                except:
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
                except:
                    dst.unlink(missing_ok=True)
    return new_entries


def create_noisy_copies(entries: list[dict], noisy_dir: Path,
                        noise_files: list[str], fraction: float = 0.4) -> list[dict]:
    noisy_dir.mkdir(parents=True, exist_ok=True)
    noisy_entries = []
    to_augment = random.sample(entries, int(len(entries) * fraction))

    for entry in to_augment:
        src = Path(entry["audio_filepath"])
        snr = random.uniform(5, 25)
        dst = noisy_dir / f"{src.stem}_noisy.wav"

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
        except:
            continue

    return noisy_entries


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--noise-fraction", type=float, default=0.4)
    parser.add_argument("--no-speed-perturb", action="store_true")
    parser.add_argument("--no-noise", action="store_true")
    args = parser.parse_args()

    all_entries = []

    # 1. ClArTTS (keep as-is, these have correct labels including final words)
    clartts_manifest = args.data_dir / "clartts" / "train_manifest.json"
    if clartts_manifest.exists():
        with open(clartts_manifest) as f:
            clartts = [json.loads(line) for line in f]
        dur = sum(e["duration"] for e in clartts) / 3600
        print(f"1. ClArTTS: {len(clartts)} samples ({dur:.1f}h)")
        all_entries.extend(clartts)

    # 2. v2 TTS data with FIXED labels
    tts_manifest = args.data_dir / "tts" / "tts_manifest.json"
    if tts_manifest.exists():
        print("2. Fixing v2 TTS labels (strip case endings from final words)...")
        tts_entries = fix_tts_final_labels(tts_manifest)
        dur = sum(e["duration"] for e in tts_entries) / 3600
        print(f"   TTS: {len(tts_entries)} samples ({dur:.1f}h)")
        all_entries.extend(tts_entries)

    # 3. Contrastive pairs
    contrastive_manifest = args.data_dir / "contrastive" / "contrastive_manifest.json"
    if contrastive_manifest.exists():
        with open(contrastive_manifest) as f:
            contrastive = [json.loads(line) for line in f]
        dur = sum(e["duration"] for e in contrastive) / 3600
        print(f"3. Contrastive pairs: {len(contrastive)} samples ({dur:.1f}h)")
        all_entries.extend(contrastive)

    if not all_entries:
        print("ERROR: No training data found!")
        return

    total_dur = sum(e["duration"] for e in all_entries) / 3600
    print(f"\nBase data: {len(all_entries)} samples ({total_dur:.1f}h)")

    # 4. Speed perturbation
    if not args.no_speed_perturb:
        print("\n4. Creating speed perturbations...")
        sp_entries = create_speed_perturbed(all_entries, "v3")
        print(f"   Speed perturbed: +{len(sp_entries)} samples")
        all_entries.extend(sp_entries)

    # 5. Noise augmentation
    if not args.no_noise:
        musan_dir = download_musan(args.data_dir)
        noise_files = load_noise_files(musan_dir)
        if noise_files:
            print(f"\n5. Adding noise to {args.noise_fraction*100:.0f}% of samples ({len(noise_files)} noise files)...")
            noisy_dir = args.data_dir / "augmented" / "noisy_v3"
            noisy_entries = create_noisy_copies(all_entries, noisy_dir, noise_files, args.noise_fraction)
            print(f"   Noisy copies: +{len(noisy_entries)} samples")
            all_entries.extend(noisy_entries)

    # Write combined manifest
    random.shuffle(all_entries)
    combined = args.data_dir / "train_v3_combined.json"
    with open(combined, "w") as f:
        for e in all_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    total_dur = sum(e["duration"] for e in all_entries) / 3600
    print(f"\n{'='*60}")
    print(f"v3 combined manifest: {combined}")
    print(f"Total: {len(all_entries)} samples ({total_dur:.1f}h)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
