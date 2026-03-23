#!/usr/bin/env python3
"""CTC Ensemble Experiment: Test MMS-1B-all for diacritics discrimination.

Tests whether facebook/mms-1b-all with Arabic adapter can distinguish
between diacritized Arabic hypotheses via CTC scoring. If successful,
this can be combined with Whisper scores for an ensemble.

Usage:
    python experiment_ctc_ensemble.py
"""

import io
import json
import sys
from pathlib import Path

import numpy as np
import torch

from i3rab.book import Book
from i3rab.config import Config
from i3rab.scorer import DiacriticsScorer

TEST_DATA_DIR = Path("test_data")
MANIFEST_PATH = TEST_DATA_DIR / "manifest.json"

# Error cases: words where Whisper picks the wrong diacritic
ERROR_CASES = [
    {"rec": "rec_031", "word": "\u0633\u064e\u0623\u064e\u0644\u064e", "correct_case": "acc", "whisper_picks": "nom"},
    {"rec": "rec_039", "word": "\u0623\u064e\u0639\u064e\u062f\u0651\u064e\u062a\u0650", "correct_case": "gen", "whisper_picks": "jussive"},
    {"rec": "rec_039", "word": "\u0627\u0644\u0644\u0651\u064e\u0630\u0650\u064a\u0630\u064e", "correct_case": "acc", "whisper_picks": "gen"},
    {"rec": "rec_040", "word": "\u0627\u0644\u0637\u0651\u064e\u0627\u0632\u0650\u062c\u064e", "correct_case": "acc", "whisper_picks": "gen"},
]

# Control cases: words where Whisper gets it right
CONTROL_CASES = [
    {"rec": "rec_016", "word": "\u0627\u0644\u0637\u0651\u064e\u0627\u0644\u0650\u0628\u064f", "correct_case": "nom"},
    {"rec": "rec_016", "word": "\u0627\u0644\u0643\u0650\u062a\u064e\u0627\u0628\u064e", "correct_case": "acc"},
    {"rec": "rec_016", "word": "\u0627\u0644\u0645\u064e\u0643\u0652\u062a\u064e\u0628\u064e\u0629\u0650", "correct_case": "gen"},
    {"rec": "rec_019", "word": "\u0627\u0644\u0648\u064e\u0644\u064e\u062f\u064f", "correct_case": "nom"},
    {"rec": "rec_019", "word": "\u0627\u0644\u0645\u064e\u0627\u0621\u064e", "correct_case": "acc"},
    {"rec": "rec_019", "word": "\u0627\u0644\u0628\u064e\u0627\u0631\u0650\u062f\u064e", "correct_case": "acc"},
    {"rec": "rec_032", "word": "\u0627\u0644\u0639\u0650\u0644\u0652\u0645\u064f", "correct_case": "nom"},
    {"rec": "rec_032", "word": "\u0627\u0644\u0641\u064e\u0631\u064e\u062c\u0650", "correct_case": "gen"},
]


def read_audio(filepath: Path) -> np.ndarray:
    """Read audio file into float32 numpy array at 16kHz."""
    import soundfile as sf

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
        if not frames:
            raise ValueError(f"No audio data from {filepath}")
        return np.concatenate(frames).astype(np.float32) / 32768.0

    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)
    if sr != 16000:
        from scipy.signal import resample

        num_samples = int(len(audio_data) * 16000 / sr)
        audio_data = resample(audio_data, num_samples).astype(np.float32)
    return audio_data


