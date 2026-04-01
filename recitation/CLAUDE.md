# Recitation — Live Arabic Readalong

## Important

- **Do NOT look at git history.** There was a previous implementation that has been deleted. We are starting from scratch. The old code is irrelevant.
- The only thing carried over from before is the **XLS-R v5 CTC model** at `models/ssl_xls_r_v5/`. Everything else is new.

## What this is

A system that listens to a student read diacritized Arabic text aloud and corrects them on:

- Wrong words (said a different word, skipped one, added one)
- Wrong tashkeel (wrong internal vowels)
- Wrong i3rab (wrong case endings)
- Sukoon on the final letter is always acceptable (pausal/waqf form)

See `ONE-PAGER.md` for the full product description.

## How the end-result works

A simple webpage. The student opens it, sees a passage of diacritized Arabic text, hits record, and reads aloud. The system listens, follows along word by word, and highlights mistakes — wrong words in red, i3rab errors in blue, tashkeel errors in orange. Tap a flagged word to see what was expected vs. what was detected. Similar to Tarteel but for any Arabic text, not just Quran.

## What we have

- `models/ssl_xls_r_v5/` — fine-tuned XLS-R 300M CTC model (HuggingFace Wav2Vec2ForCTC format, 16kHz, 58 Arabic character tokens). This is the core — it can score how likely a given diacritized string matches a segment of audio.
- `passage.json` — full text blocks, fully diacritized: المقدمة الآجرومية (grammar), الداء والدواء (prose), إحياء علوم الدين (prose)
- `ihya2.txt` — raw tashkeeled source text for the Ihya passage
- `test_data/` — saved recordings + `manifest.jsonl` for testing and iteration

## Test data

- Recordings are in `test_data/recordings/` as `.webm` files
- `test_data/manifest.jsonl` has one JSON object per line with `file`, `passage_id`, `notes`, and `timestamp`
- **The test data may have small errors** — occasional background noise, slight mispronunciations not noted, or notes that don't perfectly describe what was said. Treat it as real-world data, not lab-perfect ground truth.

## Real-world edge cases the system must handle

- **Repeating words** — readers often repeat a word or go back a few words when they stumble. The system should not penalize this.
- **Slow vs fast readers** — some readers pause between words, others read in rapid connected speech (with idgham, etc.). Must work for both.
- **Background noise** — fans, AC, traffic, other people talking. Must be robust to ambient noise.
- **Pausal forms (waqf)** — sukoon on final letter is always acceptable. Readers naturally pause and stop mid-sentence.
- **Bismillah / throat clearing / filler sounds** — readers may say bismillah before starting, clear their throat, say "umm", etc.
- **Partial phrases** — reader might only read half the phrase before stopping.
- **Connected speech** — words blend together in natural reading (e.g. wasla on alif lam, idgham of noon with following letter).
- **Microphone variation** — different devices, distances, recording quality. Laptop mic vs phone vs headset.

## Error detection philosophy

- **Conservative: false negatives > false positives.** It is far worse to flag a correct reading as wrong than to miss a real mistake. A student being told they're wrong when they read correctly destroys trust in the system. Missing a subtle i3rab error is tolerable — the teacher or the student can catch it next time.
- When in doubt, assume the student is correct.
- Threshold tuning should always err on the side of letting things pass.

## Target accuracy

- **False positive rate: <2%.** Flagging a correct reading as wrong is the worst outcome — it destroys trust. Keep this as low as possible. When unsure, stay silent.
- **Wrong word detection: >95%.** Easiest error type — the audio will be very different from the expected text.
- **I3rab detection: >90%.** Case endings (damma vs fatha vs kasra) are phonetically distinct. The CTC model should reliably distinguish them via hypothesis scoring.
- **Tashkeel detection: >90%.** Internal vowel differences can be subtle in fast speech, but the model has diacritized character tokens and should score the correct vowelization higher.
- **Position tracking: 100%.** The system must always know where the student is in the text. No exceptions — if tracking is lost, everything else breaks.

These are targets, not hard requirements. The priority order is: no false positives > position tracking > wrong words > i3rab > tashkeel.

## How it works technically

- **Real-time, word-by-word (or small groups).** The system processes audio as the student reads, tracking and scoring a word or a few words at a time. It doesn't wait for the student to finish — feedback should appear as they go.
- **GPU backend in production, CPU/MPS for dev.** In production, the CTC model and scoring pipeline run on a server with GPU. The frontend streams audio to the backend, which returns scored results. For development and testing, everything runs locally on Mac (CPU or MPS).

## Validation

- **`test_mutations.py` is the primary test.** This is the most important metric. It takes correct recordings, scores them against the correct text (FP check), then scores them against systematically mutated text (i3rab swaps, tashkeel swaps, word replacements) to measure detection rates. Always run this after any scoring change.
- `evaluate.py` runs the individual test recordings from `test_data/manifest.jsonl` — useful for debugging specific cases but less comprehensive than mutation testing.
- For any scoring change, run `test_mutations.py` and check:
  1. **False positive rate** — must stay below 2%. This is the #1 priority.
  2. **Detection rates** — i3rab, tashkeel, and word detection should all be >90%.
  3. **Correct type** — detected errors should be classified as the right error type.
- When adding new scoring logic, always test on real recordings first, not just synthetic examples.

## How to work

- **Launch sub-agents** to explore approaches in parallel, do deep research, and test alternatives.
- **Iterate heavily.** Don't stop at the first thing that works. Try multiple approaches, measure, compare, and pick the best. If something isn't hitting the accuracy targets, keep going — dig deeper, research more, try something different.
- **When stuck, research.** Search for papers, look at how other systems solve similar problems, read library docs. Don't guess — find out.
- If you need more test data to debug a specific edge case, ask the user to record it.

