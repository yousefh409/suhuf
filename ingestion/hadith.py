"""Deterministic hadith-structure detection.

Anchors on the universal prophetic-speech marker (قال رسول الله / عن النبي / …)
to split a prose hadith block into isnad / matn / takhrij inline spans, with a
confidence per span. Runs after parse, before tashkeel. See spec
docs/superpowers/specs/2026-06-03-deterministic-hadith-structure-design.md.
"""
from __future__ import annotations
import logging
import re

from ingestion.models import ParseResult, Span

logger = logging.getLogger(__name__)

HIGH_CONF = 0.95   # ≥2 signals agree (marker + quote or takhrij)
LOW_CONF = 0.70    # marker only

# Combining marks (harakat, sukun, dagger alef) + tatweel.
_TASHKEEL = re.compile(r"[ً-ْٰـ]")


def _norm(text: str) -> str:
    """Bare Arabic letters for marker matching: strip tashkeel, fold alef/ya/ta
    variants, drop non-letters (punctuation, «», digits, ﷺ)."""
    text = _TASHKEEL.sub("", text)
    text = text.translate(str.maketrans("أإآىة", "ااايه"))
    return "".join(c for c in text if "ء" <= c <= "ي")


# Words that, immediately before a prophetic subject, mark the isnad→matn
# boundary: speech/transmission (قال/عن/أن/سمعت) and prophetic-action verbs
# (نهى/كان/أمر/خطب/…). Written in readable Arabic and **normalized
# programmatically** so the set always matches _norm'd tokens (نهى→نهي, أن→ان,
# أمر→امر …) — hand-normalizing once caused silent misses. The subject-gate
# (_is_prophetic_subject) keeps a generous verb list safe: a verb only fires
# when رسول الله / النبي actually follows it.
_INTRODUCER_WORDS = [
    # speech / transmission
    "قال", "قالت", "عن", "أن", "سمعت", "حدثنا", "حدثني",
    # prophetic-action verbs (+ common -نا conjugations)
    "نهى", "نهانا", "أمر", "أمرنا", "كان", "رأى", "رأيت", "خطب", "خطبنا",
    "صلى", "توضأ", "اغتسل", "قضى", "رخص", "لعن", "بعث", "بعثنا",
    "استسقى", "دخل", "خرج", "مر", "أتى", "جاء", "نزل", "قدم", "كتب",
    "علمنا", "أوصى", "حج", "اعتمر", "سئل", "صنع", "فعل",
]
PROPHETIC_INTRODUCERS = {_norm(w) for w in _INTRODUCER_WORDS}
_BLESSING = _norm("صلى")  # opens "صلى الله عليه وسلم" — handles the الله-omitted form

# Source-attribution keywords (normalized) that open a takhrij tail.
TAKHRIJ_NORM = {"رواه", "اخرجه", "اخرجها", "رواها", "متفق"}

# Transmission openers (normalized, incl. و-prefixed) that signal an isnad — the
# hadith-context gate for the «…»-matn fallback.
_TRANSMISSIONS = {_norm(w) for w in
                  ["عن", "وعن", "وعنه", "وعنها", "حدثنا", "وحدثنا", "حدثني",
                   "أخبرنا", "أخبرني", "أنبأنا", "سمعت"]}

# A block that OPENS like this is a cross-reference / source-attribution variant
# (digest works cite where else a hadith appears), not a fresh isnad: "وللبيهقي:",
# "ولأبي داود", "وأصله في الصحيحين", "وأخرجه", "ومن حديث …". Matched on raw text.
_CROSSREF_RE = re.compile(
    r"^\s*(ولل|ولأ|وله\b|ولاب|وعند|وأخرج|وأصل|ورواه|ولدى|ولابن|وزاد|"
    r"وفي رواية|ومن حديث|وفي حديث|وله[ا]? |وعنده)")


def _is_prophetic_subject(norm: list[str], j: int) -> bool:
    """True if token j begins a reference to the Prophet: "النبي", or "رسول"
    whose next non-empty token is "الله" or the blessing "صلى" (so a generic
    "رسول فلان" is excluded)."""
    if j >= len(norm):
        return False
    if norm[j] == "النبي":
        return True
    if norm[j] == "رسول":
        k = j + 1
        while k < len(norm) and norm[k] == "":
            k += 1
        return k < len(norm) and norm[k] in ("الله", _BLESSING)
    return False


def _find_prophetic_marker(norm_tokens: list[str]) -> int | None:
    """Return the index of the earliest introducer immediately followed by a
    prophetic subject (the isnad→matn boundary), or None if absent."""
    for i in range(len(norm_tokens)):
        if norm_tokens[i] in PROPHETIC_INTRODUCERS and _is_prophetic_subject(norm_tokens, i + 1):
            return i
    return None


def detect_hadith_structure(result: ParseResult) -> dict:
    """Mutate prose hadith blocks in place, adding isnad/matn/takhrij spans.
    Returns a stats dict."""
    stats = {"hadith": 0, "isnad": 0, "matn": 0, "takhrij": 0,
             "high_conf": 0, "low_conf": 0}
    for page in result.pages:
        for block in page.content_blocks:
            if block.type != "prose":
                continue
            # Skip blocks already structured (e.g. the rare native @MATN@ path).
            if any(s.label in ("isnad", "matn", "takhrij") for s in block.spans):
                continue
            _detect_block(block, stats)
    return stats


