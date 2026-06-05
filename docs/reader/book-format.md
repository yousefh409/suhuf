# Suhuf Book Format

Arabic text flows from **OpenITI mARkdown** source files through an ingestion pipeline into Supabase Postgres. The content model is a **continuous tagged document sliced into page rows**: the book is one string with HTML-style boundary tags, cut at page boundaries for storage and download. A tag may open on one page fragment and close on a later one, so a hadith that spans pages is stored as one `<hadith>` with one `<matn>`.

## Format Lifecycle

```mermaid
flowchart LR
    A[OpenITI mARkdown] --> B[parse\nblocks + plain text]
    B --> C[tashkeel\ndiacritize]
    C --> D[assemble\none plain-text string]
    D --> E[chunk at unit boundaries]
    E --> F[AI structure pass\nboundary tags]
    F --> G[number ids\nh2 / p7 / q5]
    G --> H[build annotations\nmetadata layer]
    H --> I[slice at page offsets]
    I --> J[(Supabase\npages + annotations)]
```

The book is tagged once and frozen. Pages are only where the document is sliced for storage and streaming; they are not content containers.

---

## Source Format: OpenITI mARkdown

**OpenITI mARkdown** is a plain-text markup convention for digitized classical Arabic texts. The ingestion pipeline reads these files for structural markup (page markers, headings) and ignores semantic hadith tags, which are absent even from top-tier `.mARkdown` files (verified zero `$RWY$`/`@MATN@` across Sahih al-Bukhari, Sahih Muslim, Sunan al-Tirmidhi, and Bulugh al-Maram). All semantic structure comes from the AI pass.

### Structural Tags Used by the Parser

| mARkdown tag | Meaning | Used for |
|---|---|---|
| `PageV##P###` | Page boundary | Page number and volume; drives `page_offsets` |
| `### \|` through `### \|\|\|\|\|` | Headings (level 1-5) | Chapter titles; headings become `heading`-type blocks and chunk cut points |
| `### \|EDITOR\|` | Editorial content | Stripped |
| `%~%` | Poetry hemistich divider | Builds hemistich pairs in `poetry` blocks |
| `#META#…` / `######OpenITI#` | File metadata | Book title, author; not stored as blocks |
| All other content | Plain paragraph text | `prose` blocks |

**File quality tiers** (`.mARkdown` > `.completed` > raw) reflect how thoroughly the *structural* markup was vetted, not whether semantic tags are present. Prefer `.mARkdown` for the cleanest page markers and headings; the semantic layer always comes from the AI regardless of tier.

---

## Content Model: Continuous Tagged Document

The book is assembled into one plain-text string. The AI structure pass annotates it in-place with HTML-style boundary tags. Tags carry only a boundary and (after the id-assignment pass) a stable `id` attribute. All metadata lives in a separate `annotations` table keyed by id.

### Tag Vocabulary

**Structural tags** (wrap units; no id)

| Tag | Meaning |
|---|---|
| `<hadith>` | One complete hadith report |
| `<isnad>` | Chain of narrators |
| `<matn>` | Body text of the hadith |
| `<takhrij>` | Sourcing or grading remark |

**Entity tags** (nest freely inside structural tags; carry an id)

| Tag | Id prefix | Meta payload |
|---|---|---|
| `<person>` | `p` | `{ref, role}` — narrator/scholar reference |
| `<place>` | `pl` | `{ref}` — toponym reference |
| `<quran>` | `q` | `{sura, ayah}` — resolved against bundled ayah index |
| `<book_ref>` | `b` | `{ref}` — cited book title |
| `<hadith_ref>` | `hr` | `{ref}` — cross-reference to another hadith |
| `<date_hijri>` | `d` | `{year}` |

**Headings** are not inline tags. They are emitted as standoff `heading` annotations (book-global plain-text offsets) so the reader splits them into `heading` blocks without the AI needing to tag chapter text.

