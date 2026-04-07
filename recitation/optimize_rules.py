#!/usr/bin/env python3
"""Comprehensive offline rule optimization using signal_dump.json.

Simulates classify_words rules on cached signals to find optimal thresholds
without re-running the expensive CTC model.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))


def load_dump():
    with open(BASE / "signal_dump.json") as f:
        return json.load(f)


def safe(v, default=0.0):
    if v is None or v == 999 or v == 999.0:
        return default
    return float(v)


def simulate_classify(records, rules_fn):
    """Run rules on all records, return (fp_count, tp_count, tp_by_type, details)."""
    fp = 0
    tp = 0
    tp_by_type = defaultdict(int)
    fn_by_type = defaultdict(int)
    fp_details = []
    tp_details = []

    for rec in records:
        s = rec["signals"]
        is_mutated = rec["label"] == "mutated"
        mtype = rec.get("mutation_type")

        detected, det_type, det_detail = rules_fn(s)

        if is_mutated:
            if detected:
                tp += 1
                tp_by_type[mtype] += 1
                tp_details.append((rec, det_detail))
            else:
                fn_by_type[mtype] += 1
        else:
            if detected:
                fp += 1
                fp_details.append((rec, det_detail))

    return fp, tp, tp_by_type, fn_by_type, fp_details


def current_rules(s):
    """Replicate current server.py classify_words logic."""
    eff = s["eff"]
    word = s["word"]
    from arabic import strip_diacritics
    word_consonants = strip_diacritics(word)
    consonant_match = safe(s.get("consonant_match"), 1.0)
    frame_count = s.get("frame_count", 0)
    whisper_match = s.get("whisper_match", True)
    i3rab_delta = safe(s.get("i3rab_delta"))
    tash_delta = safe(s.get("tash_delta"))
    pc = safe(s.get("pc"), 999.0)
    sf = safe(s.get("sf"), 999.0)
    mg = safe(s.get("mg"), 999.0)
    gdm = s.get("gdm", 0)
    gfm = s.get("gfm", False)
    pd_i3 = safe(s.get("pd_i3rab"))
    pd_t = safe(s.get("pd_tashkeel"))
    lpd_i = safe(s.get("local_pd_i3rab"))
    lpd_t = safe(s.get("local_pd_tashkeel"))
    fs = safe(s.get("fs_worst_delta"), 999.0)
    rescored_eff = s.get("rescored_eff")
    rescored_sf = safe(s.get("rescored_sf"), 999.0)
    rescored_gfm = s.get("rescored_gfm", False)
    rescored_i3d = safe(s.get("rescored_i3rab_delta"))
    rescored_td = safe(s.get("rescored_tash_delta"))
    skip_i3rab = s.get("skip_i3rab", False)
    skip_tashkeel = s.get("skip_tashkeel", False)
    sukoon_delta = safe(s.get("sukoon_delta"))

    # Whisper mismatch at low eff
    if (not whisper_match and eff < -1.6
            and len(word_consonants) >= 3 and frame_count >= 5):
        return True, "wrong", "whisper_mismatch"

    # Whisper wrong word at higher eff
    if (not whisper_match and eff > -1.0
            and consonant_match <= 0.40 and frame_count >= 15
            and len(word_consonants) >= 3):
        return True, "wrong", "whisper_cm_fc"

    # Skipped word
    if (frame_count < 3 and eff < -3.5 and len(word_consonants) >= 3):
        return True, "skipped", "skipped"

    # pd_cm_mismatch
    if (eff <= -1.5 and len(word_consonants) >= 3
            and consonant_match <= 0.25 and pd_i3 >= 0.60 and frame_count >= 5):
        return True, "wrong", "pd_cm_mismatch"

    # pd_strong
    if (eff <= -1.5 and len(word_consonants) >= 3
            and pd_i3 >= 1.0 and frame_count >= 5):
        return True, "wrong", "pd_strong"

    # pd_cm_moderate
    if (-1.5 < eff <= -1.0 and len(word_consonants) >= 3
            and consonant_match <= 0.25 and pd_i3 >= 0.20 and frame_count >= 5):
        return True, "wrong", "pd_cm_moderate"

    # Rescued low-eff
    if (eff <= -1.5 and rescored_eff is not None and rescored_eff > -1.5):
        if rescored_gfm:
            return True, "i3rab", "rescue_gfm"
        if rescored_i3d >= 0.10 and pd_i3 >= 0.15:
            return True, "i3rab", "rescue_pd"
        if rescored_td >= 0.10:
            return True, "tashkeel", "rescue_td"
        if pd_t >= 0.30:
            return True, "tashkeel", "rescue_pd_t"

    # Triple signal at low eff
    td_val = tash_delta
    if (eff <= -1.5 and td_val >= 0.05 and pd_i3 >= 0.20 and pd_t >= 0.20):
        if pd_t > pd_i3:
            return True, "tashkeel", "low_eff_triple"
        else:
            return True, "i3rab", "low_eff_triple"

    # Local pd
    if eff <= -1.5:
        if lpd_t >= 0.70 and pd_t >= 0.15:
            if lpd_t > lpd_i:
                return True, "tashkeel", "local_pd_t"
            else:
                return True, "i3rab", "local_pd_i"

    # Frame scan + sf
    if eff <= -1.5:
        if fs < -2.0 and sf < -4.0:
            return True, "tashkeel", "fs_sf_combo"

    # ── Eff-adaptive tiers ──
    # Tier 1: sf_gop < -5.0 (very strong)
    if sf < -5.0:
        return True, "tashkeel", "tier1_sf"

    # Tier 2: greedy final mismatch + confirming signals
    if (not skip_i3rab and gfm and eff > -1.5
            and len(word_consonants) >= 3 and frame_count >= 8):
        if eff > -0.5:
            return True, "i3rab", "tier2_gfm_high"
        elif eff > -1.0 and sf < -1.5:
            return True, "i3rab", "tier2_gfm_mid"
        elif sf < -2.5 and i3rab_delta >= 0.03:
            return True, "i3rab", "tier2_gfm_low"

    # Tier 3: per-char
    if pc < -999:
        pass  # sentinel
    elif eff > -0.5 and pc < -4.0:
        return True, "tashkeel", "tier3_pc_high"
    elif -0.5 >= eff > -1.0 and pc < -4.0 and sf < -2.0:
        return True, "tashkeel", "tier3_pc_mid"
    elif -1.0 >= eff > -1.5 and pc < -5.0 and sf < -3.0:
        return True, "tashkeel", "tier3_pc_low"

    # Tier 4: sf + consonant
    if (eff > -0.5 and sf < -2.5 and consonant_match >= 0.75
            and not skip_tashkeel and len(word_consonants) >= 3
            and frame_count >= 8):
        return True, "tashkeel", "tier4_sf_high"
    if (eff > -1.0 and sf < -3.0 and consonant_match >= 0.60
            and not skip_tashkeel and len(word_consonants) >= 3
            and frame_count >= 8):
        return True, "tashkeel", "tier4_sf_mid"

    # Tier 5: i3rab_delta + sf
    alt = s.get("expected_score", -999) + i3rab_delta if i3rab_delta else -999
    if (alt > -900 and eff > -1.3
            and i3rab_delta >= 0.03 and sf < -3.0
            and (tash_delta <= 0 or i3rab_delta >= tash_delta)):
        return True, "i3rab", "tier5_i3d_sf"

    # pd-based tiers
    if eff > -0.5 and pd_i3 >= 0.10:
        return True, "i3rab", "pd_i3_high"
    if -0.5 >= eff > -1.0 and pd_i3 >= 0.15:
        return True, "i3rab", "pd_i3_mid"
    if -1.0 >= eff > -1.5 and pd_i3 >= 0.20:
        return True, "i3rab", "pd_i3_low"

    if eff > -0.5 and pd_t >= 0.15:
        if pd_t >= 0.25 or sf < -1.5:
            return True, "tashkeel", "pd_t_high"
    if -0.5 >= eff > -1.0 and pd_t >= 0.25:
        return True, "tashkeel", "pd_t_mid"
    if -1.0 >= eff > -1.5 and pd_t >= 0.45:
        return True, "tashkeel", "pd_t_low"

    # pd corroboration
    if (eff > -1.5 and pd_i3 >= 0.05 and i3rab_delta >= 0.05
            and sf < -2.0):
        return True, "i3rab", "pd_corr_i3"
    if (eff > -1.5 and pd_t >= 0.10 and tash_delta >= 0.05
            and sf < -2.5):
        return True, "tashkeel", "pd_corr_t"
    if (eff > -1.5 and pd_i3 >= 0.05 and i3rab_delta >= 0.03
            and consonant_match >= 0.75):
        return True, "i3rab", "pd_corr_i3_cm"

    return False, None, None


def main():
    dump = load_dump()
    n_correct = sum(1 for r in dump if r["label"] == "correct")
    n_mutated = sum(1 for r in dump if r["label"] == "mutated")

    # Run current rules
    fp, tp, tp_by_type, fn_by_type, fp_details = simulate_classify(dump, current_rules)
    print("CURRENT RULES SIMULATION:")
    print(f"  FP: {fp}/{n_correct} ({100*fp/n_correct:.1f}%)")
    print(f"  Detection: {tp}/{n_mutated} ({100*tp/n_mutated:.1f}%)")
    for t in ["i3rab", "tashkeel", "word"]:
        total = tp_by_type[t] + fn_by_type[t]
        print(f"  {t}: {tp_by_type[t]}/{total} ({100*tp_by_type[t]/total:.1f}%)")
    print(f"\n  FP details:")
    for rec, detail in fp_details:
        s = rec["signals"]
        print(f"    {s['word']:20s} eff={s['eff']:.3f} rule={detail}")

    # ── Analyze MISSED mutations ──
    print("\n\n" + "=" * 70)
    print("MISSED MUTATIONS ANALYSIS")
    print("=" * 70)

    missed = []
    for rec in dump:
        if rec["label"] != "mutated":
            continue
        s = rec["signals"]
        detected, _, _ = current_rules(s)
        if not detected:
            missed.append(rec)

    print(f"\nMissed: {len(missed)}/{n_mutated}")
    by_type = defaultdict(list)
    for rec in missed:
        by_type[rec["mutation_type"]].append(rec)

    for mtype in ["i3rab", "tashkeel", "word"]:
        recs = by_type[mtype]
        if not recs:
            continue
        print(f"\n  {mtype} missed: {len(recs)}")

        # Eff distribution
        effs = [r["signals"]["eff"] for r in recs]
        low = sum(1 for e in effs if e < -1.5)
        mid = sum(1 for e in effs if -1.5 <= e < -1.0)
        hi = sum(1 for e in effs if e >= -1.0)
        print(f"    eff < -1.5: {low}, -1.5 to -1.0: {mid}, > -1.0: {hi}")

        # Signal stats for missed
        for sig in ["sf", "pc", "mg", "pd_i3rab", "pd_tashkeel", "i3rab_delta", "tash_delta", "fs_worst_delta"]:
            vals = [safe(r["signals"].get(sig), 0.0) for r in recs]
            nonzero = sum(1 for v in vals if v != 0.0 and v != 999.0)
            if nonzero > 0:
                nz = [v for v in vals if v != 0.0 and v != 999.0]
                print(f"    {sig:20s}: nonzero={nonzero}/{len(recs)} mean={sum(nz)/len(nz):.3f} min={min(nz):.3f} max={max(nz):.3f}")

    # ── Try new rule candidates on missed ──
    print("\n\n" + "=" * 70)
    print("NEW RULE CANDIDATES")
    print("=" * 70)

    correct = [r for r in dump if r["label"] == "correct"]

    # Build candidate rules and test them
    from arabic import strip_diacritics
    candidates = []

    # Rule: sf-based with different thresholds at eff < -1.5
    for sf_th in [-3.0, -3.5, -4.0, -4.5]:
        for pd_th in [0.0, 0.05, 0.10, 0.15]:
            def make_rule(sf_th=sf_th, pd_th=pd_th):
                def rule(s):
                    if s["eff"] >= -1.5:
                        return False
                    if safe(s.get("sf"), 999) >= sf_th:
                        return False
                    if pd_th > 0 and max(safe(s.get("pd_i3rab")), safe(s.get("pd_tashkeel"))) < pd_th:
                        return False
                    return True
                return rule
            r = make_rule()
            fp_new = sum(1 for rec in correct if not current_rules(rec["signals"])[0] and r(rec["signals"]))
            tp_new = sum(1 for rec in missed if r(rec["signals"]))
            if tp_new >= 5 and fp_new <= 2:
                candidates.append((f"sf<{sf_th} + pd>={pd_th} at eff<-1.5", fp_new, tp_new, r))

    # Rule: mg-based at eff < -1.5
    for mg_th in [-50, -60, -70, -80, -100]:
        for pd_th in [0.0, 0.10, 0.15]:
            def make_rule(mg_th=mg_th, pd_th=pd_th):
                def rule(s):
                    if s["eff"] >= -1.5:
                        return False
                    if safe(s.get("mg"), 999) >= mg_th:
                        return False
                    if pd_th > 0 and max(safe(s.get("pd_i3rab")), safe(s.get("pd_tashkeel"))) < pd_th:
                        return False
                    return True
                return rule
            r = make_rule()
            fp_new = sum(1 for rec in correct if not current_rules(rec["signals"])[0] and r(rec["signals"]))
            tp_new = sum(1 for rec in missed if r(rec["signals"]))
            if tp_new >= 5 and fp_new <= 2:
                candidates.append((f"mg<{mg_th} + pd>={pd_th} at eff<-1.5", fp_new, tp_new, r))

    # Rule: pd alone at eff < -1.5 (lower than current triple requires)
    for pd_i_th in [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]:
        for sf_th in [999, -1.0, -2.0, -3.0]:
            def make_rule(pd_i_th=pd_i_th, sf_th=sf_th):
                def rule(s):
                    if s["eff"] >= -1.5:
                        return False
                    if safe(s.get("pd_i3rab")) < pd_i_th:
                        return False
                    if sf_th < 999 and safe(s.get("sf"), 999) >= sf_th:
                        return False
                    return True
                return rule
            r = make_rule()
            fp_new = sum(1 for rec in correct if not current_rules(rec["signals"])[0] and r(rec["signals"]))
            tp_new = sum(1 for rec in missed if r(rec["signals"]))
            if tp_new >= 5 and fp_new <= 2:
                candidates.append((f"pd_i>={pd_i_th} + sf<{sf_th} at eff<-1.5", fp_new, tp_new, r))

    # pd_tashkeel alone
    for pd_t_th in [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]:
        for sf_th in [999, -1.0, -2.0, -3.0]:
            def make_rule(pd_t_th=pd_t_th, sf_th=sf_th):
                def rule(s):
                    if s["eff"] >= -1.5:
                        return False
                    if safe(s.get("pd_tashkeel")) < pd_t_th:
                        return False
                    if sf_th < 999 and safe(s.get("sf"), 999) >= sf_th:
                        return False
                    return True
                return rule
            r = make_rule()
            fp_new = sum(1 for rec in correct if not current_rules(rec["signals"])[0] and r(rec["signals"]))
            tp_new = sum(1 for rec in missed if r(rec["signals"]))
            if tp_new >= 5 and fp_new <= 2:
                candidates.append((f"pd_t>={pd_t_th} + sf<{sf_th} at eff<-1.5", fp_new, tp_new, r))

    # Frame scan combos
    for fs_th in [-1.0, -1.5, -2.0, -3.0]:
        for pd_th in [0.0, 0.05, 0.10]:
            def make_rule(fs_th=fs_th, pd_th=pd_th):
                def rule(s):
                    if s["eff"] >= -1.5:
                        return False
                    if safe(s.get("fs_worst_delta"), 999) >= fs_th:
                        return False
                    if pd_th > 0 and max(safe(s.get("pd_i3rab")), safe(s.get("pd_tashkeel"))) < pd_th:
                        return False
                    return True
                return rule
            r = make_rule()
            fp_new = sum(1 for rec in correct if not current_rules(rec["signals"])[0] and r(rec["signals"]))
            tp_new = sum(1 for rec in missed if r(rec["signals"]))
            if tp_new >= 3 and fp_new <= 2:
                candidates.append((f"fs<{fs_th} + pd>={pd_th} at eff<-1.5", fp_new, tp_new, r))

    # Tashkeel delta + pd at eff < -1.5 (relaxed triple)
    for td_th in [0.02, 0.03, 0.05]:
        for pd_th in [0.05, 0.10, 0.15]:
            def make_rule(td_th=td_th, pd_th=pd_th):
                def rule(s):
                    if s["eff"] >= -1.5:
                        return False
                    if safe(s.get("tash_delta")) < td_th:
                        return False
                    if max(safe(s.get("pd_i3rab")), safe(s.get("pd_tashkeel"))) < pd_th:
                        return False
                    return True
                return rule
            r = make_rule()
            fp_new = sum(1 for rec in correct if not current_rules(rec["signals"])[0] and r(rec["signals"]))
            tp_new = sum(1 for rec in missed if r(rec["signals"]))
            if tp_new >= 5 and fp_new <= 2:
                candidates.append((f"td>={td_th} + pd>={pd_th} at eff<-1.5", fp_new, tp_new, r))

    # i3rab_delta + pd at eff < -1.5
    for i3d_th in [0.02, 0.03, 0.05]:
        for pd_th in [0.05, 0.10, 0.15]:
            def make_rule(i3d_th=i3d_th, pd_th=pd_th):
                def rule(s):
                    if s["eff"] >= -1.5:
                        return False
                    if safe(s.get("i3rab_delta")) < i3d_th:
                        return False
                    if max(safe(s.get("pd_i3rab")), safe(s.get("pd_tashkeel"))) < pd_th:
                        return False
                    return True
                return rule
            r = make_rule()
            fp_new = sum(1 for rec in correct if not current_rules(rec["signals"])[0] and r(rec["signals"]))
            tp_new = sum(1 for rec in missed if r(rec["signals"]))
            if tp_new >= 5 and fp_new <= 2:
                candidates.append((f"i3d>={i3d_th} + pd>={pd_th} at eff<-1.5", fp_new, tp_new, r))

    # Higher eff: tighten existing thresholds
    # Check if we can lower pd thresholds at eff > -1.0
    for eff_lo, eff_hi in [(-1.0, -0.5), (-0.5, 0.0), (0.0, 999)]:
        for pd_th in [0.05, 0.08, 0.10]:
            def make_rule(eff_lo=eff_lo, eff_hi=eff_hi, pd_th=pd_th):
                def rule(s):
                    if s["eff"] < eff_lo or s["eff"] >= eff_hi:
                        return False
                    if safe(s.get("pd_i3rab")) < pd_th:
                        return False
                    return True
                return rule
            r = make_rule()
            fp_new = sum(1 for rec in correct if not current_rules(rec["signals"])[0] and r(rec["signals"]))
            tp_new = sum(1 for rec in missed if r(rec["signals"]))
            if tp_new >= 2 and fp_new <= 1:
                candidates.append((f"pd_i>={pd_th} at eff[{eff_lo},{eff_hi})", fp_new, tp_new, r))

    # Sort by tp/fp ratio then tp
    candidates.sort(key=lambda x: (-x[2], x[1]))

    print(f"\nFound {len(candidates)} promising rules:")
    seen_names = set()
    for name, fp_new, tp_new, r in candidates[:40]:
        if name in seen_names:
            continue
        seen_names.add(name)
        # Show per-type catches
        tp_types = defaultdict(int)
        for rec in missed:
            if r(rec["signals"]):
                tp_types[rec["mutation_type"]] += 1
        type_str = " ".join(f"{t}={tp_types[t]}" for t in ["i3rab", "tashkeel", "word"] if tp_types[t])
        print(f"  {name:50s} FP={fp_new}  catches={tp_new}  {type_str}")


if __name__ == "__main__":
    main()
