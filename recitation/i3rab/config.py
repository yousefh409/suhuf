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
    pcd_model_path: str = "models/pcd_clartts_v4.nemo"

    # SSL CTC model directory (HuggingFace wav2vec2 or w2v-bert)
    # Set this to use SSLTranscriber instead of PCDTranscriber
    ssl_model_dir: str = "models/ssl_xls_r_v5"

    # Training sample rate of the SSL model (16000 for v5, 40100 for v1/v2)
    ssl_training_sr: int = 16000

    # Use joint lattice scoring (WFST-style beam search) instead of
    # independent per-word CTC scoring.
    use_joint_scoring: bool = False

    # RNN-T ensemble weight: 0.0 = CTC only, 0.3 = 70% CTC + 30% RNN-T
    # Note: RNN-T is ~100x slower with no accuracy improvement. Disabled.
    rnnt_weight: float = 0.0

    # Tashkeel CTC verification threshold: decoded word must score this much
    # better than reference to flag a tashkeel error. Higher = fewer FP, lower recall.
    tashkeel_threshold: float = 2.0

    # Single-position tashkeel threshold: when only one vowel position differs,
    # require a higher bar to avoid CTC noise false positives.
    single_pos_tashkeel_threshold: float = 8.0

    # Proactive tashkeel scoring threshold: segment-level CTC score gap needed
    # for an alternative vowel to be flagged. Higher = fewer FP.
    proactive_tashkeel_threshold: float = 3.5

    # Enable tashkeel detection via per-word CTC decode in PCD mode.
    # When False, PCD only detects i3rab (case ending) errors and wrong words.
    # Disable if tashkeel FP rate is too high for the current model.
    pcd_tashkeel_detection: bool = True

    # Low-confidence i3rab fallback threshold: when the CTC score gap between
    # top two hypotheses is below this, assume the student is correct.
    # Higher = more conservative (fewer FP but also fewer detections).
    # 1.0 for NeMo PCD, 1.5 for XLS-R SSL (larger CTC gaps).
    low_confidence_threshold: float = 1.5

    # ── PDF Pipeline Settings ───────────────────────────────────────────

    # Directory for uploaded PDFs
    pdf_upload_dir: str = "uploads"

    # Cache directory for analysis results
    cache_dir: str = "cache"

    # PDF page rendering DPI
    pdf_render_dpi: int = 150

    # Primary LLM for i3rab analysis (used with OPENAI_API_KEY)
    irab_primary_model: str = "gpt-4o"

    # Review LLM for i3rab cross-validation (uses ANTHROPIC_API_KEY, falls back to OpenAI)
    irab_review_model: str = "claude-sonnet-4-20250514"

    # Maximum concurrent sentence analyses
    irab_max_concurrency: int = 3
