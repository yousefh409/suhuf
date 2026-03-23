# i3rab Improvement Recommendations

## Root Causes of Current Errors

1. **Model too small** — `tarteel-ai/whisper-base-ar-quran` is only 74M parameters. The log-probability differences between diacritized variants (e.g. الكتابَ vs الكتابُ) are tiny, and a base model doesn't have enough capacity to reliably distinguish them.

2. **Attention-based scoring is the wrong tool** — Whisper's encoder-decoder uses attention (non-monotonic), but speech is monotonic. This causes attention drift, hallucinations, and unreliable log-probs, especially for short words where the diacritical difference is a single vowel.

3. **Whole-phrase scoring for individual words** — The full phrase audio is encoded but each word's hypotheses are scored against the full encoder output. The model's log-prob for one word is contaminated by the rest of the phrase.

4. **Confidence thresholds are arbitrary** — Gap-based confidence (0.15/0.3) assumes the score distribution is well-calibrated, but Whisper is known to be overconfident under noise ([arxiv.org/abs/2509.07195](https://arxiv.org/abs/2509.07195)).

---

## Quick Wins (No Architecture Changes)

| Fix | Where | Impact |
|-----|-------|--------|
| Use `whisper-large-v3` or `IJyad/whisper-large-v3-Tarteel` instead of `whisper-base` | `config.py` → `asr_model` | High — larger model = better log-probs |
| Add temperature scaling to logits before softmax | `scorer.py` → `_score_text()` | Medium — better calibrated scores |
| Score words with isolated audio segments (use word-level timestamps) | `scorer.py` → `score_phrase()` | High — avoids cross-word contamination |
| Raise position tracker match threshold from 0.5 to 0.6 | `tracker.py` | Medium — fewer false matches |
| Add dual/plural hypothesis forms | `book.py` → `_generate_irab_hypotheses()` | Medium — catches more grammatical forms |

---

## Recommended Alternatives (Ranked by Impact/Difficulty)

### 1. Drop-in: Larger Whisper Model

**Effort:** Low | **Impact:** High

Swap `tarteel-ai/whisper-base-ar-quran` for:
- **`openai/whisper-large-v3-turbo`** — same accuracy as large-v2, faster inference
- **`IJyad/whisper-large-v3-Tarteel`** — large-v3 fine-tuned on Quranic data (2B params, [HuggingFace](https://huggingface.co/IJyad/whisper-large-v3-Tarteel))
- **`KheemP/whisper-base-quran-lora`** — LoRA fine-tune with ~5.98% WER ([HuggingFace](https://huggingface.co/KheemP/whisper-base-quran-lora))

This alone could dramatically improve discrimination since larger models produce better-calibrated log-probabilities.

### 2. CTC Forced Alignment Scoring

**Effort:** Low-Medium | **Impact:** High

Replace attention-based scoring with CTC forced alignment (monotonic, better suited for pronunciation scoring):

- **[`ctc-forced-aligner`](https://github.com/MahmoudAshraf97/ctc-forced-aligner)** — `pip install ctc-forced-aligner`, supports Arabic out of the box
- Uses **`facebook/mms-1b-all`** (1B params, 1130 languages, [HuggingFace](https://huggingface.co/facebook/mms-1b-all)) or **`MahmoudAshraf/mms-300m-1130-forced-aligner`** ([HuggingFace](https://huggingface.co/MahmoudAshraf/mms-300m-1130-forced-aligner))
- Score each diacritized hypothesis by computing CTC alignment log-likelihood
- Monotonic alignment = no attention drift = more reliable scores

Also consider **torchaudio's built-in forced alignment** ([tutorial](https://docs.pytorch.org/audio/stable/tutorials/forced_alignment_tutorial.html)) with `jonatasgrosman/wav2vec2-large-xlsr-53-arabic` ([HuggingFace](https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-arabic)).

### 3. Ensemble: Whisper + CTC

**Effort:** Medium | **Impact:** Very High

Combine both scoring methods:

```
final_score = α × whisper_logprob + β × ctc_alignment_score
```

Different models capture complementary signals — Whisper captures sequence-level context, CTC captures frame-level phonetic alignment. Tune α and β on a small validation set.

### 4. CTC Head on Whisper Encoder

**Effort:** Medium | **Impact:** Very High

- Freeze Whisper's encoder (trained on 680K hours of audio)
- Add a linear CTC head: `hidden_size → diacritized_arabic_vocab_size`
- Train with CTC loss on diacritized Arabic speech data (e.g., Tarteel Quran dataset)
- Use the CTC trellis path score for hypothesis ranking

SpeechBrain provides the training framework ([docs](https://speechbrain.readthedocs.io/en/latest/tutorials/nn/using-wav2vec-2.0-hubert-wavlm-and-whisper-from-huggingface-with-speechbrain.html)).

### 5. Fine-tune Whisper on Diacritized Transcripts (Aldarmaki Approach)

**Effort:** Medium | **Impact:** Very High

Per [Aldarmaki et al. (INTERSPEECH 2023)](https://arxiv.org/abs/2302.14022): fine-tuning Whisper on manually diacritized transcripts makes it output diacritized text directly, and this significantly outperforms text-based diacritization. They achieved a **50% reduction in diacritic error rates** with only 10 hours of training data.

Two ways to use this:
- **Replace hypothesis scoring entirely** — model outputs diacritized text, compare against book's correct form
- **Keep hypothesis scoring** — but use the fine-tuned model for better log-probs when scoring hypotheses

Related open-source resources:
- ArTST v1.5 (diacritized pre-training): [github.com/mbzuai-nlp/ArTST](https://github.com/mbzuai-nlp/ArTST)
- HuggingFace models: [MBZUAI collection](https://huggingface.co/collections/MBZUAI/artst-arabic-text-speech-transformer-672cb44bb4215fd38814aeef)
- Whisper fine-tuning guide: [huggingface.co/blog/fine-tune-whisper](https://huggingface.co/blog/fine-tune-whisper)

### 6. CATT-Whisper Multimodal Architecture

**Effort:** High | **Impact:** Very High

[CATT-Whisper (Abjad AI, NADI 2025)](https://arxiv.org/abs/2510.24247) fuses a text encoder (CATT) with Whisper's speech encoder for diacritization conditioned on both undiacritized text and audio. Achieved **WER 0.55, CER 0.13**. This is purpose-built for the exact problem i3rab solves — takes undiacritized text + audio → outputs diacritized text — but end-to-end trained. No public weights yet; would need to reproduce training.

### 7. Phoneme-Level Scoring

**Effort:** Medium | **Impact:** Medium

Arabic diacritics map directly to IPA vowels (fatha=/a/, damma=/u/, kasra=/i/):
- **[Allosaurus](https://github.com/xinjli/allosaurus)** — universal phone recognizer, supports Arabic
- Extract phones from audio, convert each hypothesis to expected phone sequence, score by similarity
- Less reliable than CTC but provides an orthogonal signal useful in ensembles

---

## Alternative Base Models Worth Evaluating

| Model | Type | Arabic Perf | HuggingFace |
|-------|------|-------------|-------------|
| `openai/whisper-large-v3-turbo` | Encoder-decoder | Near SOTA | [link](https://huggingface.co/openai/whisper-large-v3-turbo) |
| `IJyad/whisper-large-v3-Tarteel` | Encoder-decoder (Quran) | Quranic domain | [link](https://huggingface.co/IJyad/whisper-large-v3-Tarteel) |
| `facebook/mms-1b-all` | CTC (wav2vec2) | 1130 languages | [link](https://huggingface.co/facebook/mms-1b-all) |
| `asafaya/hubert-large-arabic-ft` | CTC (HuBERT) | CER 5.49% CV | [link](https://huggingface.co/asafaya/hubert-large-arabic-ft) |
| `MBZUAI/artst_asr` | SpeechT5 | 12.8% WER MGB2 | [link](https://huggingface.co/MBZUAI/artst_asr) |
| Nvidia Conformer-CTC-Arabic | CTC (Conformer) | #1 Arabic leaderboard | [link](https://huggingface.co/MostafaAhmed98/Conformer-CTC-Arabic-ASR) |
| `speechbrain/asr-whisper-large-v2-commonvoice-ar` | Encoder-decoder | General Arabic | [link](https://huggingface.co/speechbrain/asr-whisper-large-v2-commonvoice-ar) |

---

## Key Papers

| Paper | Year | Core Finding | Link |
|-------|------|-------------|------|
| Aldarmaki & Ghannam | 2023 | Fine-tuning ASR with diacritized transcripts beats text-based diacritization | [arxiv.org/abs/2302.14022](https://arxiv.org/abs/2302.14022) |
| CATT-Whisper (Abjad AI) | 2025 | Multimodal text+speech fusion for diacritization (WER 0.55) | [arxiv.org/abs/2510.24247](https://arxiv.org/abs/2510.24247) |
| CrisperWhisper | 2024 | Better word timestamps via cross-attention DTW | [arxiv.org/abs/2408.16589](https://arxiv.org/abs/2408.16589) |
| Min Lookahead Beam Search | 2023 | Constrained decoding improves low-resource ASR | [arxiv.org/abs/2309.10299](https://arxiv.org/abs/2309.10299) |
| Overconfidence in Noisy ASR | 2025 | Temperature scaling fixes Whisper's overconfidence | [arxiv.org/abs/2509.07195](https://arxiv.org/abs/2509.07195) |
| Phonological MDD | 2023 | Articulatory feature detection via wav2vec2 | [arxiv.org/abs/2311.07037](https://arxiv.org/abs/2311.07037) |
| N-Shot Arabic Whisper | 2023 | Different Whisper models have complementary strengths | [arxiv.org/abs/2306.02902](https://arxiv.org/abs/2306.02902) |
| Arabic ASR Leaderboard | 2024 | Conformer-CTC #1 for Arabic | [arxiv.org/abs/2412.13788](https://arxiv.org/abs/2412.13788) |
| Whisper Confidence | 2025 | Fine-tune Whisper for calibrated confidence scores | [arxiv.org/abs/2502.13446](https://arxiv.org/abs/2502.13446) |
