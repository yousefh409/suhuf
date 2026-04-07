#!/usr/bin/env python3
"""Train a multi-class GBM for mutation type classification.

Classes: i3rab, tashkeel, word
Only trained on mutated samples.
"""
import json
import pickle
import numpy as np
from pathlib import Path

BASE = Path(__file__).parent

FEATURE_KEYS = [
    "eff", "sf", "pc", "mg",
    "pd_i3rab", "pd_tashkeel",
    "i3rab_delta", "tash_delta",
    "consonant_match", "frame_count",
    "fs_worst_delta",
    "local_pd_i3rab", "local_pd_tashkeel",
    "gfm", "gdm", "sukoon_delta",
]

TYPE_MAP = {"i3rab": 0, "tashkeel": 1, "word": 2}
TYPE_NAMES = ["i3rab", "tashkeel", "word"]


def safe(v, default=0.0):
    if v is None or v == 999 or v == 999.0:
        return default
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    return float(v)


def extract_features(s):
    feats = []
    for k in FEATURE_KEYS:
        if k == "i3rab_delta":
            eff = s.get("eff", 0)
            alt_delta = s.get("i3rab_delta")
            feats.append(safe(alt_delta))
        elif k == "tash_delta":
            feats.append(safe(s.get("tash_delta")))
        elif k == "sukoon_delta":
            feats.append(safe(s.get("sukoon_delta")))
        else:
            feats.append(safe(s.get(k)))
    return feats


def main():
    with open(BASE / "signal_dump.json") as f:
        dump = json.load(f)

    X_list, y_list = [], []
    for rec in dump:
        if rec["label"] != "mutated":
            continue
        feats = extract_features(rec["signals"])
        X_list.append(feats)
        y_list.append(TYPE_MAP[rec["mutation_type"]])

    X = np.array(X_list)
    y = np.array(y_list)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    print(f"Mutated samples: {len(X)}")
    for i, name in enumerate(TYPE_NAMES):
        print(f"  {name}: {sum(y == i)}")

    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train multi-class classifier
    gb = GradientBoostingClassifier(
        n_estimators=100, max_depth=3, learning_rate=0.1,
        min_samples_leaf=5, subsample=0.8, random_state=42
    )
    gb.fit(X_scaled, y)

    pred = gb.predict(X_scaled)
    correct = sum(pred == y)
    print(f"\nTrain accuracy: {correct}/{len(y)} ({100*correct/len(y):.1f}%)")
    for i, name in enumerate(TYPE_NAMES):
        mask = y == i
        correct_type = sum(pred[mask] == i)
        total_type = sum(mask)
        print(f"  {name}: {correct_type}/{total_type} ({100*correct_type/total_type:.1f}%)")

    # Confusion matrix
    from collections import Counter
    print("\nConfusion matrix (rows=true, cols=predicted):")
    print(f"{'':15s} {'i3rab':>8s} {'tashkeel':>8s} {'word':>8s}")
    for i, name in enumerate(TYPE_NAMES):
        row = [sum((y == i) & (pred == j)) for j in range(3)]
        print(f"  {name:13s} {row[0]:8d} {row[1]:8d} {row[2]:8d}")

    # Save
    model_data = {
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "feature_keys": FEATURE_KEYS,
        "model": gb,
        "type_names": TYPE_NAMES,
    }

    out_path = BASE / "models" / "type_classifier.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(model_data, f)
    print(f"\nSaved to {out_path}")

    # Feature importance
    print("\nFeature importance:")
    for name, imp in sorted(zip(FEATURE_KEYS, gb.feature_importances_), key=lambda x: -x[1]):
        if imp > 0.01:
            print(f"  {name:20s}: {imp:.4f}")


if __name__ == "__main__":
    main()
