# Suhuf — Project Q&A

Answers to the four project-video questions. Demo and full technical detail are in the [README](../README.md).

## Q1 — Why did you build this?

Two bottlenecks:

- **No feedback loop for reading classical Arabic.** It's written without short vowels; the same letters can be read several ways, and the vowels (*tashkeel*) and case endings (*i'rab*) carry the meaning. Without a teacher beside you, you can't tell if you're reading it right. **Tarteel** solved this for the Qur'an — nothing existed for everything else (grammar primers, hadith, tafsir, fiqh).
- **The texts are locked up.** The largest open corpus, [OpenITI](https://github.com/OpenITI) (~7,000+ books), is undiacritized and written in scholarly markup — there's no clean edition you can read on a phone or recite along to.

**Inspiration:** Tarteel, plus the CS 153 premise that one person + AI can now build what used to take a team. The unlock was realizing that **for a known book the correct answer is already known** — which turns "transcribe / diacritize Arabic" (hard, open-ended) into "score a few hypotheses against the audio" (easy, and controllable for false positives). That's what makes a one-person read-along feasible.

## Q2 — How exactly does it work?

A **domain-specific product** with a real research core, in three layers.

**[1] Research — the recitation engine.**
- **Two models, because neither does both jobs:** Whisper (`whisper-small`) tracks *where* you are in the text (it throws away the vowels); a fine-tuned **XLS-R 300M CTC** model (58 diacritized Arabic tokens) grades *which vowels* you actually said.
- **Reference-known hypothesis scoring:** because the text is known, it never transcribes — it scores the correct reading against deliberately-wrong alternatives. One rule governs everything: **false negatives ≫ false positives, target FP < 2%** (this is sacred text; wrongly flagging a correct reading destroys trust).
- **Training & eval data:** fine-tuned on **ClArTTS** (studio classical Arabic), with **Common Voice / Iqra_train** added for the everyday-reading variants; evaluated with a **mutation-based** harness (hold real audio fixed, mutate the known text to make labeled errors) against a held-out **Arabic Speech Corpus** speaker and ~206 words of **in-house** recordings. Development ran through a long graveyard of architectures (a NeMo Conformer, MixGoP GMMs, GBM classifiers, a Qwen2-Audio LLM judge, w2v-bert 600M, noise augmentation, per-error contrastive fine-tunes) and landed on a fine-tuned model + a decorrelated-agreement ensemble. Key finding: **everyday-reading vowel detection is acoustically capped**, not model-limited — if a reader drops a vowel, the "error" isn't physically in the audio.

**[2] Application / Product — architecture & deployment.**
- **`ingestion/`** (Python): OpenITI book → parse the markup into structured blocks → add diacritics with a neural model → **Claude** tags entities (people, places, references) and resolves Qur'an citations to exact `sura:ayah` → upload to Supabase.
- **`web/`** (Next.js 16 / React 19, deployed on **Cloudflare Workers** via OpenNext, **Supabase** backend): the reader, the word-tap features, recite mode (mic → WebSocket → per-word colors), auth, and theming.
- **`recitation/`** (FastAPI + PyTorch): a separate service running the models (GPU in production); the web app talks to it over a WebSocket and maps scores back onto the exact words on screen. (Production GPU deploy on **Modal** is in progress.)

**[3] Agents.** Claude annotates the books (Haiku + Sonnet) and powers the live word-tap **I'rab / Translation / Ask-AI** features (Sonnet). The whole project was built with **Claude Code** on a strict spec → plan → test → review workflow (19 plans + 18 specs committed).

## Q3 — Use cases, impact, and how people use it

**Who it's for:** students of Arabic and Islamic studies — especially non-native learners — who can't always get a teacher; people memorizing texts; and anyone who wants to actually *read* the classical library instead of staring at bare consonants.

**How people use it:** open any ingested book → read aloud and get live correction → tap a word you don't know for its grammar, meaning, and root → switch on hide-text to memorize. Every OpenITI book becomes interactive and recitable.

**Impact:** it puts a teacher-in-the-loop feedback experience in front of anyone, and opens a corpus that is currently unreadable to most people. It teaches i'rab *practically* (by correcting you as you read) and grammar *by understanding* (every word explained with its reason), instead of by rote.

**Expert feedback (evidence).** Two Arabic teachers reviewed the site. One called it very useful. The second gave detailed written feedback — translated:

> "A very distinctive idea for teaching Arabic to non-native speakers. Its standout is that it links reading, correction, and comprehension at the same time: the student reads aloud and receives immediate correction of pronunciation and harakat, which helps him master i'rab practically. It also gives a clear grammatical (*nahw*) and morphological (*sarf*) analysis of each word, with the reason explained — helping you understand the rules rather than just memorize them. And being able to see a word's meaning, root, and usage right while reading adds great value for building vocabulary. In my view it can be a powerful support for studying the *matns* (classical texts), and it brings the learning experience close to direct instruction with a teacher."

He also suggested teaching-oriented additions (graded levels, end-of-lesson quizzes, audio rule explanations, per-student progress tracking) — a good fit for classroom use, though Suhuf is built for independent readers rather than teachers. (Full feedback in Arabic in the appendix.)

**Early traction.** Beyond expert review: an Arabic-language expert with **10k+ followers** has agreed to come on board and help market the product, and the **waitlist already has 30+ signups** — early signal that the demand is real.

## Q4 — What I'd add next

**Catalog & reading:**
- **Open the full library** — scale the AI ingestion pipeline to the **~10,000 books** already available, so the catalog is the whole classical corpus (every title diacritized, structured, and recitable) instead of a handful of titles.
- **Notes & highlights** — let readers annotate passages, save favorites, and keep their own marginalia while reading.
- **A personal vocabulary** — save tapped words with their root and meaning into review lists / flashcards, so reading itself builds vocabulary over time.
- **Mobile** — a phone app for reading and reciting anywhere.

**Recitation engine:**
- **Gather real recitation data** — collect real user reading sessions. Accuracy and false-positive certification are now *data*-limited, not model-limited (~206 words of in-house audio today), so this is the single biggest lever.
- **Keep training the model to be better** — fine-tune on that new data and expand the ensemble (e.g. ship the deferred IqraEval member → i'rab ~94, consonant ~92) to push detection higher while holding FP < 2%.
- **Better diacritization** quality, with a committed benchmark.
- Finish the **decorrelated-ensemble + GPU (Modal)** deployment already in progress.

---

### Appendix — original expert feedback (Arabic)

> اطلعت على الموقع، وأراه فكرة مميزة جدًا في تعليم العربية لغير الناطقين بها.
> أبرز ما فيه أنه يربط بين القراءة والتصحيح والفهم في وقت واحد؛ فالطالب يقرأ بصوته، ويتلقى تصحيحًا فوريًا للنطق والحركات، مما يساعده على ضبط الإعراب عمليًا.
> كذلك يوفّر تحليلًا نحويًا وصرفيًا واضحًا لكل كلمة مع بيان السبب، وهذا يعين على فهم القواعد بدل الاكتفاء بحفظها.
> وإمكانية معرفة معنى الكلمة وجذرها واستخدامها مباشرة أثناء القراءة تضيف قيمة كبيرة في بناء الحصيلة اللغوية.
> في نظري، الموقع يصلح أن يكون أداة قوية مساندة لدراسة المتون، ويقرّب تجربة التعلم من التلقي المباشر مع معلم.
>
> ومن باب التطوير، يمكن إضافة بعض المزايا مثل:
> - إدراج مستويات متدرجة تناسب المبتدئ والمتوسط والمتقدم.
> - توفير اختبارات قصيرة بعد كل درس لقياس الفهم.
> - إضافة شرح صوتي لبعض القواعد أو النماذج التطبيقية.
> - إتاحة تتبع تقدم الطالب وتحليل نقاط القوة والضعف.
