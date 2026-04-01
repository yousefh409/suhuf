# Live Arabic Readalong

> A webpage where a student reads an Arabic passage aloud and gets real-time correction on wrong words, tashkeel, and i3rab — like Tarteel, but for any Arabic text.

---

## The Problem

Students of knowledge read Arabic texts daily — Ajrumiyyah, Alfiyyah, hadith, tafsir — but have no way to know if they're reading the harakat correctly. A teacher can catch your mistakes, but you can't always have a teacher next to you. Tarteel solved this for Quran. **Nothing exists for everything else.**

## What We're Building

A simple webpage. It shows a passage of diacritized Arabic text. The student hits record and starts reading. The system:

1. **Finds where they are** — no need to select a starting word. It listens, figures out which part of the passage they're reading, and starts tracking.

2. **Follows along word by word** — highlights the current word as they read through the passage.

3. **Catches wrong words** — if the student says a completely different word than what's in the text, it flags it. Skipped a word? Added one? It catches that too.

4. **Corrects i3rab mistakes** — flags wrong case endings. Read fatha where damma is expected? Missing tanween? It tells you what the ending should be.

5. **Corrects tashkeel mistakes** — flags wrong internal vowels. A kasra where a damma should be, a dropped shadda. Pinpoints the exact letter.

6. **Doesn't flag valid pauses** — sukoon on the final letter is fine. Stopping at the end of a phrase with waqf is not a mistake.

## Example

The passage on screen:

```
الكَلامُ هُوَ اللَّفْظُ المُرَكَّبُ المُفِيدُ بِالوُضْعِ
```

The student reads: *"al-kalaamu huwa al-lafdhu al-murakkaba al-mufiidu bil-wad3i wa aqsaamuhu thalaatha"*

What they see:
- **الكَلامُ** — correct
- **هُوَ** — correct
- **اللَّفْظُ** — correct
- **المُرَكَّبَ** — i3rab error: you said fatha, should be damma (it's marfu3)
- **المُفِيدُ** — correct
- **بِالوَضْعِ** — tashkeel error: you said fatha on the و, should be damma

Now the student misreads the next line:

```
وَأَقْسَامُهُ ثَلاثَةٌ اسْمٌ وَفِعْلٌ وَحَرْفٌ جَاءَ لِمَعْنًى
```

- **وَأَقْسَامُهُ** — correct
- **ثَلاثَةٌ** — correct
- **~~فِعْلٌ~~** — wrong word: you said "fi3l", but the text says "ism" (اسْمٌ) — skipped a word

## What We Have

- A fine-tuned **XLS-R 300M** CTC model that outputs character-level log-probabilities for Arabic text with diacritics (the "ssl v5" model). This is the core — it can score how likely a given diacritized string matches a segment of audio.

## Key Constraints

- **The model is not perfect.** We need to be conservative — better to miss an error than to wrongly flag a correct reading. False positives destroy trust fast.
- **We know the text.** This is not open-ended transcription. We know exactly what the student *should* be saying, which makes the problem much easier. We can score a small set of hypotheses rather than transcribe freely.
- **Sukoon on the last letter is always valid.** Pausal forms (waqf) are normal in Arabic reading. The system must accept them.

## UX (Tarteel-like)

- Clean, minimal interface — the text is the focus
- Words change color as the student reads (correct = green, wrong word = red strikethrough, i3rab error = blue underline, tashkeel error = orange underline)
- Tap a flagged word to see what was expected vs. what was detected
- Record button to start/stop
- The passage is pre-loaded (hardcoded for now, any Arabic text later)
