#!/usr/bin/env python3
"""Fine-tune wav2vec2 or w2v-bert SSL encoders with CTC head for diacritized Arabic.

Three model options:
  --model xls-r      → facebook/wav2vec2-xls-r-300m (300M, multilingual)
  --model w2v-bert   → facebook/w2v-bert-2.0 (600M, newer SSL, mel spectrogram input)
  --model mms        → facebook/mms-1b-all (1B, Arabic adapter)

Trains on ClArTTS dataset (MBZUAI/ClArTTS) loaded from HuggingFace,
optionally combined with contrastive pairs from a local manifest.

Usage:
    python training/finetune_ssl_ctc.py --model xls-r --epochs 30
    python training/finetune_ssl_ctc.py --model w2v-bert --epochs 15 --lr 5e-5
    python training/finetune_ssl_ctc.py --model mms --epochs 30
"""

import argparse
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import torch
import soundfile as sf
from datasets import Audio, Dataset, DatasetDict, load_dataset

from transformers import (
    Trainer,
    TrainingArguments,
    Wav2Vec2CTCTokenizer,
    Wav2Vec2FeatureExtractor,
    Wav2Vec2ForCTC,
    Wav2Vec2Processor,
)

# w2v-bert uses different classes
try:
    from transformers import (
        SeamlessM4TFeatureExtractor,
        Wav2Vec2BertForCTC,
    )
    HAS_W2VBERT = True
except ImportError:
    HAS_W2VBERT = False

SAMPLE_RATE = 16000

# Arabic diacritical marks
HARAKAT = set("\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652")

# ── Vocabulary ─────────────────────────────────────────────────────

# Character-level vocab including all Arabic letters + diacritics
ARABIC_CHARS = list(
    "ابتثجحخدذرزسشصضطظعغفقكلمنهويءأإآئؤةى"
    # Diacritics: tanwin (3) + harakat (3) + shadda + sukun
    "\u064b\u064c\u064d"  # tanwin: fathatan, dammatan, kasratan
    "\u064e\u064f\u0650"  # fatha, damma, kasra
    "\u0651"              # shadda
    "\u0652"              # sukun
    # Common extras
    "\u0670"              # superscript alef (dagger alef)
    "\u0671"              # alef wasla
)

# Add space, digits (for rare cases), and common punctuation
EXTRA_CHARS = list(" .,؟!:؛")


