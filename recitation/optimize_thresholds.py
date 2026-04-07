#!/usr/bin/env python3
"""Offline threshold optimizer using dumped signal data.

Loads signal_dump.json and tries many classify_words configurations
to find the best FP/detection tradeoff.
"""
import json
import sys
from pathlib import Path
from itertools import product
from collections import defaultdict

BASE = Path(__file__).parent

# Which engine error_types satisfy a given mutation kind
_MUTATION_EXPECTED_TYPES = {
    "i3rab": {"i3rab"},
    "tashkeel": {"tashkeel", "diacritic"},
    "word": {"wrong", "skipped"},
}


def classify_word(s, params):
    """Classify a single word given its signals dict and parameter dict.

    Returns (status, error_type) tuple.
    """
    eff = s["eff"]
    cm = s["consonant_match"]
    fc = s["frame_count"]
    wl = s["word_len"]
    gl = s["greedy_len"]
    i3d = s["i3rab_delta"]
    td = s["tash_delta"]
    sd = s["sukoon_delta"]
    pc = s["pc"]
    sf = s["sf"]
    gfm = s["gfm"]
    gdm = s["gdm"]
    shadda_d = s["shadda_delta"]
    whisper = s["whisper_match"]

    # === Wrong word detection ===
    # Tier 1: High-eff consonant mismatch (greedy reliable)
    if (wl >= 3 and eff > params.get("word_eff_high", -1.0)
            and cm < params.get("word_cm_high", 0.35)
            and gl > 0 and fc >= 3 and fc <= 50):
        return "error", "wrong"

    # Tier 2: Low-eff but zero consonant match (definitive mismatch)
    if (wl >= 3 and cm <= params.get("word_cm_zero", 0.1)
            and fc >= params.get("word_fc_min", 5)
            and eff < params.get("word_eff_low_max", -1.0)):
        return "error", "wrong"

    # Tier 3: Whisper disagreement
    if (not whisper and eff < -1.5 and wl >= 3 and fc >= 5):
        return "error", "wrong"

    # Tier 4: Skipped word
    if (fc < 3 and eff < -3.5 and wl >= 3):
        return "error", "skipped"

    # === Diacritic detection ===
    eff_min = params.get("diac_eff_min", -3.0)
    if eff <= eff_min:
        return "correct", None

    # Collect votes
    i3rab_votes = 0.0
    tashkeel_votes = 0.0

    # Vote 1: CTC i3rab hypothesis
    i3d_thresh = params.get("i3rab_delta_thresh", 0.12)
    i3d_strong = params.get("i3rab_delta_strong", 0.25)
    if i3d is not None and i3d >= i3d_thresh:
        i3rab_votes += 1
        if i3d >= i3d_strong:
            i3rab_votes += 1

    # Vote 2: CTC tashkeel hypothesis
    td_thresh = params.get("tash_delta_thresh", 0.15)
    td_strong = params.get("tash_delta_strong", 0.28)
    if td is not None and td >= td_thresh:
        tashkeel_votes += 1
        if td >= td_strong:
            tashkeel_votes += 1

    # Vote 2b: Sukoon hypothesis
    sd_thresh = params.get("sukoon_delta_thresh", 0.25)
    if sd is not None and sd >= sd_thresh:
        tashkeel_votes += 1

    # Vote 3: Per-char
    pc_thresh = params.get("pc_thresh", -4.5)
    pc_strong = params.get("pc_strong", -6.5)
    if pc is not None and pc < pc_thresh:
        tashkeel_votes += 1
        if pc < pc_strong:
            tashkeel_votes += 1
    # Per-char also helps i3rab
    pc_i3rab_boost_thresh = params.get("pc_i3rab_boost_thresh", -4.5)
    i3d_min_for_pc = params.get("i3d_min_for_pc", 0.08)
    if pc is not None and pc < pc_i3rab_boost_thresh and i3d is not None and i3d >= i3d_min_for_pc:
        i3rab_votes += 1

    # Vote 4: SF-GOP
    sf_thresh = params.get("sf_thresh", -4.5)
    sf_strong = params.get("sf_strong", -6.5)
    if sf is not None and sf < sf_thresh:
        tashkeel_votes += 1
        if sf < sf_strong:
            tashkeel_votes += 1
    # SF also helps i3rab
    if sf is not None and sf < sf_thresh and i3d is not None and i3d >= i3d_min_for_pc:
        i3rab_votes += 1

    # Vote 5: Greedy final mismatch (i3rab)
    gfm_eff_min = params.get("gfm_eff_min", -1.8)
    if gfm and eff > gfm_eff_min:
        i3rab_votes += 1

    # Vote 6: Greedy internal mismatch (tashkeel)
    gdm_eff_min = params.get("gdm_eff_min", -1.5)
    if gdm >= 1 and eff > gdm_eff_min:
        tashkeel_votes += 1

    # Vote 7: Shadda scoring
    shadda_thresh = params.get("shadda_thresh", 0.22)
    if shadda_d is not None and shadda_d >= shadda_thresh:
        tashkeel_votes += 1

    # === GFM-corroborated i3rab (new) ===
    # gfm has 0.3% FP rate — if it fires, need minimal corroboration
    gfm_corr_enabled = params.get("gfm_corroborate", False)
    if gfm_corr_enabled and gfm and eff > gfm_eff_min:
        # Count weak corroborating signals
        corr = 0
        if i3d is not None and i3d > 0.02:
            corr += 1
        if pc is not None and pc < params.get("gfm_corr_pc", -2.0):
            corr += 1
        if sf is not None and sf < params.get("gfm_corr_sf", -2.0):
            corr += 1
        if corr >= 1:
            i3rab_votes = max(i3rab_votes, params.get("gfm_corr_votes", 2))

    # === Voting threshold ===
    eff_boundary = params.get("eff_boundary", -2.0)
    vote_high = params.get("vote_thresh_high", 2)
    vote_low = params.get("vote_thresh_low", 3)

    if eff > eff_boundary:
        vote_thresh = vote_high
    else:
        vote_thresh = vote_low

    if i3rab_votes >= vote_thresh:
        return "error", "i3rab"
    if tashkeel_votes >= vote_thresh:
        return "error", "tashkeel"

    return "correct", None


