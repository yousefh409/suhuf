#!/usr/bin/env python3
"""Prepare augmented training data: combine ClArTTS + TTS, add speed perturbation + MUSAN noise.

Run after generate_tts_data.py and prepare_data.py.
"""

import json
import os
import random
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf


def download_musan(data_dir: Path):
    """Download MUSAN noise corpus if not present."""
    musan_dir = data_dir / "musan"
    if musan_dir.exists() and any(musan_dir.rglob("*.wav")):
        print(f"MUSAN already at {musan_dir}")
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
    print(f"MUSAN extracted to {musan_dir}")
    return musan_dir


def load_noise_files(musan_dir: Path) -> list[str]:
    """Load MUSAN noise file paths (noise + music, not speech)."""
    files = []
    for subdir in ["noise", "music"]:
        d = musan_dir / subdir
        if d.exists():
            files.extend(str(f) for f in d.rglob("*.wav"))
    print(f"Loaded {len(files)} MUSAN noise files")
    return files


def add_noise(audio: np.ndarray, sr: int, noise_files: list[str],
              snr_db: float) -> np.ndarray:
    """Add noise at specified SNR."""
    noise_path = random.choice(noise_files)
    noise, noise_sr = sf.read(noise_path, dtype="float32")

    # Resample noise if needed
    if noise_sr != sr:
        import scipy.signal
        noise = scipy.signal.resample_poly(noise, sr, noise_sr).astype(np.float32)

    # Handle stereo
    if noise.ndim > 1:
        noise = noise.mean(axis=1)

    # Loop or trim noise to match audio length
    while len(noise) < len(audio):
        noise = np.concatenate([noise, noise])
    noise = noise[:len(audio)]

    # Scale noise to desired SNR
    signal_power = np.mean(audio ** 2) + 1e-10
    noise_power = np.mean(noise ** 2) + 1e-10
    scale = np.sqrt(signal_power / (noise_power * (10 ** (snr_db / 10))))
    return audio + scale * noise


def create_speed_perturbed(manifest_entries: list[dict], wav_dir: Path,
                           prefix: str) -> list[dict]:
    """Create 0.9x and 1.1x speed-perturbed copies."""
    new_entries = []
    for speed in [0.9, 1.1]:
        for entry in manifest_entries:
            src = Path(entry["audio_filepath"])
            dst = wav_dir / f"{src.stem}_sp{speed:.1f}_{prefix}.wav"

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
                except Exception:
                    dst.unlink(missing_ok=True)
    return new_entries


def create_noisy_copies(manifest_entries: list[dict], wav_dir: Path,
                        noise_files: list[str], prefix: str,
                        fraction: float = 0.5) -> list[dict]:
    """Add noise to a fraction of samples at random SNRs."""
    noisy_entries = []
    samples_to_augment = random.sample(
        manifest_entries, int(len(manifest_entries) * fraction)
    )

    for entry in samples_to_augment:
        src = Path(entry["audio_filepath"])
        snr = random.uniform(5, 25)  # 5-25 dB SNR range
        dst = wav_dir / f"{src.stem}_noisy_{prefix}.wav"

        try:
            audio, sr = sf.read(str(src), dtype="float32")
            noisy = add_noise(audio, sr, noise_files, snr)
            # Normalize to prevent clipping
            peak = np.max(np.abs(noisy))
            if peak > 0.95:
                noisy = noisy * (0.95 / peak)
            sf.write(str(dst), noisy, sr)

            noisy_entries.append({
                "audio_filepath": str(dst),
                "duration": entry["duration"],
                "text": entry["text"],
            })
        except Exception as e:
            continue

    return noisy_entries


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--no-speed-perturb", action="store_true")
    parser.add_argument("--no-noise", action="store_true")
    parser.add_argument("--noise-fraction", type=float, default=0.5,
                        help="Fraction of samples to add noise to")
    args = parser.parse_args()

    aug_dir = args.data_dir / "augmented"
    aug_dir.mkdir(parents=True, exist_ok=True)

    # Load ClArTTS manifest
    clartts_manifest = args.data_dir / "clartts" / "train_manifest.json"
    clartts_entries = []
    if clartts_manifest.exists():
        with open(clartts_manifest) as f:
            clartts_entries = [json.loads(line) for line in f]
        dur = sum(e["duration"] for e in clartts_entries) / 3600
        print(f"ClArTTS: {len(clartts_entries)} samples ({dur:.1f}h)")

    # Load TTS manifest
    tts_manifest = args.data_dir / "tts" / "tts_manifest.json"
    tts_entries = []
    if tts_manifest.exists():
        with open(tts_manifest) as f:
            tts_entries = [json.loads(line) for line in f]
        dur = sum(e["duration"] for e in tts_entries) / 3600
        print(f"TTS: {len(tts_entries)} samples ({dur:.1f}h)")

    if not clartts_entries and not tts_entries:
        print("ERROR: No training data found!")
        return

    all_entries = clartts_entries + tts_entries
    total_dur = sum(e["duration"] for e in all_entries) / 3600
    print(f"\nCombined base: {len(all_entries)} samples ({total_dur:.1f}h)")

    # Speed perturbation
    if not args.no_speed_perturb:
        print("\nCreating speed perturbations...")
        sp_entries = []
        if clartts_entries:
            sp_dir = args.data_dir / "clartts" / "wavs"
            sp_entries += create_speed_perturbed(clartts_entries, sp_dir, "clartts")
            print(f"  ClArTTS speed perturbed: +{len(sp_entries)} samples")

        if tts_entries:
            sp_dir = args.data_dir / "tts" / "wavs"
            tts_sp = create_speed_perturbed(tts_entries, sp_dir, "tts")
            sp_entries += tts_sp
            print(f"  TTS speed perturbed: +{len(tts_sp)} samples")

        all_entries += sp_entries
        total_dur = sum(e["duration"] for e in all_entries) / 3600
        print(f"After speed perturbation: {len(all_entries)} samples ({total_dur:.1f}h)")

    # Noise augmentation
    noise_files = []
    if not args.no_noise:
        musan_dir = download_musan(args.data_dir)
        noise_files = load_noise_files(musan_dir)

        if noise_files:
            print(f"\nAdding noise to {args.noise_fraction*100:.0f}% of samples...")
            noisy_dir = aug_dir / "noisy"
            noisy_dir.mkdir(parents=True, exist_ok=True)

            noisy_entries = create_noisy_copies(
                all_entries, noisy_dir, noise_files, "aug", args.noise_fraction
            )
            all_entries += noisy_entries
            total_dur = sum(e["duration"] for e in all_entries) / 3600
            print(f"After noise augmentation: {len(all_entries)} samples ({total_dur:.1f}h)")

    # Write combined manifest
    random.shuffle(all_entries)
    combined_manifest = args.data_dir / "train_combined.json"
    with open(combined_manifest, "w") as f:
        for e in all_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    total_dur = sum(e["duration"] for e in all_entries) / 3600
    print(f"\nFinal combined manifest: {combined_manifest}")
    print(f"  Total: {len(all_entries)} samples ({total_dur:.1f}h)")
    print(f"  ClArTTS base: {len(clartts_entries)}")
    print(f"  TTS base: {len(tts_entries)}")
    print(f"  Augmented copies: {len(all_entries) - len(clartts_entries) - len(tts_entries)}")


if __name__ == "__main__":
    main()
