# Claude annotation pre-pass

## Goal

Most OpenITI sources lack the optional `$RWY$ / @MATN@ / $BIO_*$` tags,
so the parser emits everything as `prose` — and the reader's isnad/matn/
biography typography never lights up. A Claude pre-pass at ingestion
time supplies those structural labels for un-annotated books, and adds
inline span labels we couldn't get any other way (Qur'an quotes, names,
gradings, etc.).

The pre-pass is **opt-in per book**, **idempotent**, and **skipped
automatically** when the OpenITI source already carries native tags.
Output lands in `<uri>.annotated.json` between `tashkeeled.json` and
`enriched.json` in the dev-loop tier list.

## Phasing

The annotations split into three rollout tiers ordered by ROI vs. cost
vs. complexity. Each tier is shippable on its own.

### v1 — Structural relabeling (the unlock)

Lights up the typography we already implemented and the cards toggle.
Runs in seconds per book on Haiku.

- **`isnad`** — chain of transmission, "who told whom".
  Example: `حدثنا أبو بكر بن أبي شيبة قال حدثنا عبد الله بن إدريس عن
  هشام بن عروة عن أبيه عن عائشة قالت`.

- **`matn`** — the actual reported text following an isnad.
  Example: `«إنما الأعمال بالنيات وإنما لكل امرئ ما نوى…»`.

- **`takhrij`** — citation/source attribution after the matn, naming
  which collections recorded it.
  Example: `رواه البخاري في صحيحه ومسلم في صحيحه`.

- **`hadith_grading`** — حكم phrasing about the report's authenticity.
  Example: `قال الشيخ الألباني: صحيح` → label `sahih`. Other values:
  `hasan`, `daif`, `mawduʿ`.

- **`biography`** — entry in a tabaqat / rijal work, one block per
  scholar profile.
  Example: an entry beginning `محمد بن إسماعيل البخاري الإمام الحافظ
  ولد سنة ١٩٤…` and ending at the next biographical heading.

- **`commentary` vs `quoted_text`** (sharḥ books only) — distinguish
  the original embedded matn from the explanation around it.
  Example in Sharḥ al-Nawawī ʿalā Muslim: `قوله ﷺ "إنما الأعمال
  بالنيات"` → the quoted segment is `quoted_text`, the surrounding
  exegesis is `commentary`.

- **`editor_note`** — modern editor's brackets/footnotes inside
  block text.
  Example: `[في نسخة: "وأشهد"]` or a parenthesized page reference.

### v2 — Inline span labels (powers cross-references)

Per-token or per-span labels that sit alongside the structural ones.
Each one is a "find these spans inside the rendered text and tag them"
task — output is a list of (token_id_start, token_id_end, label).

- **`qur_quote`** — embedded Qur'anic verse, with sūra:āyah ref where
  possible. Drives tap-to-open Mushaf.
  Example: `قال الله تعالى: "إنما الأعمال بالنيات"` — wait, that's a
  hadith. Real one: `قال الله تعالى: ﴿وَمَا خَلَقْتُ الْجِنَّ
  وَالْإِنْسَ إِلَّا لِيَعْبُدُونِ﴾` → label span as `qur_quote`,
  ref `51:56`.

- **`hadith_quote`** — a hadith quoted inside a non-hadith book
  (fiqh, tafsir, adab). Drives the cross-ref popover.
  Example in a fiqh book: `وقد ثبت عن النبي ﷺ أنه قال "الماء طهور
  لا ينجسه شيء"`.

- **`book_title`** — name of a referenced work; matches against the
  library catalog so titles become clickable.
  Example: `كما ذكر الإمام النووي في "رياض الصالحين"`.

- **`personal_name`** — companion / scholar / narrator. Required to
  color isnad chains by transmitter generation and to seed an authors
  index. Sub-labels: `companion` (Sahābī), `tabiʿi` (Tābiʿī),
  `scholar`, `prophet` (when the Prophet is named).
  Example: `عن عائشة رضي الله عنها` → span "عائشة" with role
  `companion`.

- **`place_name`** — geographical reference. Cheap; powers a future
  map view.
  Example: `كان يصلي بمنى` → span "منى" as `place_name`.

- **`date_hijri`** — explicit Hijri date in text. Useful for biographical
  works.
  Example: `توفي سنة ٢٥٦ هـ` → span "٢٥٦" as `date_hijri`.

### v3 — Reader helpers (longer-form, more $)

Higher-cost outputs that are nice-to-have, not foundational. Defer
until v1 + v2 are validated.

- **`summary`** — one-line gloss per hadith / paragraph. Surfaces as
  a hover tooltip or an English column.
  Example for "إنما الأعمال بالنيات": gloss = "Actions are judged
  by their underlying intentions; reward depends on what each person
  intended."

