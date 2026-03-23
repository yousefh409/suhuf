#!/usr/bin/env python3
"""Prepare v4c balanced manifest: v3 contrastive + v4 TTS + full ClArTTS.

Goal: preserve v3 accuracy while adding v4b's tashkeel discrimination.
No speed perturbation or noise augmentation - keep it focused.
"""

import json
import random
from pathlib import Path


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    all_entries = []

    # 1. Full ClArTTS training set (9.5K samples)
    clartts = args.data_dir / "clartts" / "train_manifest.json"
    if clartts.exists():
        with open(clartts) as f:
            entries = [json.loads(line) for line in f]
        dur = sum(e["duration"] for e in entries) / 3600
        print(f"1. ClArTTS: {len(entries)} samples ({dur:.1f}h)")
        all_entries.extend(entries)

    # 2. v3 contrastive pairs (20K samples - i3rab/tashkeel/shadda discrimination)
    v3_contrastive = args.data_dir / "contrastive" / "contrastive_manifest.json"
    if v3_contrastive.exists():
        with open(v3_contrastive) as f:
            entries = [json.loads(line) for line in f]
        dur = sum(e["duration"] for e in entries) / 3600
        print(f"2. v3 contrastive: {len(entries)} samples ({dur:.1f}h)")
        all_entries.extend(entries)

    # 3. v4 TTS contrastive pairs (9K samples - fatha discrimination)
    v4_contrastive = args.data_dir / "contrastive_v4" / "contrastive_v4_manifest.json"
    if v4_contrastive.exists():
        with open(v4_contrastive) as f:
            entries = [json.loads(line) for line in f]
        dur = sum(e["duration"] for e in entries) / 3600
        print(f"3. v4 TTS contrastive: {len(entries)} samples ({dur:.1f}h)")
        all_entries.extend(entries)

    if not all_entries:
        print("ERROR: No data found!")
        return

    random.shuffle(all_entries)

    output = args.data_dir / "train_v4c_balanced.json"
    with open(output, "w") as f:
        for e in all_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    total_dur = sum(e["duration"] for e in all_entries) / 3600
    print(f"\nv4c balanced manifest: {output}")
    print(f"Total: {len(all_entries)} samples ({total_dur:.1f}h)")


if __name__ == "__main__":
    main()