def evaluate(records, params):
    """Evaluate a parameter set against all records."""
    n_correct = 0
    n_fp = 0
    stats = defaultdict(lambda: {"total": 0, "detected": 0, "type_correct": 0})

    for r in records:
        s = r["signals"]
        label = r["label"]
        mut_type = r.get("mutation_type")

        status, error_type = classify_word(s, params)

        if label == "correct":
            n_correct += 1
            if status != "correct":
                n_fp += 1
        else:
            stats[mut_type]["total"] += 1
            if status != "correct":
                stats[mut_type]["detected"] += 1
                if error_type in _MUTATION_EXPECTED_TYPES.get(mut_type, set()):
                    stats[mut_type]["type_correct"] += 1

    fp_rate = n_fp / n_correct * 100 if n_correct > 0 else 0
    return {
        "fp_rate": fp_rate,
        "fp_count": n_fp,
        "n_correct": n_correct,
        "i3rab_det": stats["i3rab"]["detected"],
        "i3rab_total": stats["i3rab"]["total"],
        "i3rab_type": stats["i3rab"]["type_correct"],
        "tash_det": stats["tashkeel"]["detected"],
        "tash_total": stats["tashkeel"]["total"],
        "tash_type": stats["tashkeel"]["type_correct"],
        "word_det": stats["word"]["detected"],
        "word_total": stats["word"]["total"],
        "word_type": stats["word"]["type_correct"],
    }


def score_result(r):
    """Score a result for ranking. Higher = better.

    Heavily penalizes FP > 2%, rewards detection.
    """
    fp = r["fp_rate"]
    if fp > 2.0:
        fp_penalty = -100 * (fp - 2.0)  # harsh penalty
    else:
        fp_penalty = 0

    # Detection rates (as percentage)
    i3_rate = r["i3rab_det"] / r["i3rab_total"] * 100 if r["i3rab_total"] else 0
    t_rate = r["tash_det"] / r["tash_total"] * 100 if r["tash_total"] else 0
    w_rate = r["word_det"] / r["word_total"] * 100 if r["word_total"] else 0

    # Weighted sum (i3rab and tashkeel matter more than word for this system)
    return fp_penalty + i3_rate * 0.35 + t_rate * 0.35 + w_rate * 0.30