def _emit(block, toks, isnad, matn, takhrij, conf: float, stats: dict) -> None:
    """Append the (start,end)-indexed isnad/matn/takhrij spans (None = skip)."""
    for label, rng in (("isnad", isnad), ("matn", matn), ("takhrij", takhrij)):
        if rng is None:
            continue
        s, e = rng
        block.spans.append(Span(start_token_id=toks[s].id, end_token_id=toks[e].id,
                                label=label, confidence=conf))
        stats[label] += 1
    stats["hadith"] += 1
    stats["high_conf" if conf >= HIGH_CONF else "low_conf"] += 1


# Narrator hinge (normalized): the report verb / complementizer that ends the
# isnad in a marker-less hadith ("عن X قال: …" / "عن X أن Y …").
_QAL_HINGE = {_norm(w) for w in ["قال", "قالت", "أن"]}


def _detect_block(block, stats: dict) -> None:
    toks = block.tokens
    norm = [_norm(t.text) for t in toks]
    b = _find_prophetic_marker(norm)
    if b is not None:
        _emit_from_marker(block, toks, norm, b, stats)        # tier 1: high conf
        return
    if _emit_from_quote(block, toks, norm, stats):            # tier 2: «…» matn
        return
    if _emit_from_narrator_qal(block, toks, norm, stats):     # tier 3: عن X قال:
        return
    _emit_from_crossref(block, toks, norm, stats)             # tier 4: cross-ref


def _emit_from_marker(block, toks, norm, b: int, stats: dict) -> None:
    n = len(toks)
    takhrij_idx = next((j for j in range(b + 1, n) if norm[j] in TAKHRIJ_NORM), None)
    quote_close = None
    if any("«" in toks[k].text for k in range(b, n)):
        quote_close = next((k for k in range(b, n) if "»" in toks[k].text), None)

    candidates = [n - 1]
    if takhrij_idx is not None:
        candidates.append(takhrij_idx - 1)
    if quote_close is not None:
        candidates.append(quote_close)
    matn_end = min(candidates)
    if matn_end < b:
        return  # self-check: matn would be empty

    conf = HIGH_CONF if (takhrij_idx is not None or quote_close is not None) else LOW_CONF
    isnad = (0, b - 1) if b > 0 else None
    takhrij = (takhrij_idx, n - 1) if takhrij_idx is not None else None
    _emit(block, toks, isnad, (b, matn_end), takhrij, conf, stats)


def _emit_from_quote(block, toks, norm, stats: dict) -> bool:
    """Fallback for hadith with no prophetic marker (possessive/vocative/dialogue
    forms): if a «…» matn quote sits in a transmission context, tag it.
    Low-confidence — the LLM may correct it. Never fires on quote-less editions
    (Bukhari/Tirmidhi). Returns True if it emitted spans."""
    n = len(toks)
    q_open = next((k for k in range(n) if "«" in toks[k].text), None)
    if q_open is None:
        return False
    q_close = next((k for k in range(q_open, n) if "»" in toks[k].text), None)
    if q_close is None:
        return False
    # Hadith-context gate: a transmission opener (عن/حدثنا/…) before the quote.
    if not any(norm[k] in _TRANSMISSIONS for k in range(q_open)):
        return False
    takhrij_idx = next((j for j in range(q_close + 1, n) if norm[j] in TAKHRIJ_NORM), None)
    isnad = (0, q_open - 1) if q_open > 0 else None
    takhrij = (takhrij_idx, n - 1) if takhrij_idx is not None else None
    _emit(block, toks, isnad, (q_open, q_close), takhrij, LOW_CONF, stats)
    return True


def _emit_from_narrator_qal(block, toks, norm, stats: dict) -> bool:
    """Last-resort fallback for marker-less, quote-less hadith (Companion
    statements, descriptions of the Prophet): a block that OPENS with a
    transmission isnad and has a narrator hinge (قال/قالت/أن) — isnad before the
    hinge, matn after. Low-confidence; the LLM may correct it. Returns True if it
    emitted spans."""
    n = len(toks)
    if n < 3:
        return False
    # Gate: the block must OPEN with an isnad — a strong "this is a hadith" signal
    # (a fiqh discussion rarely starts with "عن X … قال:").
    first = next((x for x in norm if x), "")
    if first not in _TRANSMISSIONS:
        return False
    hinge = next((j for j in range(1, n) if norm[j] in _QAL_HINGE), None)
    if hinge is None or hinge == 0:
        return False
    takhrij_idx = next((j for j in range(hinge + 1, n) if norm[j] in TAKHRIJ_NORM), None)
    matn_end = (takhrij_idx - 1) if takhrij_idx is not None else (n - 1)
    if matn_end < hinge:
        return False
    takhrij = (takhrij_idx, n - 1) if takhrij_idx is not None else None
    _emit(block, toks, (0, hinge - 1), (hinge, matn_end), takhrij, LOW_CONF, stats)
    return True


def _emit_from_crossref(block, toks, norm, stats: dict) -> None:
    """Tier 4: a block opening with a cross-reference / source-attribution
    variant (وللبيهقي: «…» / وأصله في الصحيحين …). With a «…» quote it's a cited
    matn (opener = takhrij); without one it's a pure source note (whole block =
    takhrij). Low-confidence — the LLM may relabel a report-variant to matn."""
    raw = " ".join(t.text for t in toks)
    if not _CROSSREF_RE.match(raw):
        return
    n = len(toks)
    q_open = next((k for k in range(n) if "«" in toks[k].text), None)
    q_close = next((k for k in range(q_open, n) if "»" in toks[k].text), None) if q_open is not None else None
    if q_open is not None and q_close is not None and q_open > 0:
        # «…» variant: the opener attributes the source (takhrij), the quote is the matn.
        _emit(block, toks, None, (q_open, q_close), (0, q_open - 1), LOW_CONF, stats)
    else:
        _emit(block, toks, None, None, (0, n - 1), LOW_CONF, stats)  # pure source note
