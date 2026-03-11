#!/usr/bin/env python3
"""Test the forced-alignment PCD approach: alignment + per-word decode/score."""

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


def main():
    from i3rab.config import Config
    from i3rab.pcd_transcriber import PCDTranscriber
    from i3rab.book import Book
    from i3rab.pipeline import I3rabPipeline
    from i3rab.arabic import normalize_arabic, strip_harakat

    config = Config()

    # Load model once
    transcriber = PCDTranscriber(config)
    transcriber.load()

    test_dir = Path("test_data")
    manifest = json.loads((test_dir / "manifest.json").read_text())
    sentences = [e for e in manifest if e.get("type") == "sentence"]

    # ── Test 1: Forced alignment basics ──────────────────────────────
    print("=" * 60)
    print("Test 1: Forced alignment on rec_016")
    print("=" * 60)

    entry = sentences[0]
    audio = read_audio(test_dir / entry["filename"])
    reference = entry["text_diacritized"]

    t0 = time.time()
    log_probs, encoded_len, _encoded = transcriber.encode(audio)
    t_encode = time.time() - t0

    # Free transcript for comparison
    free_transcript = transcriber.greedy_decode(log_probs, encoded_len)
    print(f"  Free transcript: {free_transcript}")

    # Forced alignment
    ref_words = normalize_arabic(reference).split()
    ref_text = " ".join(ref_words)

    t0 = time.time()
    alignment, scores = transcriber.forced_align_reference(
        log_probs, encoded_len, ref_text
    )
    t_align = time.time() - t0

    if alignment is not None:
        boundaries = transcriber.get_word_boundaries(alignment, scores, ref_words)
        print(f"  Encode: {t_encode*1000:.0f}ms, Align: {t_align*1000:.0f}ms")
        print(f"  Frames: {encoded_len[0].item()}, Words: {len(ref_words)}")
        print()
        for wb in boundaries:
            decoded = transcriber.decode_word_segment(log_probs, wb.start_frame, wb.end_frame)
            decoded_norm = normalize_arabic(decoded) if decoded else ""
            match = "OK" if strip_harakat(decoded_norm) == strip_harakat(ref_words[wb.word_idx]) else "XX"
            print(f"  [{match}] {ref_words[wb.word_idx]:20s} → {decoded_norm:20s}  frames=[{wb.start_frame}:{wb.end_frame}] score={wb.score:.2f}")
    else:
        print("  Forced alignment FAILED (not enough frames)")

    # ── Test 2: Full evaluate_pcd_live with forced alignment ─────────
    print("\n" + "=" * 60)
    print("Test 2: evaluate_pcd_live (forced alignment)")
    print("=" * 60)

    book = Book.from_sentence(reference)
    pipeline = I3rabPipeline(book, config)
    # Share the already-loaded transcriber
    pipeline._pcd_transcriber = transcriber

    t0 = time.time()
    result = pipeline.evaluate_pcd_live(audio)
    t_total = time.time() - t0

    print(f"  Time: {t_total*1000:.0f}ms")
    print(f"  Matched: {result['matched_indices']}")
    print()

    if result["scored_words"]:
        correct = 0
        total = len(result["scored_words"])
        for sw in result["scored_words"]:
            mark = "OK" if sw["kind"] in ("correct", "pausal_ok") else "XX"
            if mark == "OK":
                correct += 1
            hyp = sw.get("hyp_word") or "?"
            print(f"  [{mark}] {sw['ref_word']:20s} → {hyp:20s}  ({sw['kind']}, {sw['confidence']})")
        print(f"\n  Score: {correct}/{total}")

    # ── Test 3: All sentence recordings ──────────────────────────────
    print("\n" + "=" * 60)
    print("Test 3: All sentence recordings")
    print("=" * 60)

    total_correct = 0
    total_words = 0
    total_time_ms = 0

    for entry in sentences:
        filepath = test_dir / entry["filename"]
        if not filepath.exists():
            continue

        audio = read_audio(filepath)
        reference = entry["text_diacritized"]
        book = Book.from_sentence(reference)
        pip = I3rabPipeline(book, config)
        pip._pcd_transcriber = transcriber

        t0 = time.time()
        result = pip.evaluate_pcd_live(audio)
        elapsed = (time.time() - t0) * 1000
        total_time_ms += elapsed

        correct = sum(1 for sw in result["scored_words"] if sw["kind"] in ("correct", "pausal_ok"))
        total = len(result["scored_words"])
        total_correct += correct
        total_words += total

        status = "OK" if total > 0 and correct == total else f"{correct}/{total}"
        print(f"  {entry['id']}: {status:8s} ({elapsed:.0f}ms)  {reference[:50]}...")

    if total_words > 0:
        print(f"\n  Overall: {total_correct}/{total_words} ({100*total_correct/total_words:.1f}%)")
        print(f"  Avg time: {total_time_ms/len(sentences):.0f}ms per recording")


if __name__ == "__main__":
    main()
