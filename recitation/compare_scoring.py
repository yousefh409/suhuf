#!/usr/bin/env python3
"""Compare independent vs joint scoring on the 23 test recordings."""

import io
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf


def read_audio(filepath: Path) -> np.ndarray:
    audio_bytes = filepath.read_bytes()
    try:
        audio_data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    except Exception:
        import av
        container = av.open(io.BytesIO(audio_bytes))
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        frames = []
        for frame in container.decode(audio=0):
            for r in resampler.resample(frame):
                frames.append(r.to_ndarray().flatten())
        container.close()
        audio_data = np.concatenate(frames).astype(np.float32) / 32768.0
        return audio_data
    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)
    if sr != 16000:
        from scipy.signal import resample
        num_samples = int(len(audio_data) * 16000 / sr)
        audio_data = resample(audio_data, num_samples).astype(np.float32)
    return audio_data


def run_test(config_name, config):
    from i3rab.pcd_transcriber import PCDTranscriber
    from i3rab.book import Book
    from i3rab.pipeline import I3rabPipeline

    test_dir = Path("test_data")
    manifest = json.loads((test_dir / "manifest.json").read_text())
    sentences = [e for e in manifest if e.get("type") == "sentence"]

    transcriber = PCDTranscriber(config)
    transcriber.load()

    total_correct = 0
    total_words = 0
    errors = []
    t0 = time.time()

    for entry in sentences:
        filepath = test_dir / entry["filename"]
        if not filepath.exists():
            continue

        audio = read_audio(filepath)
        reference = entry["text_diacritized"]
        book = Book.from_sentence(reference)
        pip = I3rabPipeline(book, config)
        pip._pcd_transcriber = transcriber

        result = pip.evaluate_pcd_live(audio)

        for sw in result["scored_words"]:
            total_words += 1
            if sw["kind"] in ("correct", "pausal_ok"):
                total_correct += 1
            else:
                errors.append({
                    "rec": entry["id"],
                    "kind": sw["kind"],
                    "ref": sw["ref_word"],
                    "hyp": sw.get("hyp_word"),
                    "det_case": sw.get("detected_case"),
                    "exp_case": sw.get("expected_case"),
                })

    elapsed = time.time() - t0
    print(f"\n{config_name}: {total_correct}/{total_words} "
          f"({100*total_correct/total_words:.1f}%) in {elapsed:.1f}s")

    if errors:
        print(f"  Errors ({len(errors)}):")
        for e in errors:
            print(f"    {e['rec']}: {e['kind']} — {e['ref']} → {e['hyp']} "
                  f"(exp={e['exp_case']}, det={e['det_case']})")

    return total_correct, total_words, errors


def main():
    from i3rab.config import Config

    print("=" * 60)
    print("Scoring Comparison: Independent vs Joint")
    print("=" * 60)

    # Test 1: Independent (current)
    config_indep = Config()
    config_indep.use_joint_scoring = False
    c1, w1, e1 = run_test("INDEPENDENT", config_indep)

    # Test 2: Joint
    config_joint = Config()
    config_joint.use_joint_scoring = True
    c2, w2, e2 = run_test("JOINT", config_joint)

    # Compare
    print(f"\n{'='*60}")
    print(f"Independent: {c1}/{w1} ({100*c1/w1:.1f}%)")
    print(f"Joint:       {c2}/{w2} ({100*c2/w2:.1f}%)")
    if c2 > c1:
        print(f"  Joint is BETTER by {c2-c1} words")
    elif c2 < c1:
        print(f"  Joint is WORSE by {c1-c2} words")
    else:
        print(f"  Both are EQUAL")

    # Show differences
    e1_set = {(e["rec"], e["ref"]) for e in e1}
    e2_set = {(e["rec"], e["ref"]) for e in e2}
    fixed = e1_set - e2_set
    regressed = e2_set - e1_set
    if fixed:
        print(f"\n  Fixed by joint ({len(fixed)}):")
        for rec, ref in fixed:
            print(f"    {rec}: {ref}")
    if regressed:
        print(f"\n  Regressed by joint ({len(regressed)}):")
        for rec, ref in regressed:
            print(f"    {rec}: {ref}")


if __name__ == "__main__":
    main()