class CTCExperiment:
    """Loads MMS-1B-all and scores diacritized hypotheses via CTC."""

    def __init__(self):
        self.model = None
        self.processor = None
        self._device = torch.device("cpu")
        self._blank_id = 0

    def load(self):
        from transformers import Wav2Vec2ForCTC, AutoProcessor

        model_name = "facebook/mms-1b-all"
        print(f"Loading CTC model: {model_name} (Arabic adapter)...")

        # Load base model first, then set language and load adapter
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = Wav2Vec2ForCTC.from_pretrained(model_name)
        self.processor.tokenizer.set_target_lang("ara")
        self.model.load_adapter("ara")

        # Device
        if torch.cuda.is_available():
            self._device = torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self._device = torch.device("mps")
        self.model = self.model.to(self._device)
        self.model.eval()

        self._blank_id = self.processor.tokenizer.pad_token_id or 0
        print(f"CTC model loaded on {self._device}. Vocab size: {self.model.config.vocab_size}")

        # Print vocab diagnostic for harakat tokens
        self._print_vocab_diagnostic()

    def _print_vocab_diagnostic(self):
        """Check which harakat tokens exist in the vocabulary."""
        tokenizer = self.processor.tokenizer
        harakat = {
            "fatha": "\u064E",
            "damma": "\u064F",
            "kasra": "\u0650",
            "fathatan": "\u064B",
            "dammatan": "\u064C",
            "kasratan": "\u064D",
            "shadda": "\u0651",
            "sukun": "\u0652",
        }
        print("\nVocab diagnostic -- harakat token IDs:")
        for name, char in harakat.items():
            ids = tokenizer.encode(char, add_special_tokens=False)
            token_str = tokenizer.convert_ids_to_tokens(ids) if ids else "N/A"
            print(f"  {name} ({char}): ids={ids} tokens={token_str}")
        print()

    def get_logits(self, audio: np.ndarray) -> torch.Tensor:
        """Get CTC logits for audio. Returns (1, T, V)."""
        inputs = self.processor(
            audio, sampling_rate=16000, return_tensors="pt", padding=True,
        )
        input_values = inputs.input_values.to(self._device)
        with torch.no_grad():
            logits = self.model(input_values).logits
        return logits

    def tokenize(self, text: str) -> list[int]:
        """Tokenize diacritized Arabic text for CTC scoring.

        Strips sukun (not in vocab) and filters <unk> tokens.
        """
        cleaned = text.replace("\u0652", "")  # remove sukun
        ids = self.processor.tokenizer.encode(cleaned, add_special_tokens=False)
        unk_id = self.processor.tokenizer.unk_token_id or 3
        ids = [t for t in ids if t != unk_id]
        return ids

    def ctc_score(self, log_probs: torch.Tensor, target_ids: list[int]) -> float:
        """Compute CTC log-probability of target sequence.

        Returns negative CTC loss (higher = better match).
        """
        if not target_ids or log_probs.size(1) == 0:
            return float("-inf")
        if log_probs.size(1) < len(target_ids):
            return float("-inf")

        # CTC loss not supported on MPS -- compute on CPU
        lp_cpu = log_probs.cpu()
        target = torch.tensor([target_ids], dtype=torch.long)
        input_lengths = torch.tensor([lp_cpu.size(1)])
        target_lengths = torch.tensor([len(target_ids)])

        loss = torch.nn.functional.ctc_loss(
            lp_cpu.transpose(0, 1),  # (T, 1, V)
            target,
            input_lengths,
            target_lengths,
            blank=self._blank_id,
            reduction="none",
            zero_infinity=True,
        )
        return -loss.item()

    def check_harakat_logit_magnitudes(self, audio: np.ndarray):
        """Check if harakat tokens have meaningful probabilities in logits."""
        logits = self.get_logits(audio)
        probs = torch.softmax(logits[0].cpu(), dim=-1)  # (T, V)

        tokenizer = self.processor.tokenizer
        harakat_chars = {
            "fatha": "\u064E",
            "kasra": "\u0650",
            "damma": "\u064F",
        }

        print("Harakat token probability statistics across frames:")
        for name, char in harakat_chars.items():
            ids = tokenizer.encode(char, add_special_tokens=False)
            if not ids:
                print(f"  {name}: NOT IN VOCAB")
                continue
            tok_id = ids[0]
            tok_probs = probs[:, tok_id].numpy()
            print(
                f"  {name} (id={tok_id}): "
                f"max={tok_probs.max():.6f}  "
                f"mean={tok_probs.mean():.6f}  "
                f"median={np.median(tok_probs):.6f}  "
                f"frames_above_0.01={int((tok_probs > 0.01).sum())}/{len(tok_probs)}"
            )

        # Also check blank token for reference
        blank_probs = probs[:, self._blank_id].numpy()
        print(
            f"  blank (id={self._blank_id}): "
            f"max={blank_probs.max():.6f}  "
            f"mean={blank_probs.mean():.6f}"
        )
        print()
        return logits

    def score_hypotheses(self, logits, book_word):
        """Score all hypotheses for a BookWord using CTC.

        Returns list of (diacritized, case, ctc_score, token_ids).
        """
        log_probs = torch.log_softmax(logits, dim=-1)

        results = []
        for hyp in book_word.hypotheses:
            token_ids = self.tokenize(hyp.diacritized)
            score = self.ctc_score(log_probs, token_ids)
            results.append((hyp.diacritized, hyp.case, score, token_ids))

        results.sort(key=lambda x: x[2], reverse=True)
        return results