### Id Assignment

Ids are assigned deterministically by a post-AI pass in document order: the first `<hadith>` becomes `h1`, the second `h2`; the first `<person>` becomes `p1`, and so on. The AI emits no ids. Re-running the id-assignment pass on already-numbered text is a no-op (pre-existing ids are skipped).

### Example Fragment

```
<hadith id="h2"><isnad>«عن <person id="p7">عمر</person> بن الخطاب قال:</isnad>
<matn>سمعت رسول الله صلى الله عليه وسلم يقول: إنما الأعمال بالنيات</matn>
<takhrij>متفق عليه</takhrij></hadith>
```

---

## Storage Format: Supabase Schema

### Authors

```sql
authors (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  openiti_id TEXT UNIQUE NOT NULL,     -- e.g., '0748Dhahabi'

  -- Names
  shuhra_ar TEXT,                      -- Famous name in Arabic
  shuhra_lat TEXT,                     -- Famous name in Latin transliteration
  ism_ar TEXT,                         -- Given name
  nasab_ar TEXT,                       -- Patronymic chain
  kunya_ar TEXT,                       -- Honorific epithet (Abu...)
  laqab_ar TEXT,                       -- Title (Shams al-Din, etc.)
  nisba_ar TEXT,                       -- Geographic/professional affiliation
  full_name_ar TEXT,                   -- Composite display name

  -- Dates
  birth_ah INTEGER,
  death_ah INTEGER,

  -- External IDs
  wikidata_id TEXT,
  external_ids JSONB DEFAULT '{}',

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Book data

```sql
books (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  openiti_id TEXT UNIQUE NOT NULL,
  author_id UUID REFERENCES authors(id) NOT NULL,

  title_ar TEXT NOT NULL,
  title_lat TEXT,
  description TEXT,
  genres TEXT[] DEFAULT '{}',

  word_count INTEGER,
  char_count INTEGER,
  total_pages INTEGER,
  total_volumes INTEGER DEFAULT 1,

  version_status TEXT,
  source_edition_url TEXT,
  quality_issues TEXT[] DEFAULT '{}',
  language TEXT DEFAULT 'ara',
  composition_date_ah INTEGER,

  commentary_on TEXT,
  abridgement_of TEXT,

  is_starter BOOLEAN DEFAULT FALSE,    -- shown in "Start here" for new users
  has_tashkeel BOOLEAN DEFAULT FALSE,

  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

pages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID REFERENCES books(id),
  page_number INTEGER NOT NULL,
  volume INTEGER DEFAULT 1,

  -- Flow format columns
  tagged TEXT,                  -- this page's fragment of the continuous tagged document
  open_tags JSONB DEFAULT '[]', -- tag stack open at this page's start: [{"name","id"}, ...]
  content_plain TEXT,           -- page plain text (tags stripped), used for search
  content_hash TEXT,            -- hash of content_plain for change detection
  start_offset INTEGER,         -- this page's start char position in the book plain text

  UNIQUE(book_id, volume, page_number)
);

chapters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID REFERENCES books(id),
  title TEXT NOT NULL,
  level INTEGER NOT NULL,       -- 1 = chapter, 2 = section, 3 = subsection
  page_id UUID REFERENCES pages(id),
  parent_id UUID REFERENCES chapters(id),
  sort_order INTEGER NOT NULL
);

