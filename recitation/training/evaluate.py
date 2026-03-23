#!/usr/bin/env python3
"""Evaluate fine-tuned PCD model on diacritics quality and i3rab test cases.

Tests:
  1. General diacritics: Does the model output diacritized text on ClArTTS test set?
  2. Diacritics accuracy: Character-level diacritics error rate (DER)
  3. i3rab hypothesis scoring: CTC scoring on error/control cases
  4. Transcribe-then-diff: Does transcription match expected diacritized text?

Usage:
  python training/evaluate.py --model checkpoints/pcd_clartts_final.nemo
  python training/evaluate.py --model checkpoints/pcd_clartts_final.nemo --test-i3rab
"""

import argparse
import io
import json
import sys
from pathlib import Path

import numpy as np
import torch


def load_model(model_path: str):
    """Load fine-tuned NeMo model."""
    import nemo.collections.asr as nemo_asr

    if model_path.endswith(".nemo"):
        model = nemo_asr.models.EncDecHybridRNNTCTCBPEModel.restore_from(model_path)
    else:
        model = nemo_asr.models.EncDecHybridRNNTCTCBPEModel.from_pretrained(model_path)

    # Disable CUDA graphs (known NeMo bug)
    for name, module in model.named_modules():
        if hasattr(module, 'cuda_graphs_mode'):
            module.cuda_graphs_mode = None

    model.eval()
    return model


def to_text(hyp) -> str:
    """Extract text from NeMo transcription result (str or Hypothesis)."""
    if isinstance(hyp, str):
        return hyp
    if hasattr(hyp, 'text'):
        return hyp.text
    return str(hyp)


def count_diacritics(text: str) -> int:
    """Count diacritical marks in text."""
    return sum(1 for ch in text if "\u064B" <= ch <= "\u0652")


def strip_harakat(text: str) -> str:
    """Remove diacritical marks from text."""
    return "".join(ch for ch in text if not ("\u064B" <= ch <= "\u0652"))


def diacritics_error_rate(ref: str, hyp: str) -> float:
    """Compute Diacritics Error Rate (DER).

    Compares diacritics at each character position.
    Returns: fraction of character positions where diacritics differ.
    """
    # Align by base characters (without diacritics)
    def decompose(text):
        """Split text into (base_char, [diacritics]) pairs."""
        result = []
        current_base = None
        current_diac = []
        for ch in text:
            if "\u064B" <= ch <= "\u0652":
                current_diac.append(ch)
            else:
                if current_base is not None:
                    result.append((current_base, tuple(sorted(current_diac))))
                current_base = ch
                current_diac = []
        if current_base is not None:
            result.append((current_base, tuple(sorted(current_diac))))
        return result

    ref_decomp = decompose(ref)
    hyp_decomp = decompose(hyp)

    # Simple: compare position by position (requires same base text)
    if len(ref_decomp) != len(hyp_decomp):
        # Fall back to counting diacritics presence
        ref_count = count_diacritics(ref)
        hyp_count = count_diacritics(hyp)
        if ref_count == 0:
            return 1.0 if hyp_count == 0 else 0.0
        return abs(ref_count - hyp_count) / ref_count

    total = 0
    errors = 0
    for (rb, rd), (hb, hd) in zip(ref_decomp, hyp_decomp):
        if rb == hb:  # same base char
            total += 1
            if rd != hd:
                errors += 1
        else:
            total += 1
            errors += 1

    return errors / total if total > 0 else 0.0