def grid_search(records):
    """Try many parameter combinations and find the best."""
    # Base params
    base = {
        "word_eff_high": -1.0,
        "word_cm_high": 0.35,
        "word_cm_zero": 0.1,
        "word_fc_min": 5,
        "word_eff_low_max": -1.0,
        "diac_eff_min": -3.0,
        "eff_boundary": -2.0,
        "vote_thresh_high": 2,
        "vote_thresh_low": 3,
        "gfm_eff_min": -1.8,
        "gdm_eff_min": -1.5,
        "shadda_thresh": 0.22,
        "gfm_corroborate": False,
    }

    # Parameters to sweep
    sweeps = {
        "i3rab_delta_thresh": [0.04, 0.06, 0.08, 0.10, 0.12, 0.15],
        "i3rab_delta_strong": [0.20, 0.25, 0.30],
        "tash_delta_thresh": [0.06, 0.08, 0.10, 0.12, 0.15],
        "tash_delta_strong": [0.22, 0.28, 0.35],
        "pc_thresh": [-3.0, -3.5, -4.0, -4.5],
        "pc_strong": [-5.5, -6.5],
        "sf_thresh": [-3.0, -3.5, -4.0, -4.5],
        "sf_strong": [-5.5, -6.5],
        "pc_i3rab_boost_thresh": [-3.0, -3.5, -4.0, -4.5],
        "i3d_min_for_pc": [0.02, 0.05, 0.08],
    }

    # Phase 1: Sweep individual signal thresholds
    print("Phase 1: Individual signal sweeps...")
    best_params = dict(base)
    best_params.update({
        "i3rab_delta_thresh": 0.12,
        "i3rab_delta_strong": 0.25,
        "tash_delta_thresh": 0.15,
        "tash_delta_strong": 0.28,
        "pc_thresh": -4.5,
        "pc_strong": -6.5,
        "sf_thresh": -4.5,
        "sf_strong": -6.5,
        "pc_i3rab_boost_thresh": -4.5,
        "i3d_min_for_pc": 0.08,
    })

    best_score = score_result(evaluate(records, best_params))
    best_result = evaluate(records, best_params)

    print(f"  Baseline: score={best_score:.1f} FP={best_result['fp_rate']:.1f}% "
          f"i3={best_result['i3rab_det']}/{best_result['i3rab_total']} "
          f"t={best_result['tash_det']}/{best_result['tash_total']} "
          f"w={best_result['word_det']}/{best_result['word_total']}")

    # Sweep each parameter individually first
    for param_name, values in sweeps.items():
        local_best_score = best_score
        local_best_val = best_params[param_name]
        for val in values:
            trial = dict(best_params)
            trial[param_name] = val
            r = evaluate(records, trial)
            s = score_result(r)
            if s > local_best_score:
                local_best_score = s
                local_best_val = val
        if local_best_val != best_params[param_name]:
            print(f"  {param_name}: {best_params[param_name]} -> {local_best_val} (score +{local_best_score - best_score:.1f})")
            best_params[param_name] = local_best_val
            best_score = local_best_score

    best_result = evaluate(records, best_params)
    print(f"\n  After individual sweeps: score={best_score:.1f} FP={best_result['fp_rate']:.1f}% "
          f"i3={best_result['i3rab_det']}/{best_result['i3rab_total']} "
          f"t={best_result['tash_det']}/{best_result['tash_total']} "
          f"w={best_result['word_det']}/{best_result['word_total']}")

    # Phase 2: Try GFM corroboration
    print("\nPhase 2: GFM corroboration...")
    for gfm_pc in [-1.5, -2.0, -2.5, -3.0]:
        for gfm_sf in [-1.5, -2.0, -2.5, -3.0]:
            for gfm_votes in [2, 3]:
                trial = dict(best_params)
                trial["gfm_corroborate"] = True
                trial["gfm_corr_pc"] = gfm_pc
                trial["gfm_corr_sf"] = gfm_sf
                trial["gfm_corr_votes"] = gfm_votes
                r = evaluate(records, trial)
                s = score_result(r)
                if s > best_score and r["fp_rate"] <= 2.5:
                    best_score = s
                    best_params = trial
                    best_result = r
                    print(f"  gfm_corr pc={gfm_pc} sf={gfm_sf} votes={gfm_votes}: "
                          f"score={s:.1f} FP={r['fp_rate']:.1f}% "
                          f"i3={r['i3rab_det']}/{r['i3rab_total']}")

    # Phase 3: Word detection tiers
    print("\nPhase 3: Word detection tiers...")
    for cm_zero in [0.05, 0.10, 0.15, 0.20]:
        for fc_min in [4, 5, 6, 7]:
            for eff_low_max in [-0.5, -1.0, -1.5, -2.0]:
                trial = dict(best_params)
                trial["word_cm_zero"] = cm_zero
                trial["word_fc_min"] = fc_min
                trial["word_eff_low_max"] = eff_low_max
                r = evaluate(records, trial)
                s = score_result(r)
                if s > best_score and r["fp_rate"] <= 2.5:
                    best_score = s
                    best_params = trial
                    best_result = r
                    print(f"  word cm<={cm_zero} fc>={fc_min} eff<{eff_low_max}: "
                          f"score={s:.1f} FP={r['fp_rate']:.1f}% "
                          f"w={r['word_det']}/{r['word_total']}")

    # Phase 4: Vote thresholds
    print("\nPhase 4: Vote threshold tuning...")
    for vh in [1.5, 2, 2.5]:
        for vl in [2, 2.5, 3, 3.5]:
            for eb in [-1.5, -2.0, -2.5]:
                trial = dict(best_params)
                trial["vote_thresh_high"] = vh
                trial["vote_thresh_low"] = vl
                trial["eff_boundary"] = eb
                r = evaluate(records, trial)
                s = score_result(r)
                if s > best_score and r["fp_rate"] <= 2.5:
                    best_score = s
                    best_params = trial
                    best_result = r

    # Phase 5: GFM/GDM eff ranges
    print("\nPhase 5: Greedy eff ranges...")
    for gfm_eff in [-1.5, -1.8, -2.0, -2.5, -3.0]:
        for gdm_eff in [-1.0, -1.5, -2.0, -2.5]:
            trial = dict(best_params)
            trial["gfm_eff_min"] = gfm_eff
            trial["gdm_eff_min"] = gdm_eff
            r = evaluate(records, trial)
            s = score_result(r)
            if s > best_score and r["fp_rate"] <= 2.5:
                best_score = s
                best_params = trial
                best_result = r

    # Final result
    print(f"\n{'='*60}")
    print("BEST CONFIGURATION:")
    print(f"{'='*60}")
    print(f"Score:    {best_score:.1f}")
    print(f"FP rate:  {best_result['fp_rate']:.1f}% ({best_result['fp_count']}/{best_result['n_correct']})")
    i3_rate = best_result['i3rab_det'] / best_result['i3rab_total'] * 100
    t_rate = best_result['tash_det'] / best_result['tash_total'] * 100
    w_rate = best_result['word_det'] / best_result['word_total'] * 100
    print(f"I3rab:    {i3_rate:.0f}% ({best_result['i3rab_det']}/{best_result['i3rab_total']}) "
          f"type_correct={best_result['i3rab_type']}")
    print(f"Tashkeel: {t_rate:.0f}% ({best_result['tash_det']}/{best_result['tash_total']}) "
          f"type_correct={best_result['tash_type']}")
    print(f"Word:     {w_rate:.0f}% ({best_result['word_det']}/{best_result['word_total']}) "
          f"type_correct={best_result['word_type']}")
    print(f"\nParameters:")
    for k, v in sorted(best_params.items()):
        print(f"  {k}: {v}")

    # Also show a few configs at different FP levels
    print(f"\n{'='*60}")
    print("PARETO FRONTIER (FP vs Detection):")
    print(f"{'='*60}")

    # Collect all tried configs... actually let's just do a targeted sweep
    fp_targets = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
    for fp_target in fp_targets:
        # Find best config at this FP level
        pareto_best_score = -999
        pareto_best_result = None
        pareto_best_params = None

        # Quick sweep of key params
        for i3d_t in [0.04, 0.08, 0.12, 0.16, 0.20]:
            for td_t in [0.06, 0.10, 0.15, 0.20]:
                for pc_t in [-3.0, -3.5, -4.0, -4.5, -5.0]:
                    for sf_t in [-3.0, -3.5, -4.0, -4.5, -5.0]:
                        trial = dict(best_params)
                        trial["i3rab_delta_thresh"] = i3d_t
                        trial["tash_delta_thresh"] = td_t
                        trial["pc_thresh"] = pc_t
                        trial["sf_thresh"] = sf_t
                        r = evaluate(records, trial)
                        if r["fp_rate"] <= fp_target:
                            total_det = r["i3rab_det"] + r["tash_det"] + r["word_det"]
                            total_n = r["i3rab_total"] + r["tash_total"] + r["word_total"]
                            overall = total_det / total_n * 100 if total_n else 0
                            if overall > pareto_best_score:
                                pareto_best_score = overall
                                pareto_best_result = r
                                pareto_best_params = trial

        if pareto_best_result:
            r = pareto_best_result
            i3r = r['i3rab_det'] / r['i3rab_total'] * 100 if r['i3rab_total'] else 0
            tr = r['tash_det'] / r['tash_total'] * 100 if r['tash_total'] else 0
            wr = r['word_det'] / r['word_total'] * 100 if r['word_total'] else 0
            print(f"  FP<={fp_target:.1f}%: actual={r['fp_rate']:.1f}% "
                  f"i3={i3r:.0f}% t={tr:.0f}% w={wr:.0f}% "
                  f"overall={pareto_best_score:.0f}%")
            print(f"    i3d={pareto_best_params['i3rab_delta_thresh']} "
                  f"td={pareto_best_params['tash_delta_thresh']} "
                  f"pc={pareto_best_params['pc_thresh']} "
                  f"sf={pareto_best_params['sf_thresh']}")