annotations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  tag_id TEXT NOT NULL,         -- the in-text tag id: 'h2', 'p7', 'q5'
  label TEXT NOT NULL,          -- hadith | person | place | quran | book_ref | hadith_ref | date_hijri | heading
  start_offset INTEGER,         -- plain-text char range of the span (convenience; `tagged` is canonical)
  end_offset INTEGER,
  meta JSONB DEFAULT '{}',      -- resolved payload: {number} for hadith, {sura,ayah} for quran, etc.
  UNIQUE(book_id, tag_id)
);
```

The `annotations` table holds the metadata layer, one row per id-bearing tag, plus one row per standoff `heading` span. `meta` carries resolved data: `{number}` for hadith, `{sura, ayah}` for quran, `{ref, role}` for persons, etc. Resolvers write to `meta`; the AI writes neither ids nor meta.

### I'rab cache

```sql
irab_cache (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  word TEXT NOT NULL,
  sentence_hash TEXT NOT NULL,
  model_version TEXT NOT NULL DEFAULT 'sonnet-1',
  result_json JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(word, sentence_hash, model_version)
);
```

Global table shared across all users. Cache key is `(word, sentence_hash, model_version)`.

### User library state

```sql
user_library (
  user_id UUID REFERENCES auth.users(id),
  book_id UUID REFERENCES books(id),
  status TEXT NOT NULL DEFAULT 'none',  -- none | downloading | downloaded | reading | favorited
  download_progress REAL DEFAULT 0,
  last_opened_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (user_id, book_id)
);
```

### User data

User highlights, bookmarks, and notes anchor to **token ids**: the reader's derived word handles of the form `{blockKey}:{wordIndex}` (e.g. `b0:3`). These ids are produced at render time by `flowToNewBook` -> `convertNewBook` (`web/src/lib/reader/newFormat.ts`); they are not stored per-word in the format. `anchor_context` keeps ~30 surrounding chars so a highlight can be re-found if a token id shifts. Migrating these onto durable plain-text offsets is a planned follow-up (see Sharing and Citation); the tables today are unchanged.

```sql
user_bookmarks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id),
  book_id UUID REFERENCES books(id),
  page_id UUID REFERENCES pages(id),
  token_id TEXT,                -- derived word id '{blockKey}:{wordIndex}', e.g. 'b0:3'
  label TEXT,
  anchor_context TEXT,          -- ~30 chars for re-anchoring if a token id shifts
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ        -- tombstone for sync
);

user_highlights (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id),
  book_id UUID REFERENCES books(id),
  page_id UUID REFERENCES pages(id),
  start_token_id TEXT NOT NULL, -- first token in range, '{blockKey}:{wordIndex}'
  end_token_id TEXT NOT NULL,   -- last token in range
  color TEXT DEFAULT 'yellow',
  note TEXT,
  anchor_context TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);

user_notes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id),
  book_id UUID REFERENCES books(id),
  page_id UUID REFERENCES pages(id),
  token_id TEXT NOT NULL,       -- token the note is anchored to
  content TEXT NOT NULL,
  anchor_context TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ
);

user_reading_positions (
  user_id UUID REFERENCES auth.users(id),
  book_id UUID REFERENCES books(id),
  page_id UUID REFERENCES pages(id),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (user_id, book_id)
);
```

The **tombstone pattern** (`deleted_at TIMESTAMPTZ`) propagates deletes across sync boundaries. Tombstones are purged after 90 days.

---

## Reader Reconstruction

The reader loads page rows in order and concatenates `tagged` fragments. `open_tags` on each page seeds the parser's tag stack, so "jump to page 49" renders correctly without loading page 47 first.

```
load pages (window) + annotations (small, fetched up front)
  -> seed parser with page.open_tags
  -> concatenate page.tagged in order
  -> parse tag tree: hadith #2 is one <hadith> across pages 47, 49, 50
  -> apply annotations.meta by id: number, grading, ayah ref
  -> split each page at heading annotation ranges -> heading + prose blocks
  -> render: isnad/matn styling, hadith card, ayah link
