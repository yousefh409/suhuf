# i3rab: Plans for High-Accuracy Diacritized Arabic Reading Correction

**Goal:** User reads a known book aloud. System follows along in real-time and corrects their i3rab (grammatical diacritization/case endings).

**Core challenge:** We need to detect what diacritics the user ACTUALLY PRONOUNCED (including their mistakes), then compare against the known correct diacritization. This is pronunciation assessment, not text diacritization.

---

## Plan 1: Fine-Tune NeMo PCD on Diacritized MSA Data

**Concept:** The PCD model already produces diacritics on Quranic Arabic (6.55% WER). Fine-tune it on additional fully diacritized MSA data so it generalizes beyond Quran.

**How it works:**
1. Start from `nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0`
2. Freeze encoder (unfreeze BatchNorm/SqueezeExcite layers)
3. Fine-tune decoder on diacritized MSA speech data
4. Use the fine-tuned model to transcribe user speech with diacritics
5. Diff the transcription against the known correct text

**Training data:**
- EveryAyah: ~830h, fully diacritized Quranic (already seen by model)
- ClArTTS: 12h, fully diacritized Classical Arabic (MBZUAI)
- ArVoice: 83.5h, multi-speaker diacritized MSA (new, 2025)
- Synthetic TTS: Generate speech from Tashkeela corpus (~75M diacritized words) using `facebook/mms-tts-ara` or `MBZUAI/speecht5_tts_clartts_ar` — potentially hundreds of hours
- NADI 2025 data: 85K+ diacritized sentences with audio

**Compute:** 1x A100 80GB, days to low weeks

**Expected accuracy:**
- Quranic text: ~93-95% (already near this)
- MSA with diacritics: ~80-85% (up from current ~83% undiacritized, minus diacritic overhead)
- I3rab specifically (case endings): ~70-80% — the hardest part, requires syntactic understanding

**Risks:**
- NeMo Issue #3795: SentencePiece tokenizer can silently drop diacritics during training. Must test on NeMo 2.0+ carefully.
- Domain mismatch: Quranic recitation style != natural MSA reading
- Limited fully diacritized MSA speech data exists (the fundamental bottleneck)

**Pros:**
- Single model, clean architecture
- Captures what the user actually said (including errors)
- FastConformer is fast at inference (~1000x real-time)

**Cons:**
- Diacritized MSA training data is scarce
- May need synthetic data heavily, which introduces TTS artifacts
- i3rab accuracy will likely be the weak point

---

## Plan 2: Fine-Tune Whisper + LoRA on Diacritized Data

**Concept:** Same idea as Plan 1 but using Whisper (larger model, better multilingual pretraining). LoRA makes it feasible on consumer GPUs.

**How it works:**
1. Start from `openai/whisper-large-v3`
2. Apply LoRA (r=32, alpha=64, target: q_proj + v_proj)
3. Fine-tune on diacritized Arabic speech
4. Transcribe user speech → diff against known text

**Key evidence:** Aldarmaki (Interspeech 2023) showed that fine-tuning Whisper on 10h of diacritized ClArTTS data achieved good diacritic coverage+precision. The follow-up (NAACL 2024) achieved **2.7% DER** with a hybrid Text+ASR approach on Classical Arabic.

**Training data:** Same as Plan 1

**Compute:** Feasible on free Colab T4 (16GB) with INT8 quantization + LoRA. Training: ~5-10 epochs, lr=5e-4, batch size 6.

