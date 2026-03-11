"""Configuration and settings for i3rab."""

from dataclasses import dataclass, field


@dataclass
class Config:
    # Audio
    sample_rate: int = 16000
    channels: int = 1
    min_audio_seconds: float = 0.5

    # ASR model for transcription and hypothesis scoring
    # Alternatives:
    #   "tarteel-ai/whisper-base-ar-quran"  — 74M params, fast, Quranic domain
    #   "openai/whisper-large-v3-turbo"     — 809M params, best general accuracy
    #   "IJyad/whisper-large-v3-Tarteel"    — large-v3 fine-tuned on Quran
    asr_model: str = "openai/whisper-large-v3"

    # Device: "auto" detects cuda > mps > cpu
    device: str = "auto"

    # Dtype: "auto" uses float16 on GPU/MPS, float32 on CPU
    torch_dtype: str = "auto"

    # Temperature for scoring logits (>1.0 reduces overconfidence, 1.0 = no change)
    score_temperature: float = 1.0

    # Scoring thresholds
    # Minimum log-likelihood gap between best and second-best hypothesis
    # to consider the detection confident
    high_confidence_gap: float = 0.3
    medium_confidence_gap: float = 0.15

    # Use CTC forced alignment for word timestamps (if ctc-forced-aligner installed)
    use_ctc_timestamps: bool = True

    # Pausal detection: silence duration (seconds) to consider a pause
    pause_threshold: float = 0.3

    # Phoneme model for fallback scoring (syllable-level Arabic recognition)
    phoneme_model: str = "IbrahimSalah/Wav2vecLarge_quran_syllables_recognition"
    use_phoneme_fallback: bool = False

    # Maximum words to search ahead when tracking position
    tracker_window: int = 50

    # Max hypotheses to score in one decoder forward pass (memory vs speed)
    # Higher = faster but uses more memory. 4 is safe for 16GB, 8 for 32GB+.
    scorer_batch_size: int = 4

    # PCD model for direct diacritized transcription (optional)
    # Path to a .nemo checkpoint fine-tuned for diacritized Arabic output
    pcd_model_path: str = "models/pcd_clartts_v2.nemo"

    # Use joint lattice scoring (WFST-style beam search) instead of
    # independent per-word CTC scoring.
    use_joint_scoring: bool = False

    # RNN-T ensemble weight: 0.0 = CTC only, 0.3 = 70% CTC + 30% RNN-T
    # Note: RNN-T is ~100x slower with no accuracy improvement. Disabled.
    rnnt_weight: float = 0.0

    # Tashkeel CTC verification threshold: decoded word must score this much
    # better than reference to flag a tashkeel error. Higher = fewer FP, lower recall.
    tashkeel_threshold: float = 2.0

    # Low-confidence i3rab fallback threshold: when the CTC score gap between
    # top two hypotheses is below this, assume the student is correct.
    # Higher = more conservative (fewer FP but also fewer detections).
    low_confidence_threshold: float = 1.5