- **`glossary_terms`** — list of rare / technical words extracted per
  block, each with a one-line definition. Drives tap-to-define.
  Example: from a fiqh block, extract `جنابة` → "ritual impurity from
  major events requiring ghusl".

- **`difficulty`** — `easy | medium | hard` per block, based on
  vocabulary density and syntactic complexity. Powers reader-level
  filtering and the read-aloud feature.

- **`topic_tags`** — small fixed taxonomy (intentions, ṣalāh, ṣawm,
  zakāh, akhlāq, ʿaqīda, riba, …) per block or per chapter. Powers
  topic browsing & "more like this".
  Example: a hadith about prayer postures → tags `["salah",
  "physical_posture"]`.

### Quality flags (free, runs in any pass)

Cheap diagnostics that come along for the ride at no extra cost:

- **`parse_error`** — block looks malformed (broken nesting,
  zero-token blocks, suspicious whitespace). Routes to inspector.

- **`tashkeel_suspect`** — diacritization probably wrong (e.g.
  Shakkala produced an impossible vocalization). Used to flag tokens
  for the diff-viewer.

- **`ocr_artifact`** — scanning glitch (mojibake, broken chars,
  non-Arabic letter inside Arabic word).

## Pipeline integration

- New stage `annotate.py` between `tashkeel.py` and `enrich.py`.
- Reads `<uri>.tashkeeled.json`, writes `<uri>.annotated.json`.
- Reader's tier preference becomes:
  `enriched > annotated > tashkeeled > parsed`.
- `enriched.json` continues to wrap the annotated payload + book/author
  enrichment.
- **Skip-if-tagged**: if the parser emitted ≥10 native isnad/matn/bio
  blocks for this book, skip the structural pass entirely.
- **Idempotency**: the pass writes a `model + prompt_version` header.
  Re-running with the same version is a no-op; bumping the version
  invalidates and reruns.
- **CLI flags**: `--skip-annotate` (parallel to `--skip-enrich`),
  `--annotation-tier {v1, v2, v3}` to scope cost during iteration.
- **Error mode**: same as enrichment — log a warning, write an empty
  annotation payload, dump still completes.

## Output schema (sketch)

Two payload types per block:

1. **Structural relabel** — the parser's `Block.type` is overwritten
   in-place when the model is ≥X confident. Original parser type is
   preserved alongside as `parser_type` so we can audit drift.

2. **Inline spans** — list of `{ start_token_id, end_token_id, label,
   sub_label?, ref?, confidence }` attached to each block. The reader
   walks the span list at render time to wrap matched ranges with
   the right `<span>` class.

## Reader changes required to consume each tier

- v1 → none. The styling and cards toggle are already wired to block
  types; relabeling alone makes them appear.
- v2 → a `SpanRenderer` that reads `block.spans[]` and wraps token
  ranges with `<span class="quran-quote">` / `personal-name` / etc.
  Tap-handlers for cross-link spans land here.
- v3 → tooltip layer (`summary`, `glossary_terms`), a difficulty
  badge in chrome, topic-filter UI in the chapter drawer.

## Eval before scaling

Before running the full corpus:

1. Pick 3 books with native `$RWY$ / @MATN@ / $BIO_*$` tags as
   ground truth.
2. Strip the native tags, run the v1 pass, compute precision/recall
   per label.
3. Target: ≥0.95 on `isnad` and `matn` (high-volume, easy);
   ≥0.85 on `takhrij` and `biography`.
4. Pick 1 book with rich Qur'an quotes (a tafsīr) for v2 span
   eval — measure boundary accuracy on `qur_quote`.
5. If a label fails its bar, ship without it; don't degrade trust
   on the labels that do pass.

## Cost ceiling at corpus scale

- v1 only: ~$0.002/page on Haiku → starter library (~20 books at
  ~400 avg pages) ≈ **$16**.
- v1 + v2: ~$0.004/page → starter library ≈ **$32**.
- v1 + v2 + v3: ~$0.012/page → starter library ≈ **$95**.
- Full OpenITI corpus (~10k books): v1 only ≈ **$10–20k**, scoped
  to un-annotated hadith/biographical works only it's roughly 1/3
  of that.

These are upper bounds. Prompt caching for the system prompt cuts
~10% off; skip-if-tagged cuts another large chunk on the books that
already carry the markers.

## Open questions

- Confidence threshold for accepting a structural relabel — too low
  and we degrade good books, too high and v1 doesn't fire enough.
- Should `takhrij` be a third structural type, or a span tag inside
  a `prose` / `matn` block? Pro span: takhrij can sit mid-paragraph.
  Pro block: it's typographically distinct.
- Where does `personal_name` live when a span crosses block
  boundaries (rare but real for long compound names split by
  pagination)?
- Do we cache the model output keyed on (uri, parser_version,
  prompt_version) so re-ingesting after a parser tweak doesn't
  re-spend?