**Expected accuracy:**
- Classical Arabic: ~97% DER (based on Aldarmaki's 2.7% DER result)
- MSA with diacritics: ~85-90% (with sufficient training data)
- I3rab specifically: ~75-85%

**Pros:**
- Lower compute cost than Plan 1 (LoRA)
- Whisper has stronger multilingual pretraining
- Proven to work for diacritized Arabic (Aldarmaki 2023)
- Captures actual user pronunciation

**Cons:**
- Whisper is seq2seq — may "hallucinate" or auto-correct user mistakes instead of faithfully transcribing errors
- Slower inference than FastConformer
- Same data scarcity issue as Plan 1

---

## Plan 3: Forced Alignment + GOP Hypothesis Testing (Known-Text Advantage)

**Concept:** Since you know the book text, don't do open ASR at all. Instead, force-align the audio to the expected phoneme sequence and score whether each vowel matches.

**How it works:**
1. Pre-process: Convert the known diacritized text to phoneme sequences (including short vowels fatha=/a/, kasra=/i/, damma=/u/)
2. For each word, generate alternative phoneme sequences for all valid i3rab options (nominative, accusative, genitive)
3. When user reads: run CTC-based forced alignment against the audio
4. Compute GOP (Goodness of Pronunciation) score for each phoneme
5. For ambiguous vowels: score the audio against ALL hypothesis phoneme sequences, pick the best match
6. Compare best-matching hypothesis to the correct diacritization

**Tools:**
- Phonemizer: `quran-phonemizer` (71 phonemes, NeurIPS 2025) for Quranic text, or build an MSA phonemizer using CAMeL Tools morphology analyzer
- Forced aligner: `ctc-forced-aligner` (pip install, supports Arabic, uses wav2vec2/MMS)
- GOP scoring: CTC-based GOP (Interspeech 2024, no alignment needed) or classic alignment-based GOP
- Morphological analysis: `camel-tools` to generate all valid diacritized forms per word with case info

**The ERN (Extended Recognition Network) approach:**
```
For the word "الكتاب" in context:

Correct (nominative):  al-kitaab-U  (damma)
Wrong (accusative):    al-kitaab-A  (fatha)
Wrong (genitive):      al-kitaab-I  (kasra)
Wrong (no vowel):      al-kitaab-∅  (sukun/pausal)

Score audio against all 4 → pick best match → compare to correct
```

**Expected accuracy:**
- Word tracking (position in book): ~95%+ (undiacritized ASR is reliable for this)
- Vowel detection (careful reading): ~80-90%
- Vowel detection (natural speech): ~65-75%
- Vowel detection (pausal forms): Need explicit handling — pausal = no case ending = correct

**Key research numbers:**
- Horouf study (2025): wav2vec2-xlsr fine-tuned on Arabic phonemes → 65% test accuracy on isolated diacritized letters, but this is 112-way classification. Binary/4-way (which vowel?) on known words should be much higher.
- QPS system (2025): 0.16% PER on Quranic phonemes using multi-level CTC — but that's with extensive Quranic training data
- QuranMB (Interspeech 2025): 87.35% true acceptance, 25.71% false acceptance — concerning false acceptance rate

**Pros:**
- No ASR hallucination — you're scoring against known hypotheses
- Directly answers "which diacritization did they say?"
- Works without massive diacritized speech training data
- Per-word granularity for feedback
- Can provide confidence scores per word

**Cons:**
- Requires building phoneme dictionaries for the book text
- Pausal forms are a major complication (stopping mid-sentence drops i3rab — and that's correct)
- Short vowels at word endings are acoustically subtle (~30-50ms)
- 25% false acceptance rate (accepting wrong pronunciation) is a concern
- Requires the phonemizer to handle MSA, not just Quran

---

## Plan 4: Two-Stage Hybrid (ASR Tracking + Phoneme Diacritics Scoring)

**Concept:** Separate the easy problem (tracking position) from the hard problem (detecting diacritics). Use a standard ASR model for tracking, and a specialized phoneme model for diacritics assessment.

**How it works:**

**Stage 1 — Position Tracking (easy, solved):**
1. Run undiacritized ASR (NeMo PC model, Whisper, or Munsit) on streaming audio
2. Fuzzy-match output against the book text to find current position
3. Segment audio into per-word or per-phrase chunks aligned to book position

**Stage 2 — Diacritics Assessment (hard, per-word):**
1. For each word segment from Stage 1, extract the audio chunk
2. Generate expected phoneme sequences for all valid diacritizations of that word (using CAMeL Tools)
3. Score the audio against each hypothesis using:
   - CTC forced alignment + phoneme posterior probabilities
   - A fine-tuned wav2vec2 Arabic phoneme classifier
   - GOP scoring
4. Select the best-matching diacritization
5. Compare to correct i3rab → generate feedback

**Expected accuracy:**
- Stage 1 (position tracking): ~95%+
- Stage 2 (diacritics per word, careful reading): ~80-88%
- Stage 2 (natural reading): ~70-80%

**Pros:**
- Clean separation of concerns
- Position tracking is already solved and reliable
- Diacritics assessment operates on isolated word segments (easier than full-sentence phoneme recognition)
- Can tune confidence thresholds — only flag errors you're sure about
- Modular: can upgrade each stage independently

**Cons:**
- Two-model pipeline adds latency
- Word segmentation errors in Stage 1 propagate to Stage 2
- Connected speech effects (liaison, assimilation) between words are lost when segmenting

---

## Plan 5: Multimodal Diacritization (CATT-Whisper Architecture)

**Concept:** Combine a text diacritization model (which knows correct grammar) with a speech encoder (which hears what the user actually said). The text model provides the "what should be correct" signal, the speech model provides the "what was actually said" signal.

**How it works:**
1. Text encoder: CATT (Character-based Arabic Tashkeel Transformer) — SOTA text diacritizer
2. Speech encoder: Whisper-base or wav2vec2 — extracts acoustic features
3. Fusion: Cross-attention between text tokens and speech tokens
4. Output: Per-character diacritic prediction informed by BOTH text context and acoustic evidence
5. Train end-to-end on diacritized speech data

**Architecture (from NADI 2025 winning system):**
```
Known text → CATT encoder → text embeddings ─────┐
                                                   ├→ Cross-Attention → Diacritic classifier
User audio → Whisper encoder → speech embeddings ─┘
```

**Key innovation:** During training, randomly deactivate the speech input so the model learns to work with text-only (fallback) or text+speech (full accuracy). This means:
- With audio: detects what the user actually said
- Without audio: falls back to text-only diacritization (gives correct answer)
- The DIFFERENCE between the two = user's errors

**Expected accuracy:**
- NADI 2025 results: Dev WER 0.25%, Test WER 55% (but this was on dialectal Arabic, a much harder setting)
- On MSA known text with audio: estimated ~88-93% per-character diacritic accuracy
- On i3rab specifically: ~82-88%

**Training data needed:**
- Diacritized text: Tashkeela + ATB (millions of words, readily available)
- Diacritized speech: EveryAyah + ClArTTS + ArVoice + synthetic TTS
- Can pre-train text and speech encoders separately, then fine-tune fusion

**Compute:** Moderate — CATT is small, Whisper-base is small. Main cost is fusion training.

**Pros:**
- Theoretically the highest accuracy ceiling — uses both modalities
- Text encoder provides strong syntactic prior (helps with i3rab)
- Speech encoder captures actual pronunciation
- Can compare text-only vs text+speech outputs to identify errors
- Cutting-edge approach (NADI 2025 winning system)

**Cons:**
- Most complex to implement
- Requires training a fusion model
- Relatively new approach — less proven
- Still needs diacritized speech data for training

---

## Plan 6: Diacritized ASR + Text Diacritizer Comparison

**Concept:** Run two systems in parallel on the same input. One captures what the user said, the other computes what's correct. Diff them.

**How it works:**
1. **What they said:** Fine-tuned diacritized ASR model (Plan 1 or 2) transcribes user audio with diacritics
2. **What's correct:** The known book text already has correct diacritization (or compute it with CATT/SUKOUN if the book is undiacritized)
3. **Diff:** Character-level comparison between ASR output and reference text
4. Where diacritics differ → flag as i3rab error

**Reference text diacritization (if book isn't already diacritized):**

| Model | DER (with i3rab) | Type |
|-------|-----------------|------|
| CATT | 8.6% | Open-source, pip install |
| SUKOUN | 1.14% syntactic | BERT-based |
| Claude 3.7 Sonnet | 1.4% | API call |
| GPT-4 | 3.9% | API call |
| PTCAD | 1.1% | BERT-based |

For a known book, you'd diacritize the text ONCE offline (or have it manually diacritized) — so accuracy here can be very high with human review.

**Expected accuracy:**
- Depends entirely on the ASR diacritization quality (Plan 1 or 2)
- If ASR faithfully transcribes what user said with diacritics: ~85-90% error detection
- Main failure mode: ASR "corrects" user mistakes (produces correct diacritics even when user said wrong ones)

**Pros:**
- Conceptually simple
- Reference text can be verified by humans for 100% accuracy
- Clean comparison

**Cons:**
- ASR seq2seq models (especially Whisper) tend to auto-correct, making them UNFAITHFUL to pronunciation errors
- This is the fundamental flaw: if the user says "الكتابَ" (wrong, accusative) where it should be "الكتابُ" (correct, nominative), the ASR might output the correct form anyway because it has language model bias
- CTC-based models (FastConformer CTC decoder) are more faithful than seq2seq models

---

## Plan 7: LLM-Powered Assessment (Fallback / Augmentation)

**Concept:** Use an Arabic-capable LLM to analyze the undiacritized ASR output in context and assess what the user likely said, given acoustic confidence scores.

**How it works:**
1. Run standard ASR to get undiacritized transcription + word-level confidence scores
2. Run forced alignment to get phoneme-level posterior probabilities for vowels at word endings
3. Feed to LLM: "Given this text, these acoustic confidence scores for final vowels, and the correct diacritization, what did the user likely say and where did they make i3rab errors?"
4. LLM uses its syntactic knowledge to disambiguate borderline cases

**LLM diacritization accuracy (for reference text):**

| Model | DER (SadeedDiac-25) | Cost |
|-------|---------------------|------|
| Claude 3.7 Sonnet | 1.4% | ~$0.01/paragraph |
| GPT-4 | 3.9% | ~$0.02/paragraph |
| Gemini 2.0 Pro | ~0-0.8% (inconsistent) | ~$0.01/paragraph |

**Expected accuracy:** Depends on acoustic feature quality. The LLM would mainly help with disambiguation in borderline cases.

**Pros:**
- Can leverage the world's best Arabic language understanding
- Handles complex i3rab rules (idafa, predicates, exceptions) better than any specialized model
- No training needed

**Cons:**
- Latency (API calls per sentence)
- Cost at scale
- LLM has no direct access to audio — relies on acoustic features you extract
- Not a standalone solution — needs acoustic input from another system

---

## Comparison Matrix

| Plan | i3rab Accuracy (est.) | Latency | Compute Cost | Data Needs | Complexity | Captures User Errors? |
|------|----------------------|---------|--------------|------------|------------|----------------------|
| 1. Fine-tune NeMo PCD | 70-80% | Low | High (A100) | High | Medium | Yes (CTC decoder) |
| 2. Fine-tune Whisper+LoRA | 75-85% | Medium | Low (T4) | High | Low | Partially (seq2seq corrects) |
| 3. Forced Alignment + GOP | 80-90% | Low | None (inference only) | Low | High | Yes (direct scoring) |
| 4. Two-Stage Hybrid | 80-88% | Medium | Medium | Medium | High | Yes |
| 5. CATT-Whisper Multimodal | 82-88% | Medium | Medium | Medium | Very High | Yes |
| 6. ASR + Reference Diff | 70-85% | Low | Medium | High | Low | Partially |
| 7. LLM Augmentation | +5-10% boost | High | Low (API) | None | Low | Indirectly |

---

## My Recommended Approach: Plan 4 + Plan 3 + Plan 7

A combination that plays to each approach's strength:

### Phase 1: Position Tracking (Plan 4, Stage 1)
- Use NeMo PC model or Whisper for streaming undiacritized ASR
- Fuzzy-match to book text for real-time position tracking
- This is solved technology — expect 95%+ accuracy

### Phase 2: Diacritics Detection (Plan 3)
- For each word the user reads, generate all valid diacritized forms using CAMeL Tools
- Run CTC forced alignment with hypothesis testing
- Score which diacritization the user actually produced
- Only flag errors above a confidence threshold (tunable)

### Phase 3: Smart Disambiguation (Plan 7)
- For borderline/ambiguous cases, use LLM context to improve accuracy
- Batch borderline cases and send to Claude/GPT for syntactic analysis
- Handles complex i3rab rules that pure acoustic models miss

### Phase 4 (Future): Fine-Tune End-to-End (Plan 1 or 5)
- Once you have user data (with corrections), train a specialized model
- Use the correction feedback as supervised training signal
- Build toward a single-model solution over time

**Expected combined accuracy:** ~85-92% i3rab detection in careful reading

---

## Critical Considerations

### Pausal Forms (waqf)
When a speaker stops at the end of a phrase, Arabic grammar drops the case ending. "الكتابْ" (with sukun) at a pause is CORRECT — not an error. Your system must:
- Detect phrase boundaries/pauses
- Not flag missing case endings at pauses as errors
- Only assess i3rab in connected speech (wasl)

### What "Error" Means
Define clearly:
- Missing diacritic where one is required → error
- Wrong case ending (fatha instead of damma) → clear error
- Pausal form at end of phrase → NOT an error
- Partial diacritization (some words diacritized, some not) → context-dependent

### User Experience
- Don't flag every error in real-time (overwhelming)
- Consider sentence-by-sentence or phrase-by-phrase assessment
- Provide a confidence indicator: "certain error" vs "possible error"
- Allow users to replay and self-assess borderline cases

### Training Data Gap
The single biggest bottleneck is **diacritized MSA speech data**. Currently available:
- EveryAyah: 830h (Quranic only)
- ClArTTS: 12h (Classical, single speaker)
- ArVoice: 83.5h (MSA, multi-speaker, 2025)
- Everything else is undiacritized

**The TTS synthetic data approach is critical** for bridging this gap.

---

## Key References

### Models
- NVIDIA PCD: https://huggingface.co/nvidia/stt_ar_fastconformer_hybrid_large_pcd_v1.0
- CATT diacritizer: https://github.com/abjadai/catt (`pip install catt-tashkeel`)
- CAMeL Tools morphology: https://github.com/CAMeL-Lab/camel_tools
- Quranic Phonemizer: https://github.com/Hetchy/Quranic-Phonemizer
- CTC Forced Aligner: https://github.com/MahmoudAshraf97/ctc-forced-aligner
- Tarteel Whisper: https://huggingface.co/tarteel-ai/whisper-base-ar-quran

### Papers
- Aldarmaki 2023 (ASR diacritics): https://arxiv.org/abs/2302.14022
- Aldarmaki 2024 (hybrid Text+ASR diacritics, 2.7% DER): https://arxiv.org/abs/2311.10771
- CATT (SOTA text diacritizer): https://arxiv.org/abs/2407.03236
- CATT-Whisper multimodal: https://arxiv.org/abs/2510.24247
- NVIDIA ICASSP 2025: https://arxiv.org/abs/2507.13977
- Horouf (Arabic phoneme assessment): https://arxiv.org/abs/2508.19587
- QPS Quran system (0.16% PER): https://arxiv.org/abs/2509.00094
- IqraEval shared task: https://huggingface.co/IqraEval
- SUKOUN (syntactic diacritics, 1.14% DER): https://www.sciencedirect.com/science/article/abs/pii/S0957417424002811
- Sadeed (small LM diacritizer): https://arxiv.org/abs/2504.21635

### Datasets
- EveryAyah: https://huggingface.co/datasets/tarteel-ai/everyayah
- ClArTTS: https://huggingface.co/datasets/MBZUAI/ClArTTS
- Tashkeela: https://www.kaggle.com/linuxscout/tashkeela
- Sadeed Tashkeela (cleaned): https://huggingface.co/datasets/Misraj/Sadeed_Tashkeela