def evaluate_clartts(model, data_dir: Path, decoder: str = "ctc"):
    """Evaluate diacritics quality on ClArTTS test set."""
    test_manifest = data_dir / "clartts" / "test_manifest.json"
    if not test_manifest.exists():
        print(f"Test manifest not found: {test_manifest}")
        return

    with open(test_manifest, "r") as f:
        entries = [json.loads(line) for line in f]

    print(f"\n{'='*60}")
    print(f"ClArTTS Test Set Evaluation ({len(entries)} samples)")
    print(f"{'='*60}")

    model.change_decoding_strategy(decoder_type=decoder)

    total_diac_in_ref = 0
    total_diac_in_hyp = 0
    total_der = 0.0
    total_wer_samples = 0
    n_with_diacritics = 0

    audio_paths = [e["audio_filepath"] for e in entries]

    # Batch transcribe
    transcriptions = model.transcribe(audio_paths, batch_size=16)

    for entry, raw_hyp in zip(entries, transcriptions):
        hyp = to_text(raw_hyp)
        ref = entry["text"]
        ref_diac = count_diacritics(ref)
        hyp_diac = count_diacritics(hyp)

        total_diac_in_ref += ref_diac
        total_diac_in_hyp += hyp_diac

        if hyp_diac > 0:
            n_with_diacritics += 1

        der = diacritics_error_rate(ref, hyp)
        total_der += der
        total_wer_samples += 1

    avg_der = total_der / total_wer_samples if total_wer_samples > 0 else 0

    print(f"\nResults:")
    print(f"  Samples with diacritics: {n_with_diacritics}/{len(entries)} ({100*n_with_diacritics/len(entries):.1f}%)")
    print(f"  Diacritics in reference: {total_diac_in_ref}")
    print(f"  Diacritics in output:    {total_diac_in_hyp}")
    print(f"  Diacritic coverage:      {100*total_diac_in_hyp/total_diac_in_ref:.1f}%")
    print(f"  Average DER:             {100*avg_der:.2f}%")

    # Show some examples
    print(f"\nExamples:")
    for entry, raw_hyp in list(zip(entries, transcriptions))[:5]:
        hyp = to_text(raw_hyp)
        ref = entry["text"]
        has_diac = "DIAC" if count_diacritics(hyp) > 0 else "PLAIN"
        print(f"\n  [{has_diac}]")
        print(f"    ref:  {ref[:80]}")
        print(f"    pred: {hyp[:80]}")


def evaluate_i3rab(model, i3rab_dir: Path, decoder: str = "ctc"):
    """Evaluate on i3rab test cases using transcribe-then-diff approach."""
    test_data_dir = i3rab_dir / "test_data"
    manifest_path = test_data_dir / "manifest.json"

    if not manifest_path.exists():
        print(f"i3rab manifest not found: {manifest_path}")
        return

    manifest = json.loads(manifest_path.read_text())
    sentence_entries = [e for e in manifest if e.get("type") == "sentence"]

    print(f"\n{'='*60}")
    print(f"i3rab Transcribe-then-Diff Evaluation ({len(sentence_entries)} sentences)")
    print(f"{'='*60}")

    model.change_decoding_strategy(decoder_type=decoder)

    audio_paths = []
    for entry in sentence_entries:
        filepath = test_data_dir / entry["filename"]
        audio_paths.append(str(filepath))

    transcriptions = model.transcribe(audio_paths, batch_size=8)

    total_words = 0
    correct_words = 0
    diac_errors = []

    for entry, raw_hyp in zip(sentence_entries, transcriptions):
        hyp = to_text(raw_hyp)
        ref = entry["text_diacritized"]
        ref_words = ref.split()
        hyp_words = hyp.split()

        has_diac = count_diacritics(hyp) > 0
        mark = "DIAC" if has_diac else "PLAIN"

        # Simple word-level comparison
        # For each reference word, find best match in hypothesis
        matched = 0
        for rw in ref_words:
            rw_base = strip_harakat(rw)
            for hw in hyp_words:
                hw_base = strip_harakat(hw)
                if rw_base == hw_base:
                    # Base word matches, check diacritics
                    if rw == hw:
                        matched += 1
                    else:
                        diac_errors.append({
                            "rec": entry["id"],
                            "expected": rw,
                            "got": hw,
                        })
                    break

        total_words += len(ref_words)
        correct_words += matched

        print(f"\n  [{mark}] {entry['id']}")
        print(f"    ref:  {ref[:80]}")
        print(f"    pred: {hyp[:80]}")
        if matched < len(ref_words):
            print(f"    matched: {matched}/{len(ref_words)} words")

    print(f"\n{'='*60}")
    print(f"Word-level accuracy: {correct_words}/{total_words} ({100*correct_words/total_words:.1f}%)")
    print(f"Diacritics mismatches: {len(diac_errors)}")

    if diac_errors:
        print(f"\nDiacritics errors:")
        for err in diac_errors[:10]:
            print(f"  {err['rec']}: expected '{err['expected']}' got '{err['got']}'")


