#!/usr/bin/env python3
"""Train a GBM classifier on signal_dump.json and serialize for production use.

Focus on eff < -1.5 where hand-tuned rules achieve only ~30% detection.
The GBM uses all available signals with strong regularization.
"""
import json
import pickle
import numpy as np
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent

# Features to use (carefully selected for low-eff regime)
FEATURE_KEYS = [
    "eff", "sf", "pc", "mg",
    "pd_i3rab", "pd_tashkeel",
    "i3rab_delta", "tash_delta",
    "consonant_match", "frame_count",
    "fs_worst_delta",
    "local_pd_i3rab", "local_pd_tashkeel",
]


def safe(v, default=0.0):
    if v is None or v == 999 or v == 999.0:
        return default
    return float(v)


def extract_features(s):
    return [safe(s.get(k)) for k in FEATURE_KEYS]


def main():
    with open(BASE / "signal_dump.json") as f:
        dump = json.load(f)

    # Use ALL data (both eff ranges) for training
    X_list, y_list, types_list, effs = [], [], [], []
    for rec in dump:
        s = rec["signals"]
        feats = extract_features(s)
        X_list.append(feats)
        y_list.append(1 if rec["label"] == "mutated" else 0)
        types_list.append(rec.get("mutation_type") or "correct")
        effs.append(s["eff"])

    X = np.array(X_list)
    y = np.array(y_list)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    n_correct = sum(y == 0)
    n_mutated = sum(y == 1)
    print(f"Total: {len(X)} (correct={n_correct}, mutated={n_mutated})")

    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler

    # Train with strong regularization to reduce overfitting
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Multiple models with different regularization
    configs = [
        ("conservative", {"n_estimators": 50, "max_depth": 2, "learning_rate": 0.05,
                          "min_samples_leaf": 10, "subsample": 0.8}),
        ("moderate", {"n_estimators": 100, "max_depth": 3, "learning_rate": 0.05,
                      "min_samples_leaf": 5, "subsample": 0.8}),
        ("aggressive", {"n_estimators": 200, "max_depth": 4, "learning_rate": 0.05,
                        "min_samples_leaf": 3, "subsample": 0.8}),
    ]

    for name, params in configs:
        gb = GradientBoostingClassifier(random_state=42, **params)
        gb.fit(X_scaled, y)
        probs = gb.predict_proba(X_scaled)[:, 1]

        correct_probs = probs[y == 0]
        mutated_probs = probs[y == 1]
        mutated_types = [t for t, yi in zip(types_list, y) if yi == 1]
        mutated_effs = [e for e, yi in zip(effs, y) if yi == 1]

        print(f"\n{'='*60}")
        print(f"Model: {name} ({params})")

        for max_fp_rate in [0.01, 0.02, 0.03]:
            max_fp = max(1, int(max_fp_rate * n_correct))
            sorted_c = sorted(correct_probs, reverse=True)
            thresh = sorted_c[max_fp - 1] if max_fp < len(sorted_c) else 0.0
            fp = sum(correct_probs >= thresh)
            tp = sum(mutated_probs >= thresh)

            # Per type
            tp_by_type = defaultdict(int)
            fn_by_type = defaultdict(int)
            for p, t in zip(mutated_probs, mutated_types):
                (tp_by_type if p >= thresh else fn_by_type)[t] += 1

            # Per eff range
            tp_low = sum(1 for p, e in zip(mutated_probs, mutated_effs) if p >= thresh and e < -1.5)
            total_low = sum(1 for e in mutated_effs if e < -1.5)
            tp_high = tp - tp_low

            print(f"\n  FP<={100*max_fp_rate:.0f}%: thresh={thresh:.4f} FP={fp}  det={tp}/{n_mutated} ({100*tp/n_mutated:.1f}%)")
            for t in ["i3rab", "tashkeel", "word"]:
                total = tp_by_type[t] + fn_by_type[t]
                if total > 0:
                    print(f"    {t}: {tp_by_type[t]}/{total} ({100*tp_by_type[t]/total:.1f}%)")
            print(f"    eff<-1.5: {tp_low}/{total_low} ({100*tp_low/total_low:.1f}%)")

        # Feature importance
        print(f"\n  Feature importance:")
        for feat_name, imp in sorted(zip(FEATURE_KEYS, gb.feature_importances_), key=lambda x: -x[1]):
            if imp > 0.01:
                print(f"    {feat_name:20s}: {imp:.4f}")

    # Save the aggressive model (use high threshold in production)
    best_name = "aggressive"
    best_params = configs[2][1]
    gb_best = GradientBoostingClassifier(random_state=42, **best_params)
    gb_best.fit(X_scaled, y)

    model_data = {
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "feature_keys": FEATURE_KEYS,
        "model": gb_best,
    }

    out_path = BASE / "models" / "error_classifier.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(model_data, f)
    print(f"\nSaved {best_name} model to {out_path}")

    # Also test: what threshold gives 0 FP on training data?
    probs = gb_best.predict_proba(X_scaled)[:, 1]
    correct_probs = probs[y == 0]
    mutated_probs = probs[y == 1]
    max_correct = max(correct_probs)
    tp_at_0fp = sum(mutated_probs > max_correct)
    print(f"\nAt 0 FP: threshold > {max_correct:.4f}, detection = {tp_at_0fp}/{n_mutated}")


if __name__ == "__main__":
    main()
