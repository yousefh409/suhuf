# Suhuf — Demo Video Script

Just you, screen-recording, talking. ~5 min. Walk through the real app in this order. Each section: **what to have on screen**, then roughly what to say (your words — keep it casual, not salesy).

---

**1. The problem (no screen needed, or show a raw undiacritized Arabic text) — ~45s**

Classical Arabic is written without short vowels. The same letters can be read several ways, and which vowels you pick changes the meaning. If you're learning, there's no way to know if you're reading it right unless a teacher is next to you. Tarteel solved this for the Qur'an — but there's nothing for everything else: grammar texts, hadith, tafsir. And the biggest open library of these books, OpenITI, is undiacritized and basically unreadable for a normal person. So I built Suhuf: it turns any of those books into a clean reader, and it listens to you read aloud and corrects your mistakes. Tarteel, but for any Arabic text.

---

**2. The reader — open a book in the app — ~30s**

This started as raw OpenITI markup. Now it's a real reading surface — fully diacritized, hadith chain set apart from the Prophet's words, Qur'an verses highlighted, poetry laid out properly. Light, sepia, and night modes.

---

**3. Tap a word — open the popover, click through the three tabs — ~45s**

Tap any word and you get a tutor. **I'rab** — the full grammar: part of speech, its role, the case, and *why* it's that case. **Translation** — the sentence meaning plus other words from the same root. And **Ask AI** — just ask a question about the word. All Claude, on demand.

---

**4. Recite mode — hit Recite and read aloud — ~60s**

This is the main thing. I hit Recite and start reading — I don't tell it where I am, it finds me. Watch the words turn green as I read. *(Make a mistake on purpose.)* Wrong case ending — blue. Wrong internal vowel — orange. Wrong word — red. In real time, on the exact word. And when I pause naturally *(pause)* — it doesn't flag me, because telling someone they're wrong when they're right is the fastest way to lose trust.

---

**5. Hide-text mode — toggle it, recite from memory — ~20s**

There's also a memorization mode: hide the text, and each word only appears when you recite it correctly.

---

**6. How it works — talk over the inspector view or just the README diagram — ~75s**

Two AI systems. **Ingestion:** it takes a raw OpenITI book, parses it into structure, adds the diacritics with a neural model, and has Claude tag the people, places, and references and resolve every Qur'an quote to the exact verse. That's how a scholarly markup file becomes a clean, readable book.

**Recitation:** two models, because neither does both jobs. Whisper figures out *where* I am but throws away the vowels. A fine-tuned XLS-R model does the grading — it can tell the vowels apart. And because I already know the correct text, I never transcribe — I just score the right reading against a few wrong versions. That's what keeps false positives near zero. Getting there took a graveyard of architectures — I'll show that in a second.

And to be transparent: I built almost all of this with Claude Code on a strict spec → plan → test → review workflow — it's all in the repo. The recitation engine especially I built in long overnight loops: Claude would try an architecture, score it against my recordings, repeat, and I'd redirect it each morning.

---

**7. Does it work? — show the evolution table in the README (or experiments.md) — ~40s**

I built this across a lot of dead ends — a NeMo model I scrapped, GMM scorers, an audio-LLM judge, a 600M model, noise augmentation, a bunch of fine-tunes. Most got parked, and the table shows why. Where it landed: wrong-word detection ~100%, false positives near zero on clean in-domain reading. Honestly — on an unseen speaker false positives rise to ~3.7%, above my 2% goal, and detecting dropped internal vowels turned out to be an acoustic limit, not a model one: if someone reads quickly and drops the vowel, the error literally isn't in the audio. Every model I tried plateaued the same way. So the real bottleneck now is real user data, not a bigger model.

---

**8. Wrap — use cases + what's next — ~25s**

This is for students of Arabic who can't always get a teacher, anyone memorizing, or anyone who just wants to actually read the classical library. Every OpenITI book becomes interactive and recitable. Next: open the catalog to the full ~10,000-book corpus we can AI-ingest, add notes and a saved vocabulary for readers, and keep feeding the recitation model real usage data to push past the acoustic ceiling. Thanks for watching.

---

### Numbers to quote (keep it honest)
- Hadith structure: **8% → 99%**.
- Recitation: wrong-word **100%**; false positives **near-zero on my own voice (~0–2%)**, **3.77% on an unseen speaker** (above the 2% target); tashkeel detection ~**57–66%** (acoustic limit).
- Say "fine-tuned XLS-R model" — don't name a version. The engine is a from-scratch rewrite; only the model checkpoint carried over from an earlier prototype.