```

Word-tap, highlight, and recitation operate on the rendered word list keyed by derived `{blockKey}:{wordIndex}` token ids. There are no stored per-word tokens; the ids are produced at render time by `convertNewBook`.

---

## Sharing and Citation

The format is built to support **durable citation**. The book's plain text is frozen (classical texts do not change), so a `{book, start, end}` plain-text char range is a stable address for any selection, and a hadith is addressable by its tag id / number. Pages do not enter into it: the page containing an offset is derivable from `pages.start_offset`.

The planned share address frames a selection as a frozen-text range:

```json
{
  "book_id": "...",
  "start": 1240,
  "end": 1268,
  "anchor": "بينما نحن جلوس",
  "in": "h2"
}
```

`start`/`end` are character offsets into the frozen plain text; `in` is the enclosing tag id, from which the human citation is derived via `annotations.meta`.

**Not built yet.** The sharing feature does not exist, and user data is not anchored this way today: the reader renders from flow and anchors highlights/bookmarks/notes by the derived `{blockKey}:{wordIndex}` token ids (see User data). Migrating user data onto durable plain-text offsets is a follow-up, not a current API.

---

## Curated Starter Catalog

18 classical Arabic/Islamic texts verified in the [OpenITI corpus](https://github.com/OpenITI). These are marked `is_starter = true` and shown in the "Start here" section for new users.

### File quality hierarchy

1. **`.mARkdown`** -- Structurally verified (best page markers and headings)
2. **`.completed`** -- Conversion done, awaiting final vetting
3. **Raw (no extension)** -- Auto-converted, may need cleanup

### Catalog

| # | OpenITI URI | Title (Arabic) | Title (Transliterated) | Author (d. AH) | Genre | Size | File Status |
|---|---|---|---|---|---|---|---|
| 1 | `0676Nawawi.ArbacunaNawawiyya` | الأربعون النووية | al-Arba'un al-Nawawiyyah | al-Nawawi (676) | Hadith | Short (~15 pp) | `.mARkdown` |
| 2 | `0676Nawawi.RiyadSalihin` | رياض الصالحين | Riyad al-Salihin | al-Nawawi (676) | Hadith | Medium (~600 pp) | `.mARkdown` |
| 3 | `0256Bukhari.Sahih` | صحيح البخاري | Sahih al-Bukhari | al-Bukhari (256) | Hadith | Long (~2,600 pp) | `.completed` |
| 4 | `0261Muslim.Sahih` | صحيح مسلم | Sahih Muslim | Muslim (261) | Hadith | Long (~2,200 pp) | Raw |
| 5 | `0852IbnHajarCasqalani.BulughMaram` | بلوغ المرام | Bulugh al-Maram | Ibn Hajar (852) | Hadith/Fiqh | Medium (~350 pp) | Raw |
| 6 | `0774IbnKathir.TafsirQuran` | تفسير القرآن العظيم | Tafsir Ibn Kathir | Ibn Kathir (774) | Tafsir | Long (~3,000 pp) | `.mARkdown` |
| 7 | `0911Suyuti.TafsirJalalayn` | تفسير الجلالين | Tafsir al-Jalalayn | al-Suyuti (911) | Tafsir | Medium (~700 pp) | Raw |
| 8 | `0723IbnAjrum.Ajrumiyya` | المقدمة الآجرومية | al-Ajrumiyyah | Ibn Ajurrum (723) | Grammar | Short (~10 pp) | Raw |
| 9 | `0672IbnMalik.Alfiyya` | ألفية ابن مالك | Alfiyyat Ibn Malik | Ibn Malik (672) | Grammar | Short (~50 pp) | Raw |
| 10 | `0761JamalDinIbnHisham.QatrNada` | قطر الندى وبل الصدى | Qatr al-Nada | Ibn Hisham (761) | Grammar | Short-Med (~100 pp) | Raw |
| 11 | `0620IbnQudamaMaqdisi.CumdatFiqh` | عمدة الفقه | 'Umdat al-Fiqh | Ibn Qudama (620) | Fiqh | Short-Med (~150 pp) | Raw |
| 12 | `0204Shafici.Risala` | الرسالة | al-Risala | al-Shafi'i (204) | Usul al-Fiqh | Medium (~300 pp) | Raw |
| 13 | `0213IbnHisham.SiraNabawiyya` | السيرة النبوية | al-Sira al-Nabawiyya | Ibn Hisham (213) | Sira | Long (~1,500 pp) | Raw |
| 14 | `0728IbnTaymiyya.CaqidaWasitiyya` | العقيدة الواسطية | al-'Aqida al-Wasitiyya | Ibn Taymiyya (728) | Aqeedah | Short (~30 pp) | Raw |
| 15 | `0620IbnQudamaMaqdisi.LumcatIctiqad` | لمعة الاعتقاد | Lum'at al-I'tiqad | Ibn Qudama (620) | Aqeedah | Short (~15 pp) | Raw |
| 16 | `0505Ghazali.IhyaCulumDin` | إحياء علوم الدين | Ihya' 'Ulum al-Din | al-Ghazali (505) | Spirituality | Long (~2,500 pp) | `.completed` |
| 17 | `0505Ghazali.BidayatHidaya` | بداية الهداية | Bidayat al-Hidaya | al-Ghazali (505) | Spirituality | Short (~80 pp) | Raw |
| 18 | `0748Dhahabi.SiyarAclamNubala` | سير أعلام النبلاء | Siyar A'lam al-Nubala' | al-Dhahabi (748) | Biography | Very Long (~10,000 pp) | Raw |

### Genre coverage

| Genre | Count | Books |
|---|---|---|
| Hadith | 5 | Arba'un, Riyad al-Salihin, Bukhari, Muslim, Bulugh al-Maram |
| Tafsir | 2 | Ibn Kathir, Jalalayn |
| Grammar | 3 | Ajrumiyyah, Alfiyyat Ibn Malik, Qatr al-Nada |
| Fiqh | 2 | 'Umdat al-Fiqh, al-Risala |
| Sira | 1 | Ibn Hisham |
| Aqeedah | 2 | al-Wasitiyya, Lum'at al-I'tiqad |
| Spirituality / Biography | 3 | Ihya', Bidayat al-Hidaya, Siyar |

### Ingestion priority

Ingest `.mARkdown` and `.completed` files first (cleanest structural markup):

1. al-Arba'un al-Nawawiyyah (tiny, `.mARkdown`)
2. Riyad al-Salihin (medium, `.mARkdown`)
3. Tafsir Ibn Kathir (large, `.mARkdown`)
4. Sahih al-Bukhari (large, `.completed`)
5. Ihya' 'Ulum al-Din (large, `.completed`)
6. Remaining 13 texts (raw)

---

## Gotchas

**The `tagged` column is canonical; `content_plain` is derived.** The plain text column stores the page text (tags stripped) and powers search. It must stay in sync with `tagged`. The pipeline derives it during the assemble step; never write it independently.

**Unicode diacritic ordering.** Mis-ordered diacritics produce identical visual output but different byte sequences, breaking `content_hash` comparisons. Apply NFC normalization before hashing or comparing.

**`open_tags` enables random-access page jumps.** Without it, jumping to page 49 would require re-parsing from the chapter start to know which tags are open. The `open_tags` stack seeds the parser so any page can be rendered independently.

**Plain-text addresses are stable because the text is frozen.** Classical texts do not change, so a `{book, start, end}` plain-text range is a durable citation address: the basis for the planned sharing feature. User data today anchors by derived `{blockKey}:{wordIndex}` token ids; `anchor_context` is the re-anchoring fallback if a token id shifts.

**Tombstone 90-day purge.** Rows with non-null `deleted_at` are kept for sync propagation. Purge tombstones older than 90 days.

---

## Related Docs

- [Ingestion Pipeline](ingestion-pipeline.md) -- step-by-step pipeline reference
- [Reader App](app.md) -- app architecture, rendering, offline sync
- [I'rab Agents](../agents/irab.md) -- i'rab edge function, cache, and Claude prompt