def analyze_signal_distributions(records):
    """Print signal distribution stats for correct vs mutated words."""
    print("\n" + "="*60)
    print("SIGNAL DISTRIBUTIONS")
    print("="*60)

    correct = [r["signals"] for r in records if r["label"] == "correct"]
    i3rab = [r["signals"] for r in records if r.get("mutation_type") == "i3rab"]
    tashkeel = [r["signals"] for r in records if r.get("mutation_type") == "tashkeel"]
    word = [r["signals"] for r in records if r.get("mutation_type") == "word"]

    for sig_name in ["eff", "i3rab_delta", "tash_delta", "pc", "sf", "consonant_match"]:
        print(f"\n  {sig_name}:")
        for group_name, group in [("correct", correct), ("i3rab", i3rab),
                                   ("tashkeel", tashkeel), ("word", word)]:
            vals = [s[sig_name] for s in group if s.get(sig_name) is not None]
            if not vals:
                continue
            vals.sort()
            n = len(vals)
            p10 = vals[int(n * 0.1)]
            p25 = vals[int(n * 0.25)]
            p50 = vals[int(n * 0.5)]
            p75 = vals[int(n * 0.75)]
            p90 = vals[int(n * 0.9)]
            mean = sum(vals) / n
            print(f"    {group_name:10s} n={n:4d} "
                  f"p10={p10:+.3f} p25={p25:+.3f} med={p50:+.3f} "
                  f"p75={p75:+.3f} p90={p90:+.3f} mean={mean:+.3f}")

    # GFM rates
    print(f"\n  gfm (greedy final mismatch) rates:")
    for group_name, group in [("correct", correct), ("i3rab", i3rab),
                               ("tashkeel", tashkeel), ("word", word)]:
        gfm_true = sum(1 for s in group if s.get("gfm"))
        gfm_at_high_eff = sum(1 for s in group if s.get("gfm") and s["eff"] > -2.0)
        n = len(group)
        print(f"    {group_name:10s}: {gfm_true}/{n} ({gfm_true/n*100:.1f}%) "
              f"at eff>-2.0: {gfm_at_high_eff}")

    # GDM rates
    print(f"\n  gdm (greedy diac mismatches) rates:")
    for group_name, group in [("correct", correct), ("tashkeel", tashkeel)]:
        gdm_pos = sum(1 for s in group if s.get("gdm", 0) >= 1)
        gdm_at_high_eff = sum(1 for s in group if s.get("gdm", 0) >= 1 and s["eff"] > -1.5)
        n = len(group)
        print(f"    {group_name:10s}: {gdm_pos}/{n} ({gdm_pos/n*100:.1f}%) "
              f"at eff>-1.5: {gdm_at_high_eff}")


def main():
    dump_path = BASE / "signal_dump.json"
    if not dump_path.exists():
        print("signal_dump.json not found. Run dump_signals.py first.")
        return

    with open(dump_path) as f:
        records = json.load(f)

    n_correct = sum(1 for r in records if r["label"] == "correct")
    n_mutated = sum(1 for r in records if r["label"] != "correct")
    print(f"Loaded {len(records)} records ({n_correct} correct, {n_mutated} mutated)")

    analyze_signal_distributions(records)
    print()
    grid_search(records)


if __name__ == "__main__":
    main()
