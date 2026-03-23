#!/usr/bin/env python3
"""Fine-tune NVIDIA FastConformer PCD on ClArTTS for general Arabic diacritics."""

import argparse
import json
from pathlib import Path

import torch
# Use lightning.pytorch (same as NeMo), NOT pytorch_lightning
import lightning.pytorch as pl
from omegaconf import OmegaConf, open_dict

import nemo.collections.asr as nemo_asr
from nemo.utils import logging


def count_manifest(path):
    n, dur = 0, 0.0
    with open(path) as f:
        for line in f:
            n += 1
            dur += json.loads(line).get("duration", 0)
    return n, dur / 3600


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("checkpoints"))
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--warmup-steps", type=int, default=200)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--no-noise", action="store_true")
    parser.add_argument("--gpus", type=int, default=1)
    parser.add_argument("--precision", type=str, default="bf16-mixed")
    parser.add_argument("--accumulate-grad", type=int, default=2)
    parser.add_argument("--freeze-encoder-epochs", type=int, default=5)
    parser.add_argument("--train-manifest", type=str, default=None,
                        help="Override train manifest path (e.g. data/train_combined.json)")
    parser.add_argument("--resume", type=str, default=None,
                        help="Resume from checkpoint path")
    parser.add_argument("--from-nemo", type=str, default=None,
                        help="Start from a .nemo model instead of HuggingFace pretrained")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Manifests — prefer explicit, then combined, then ClArTTS-only
    if args.train_manifest:
        train_manifest = args.train_manifest
    else:
        combined = args.data_dir / "train_combined.json"
        sp_manifest = args.data_dir / "clartts" / "train_manifest_sp.json"
        plain_manifest = args.data_dir / "clartts" / "train_manifest.json"
        if combined.exists():
            train_manifest = str(combined)
        elif sp_manifest.exists():
            train_manifest = str(sp_manifest)
        else:
            train_manifest = str(plain_manifest)
    val_manifest = str(args.data_dir / "clartts" / "test_manifest.json")

    n_train, h_train = count_manifest(train_manifest)
    n_val, h_val = count_manifest(val_manifest)
    logging.info(f"Train: {n_train} samples ({h_train:.1f}h)")
    logging.info(f"Val:   {n_val} samples ({h_val:.1f}h)")

    # Load model — either from .nemo file or HuggingFace pretrained
    if args.from_nemo:
        logging.info(f"Loading model from {args.from_nemo}...")
        model = nemo_asr.models.EncDecHybridRNNTCTCBPEModel.restore_from(args.from_nemo)
    else:
        logging.info("Loading pretrained PCD model from HuggingFace...")
        model = nemo_asr.models.EncDecHybridRNNTCTCBPEModel.from_pretrained(
            "nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0"
        )

    # Disable CUDA graphs in RNNT decoder (cu_call API mismatch with this CUDA version)
    # Must patch the instantiated decoding objects, not just config
    for name, module in model.named_modules():
        if hasattr(module, 'cuda_graphs_mode'):
            module.cuda_graphs_mode = None
            logging.info(f"Disabled CUDA graphs on {name}")
    logging.info("RNNT CUDA graphs disabled")

    # Resolve ALL mandatory config values
    with open_dict(model.cfg):
        model.cfg.train_ds.manifest_filepath = train_manifest
        model.cfg.train_ds.batch_size = args.batch_size
        model.cfg.train_ds.num_workers = args.num_workers
        model.cfg.train_ds.is_tarred = False
        model.cfg.train_ds.tarred_audio_filepaths = ""
        model.cfg.train_ds.sample_rate = 16000
        model.cfg.train_ds.shuffle = True
        model.cfg.train_ds.max_duration = 20.0
        model.cfg.train_ds.min_duration = 0.5

        model.cfg.validation_ds.manifest_filepath = val_manifest
        model.cfg.validation_ds.batch_size = args.batch_size
        model.cfg.validation_ds.num_workers = args.num_workers
        model.cfg.validation_ds.sample_rate = 16000
        model.cfg.validation_ds.shuffle = False

        model.cfg.test_ds.manifest_filepath = val_manifest
        model.cfg.tokenizer.dir = "/tmp/nemo_tokenizer"

    model.setup_training_data(model.cfg.train_ds)
    model.setup_validation_data(model.cfg.validation_ds)

    # Optimizer
    with open_dict(model.cfg):
        model.cfg.optim = {
            "name": "adamw",
            "lr": args.lr,
            "betas": [0.9, 0.98],
            "weight_decay": 0.01,
            "sched": {
                "name": "CosineAnnealing",
                "warmup_steps": args.warmup_steps,
                "min_lr": 1e-7,
            },
        }
    model.setup_optimization(model.cfg.optim)

    # Freeze encoder
    if args.freeze_encoder_epochs > 0:
        logging.info(f"Freezing encoder for first {args.freeze_encoder_epochs} epochs")
        model.encoder.freeze()

    # Callbacks
    callbacks = [
        pl.callbacks.ModelCheckpoint(
            dirpath=str(args.output_dir),
            filename="pcd-clartts-{epoch:02d}-{val_wer:.4f}",
            monitor="val_wer",
            mode="min",
            save_top_k=3,
            save_last=True,
        ),
        pl.callbacks.EarlyStopping(
            monitor="val_wer", patience=8, mode="min", verbose=True,
        ),
        pl.callbacks.LearningRateMonitor(logging_interval="step"),
    ]

    if args.freeze_encoder_epochs > 0:
        class UnfreezeEncoder(pl.Callback):
            def __init__(self, epoch):
                self.epoch = epoch
            def on_train_epoch_start(self, trainer, pl_module):
                if trainer.current_epoch == self.epoch:
                    logging.info(f"Epoch {self.epoch}: Unfreezing encoder")
                    pl_module.encoder.unfreeze()
        callbacks.append(UnfreezeEncoder(args.freeze_encoder_epochs))

    # Use lightning.pytorch.Trainer (same as NeMo's LightningModule)
    trainer = pl.Trainer(
        devices=args.gpus,
        accelerator="gpu",
        strategy="auto",
        max_epochs=args.epochs,
        accumulate_grad_batches=args.accumulate_grad,
        precision=args.precision,
        callbacks=callbacks,
        log_every_n_steps=10,
        val_check_interval=0.5,
        gradient_clip_val=1.0,
        enable_progress_bar=True,
        default_root_dir=str(args.output_dir),
    )

    logging.info(f"Epochs: {args.epochs}, Batch: {args.batch_size}x{args.accumulate_grad}, LR: {args.lr}")
    trainer.fit(model, ckpt_path=args.resume)

    # Save
    final_path = args.output_dir / "pcd_clartts_final.nemo"
    model.save_to(str(final_path))
    logging.info(f"Saved to {final_path}")

    # Quick test
    logging.info("Quick transcription test:")
    model.eval()
    model.change_decoding_strategy(decoder_type="ctc")
    with open(val_manifest) as f:
        test_entries = [json.loads(line) for line in f]
    for entry in test_entries[:5]:
        result = model.transcribe([entry["audio_filepath"]])[0]
        # NeMo may return Hypothesis objects or strings depending on version
        transcription = result.text if hasattr(result, 'text') else str(result)
        has_diac = any("\u064B" <= ch <= "\u0652" for ch in transcription)
        mark = "DIAC" if has_diac else "PLAIN"
        logging.info(f"  [{mark}] ref:  {entry['text'][:60]}")
        logging.info(f"         pred: {transcription[:60]}")


if __name__ == "__main__":
    main()
