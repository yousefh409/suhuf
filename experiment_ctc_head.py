#!/usr/bin/env python3
"""Experiment: Train a CTC head on frozen Whisper encoder features.

Tests whether Whisper's encoder representations contain diacritics information
that a simple linear CTC head can extract. If a linear layer can overfit on
our 23 sentence recordings to predict diacritized text, the signal exists.

Architecture:
    Frozen whisper-large-v3 encoder (1280-dim) -> nn.Linear(1280, vocab_size) -> CTC loss

Vocab: character-level diacritized Arabic (~50 tokens including harakat)
"""

import io
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

TEST_DATA_DIR = Path("test_data")
MANIFEST_PATH = TEST_DATA_DIR / "manifest.json"

# -- Character-level vocab for diacritized Arabic --

ARABIC_LETTERS = list(
    "\u0621\u0627\u0628\u062a\u062b\u062c\u062d\u062e\u062f\u0630\u0631\u0632\u0633\u0634\u0635\u0636\u0637\u0638\u0639\u063a\u0641\u0642\u0643\u0644\u0645\u0646\u0647\u0648\u064a"
    "\u0629\u0624\u0626\u0623\u0625\u0622"
    "\u0649"
)

HARAKAT = [
    "\u064E",  # fatha
    "\u064F",  # damma
    "\u0650",  # kasra
    "\u064B",  # fathatan
    "\u064C",  # dammatan
    "\u064D",  # kasratan
    "\u0651",  # shadda
    "\u0652",  # sukun
]

OTHER = [" ", "\u0640"]  # space, tatweel

ALL_CHARS = ["<blank>"] + ARABIC_LETTERS + HARAKAT + OTHER
CHAR2ID = {c: i for i, c in enumerate(ALL_CHARS)}
BLANK_ID = 0


def text_to_ids(text):
    ids = []
    for ch in text:
        if ch in CHAR2ID:
            ids.append(CHAR2ID[ch])
    return ids


def ids_to_text(ids):
    return "".join(ALL_CHARS[i] for i in ids if i > 0)


def read_audio(filepath):
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
        return np.concatenate(frames).astype(np.float32) / 32768.0
    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)
    if sr != 16000:
        from scipy.signal import resample
        num_samples = int(len(audio_data) * 16000 / sr)
        audio_data = resample(audio_data, num_samples).astype(np.float32)
    return audio_data


class CTCHead(nn.Module):
    def __init__(self, input_dim, vocab_size):
        super().__init__()
        self.proj = nn.Linear(input_dim, vocab_size)

    def forward(self, encoder_features):
        logits = self.proj(encoder_features)
        return torch.log_softmax(logits, dim=-1)


