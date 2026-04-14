#!/usr/bin/env python3
"""Cross-validated classifier ceiling + decision tree rule extraction from signal_dump.json."""
import json
import numpy as np
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent

SIGNAL_KEYS = [
    "eff", "i3rab_delta", "tash_delta", "pc", "sf", "mg",
    "consonant_match", "frame_count", "gdm",
    "pd_i3rab", "pd_tashkeel",
    "local_pd_i3rab", "local_pd_tashkeel",
    "fs_worst_delta",
]


def extract_features(s):
    feats = []
    for k in SIGNAL_KEYS:
        v = s.get(k)
        if v is None or v == 999 or v == 999.0:
            feats.append(0.0)
        elif isinstance(v, bool):
            feats.append(1.0 if v else 0.0)
        else:
            feats.append(float(v))
    return feats


def main():
    with open(BASE / "signal_dump.json") as f:
        dump = json.load(f)

    X_list, y_list, types_list, groups = [], [], [], []
    for rec in dump:
        s = rec["signals"]
        feats = extract_features(s)
        X_list.append(feats)
        is_mutated = 1 if rec["label"] == "mutated" else 0
        y_list.append(is_mutated)
        types_list.append(rec.get("mutation_type") or "correct")
        # Group by passage_id for group-based CV
        groups.append(rec["passage_id"])

    X = np.array(X_list)
    y = np.array(y_list)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    n_correct = sum(y == 0)
    n_mutated = sum(y == 1)
    print(f"Total: {len(X)} (correct={n_correct}, mutated={n_mutated})")
    print(f"Features: {SIGNAL_KEYS}")

    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.tree import DecisionTreeClassifier, export_text
    from sklearn.model_selection import LeaveOneGroupOut
    from sklearn.preprocessing import StandardScaler

    # ---- Leave-One-Group-Out CV (split by passage) ----
    print("\n" + "=" * 70)
    print("LEAVE-ONE-GROUP-OUT CROSS-VALIDATION")
    print("=" * 70)

    unique_groups = sorted(set(groups))
    print(f"Groups: {unique_groups}")

    logo = LeaveOneGroupOut()
    groups_arr = np.array(groups)

    for name, clf in [
        ("GBM-200-d3", GradientBoostingClassifier(n_estimators=200, max_depth=3, random_state=42)),
        ("GBM-200-d4", GradientBoostingClassifier(n_estimators=200, max_depth=4, random_state=42)),
        ("GBM-500-d4", GradientBoostingClassifier(n_estimators=500, max_depth=4, random_state=42)),
        ("DecTree-d8", DecisionTreeClassifier(max_depth=8, random_state=42)),
        ("DecTree-d12", DecisionTreeClassifier(max_depth=12, random_state=42)),
    ]:
        # Scale within each fold
        probs = np.zeros(len(X))
        for train_idx, test_idx in logo.split(X, y, groups_arr):
            scaler = StandardScaler()
            X_train = scaler.fit_transform(X[train_idx])
            X_test = scaler.transform(X[test_idx])
            clf_copy = type(clf)(**clf.get_params())
            clf_copy.fit(X_train, y[train_idx])
            if hasattr(clf_copy, "predict_proba"):
                probs[test_idx] = clf_copy.predict_proba(X_test)[:, 1]
            else:
                probs[test_idx] = clf_copy.predict(X_test).astype(float)

        correct_probs = probs[y == 0]
        mutated_probs = probs[y == 1]
        mutated_types_arr = [t for t, yi in zip(types_list, y) if yi == 1]

        print(f"\n  {name}:")
        for max_fp_rate in [0.01, 0.02, 0.03, 0.05]:
            max_fp = max(1, int(max_fp_rate * n_correct))
            sorted_c = sorted(correct_probs, reverse=True)
            if max_fp >= len(sorted_c):
                thresh = 0.0
            else:
                thresh = sorted_c[max_fp - 1]
            fp = sum(correct_probs >= thresh)
            tp = sum(mutated_probs >= thresh)
            tp_by_type = defaultdict(int)
            fn_by_type = defaultdict(int)
            for p, t in zip(mutated_probs, mutated_types_arr):
                if p >= thresh:
                    tp_by_type[t] += 1
                else:
                    fn_by_type[t] += 1
            print(f"    FP<={100*max_fp_rate:.0f}%: thresh={thresh:.3f} FP={fp}  "
                  f"det={tp}/{n_mutated} ({100*tp/n_mutated:.1f}%)")
            for t in ["i3rab", "tashkeel", "word"]:
                total_t = tp_by_type[t] + fn_by_type[t]
                if total_t > 0:
                    print(f"      {t}: {tp_by_type[t]}/{total_t} ({100*tp_by_type[t]/total_t:.1f}%)")

    # ---- Decision tree rule extraction ----
    print("\n" + "=" * 70)
    print("DECISION TREE RULES (depth=5, for interpretability)")
    print("=" * 70)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    dt = DecisionTreeClassifier(max_depth=5, random_state=42, class_weight={0: 1, 1: 0.5})
    dt.fit(X_scaled, y)
    pred = dt.predict(X_scaled)
    fp = sum(pred[y == 0] == 1)
    tp = sum(pred[y == 1] == 1)
    print(f"\nTrain: FP={fp}/{n_correct} ({100*fp/n_correct:.1f}%)  det={tp}/{n_mutated} ({100*tp/n_mutated:.1f}%)")
    print(export_text(dt, feature_names=SIGNAL_KEYS, max_depth=5))

    # ---- Feature interactions: what separates correct from mutated at eff < -1.5? ----
    print("\n" + "=" * 70)
    print("LOW-EFF ANALYSIS (eff < -1.5)")
    print("=" * 70)

    low_mask = X[:, 0] < -1.5  # eff is first feature
    X_low = X[low_mask]
    y_low = y[low_mask]
    types_low = [t for t, m in zip(types_list, low_mask) if m]

    n_c_low = sum(y_low == 0)
    n_m_low = sum(y_low == 1)
    print(f"Low-eff samples: {len(X_low)} (correct={n_c_low}, mutated={n_m_low})")

    # Fit GBM on just low-eff
    scaler_low = StandardScaler()
    X_low_s = scaler_low.fit_transform(X_low)

    gb_low = GradientBoostingClassifier(n_estimators=200, max_depth=4, random_state=42)
    gb_low.fit(X_low_s, y_low)
    probs_low = gb_low.predict_proba(X_low_s)[:, 1]

    correct_probs_low = probs_low[y_low == 0]
    mutated_probs_low = probs_low[y_low == 1]
    mutated_types_low = [t for t, yi in zip(types_low, y_low) if yi == 1]

    print(f"\nGBM on low-eff only (train, no CV):")
    for max_fp_rate in [0.0, 0.01, 0.02, 0.05, 0.10]:
        max_fp = max(0 if max_fp_rate == 0 else 1, int(max_fp_rate * n_c_low))
        sorted_c = sorted(correct_probs_low, reverse=True)
        if max_fp == 0:
            thresh = sorted_c[0] + 0.001
        elif max_fp >= len(sorted_c):
            thresh = 0.0
        else:
            thresh = sorted_c[max_fp - 1]
        fp = sum(correct_probs_low >= thresh)
        tp = sum(mutated_probs_low >= thresh)
        tp_by_type = defaultdict(int)
        for p, t in zip(mutated_probs_low, mutated_types_low):
            if p >= thresh:
                tp_by_type[t] += 1
        print(f"  FP<={100*max_fp_rate:.0f}%: FP={fp}  det={tp}/{n_m_low} ({100*tp/n_m_low:.1f}%)")
        for t in ["i3rab", "tashkeel", "word"]:
            total_t = sum(1 for tt in mutated_types_low if tt == t)
            if total_t > 0:
                print(f"    {t}: {tp_by_type.get(t,0)}/{total_t} ({100*tp_by_type.get(t,0)/total_t:.1f}%)")

    print(f"\nFeature importance (low-eff GBM):")
    for name, imp in sorted(zip(SIGNAL_KEYS, gb_low.feature_importances_), key=lambda x: -x[1]):
        if imp > 0.01:
            print(f"  {name:20s}: {imp:.4f}")

    # Decision tree on low-eff
    dt_low = DecisionTreeClassifier(max_depth=5, random_state=42)
    dt_low.fit(X_low_s, y_low)
    pred_low = dt_low.predict(X_low_s)
    fp_low = sum(pred_low[y_low == 0] == 1)
    tp_low = sum(pred_low[y_low == 1] == 1)
    print(f"\nDecTree d=5 on low-eff: FP={fp_low}/{n_c_low} ({100*fp_low/n_c_low:.1f}%)  "
          f"det={tp_low}/{n_m_low} ({100*tp_low/n_m_low:.1f}%)")
    print(export_text(dt_low, feature_names=SIGNAL_KEYS, max_depth=5))


if __name__ == "__main__":
    main()
