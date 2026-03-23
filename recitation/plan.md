# Plan: WFST Lattice Scoring + Large-Scale Evaluation

## Goal
1. Replace N-separate-CTC-score approach with WFST-style joint lattice scoring
2. Build a larger evaluation suite using ClArTTS test set (205 samples) with optional MUSAN noise
3. Tune for precision > recall (minimize false positives, accept missing some errors)

## Current Bottleneck
`score_word_in_context()` does ~8 CTC loss computations per content word (one per hypothesis). For a 10-word sentence, that's ~80 CTC loss calls. Each builds a full sentence string, tokenizes, and runs CTCLoss forward. These are cheap (no encoder re-run), but:
- Each word is scored independently — no joint optimization
- Can't capture inter-word constraints (e.g., if word 3 is genitive, word 4's score distribution may shift)
- Redundant tokenization: words that aren't changing get re-tokenized every time

## Approach: Lattice CTC Scoring (no external WFST library needed)

Since k2/gtn aren't installed and installing them on macOS is non-trivial, we'll implement lattice scoring **using pure PyTorch CTC loss** — no new dependencies.

### How it works:

Instead of building N full sentences per word and scoring each independently, we:

1. **Build a lattice of all hypothesis combinations** — but intelligently pruned
2. **Score the top-K joint paths** through the lattice using CTC loss
3. **Extract per-word marginal scores** from the joint path scores

**Pruning strategy** (keeps it tractable):
- Words with 1 hypothesis: fixed (particles, function words) — no branching
- Words with >1 hypothesis: only branch at positions where scoring matters
- Grammar constraints already prune ~30% of hypotheses
- For a 10-word sentence with ~3 content words averaging 8 hypotheses: 8^3 = 512 paths → prune to top-K (e.g., K=32) using beam search

**Beam search approach:**
1. Start with the reference sentence (all correct forms) as the initial beam
2. For each content word position (left to right), expand the beam:
   - For each path in the beam, try all hypotheses at this position
   - Score each expanded path with `_ctc_score()`
   - Keep top-K paths
3. After processing all positions, extract per-word winners by marginalizing

This is architecturally similar to WFST composition but implemented directly with CTC scoring. The key advantage: **words are scored in the context of other words' hypotheses**, not independently.

### Implementation: `score_words_joint()` in `pcd_transcriber.py`

```python
def score_words_joint(
    self,
    log_probs,
    encoded_len,
    all_words: list[BookWord],
    beam_width: int = 16,
) -> list[ScoredWord]:
    """Score all words jointly using beam search over hypothesis lattice."""
```

Returns `list[ScoredWord]` for all words at once (vs calling `score_word_in_context()` per word).

## Step 1: Implement `score_words_joint()` in `pcd_transcriber.py`

- Beam search over hypothesis lattice
- Only branch at multi-hypothesis word positions
- Return per-word ScoredWord with joint-context confidence

## Step 2: Build ClArTTS evaluation harness

New file: `eval_clartts.py`

- Load ClArTTS test set (205 samples) from HuggingFace
- Each sample has diacritized text + audio
- For each sample:
  - Use the diacritized text as the "book" (reference)
  - Feed audio through `evaluate_pcd_live()`
  - Since the audio IS the correct reading, every word should be CORRECT or PAUSAL_OK
  - Any WRONG_IRAB or WRONG_TASHKEEL = **false positive**
- Compute: false positive rate, per-category breakdown

Optional: add MUSAN noise at various SNR levels (5, 10, 15, 20 dB) to test robustness.

## Step 3: Run comparison

Compare on both test sets:
1. **Your 23 recordings** (271 words): measures recall (catching actual errors + avoiding false positives on correct readings)
2. **ClArTTS 205 samples** (~2000+ words): measures false positive rate (all readings are correct, any error = false positive)

Metrics:
- **False positive rate** (ClArTTS): % of correct words flagged as errors
- **Accuracy** (your recordings): current 268/271
- Run both with current approach vs WFST lattice approach

## Step 4: Tune thresholds on ClArTTS

If false positive rate is high, tune:
- `_PAUSAL_MARGIN` (currently 5.0)
- Low-confidence fallback threshold (currently 1.5)
- CTC tashkeel verification threshold (currently 2.0)
- Alignment score threshold for tashkeel checking (currently -2.0)

Goal: minimize false positives on ClArTTS while maintaining accuracy on your recordings.

## Estimated Impact
- WFST lattice: may improve 0-2 words on your recordings (joint context), main benefit is architectural correctness
- ClArTTS evaluation: gives confidence in real-world false positive rate
- Threshold tuning on larger dataset: likely the biggest practical improvement for balance