def run_experiment():
    from transformers import WhisperProcessor, WhisperForConditionalGeneration

    manifest = json.loads(MANIFEST_PATH.read_text())
    sentence_entries = [e for e in manifest if e.get("type") == "sentence"]
    word_entries = [e for e in manifest if e.get("type", "word") == "word"]

    if not sentence_entries:
        print("No sentence recordings found.")
        sys.exit(1)

    print(f"Found {len(sentence_entries)} sentence, {len(word_entries)} word recordings")

    # Load Whisper encoder (frozen)
    model_name = "openai/whisper-large-v3"
    print(f"Loading {model_name} encoder...")

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    dtype = torch.float32

    processor = WhisperProcessor.from_pretrained(model_name)
    whisper = WhisperForConditionalGeneration.from_pretrained(model_name, torch_dtype=dtype)
    whisper = whisper.to(device)
    whisper.eval()
    encoder = whisper.get_encoder()

    for param in encoder.parameters():
        param.requires_grad = False

    hidden_dim = whisper.config.d_model
    vocab_size = len(ALL_CHARS)
    print(f"Encoder dim: {hidden_dim}, CTC vocab: {vocab_size}")
    print(f"CTC head params: {hidden_dim * vocab_size + vocab_size:,}")

    # Prepare training data
    print("\nExtracting encoder features...")
    train_data = []

    for entry in sentence_entries + word_entries:
        filepath = TEST_DATA_DIR / entry["filename"]
        if not filepath.exists():
            continue

        text = entry.get("text_diacritized") or entry.get("word_diacritized", "")
        target_ids = text_to_ids(text)
        if not target_ids:
            continue

        audio = read_audio(filepath)
        input_features = processor(
            audio, sampling_rate=16000, return_tensors="pt"
        ).input_features.to(device=device, dtype=dtype)

        with torch.no_grad():
            enc_out = encoder(input_features)
        features = enc_out.last_hidden_state

        if features.size(1) < len(target_ids):
            print(f"  SKIP {entry['id']}: T={features.size(1)} < len={len(target_ids)}")
            continue

        train_data.append({
            "id": entry["id"],
            "text": text,
            "features": features.detach(),
            "target_ids": target_ids,
        })
        etype = entry.get("type", "word")
        print(f"  {entry['id']} ({etype}): T={features.size(1)}, chars={len(target_ids)}")

    print(f"\nTraining data: {len(train_data)} recordings")

    # Train CTC head
    ctc_head = CTCHead(hidden_dim, vocab_size).to(device).float()
    optimizer = torch.optim.Adam(ctc_head.parameters(), lr=1e-3)
    n_epochs = 200

    print(f"\nTraining for {n_epochs} epochs...")
    for epoch in range(n_epochs):
        total_loss = 0.0
        for item in train_data:
            features = item["features"].float()
            target_ids = item["target_ids"]

            log_probs = ctc_head(features)

            lp_cpu = log_probs.cpu()
            target = torch.tensor([target_ids], dtype=torch.long)
            input_lengths = torch.tensor([lp_cpu.size(1)])
            target_lengths = torch.tensor([len(target_ids)])

            loss = torch.nn.functional.ctc_loss(
                lp_cpu.transpose(0, 1),
                target, input_lengths, target_lengths,
                blank=BLANK_ID, reduction="mean", zero_infinity=True,
            )

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        avg_loss = total_loss / len(train_data)
        if epoch % 20 == 0 or epoch == n_epochs - 1:
            print(f"  Epoch {epoch:3d}: loss={avg_loss:.4f}")

    # Evaluate: greedy decode on training data
    print("\n" + "=" * 60)
    print("CTC Greedy Decode (first 5 training samples)")
    print("=" * 60)

    ctc_head.eval()
    for item in train_data[:5]:
        features = item["features"].float()
        with torch.no_grad():
            log_probs = ctc_head(features)

        pred_ids = log_probs.argmax(dim=-1).squeeze(0).cpu().tolist()
        decoded = []
        prev = BLANK_ID
        for pid in pred_ids:
            if pid != prev and pid != BLANK_ID:
                decoded.append(pid)
            prev = pid

        pred_text = ids_to_text(decoded)
        print(f"\n  [{item['id']}]")
        print(f"    ref:  {item['text']}")
        print(f"    pred: {pred_text}")

    # Key test: hypothesis scoring on error cases
    print("\n" + "=" * 60)
    print("CTC Hypothesis Scoring")
    print("=" * 60)

    from i3rab.book import Book
    from i3rab.arabic import strip_harakat

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
        {"rec": "rec_019", "word": "\u0627\u0644\u0645\u064e\u0627\u0621\u064e", "correct_case": "acc"},
        {"rec": "rec_019", "word": "\u0627\u0644\u0628\u064e\u0627\u0631\u0650\u062f\u064e", "correct_case": "acc"},
        {"rec": "rec_032", "word": "\u0627\u0644\u0639\u0650\u0644\u0652\u0645\u064f", "correct_case": "nom"},
        {"rec": "rec_032", "word": "\u0627\u0644\u0641\u064e\u0631\u064e\u062c\u0650", "correct_case": "gen"},
    ]

    manifest_by_id = {e["id"]: e for e in manifest}

    enc_cache = {}
    needed_recs = {c["rec"] for c in ERROR_CASES + CONTROL_CASES}
    for entry in manifest:
        rec_id = entry["id"]
        if rec_id not in needed_recs or rec_id in enc_cache:
            continue
        filepath = TEST_DATA_DIR / entry["filename"]
        if not filepath.exists():
            continue
        audio = read_audio(filepath)
        input_features = processor(
            audio, sampling_rate=16000, return_tensors="pt"
        ).input_features.to(device=device, dtype=dtype)
        with torch.no_grad():
            enc_out = encoder(input_features)
        enc_cache[rec_id] = enc_out.last_hidden_state.detach()

    def ctc_score(features, text):
        target_ids = text_to_ids(text)
        if not target_ids or features.size(1) < len(target_ids):
            return float("-inf")
        with torch.no_grad():
            log_probs = ctc_head(features.float())
        lp_cpu = log_probs.cpu()
        target = torch.tensor([target_ids], dtype=torch.long)
        input_lengths = torch.tensor([lp_cpu.size(1)])
        target_lengths = torch.tensor([len(target_ids)])
        loss = torch.nn.functional.ctc_loss(
            lp_cpu.transpose(0, 1), target,
            input_lengths, target_lengths,
            blank=BLANK_ID, reduction="none", zero_infinity=True,
        )
        return -loss.item()

    def find_word(book, target_diac):
        target_base = strip_harakat(target_diac)
        for w in book.words:
            if w.correct_diac == target_diac:
                return w
        for w in book.words:
            if w.base == target_base:
                return w
        return None

    book_cache = {}
    correct_errors = 0
    correct_controls = 0

    for label, cases in [("ERROR CASES", ERROR_CASES), ("CONTROL CASES", CONTROL_CASES)]:
        print(f"\n-- {label} --")
        for case in cases:
            rec_id = case["rec"]
            if rec_id not in enc_cache:
                print(f"  SKIP: {rec_id}")
                continue

            features = enc_cache[rec_id]
            entry = manifest_by_id[rec_id]

            if rec_id not in book_cache:
                book_cache[rec_id] = Book.from_sentence(entry["text_diacritized"])
            book = book_cache[rec_id]

            book_word = find_word(book, case["word"])
            if not book_word:
                print(f"  SKIP: word not found in {rec_id}")
                continue

            scored = []
            for hyp in book_word.hypotheses:
                score = ctc_score(features, hyp.diacritized)
                scored.append((hyp.diacritized, hyp.case, score))
            scored.sort(key=lambda x: x[2], reverse=True)

            pick = scored[0][1]
            gap = scored[0][2] - scored[1][2] if len(scored) > 1 else float("inf")
            is_correct = pick == case["correct_case"]

            if label == "ERROR CASES":
                correct_errors += int(is_correct)
            else:
                correct_controls += int(is_correct)

            mark = "OK" if is_correct else "XX"
            print(f"  [{mark}] [{rec_id}] {case['word']:>15s}  correct={case['correct_case']:<8s}  picked={pick:<8s}  gap={gap:.4f}")

            for diac, cas, sc in scored[:4]:
                marker = " <--" if cas == case["correct_case"] else ""
                print(f"         {diac:>20s}  {cas:<8s}  {sc:.4f}{marker}")

    print(f"\n{'='*60}")
    print(f"Error cases:   {correct_errors}/{len(ERROR_CASES)}")
    print(f"Control cases: {correct_controls}/{len(CONTROL_CASES)}")
    print(f"Total:         {correct_errors + correct_controls}/{len(ERROR_CASES) + len(CONTROL_CASES)}")
    print(f"{'='*60}")

    print("\n-- Analysis --")
    print("If error cases > 0: Whisper encoder CONTAINS diacritics signal")
    print("If error cases = 0: encoder lacks signal -> LoRA fine-tuning needed")
    print()
    if correct_errors > 0:
        print("NEXT: Train CTC head on ClArTTS (12h) for generalization")
    else:
        print("NEXT: LoRA fine-tune whisper-large-v3 on diacritized Arabic")


if __name__ == "__main__":
    run_experiment()
