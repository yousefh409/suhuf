# Next Steps: Pushing Past 98.6% Accuracy

Current state: **282/286 words correct (98.6%)**. Up from 97.6% after switching to `whisper-large-v3`. The remaining 4 errors are all i3rab scoring errors where Whisper's decoder picks the wrong case ending.

---

## What's Been Tried

### whisper-large-v3 (1.55B) — IMPLEMENTED, +1.0%

Swapped `whisper-large-v3-turbo` (809M, 4 decoder layers) for the full `whisper-large-v3` (1.55B, 32 decoder layers). The 32 decoder layers give richer contextual modeling of token sequences.

- **Result**: 97.6% → 98.6% (+3 net words). Fixed 5 of the original 7 errors, introduced 2 new ones.
- **Note**: MPS (Apple Silicon) requires float32 — float16 produces garbage output with the larger model. This is handled in `scorer.py:_resolve_dtype()`.
- **Tradeoff**: ~2x slower inference, ~2x more memory. Float32 on MPS adds further overhead.

### Phoneme-Based Scoring — TESTED, NOT VIABLE

Tested `IbrahimSalah/Wav2vecLarge_quran_syllables_recognition` (300M, Wav2Vec2ForCTC) as a fallback scorer for low-confidence Whisper results. Two approaches were tried:

**Approach 1: Single-word syllable decoding**
- Extract word audio using timestamps, run phoneme model, decode syllables, extract last haraka
- **Result**: Catastrophic regression (98.6% → ~90%). The model needs full-sentence context — single-word audio segments are too short and noisy. It confidently detected wrong case endings, overriding correct Whisper results.

**Approach 2: Full-audio CTC scoring**
- Run phoneme model on full audio, extract CTC logits for each word's time range, compute CTC forward probability for each hypothesis
- **Result**: Regression (98.6% → 94.8%). The model's tokenizer is designed for syllable-segmented Quran text (e.g., "مِ نَلْ جِ نْ نَ تِ"), not unsegmented diacritized words (e.g., "المُعَلِّمِ"). CTC scores were unreliable — huge gaps (100+) in the wrong direction.
- **Root cause**: Fundamental vocabulary mismatch. The tokenizer can't meaningfully tokenize standard diacritized Arabic words, so P(hypothesis|audio) computations are meaningless.

**Infrastructure preserved**: `phoneme_scorer.py` and pipeline integration are in place but disabled (`use_phoneme_fallback: bool = False`). Can be re-enabled with a character-level phoneme model if one becomes available.

---

## Remaining 4 Errors

| Word | Expected | Detected | Gap | Sentence |
|---|---|---|---|---|
| سَأَلَ | acc (fatha) | nom (damma) | ~0.05 | rec_031 (20-word sentence) |
| أَعَدَّتِ | gen (kasra) | jussive (sukun) | small | rec_039 (32-word sentence) |
| اللَّذِيذَ | acc (fatha) | gen (kasra) | small | rec_039 (32-word sentence) |
| الطَّازِجَ | acc (fatha) | gen (kasra) | small | rec_040 (26-word sentence) |

Pattern: 3 of 4 errors are fatha→kasra (acc→gen). This suggests Whisper has a systematic bias toward kasra in certain phonetic contexts (possibly influenced by the preceding/following consonants or BPE tokenization).

---

## Remaining Approaches (ranked by effort-to-impact)

### 1. Fine-Tuning Whisper on Diacritized Arabic

**What**: Fine-tune `whisper-large-v3` on diacritized Arabic corpora so the decoder learns to distinguish case endings directly.

**Best datasets**:

| Dataset | Size | Quality | Use |
|---|---|---|---|
| `MBZUAI/ClArTTS` | 12h | Excellent (manual diacritics, single speaker, CC-BY-4.0) | Start here |
| `tarteel-ai/everyayah` | 829h | Good (canonical Quran diacritics, multi-reciter) | Scale up |
| `halabi2016/arabic_speech_corpus` | 3.7h | Excellent (manual diacritics, studio quality, CC-BY-4.0) | Evaluation |

**Key insight from literature**: The model must be trained with **manually diacritized transcripts** — auto-diacritization during training produces significantly worse results. (Aldarmaki & Ghannam, INTERSPEECH 2023 — https://arxiv.org/abs/2302.14022)

**Expected impact**: High. This is the only remaining approach that can fundamentally improve case ending discrimination. The hypothesis scoring architecture would still work on top.

**Effort**: High — requires GPU training (A100 recommended), dataset preparation, evaluation pipeline. ~1-2 days of engineering plus training time.

### 2. Character-Level Phoneme Model

**What**: Find or train a phoneme model with character-level vocabulary (not syllable-level) that can meaningfully tokenize diacritized Arabic words.

**Why the syllable model failed**: Its tokenizer splits text into syllables like "مِ", "نَلْ", etc. When given unsegmented words like "المُعَلِّمِ", the tokenizer produces nonsensical token sequences, making CTC scoring unreliable.

**What would work**: A Wav2Vec2ForCTC model trained on character-level Arabic (each diacritized character as a vocab token). This would allow direct CTC scoring of hypotheses since each haraka would be its own token.

**Status**: No such model exists on HuggingFace. Would need to be trained.

### 3. NVIDIA FastConformer (Quran-specific use case only)

`nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0` — 115M params, trained on 1,100h including 390h Quran recitations.

**Critical caveat**: Only outputs diacritics for Quranic Arabic audio. For MSA, diacritics are absent. See: https://github.com/NVIDIA-NeMo/NeMo/issues/15428

**Still useful for**: CTC forced alignment (better timestamps), Quran-specific applications, edge deployment (131MB ONNX).

---

## Available Models Summary

| Model | Size | Status | Result |
|---|---|---|---|
| `openai/whisper-large-v3` | 1.55B | **Active** | 98.6% accuracy |
| `openai/whisper-large-v3-turbo` | 809M | Replaced | 97.6% accuracy |
| `IbrahimSalah/Wav2vecLarge_quran_syllables_recognition` | 300M | Tested, not viable | Vocabulary mismatch |
| `nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0` | 115M | Not tested | Quran-only diacritics |
| `tarteel-ai/whisper-base-ar-quran` | 74M | Tested, failed | No timestamp support |

## Accuracy History

| Change | Accuracy | Delta |
|---|---|---|
| Baseline (isolated per-word scoring) | ~80% | — |
| Contextual scoring (full-sentence hypothesis swapping) | 92.0% | +12.0 |
| Fathatan+alef bug fix | 93.0% | +1.0 |
| Fuzzy match tolerance (SequenceMatcher >= 0.6) | 97.6% | +4.6 |
| whisper-large-v3 (32 decoder layers) | 98.6% | +1.0 |