def evaluate_ctc_scoring(model, i3rab_dir: Path):
    """Test CTC hypothesis scoring with the fine-tuned model's CTC head."""
    sys.path.insert(0, str(i3rab_dir))
    from i3rab.book import Book

    test_data_dir = i3rab_dir / "test_data"
    manifest_path = test_data_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest_by_id = {e["id"]: e for e in manifest}

    ERROR_CASES = [
        {"rec": "rec_031", "word": "\u0633\u064e\u0623\u064e\u0644\u064e", "correct_case": "acc"},
        {"rec": "rec_039", "word": "\u0623\u064e\u0639\u064e\u062f\u0651\u064e\u062a\u0650", "correct_case": "gen"},
        {"rec": "rec_039", "word": "\u0627\u0644\u0644\u0651\u064e\u0630\u0650\u064a\u0630\u064e", "correct_case": "acc"},
        {"rec": "rec_040", "word": "\u0627\u0644\u0637\u0651\u064e\u0627\u0632\u0650\u062c\u064e", "correct_case": "acc"},
    ]

    CONTROL_CASES = [
        {"rec": "rec_016", "word": "\u0627\u0644\u0637\u0651\u064e\u0627\u0644\u0650\u0628\u064f", "correct_case": "nom"},
        {"rec": "rec_016", "word": "\u0627\u0644\u0643\u0650\u062a\u064e\u0627\u0628\u064e", "correct_case": "acc"},
        {"rec": "rec_016", "word": "\u0627\u0644\u0645\u064e\u0643\u0652\u062a\u064e\u0628\u064e\u0629\u0650", "correct_case": "gen"},
        {"rec": "rec_019", "word": "\u0627\u0644\u0648\u064e\u0644\u064e\u062f\u064f", "correct_case": "nom"},
        {"rec": "rec_032", "word": "\u0627\u0644\u0639\u0650\u0644\u0652\u0645\u064f", "correct_case": "nom"},
        {"rec": "rec_032", "word": "\u0627\u0644\u0641\u064e\u0631\u064e\u062c\u0650", "correct_case": "gen"},
    ]

    print(f"\n{'='*60}")
    print(f"CTC Hypothesis Scoring (fine-tuned PCD)")
    print(f"{'='*60}")

    model.change_decoding_strategy(decoder_type="ctc")

    def read_audio(filepath):
        import soundfile as sf
        audio_bytes = filepath.read_bytes()
        audio_data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)
        if sr != 16000:
            from scipy.signal import resample
            num_samples = int(len(audio_data) * 16000 / sr)
            audio_data = resample(audio_data, num_samples).astype(np.float32)
        return audio_data

    def find_word(book, target_diac):
        base = strip_harakat(target_diac)
        for w in book.words:
            if w.correct_diac == target_diac:
                return w
        for w in book.words:
            if w.base == base:
                return w
        return None

    correct_errors = 0
    correct_controls = 0

    for label, cases in [("ERROR CASES", ERROR_CASES), ("CONTROL CASES", CONTROL_CASES)]:
        print(f"\n-- {label} --")
        for case in cases:
            rec_id = case["rec"]
            entry = manifest_by_id.get(rec_id)
            if not entry:
                continue

            filepath = test_data_dir / entry["filename"]
            transcription = to_text(model.transcribe([str(filepath)])[0])

            book = Book.from_sentence(entry["text_diacritized"])
            book_word = find_word(book, case["word"])
            if not book_word:
                continue

            # Check: does the transcription contain the correct diacritized word?
            is_correct = case["word"] in transcription
            if label == "ERROR CASES":
                correct_errors += int(is_correct)
            else:
                correct_controls += int(is_correct)

            mark = "OK" if is_correct else "XX"
            print(f"  [{mark}] [{rec_id}] {case['word']:>15s}  correct={case['correct_case']}")
            print(f"          transcription: {transcription[:60]}")

    print(f"\n{'='*60}")
    print(f"Error cases:   {correct_errors}/{len(ERROR_CASES)}")
    print(f"Control cases: {correct_controls}/{len(CONTROL_CASES)}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate fine-tuned PCD model")
    parser.add_argument("--model", type=str, required=True,
                        help="Path to .nemo file or HuggingFace model name")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--i3rab-dir", type=Path, default=Path("."))
    parser.add_argument("--decoder", type=str, default="ctc", choices=["ctc", "rnnt"])
    parser.add_argument("--test-clartts", action="store_true", default=True)
    parser.add_argument("--test-i3rab", action="store_true")
    parser.add_argument("--test-ctc-scoring", action="store_true")
    args = parser.parse_args()

    model = load_model(args.model)

    if args.test_clartts:
        evaluate_clartts(model, args.data_dir, args.decoder)

    if args.test_i3rab:
        evaluate_i3rab(model, args.i3rab_dir, args.decoder)

    if args.test_ctc_scoring:
        evaluate_ctc_scoring(model, args.i3rab_dir)


if __name__ == "__main__":
    main()