def find_word_in_book(book, target_diac):
    """Find a BookWord by its diacritized form."""
    from i3rab.arabic import strip_harakat

    target_base = strip_harakat(target_diac)
    for w in book.words:
        if w.correct_diac == target_diac:
            return w
    # Fallback: match by base
    for w in book.words:
        if w.base == target_base:
            return w
    return None


def run_experiment():
    manifest = json.loads(MANIFEST_PATH.read_text())
    manifest_by_id = {e["id"]: e for e in manifest}

    # Load CTC model
    ctc = CTCExperiment()
    ctc.load()

    # Load Whisper scorer for comparison
    print("Loading Whisper scorer for comparison...")
    config = Config()
    whisper = DiacriticsScorer(config)
    whisper.load()
    print()

    # Cache audio and books per recording
    audio_cache = {}
    book_cache = {}
    ctc_logits_cache = {}
    whisper_enc_cache = {}

    def get_audio_and_book(rec_id):
        if rec_id not in audio_cache:
            entry = manifest_by_id[rec_id]
            audio = read_audio(TEST_DATA_DIR / entry["filename"])
            book = Book.from_sentence(entry["text_diacritized"])
            audio_cache[rec_id] = audio
            book_cache[rec_id] = book
        return audio_cache[rec_id], book_cache[rec_id]

    def get_ctc_logits(rec_id):
        if rec_id not in ctc_logits_cache:
            audio, _ = get_audio_and_book(rec_id)
            ctc_logits_cache[rec_id] = ctc.get_logits(audio)
        return ctc_logits_cache[rec_id]

    def get_whisper_enc(rec_id):
        if rec_id not in whisper_enc_cache:
            audio, _ = get_audio_and_book(rec_id)
            whisper_enc_cache[rec_id] = whisper._get_encoder_output(audio)
        return whisper_enc_cache[rec_id]

    # Phase 1: Feasibility check
    print("=" * 70)
    print("PHASE 1: Harakat Logit Feasibility Check")
    print("=" * 70)
    audio_016, _ = get_audio_and_book("rec_016")
    ctc.check_harakat_logit_magnitudes(audio_016)

    # Phase 2: Score error cases
    print("=" * 70)
    print("PHASE 2: Error Cases (words Whisper gets wrong)")
    print("=" * 70)

    error_ctc_correct = 0
    error_total = 0

    for case in ERROR_CASES:
        rec_id = case["rec"]
        audio, book = get_audio_and_book(rec_id)
        logits = get_ctc_logits(rec_id)
        enc_out = get_whisper_enc(rec_id)

        book_word = find_word_in_book(book, case["word"])
        if not book_word:
            print(f"  SKIP: word not found in {rec_id}")
            continue

        print(f"\n[{rec_id}] Word: {case['word']}  (correct: {case['correct_case']})")

        # CTC scores (full-audio)
        ctc_results = ctc.score_hypotheses(logits, book_word)

        # Whisper scores
        print("  Whisper scores:")
        whisper_scored = []
        for hyp in book_word.hypotheses:
            score = whisper._score_text(enc_out, hyp.diacritized)
            whisper_scored.append((hyp.diacritized, hyp.case, score))
        whisper_scored.sort(key=lambda x: x[2], reverse=True)
        for diac, cas, score in whisper_scored:
            marker = " <-- CORRECT" if cas == case["correct_case"] else ""
            pick = " << WHISPER PICK" if diac == whisper_scored[0][0] else ""
            print(f"    {diac:>20s}  case={cas:<12s}  score={score:>10.4f}{marker}{pick}")

        # CTC scores
        print("  CTC scores:")
        for diac, cas, score, tids in ctc_results:
            marker = " <-- CORRECT" if cas == case["correct_case"] else ""
            pick = " << CTC PICK" if diac == ctc_results[0][0] else ""
            print(f"    {diac:>20s}  case={cas:<12s}  score={score:>10.4f}  toks={len(tids)}{marker}{pick}")

        ctc_pick = ctc_results[0][1] if ctc_results else None
        is_correct = ctc_pick == case["correct_case"]
        if is_correct:
            error_ctc_correct += 1
        error_total += 1
        print(f"  CTC verdict: {'CORRECT' if is_correct else 'WRONG'} (picked {ctc_pick})")

    print(f"\nError cases: CTC correct on {error_ctc_correct}/{error_total}")

    # Phase 3: Score control cases
    print("\n" + "=" * 70)
    print("PHASE 3: Control Cases (words Whisper gets right)")
    print("=" * 70)

    control_ctc_correct = 0
    control_whisper_correct = 0
    control_total = 0

    for case in CONTROL_CASES:
        rec_id = case["rec"]
        audio, book = get_audio_and_book(rec_id)
        logits = get_ctc_logits(rec_id)
        enc_out = get_whisper_enc(rec_id)

        book_word = find_word_in_book(book, case["word"])
        if not book_word:
            print(f"  SKIP: word not found in {rec_id}")
            continue

        ctc_results = ctc.score_hypotheses(logits, book_word)

        whisper_scored = []
        for hyp in book_word.hypotheses:
            score = whisper._score_text(enc_out, hyp.diacritized)
            whisper_scored.append((hyp.diacritized, hyp.case, score))
        whisper_scored.sort(key=lambda x: x[2], reverse=True)

        ctc_pick = ctc_results[0][1] if ctc_results else None
        whisper_pick = whisper_scored[0][1] if whisper_scored else None

        ctc_ok = ctc_pick == case["correct_case"]
        whisper_ok = whisper_pick == case["correct_case"]

        if ctc_ok:
            control_ctc_correct += 1
        if whisper_ok:
            control_whisper_correct += 1
        control_total += 1

        ctc_gap = (ctc_results[0][2] - ctc_results[1][2]) if len(ctc_results) > 1 else float("inf")
        w_gap = (whisper_scored[0][2] - whisper_scored[1][2]) if len(whisper_scored) > 1 else float("inf")

        ctc_mark = "OK" if ctc_ok else "XX"
        w_mark = "OK" if whisper_ok else "XX"
        print(
            f"  [{rec_id}] {case['word']:>15s}  correct={case['correct_case']:<5s}  "
            f"Whisper=[{w_mark}] {whisper_pick:<10s} gap={w_gap:.4f}  "
            f"CTC=[{ctc_mark}] {str(ctc_pick):<10s} gap={ctc_gap:.4f}"
        )

    print(f"\nControl: Whisper {control_whisper_correct}/{control_total}, CTC {control_ctc_correct}/{control_total}")

    # Phase 4: Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Error cases (Whisper gets wrong):  CTC correct on {error_ctc_correct}/{error_total}")
    print(f"Control cases (Whisper gets right): CTC correct on {control_ctc_correct}/{control_total}")
    total_ctc = error_ctc_correct + control_ctc_correct
    total_all = error_total + control_total
    print(f"Overall CTC accuracy: {total_ctc}/{total_all}")

    if error_ctc_correct > 0 and control_ctc_correct >= control_total - 1:
        print("\n--> CTC shows discriminative ability! Ensemble is worth building.")
    elif error_ctc_correct == 0:
        print("\n--> CTC cannot fix Whisper's errors. Try MMS_FA fallback or fine-tuning.")
    else:
        print(f"\n--> Mixed results. CTC fixes {error_ctc_correct} errors but regresses {control_total - control_ctc_correct} controls.")
        print("    Confidence-gated ensemble might work (only apply CTC for low-confidence words).")


if __name__ == "__main__":
    run_experiment()