def build_vocab(output_dir: Path) -> Path:
    """Build character-level vocab for CTC and save vocab.json."""
    vocab = {"<pad>": 0, "<s>": 1, "</s>": 2, "<unk>": 3, "|": 4}  # | = word boundary
    idx = len(vocab)
    for ch in ARABIC_CHARS + EXTRA_CHARS:
        if ch not in vocab:
            vocab[ch] = idx
            idx += 1
    vocab_path = output_dir / "vocab.json"
    vocab_path.parent.mkdir(parents=True, exist_ok=True)
    with open(vocab_path, "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False, indent=2)
    print(f"Vocab: {len(vocab)} tokens → {vocab_path}")
    return vocab_path


def normalize_text(text: str) -> str:
    """Normalize Arabic text for CTC training."""
    text = unicodedata.normalize("NFC", text)
    # Replace multiple spaces with single
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Data loading ───────────────────────────────────────────────────


def _resample_audio(array: np.ndarray, orig_sr: int) -> np.ndarray:
    """Resample audio from orig_sr to SAMPLE_RATE (16kHz) if needed."""
    if orig_sr == SAMPLE_RATE:
        return array
    from scipy.signal import resample
    n = int(len(array) * SAMPLE_RATE / orig_sr)
    return resample(array, n).astype(np.float32)


def load_clartts_splits():
    """Load ClArTTS from HuggingFace and prepare train/test."""
    print("Loading ClArTTS from HuggingFace...")
    ds = load_dataset("MBZUAI/ClArTTS")

    train_ds = ds["train"]
    test_ds = ds["test"]

    print(f"  Train: {len(train_ds)} samples")
    print(f"  Test:  {len(test_ds)} samples")
    return train_ds, test_ds


def load_manifest_dataset(manifest_path: str) -> Dataset:
    """Load a NeMo-style manifest as a HuggingFace Dataset."""
    print(f"Loading manifest: {manifest_path}")
    entries = []
    skipped = 0
    with open(manifest_path) as f:
        for line in f:
            entry = json.loads(line)
            audio_path = entry["audio_filepath"]
            if not os.path.exists(audio_path):
                skipped += 1
                continue
            entries.append({
                "audio_filepath": audio_path,
                "text": normalize_text(entry["text"]),
                "duration": entry.get("duration", 0),
            })
    if skipped > 0:
        print(f"  Skipped {skipped} entries (missing audio files)")
    print(f"  Loaded {len(entries)} entries")

    if not entries:
        return None

    # Build HF dataset
    def gen():
        for e in entries:
            audio, sr = sf.read(e["audio_filepath"], dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            if sr != SAMPLE_RATE:
                from scipy.signal import resample
                n = int(len(audio) * SAMPLE_RATE / sr)
                audio = resample(audio, n).astype(np.float32)
            yield {
                "audio": {"array": audio, "sampling_rate": SAMPLE_RATE},
                "text": e["text"],
            }

    ds = Dataset.from_generator(gen)
    return ds


# ── Data collator ──────────────────────────────────────────────────


@dataclass
class DataCollatorCTCWithPadding:
    processor: Any
    padding: Union[bool, str] = True
    is_w2v_bert: bool = False  # w2v-bert: extract mel on-the-fly, pad 2D features

    def __call__(self, features: List[Dict[str, Any]]) -> Dict[str, torch.Tensor]:
        label_features = [{"input_ids": f["labels"]} for f in features]

        if self.is_w2v_bert:
            # w2v-bert: extract mel features from raw audio, then pad 2D (T, feat_dim)
            mel_features = []
            for f in features:
                audio = np.array(f["audio_array"], dtype=np.float32)
                inputs = self.processor.feature_extractor(
                    audio, sampling_rate=SAMPLE_RATE, return_tensors="np"
                )
                mel = inputs["input_features"][0]  # (T, feat_dim)
                mel_features.append(mel)

            max_len = max(m.shape[0] for m in mel_features)
            feat_dim = mel_features[0].shape[1]
            padded = np.zeros((len(mel_features), max_len, feat_dim), dtype=np.float32)
            attention_mask = np.zeros((len(mel_features), max_len), dtype=np.int64)
            for i, m in enumerate(mel_features):
                padded[i, :m.shape[0]] = m
                attention_mask[i, :m.shape[0]] = 1
            batch = {
                "input_features": torch.from_numpy(padded),
                "attention_mask": torch.from_numpy(attention_mask),
            }
        else:
            # wav2vec2: input_values is 1D — use processor.pad()
            input_list = [{"input_values": f["input_values"]} for f in features]
            batch = self.processor.pad(
                input_list,
                padding=self.padding,
                return_tensors="pt",
            )

        labels_batch = self.processor.tokenizer.pad(
            label_features,
            padding=self.padding,
            return_tensors="pt",
        )

        # Replace padding with -100 for CTC loss
        labels = labels_batch["input_ids"].masked_fill(
            labels_batch.attention_mask.ne(1), -100
        )
        batch["labels"] = labels
        return batch


# ── Metrics ────────────────────────────────────────────────────────


def compute_wer(pred_str, label_str):
    """Simple WER computation."""
    pred_words = pred_str.split()
    label_words = label_str.split()
    if len(label_words) == 0:
        return 0.0
    # Levenshtein at word level
    d = np.zeros((len(pred_words) + 1, len(label_words) + 1), dtype=int)
    for i in range(len(pred_words) + 1):
        d[i][0] = i
    for j in range(len(label_words) + 1):
        d[0][j] = j
    for i in range(1, len(pred_words) + 1):
        for j in range(1, len(label_words) + 1):
            if pred_words[i - 1] == label_words[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = min(d[i - 1][j], d[i][j - 1], d[i - 1][j - 1]) + 1
    return d[len(pred_words)][len(label_words)] / len(label_words)


# ── Main ───────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="xls-r",
                        choices=["xls-r", "w2v-bert", "mms"],
                        help="Base model: xls-r, w2v-bert, or mms")
    parser.add_argument("--output-dir", type=Path, default=Path("checkpoints/ssl_ctc"))
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--warmup-steps", type=int, default=500)
    parser.add_argument("--freeze-encoder-epochs", type=int, default=5)
    parser.add_argument("--extra-manifest", type=str, default=None,
                        help="Additional NeMo manifest for contrastive data")
    parser.add_argument("--max-duration", type=float, default=20.0,
                        help="Max audio duration in seconds")
    parser.add_argument("--fp16", action="store_true", default=True)
    args = parser.parse_args()

    # Model selection
    if args.model == "xls-r":
        model_name = "facebook/wav2vec2-xls-r-300m"
        output_subdir = "xls_r_300m"
    elif args.model == "mms":
        model_name = "facebook/mms-1b-all"
        output_subdir = "mms_1b"
    elif args.model == "w2v-bert":
        if not HAS_W2VBERT:
            print("ERROR: Wav2Vec2BertForCTC not available. "
                  "Update transformers: pip install -U transformers")
            return
        model_name = "facebook/w2v-bert-2.0"
        output_subdir = "w2v_bert"
    else:
        raise ValueError(f"Unknown model: {args.model}")

    output_dir = args.output_dir / output_subdir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build vocab
    vocab_path = build_vocab(output_dir)

    # Create tokenizer
    tokenizer = Wav2Vec2CTCTokenizer(
        str(vocab_path),
        unk_token="<unk>",
        pad_token="<pad>",
        word_delimiter_token="|",
    )

    # Create feature extractor + processor
    is_w2v_bert = (args.model == "w2v-bert")
    if is_w2v_bert:
        feature_extractor = SeamlessM4TFeatureExtractor.from_pretrained(model_name)
    else:
        # wav2vec2 / xls-r / mms all use Wav2Vec2FeatureExtractor
        feature_extractor = Wav2Vec2FeatureExtractor(
            feature_size=1,
            sampling_rate=SAMPLE_RATE,
            padding_value=0.0,
            do_normalize=True,
            return_attention_mask=True,
        )

    processor = Wav2Vec2Processor(
        feature_extractor=feature_extractor,
        tokenizer=tokenizer,
    )
    processor.save_pretrained(str(output_dir))

    # Load data
    train_ds, test_ds = load_clartts_splits()

    # Optionally add extra manifest data
    if args.extra_manifest and os.path.exists(args.extra_manifest):
        extra_ds = load_manifest_dataset(args.extra_manifest)
        if extra_ds is not None:
            from datasets import concatenate_datasets
            train_ds = concatenate_datasets([train_ds, extra_ds])
            print(f"  Combined train: {len(train_ds)} samples")

    # Preprocess: extract features and tokenize
    # w2v-bert uses input_features (2D mel spectrogram) — can't store variable-length 2D in HF datasets
    # So for w2v-bert: store raw audio + labels, extract mel in the collator
    # For wav2vec2: store 1D input_values + labels (standard approach)

    if is_w2v_bert:
        # w2v-bert: keep raw audio, only tokenize text
        def prepare_dataset(batch):
            audio = batch["audio"]
            if isinstance(audio, dict):
                array = np.array(audio["array"], dtype=np.float32)
                orig_sr = audio.get("sampling_rate", SAMPLE_RATE)
            else:
                array = np.array(audio, dtype=np.float32)
                orig_sr = SAMPLE_RATE

            # Resample to 16kHz if needed (ClArTTS is 40100Hz)
            array = _resample_audio(array, orig_sr)

            duration = len(array) / SAMPLE_RATE
            if duration > args.max_duration or duration < 0.5:
                return {"audio_array": None, "labels": None}

            text = normalize_text(batch["text"])
            text_with_delim = text.replace(" ", "|")
            labels = processor.tokenizer(text_with_delim, return_tensors=None)

            return {
                "audio_array": array.tolist(),
                "labels": labels["input_ids"],
            }

        storage_key = "audio_array"
    else:
        def prepare_dataset(batch):
            audio = batch["audio"]
            if isinstance(audio, dict):
                array = np.array(audio["array"], dtype=np.float32)
                orig_sr = audio.get("sampling_rate", SAMPLE_RATE)
            else:
                array = np.array(audio, dtype=np.float32)
                orig_sr = SAMPLE_RATE

            # Resample to 16kHz if needed (ClArTTS is 40100Hz)
            array = _resample_audio(array, orig_sr)

            duration = len(array) / SAMPLE_RATE
            if duration > args.max_duration or duration < 0.5:
                return {"input_values": None, "labels": None}

            inputs = processor(
                array,
                sampling_rate=SAMPLE_RATE,
                return_tensors=None,
            )
            feat = inputs["input_values"]
            if isinstance(feat, list) and len(feat) == 1 and isinstance(feat[0], (list, np.ndarray)):
                feat = feat[0]

            text = normalize_text(batch["text"])
            text_with_delim = text.replace(" ", "|")
            labels = processor.tokenizer(text_with_delim, return_tensors=None)

            return {
                "input_values": feat,
                "labels": labels["input_ids"],
            }

        storage_key = "input_values"

    # w2v-bert stores raw audio arrays (large) — use num_proc=1 to avoid cache issues
    n_proc = 1 if is_w2v_bert else 4

    print("Preprocessing train set...")
    train_ds = train_ds.map(
        prepare_dataset,
        remove_columns=train_ds.column_names,
        num_proc=n_proc,
        load_from_cache_file=False,
    )
    train_ds = train_ds.filter(lambda x: x[storage_key] is not None)

    print("Preprocessing test set...")
    test_ds = test_ds.map(
        prepare_dataset,
        remove_columns=test_ds.column_names,
        num_proc=n_proc,
        load_from_cache_file=False,
    )
    test_ds = test_ds.filter(lambda x: x[storage_key] is not None)

    print(f"Train: {len(train_ds)}, Test: {len(test_ds)}")

    # Load model
    print(f"Loading {model_name}...")
    if is_w2v_bert:
        # w2v-bert: lower regularization, add_adapter for CTC projection
        model_kwargs = dict(
            add_adapter=True,
            attention_dropout=0.0,
            hidden_dropout=0.0,
            feat_proj_dropout=0.0,
            mask_time_prob=0.0,
            layerdrop=0.0,
            ctc_loss_reduction="mean",
            pad_token_id=processor.tokenizer.pad_token_id,
            vocab_size=len(processor.tokenizer),
            ctc_zero_infinity=True,
        )
        model = Wav2Vec2BertForCTC.from_pretrained(
            model_name, **model_kwargs
        )
    else:
        # xls-r, mms — all use Wav2Vec2ForCTC
        model_kwargs = dict(
            attention_dropout=0.1,
            hidden_dropout=0.1,
            feat_proj_dropout=0.0,
            mask_time_prob=0.075,
            layerdrop=0.1,
            ctc_loss_reduction="mean",
            pad_token_id=processor.tokenizer.pad_token_id,
            vocab_size=len(processor.tokenizer),
            ctc_zero_infinity=True,
        )
        model = Wav2Vec2ForCTC.from_pretrained(
            model_name, ignore_mismatched_sizes=True, **model_kwargs
        )

    # Freeze encoder for initial epochs
    if args.freeze_encoder_epochs > 0:
        print(f"Freezing feature encoder...")
        if hasattr(model, 'freeze_feature_encoder'):
            model.freeze_feature_encoder()
        else:
            # w2v-bert: manually freeze feature projection
            if hasattr(model, 'wav2vec2_bert'):
                for param in model.wav2vec2_bert.feature_projection.parameters():
                    param.requires_grad = False
                print("  Froze wav2vec2_bert.feature_projection")

    # Data collator
    data_collator = DataCollatorCTCWithPadding(processor=processor, is_w2v_bert=is_w2v_bert)

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        eval_strategy="steps",
        eval_steps=500 if not is_w2v_bert else 1000,
        save_strategy="steps",
        save_steps=500 if not is_w2v_bert else 1000,
        save_total_limit=2,
        num_train_epochs=args.epochs,
        fp16=args.fp16,
        logging_steps=50,
        learning_rate=args.lr,
        warmup_steps=args.warmup_steps,
        max_grad_norm=1.0,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        dataloader_num_workers=0 if is_w2v_bert else 4,
        remove_unused_columns=not is_w2v_bert,  # w2v-bert needs audio_array in collator
        report_to="none",
        gradient_checkpointing=True,
    )

    # Custom callback to unfreeze encoder after N epochs
    if args.freeze_encoder_epochs > 0:
        from transformers import TrainerCallback

        class UnfreezeCallback(TrainerCallback):
            def __init__(self, unfreeze_epoch):
                self.unfreeze_epoch = unfreeze_epoch
                self.unfrozen = False

            def on_epoch_begin(self, args, state, control, model=None, **kwargs):
                if (
                    not self.unfrozen
                    and state.epoch is not None
                    and state.epoch >= self.unfreeze_epoch
                ):
                    print(f"\n>>> Unfreezing encoder at epoch {state.epoch:.1f}")
                    for param in model.parameters():
                        param.requires_grad = True
                    self.unfrozen = True

        callbacks = [UnfreezeCallback(args.freeze_encoder_epochs)]
    else:
        callbacks = []

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=test_ds,
        data_collator=data_collator,
        processing_class=processor,
        callbacks=callbacks,
    )

    print(f"\nStarting training: {args.model}")
    print(f"  Epochs: {args.epochs}")
    print(f"  Batch: {args.batch_size} x {args.grad_accum} = {args.batch_size * args.grad_accum}")
    print(f"  LR: {args.lr}")
    print(f"  Output: {output_dir}")
    print()

    trainer.train()

    # Save final model
    trainer.save_model(str(output_dir / "final"))
    processor.save_pretrained(str(output_dir / "final"))
    print(f"\nFinal model saved to {output_dir / 'final'}")

    # Quick eval: decode a few test samples
    print("\n" + "=" * 60)
    print("Sample predictions:")
    print("=" * 60)
    model.eval()
    for i in range(min(5, len(test_ds))):
        if is_w2v_bert:
            # Extract mel features from stored raw audio
            audio = np.array(test_ds[i]["audio_array"], dtype=np.float32)
            inputs = processor.feature_extractor(
                audio, sampling_rate=SAMPLE_RATE, return_tensors="pt"
            )
            sample_input = inputs["input_features"].to(model.device)
        else:
            sample_input = torch.tensor(
                test_ds[i]["input_values"], dtype=torch.float32
            ).unsqueeze(0).to(model.device)

        with torch.no_grad():
            if is_w2v_bert:
                logits = model(input_features=sample_input).logits
            else:
                logits = model(input_values=sample_input).logits

        pred_ids = torch.argmax(logits, dim=-1)
        pred_str = processor.batch_decode(pred_ids)[0]

        label_ids = test_ds[i]["labels"]
        # Filter out -100
        label_ids = [l for l in label_ids if l != -100]
        label_str = processor.tokenizer.decode(label_ids)

        pred_clean = pred_str.replace("|", " ").strip()
        label_clean = label_str.replace("|", " ").strip()

        wer = compute_wer(pred_clean, label_clean)
        has_diac = any("\u064b" <= ch <= "\u0652" for ch in pred_clean)
        mark = "DIAC" if has_diac else "PLAIN"

        print(f"\n[{mark}] WER={wer:.0%}")
        print(f"  REF:  {label_clean[:80]}")
        print(f"  PRED: {pred_clean[:80]}")


if __name__ == "__main__":
    main()
