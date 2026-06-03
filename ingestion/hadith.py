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


def _deconj(n: str) -> str:
    """Drop a leading conjunction ف/و so prefixed verbs (فقال/وصلى) still match a
    bare introducer/hinge. Only when the remainder stays a plausible word."""
    return n[1:] if len(n) > 3 and n[0] in ("ف", "و") else n


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
    r"^\s*(ولل|ولأ|ولمسلم|ولاب|وعند|وعنده|وأخرج|وأصل|ورواه|وروى|روى|ولدى|"
    r"وزاد|زاد|ونحوه|واتفق|وهو في|وكذا|ومثله|وذكر|وأورد|وقد روى|ومن طريق|"
    r"وفي الباب|وآخر|وقصة|وثبت|حديث |وفي رواية|ومن حديث|وفي حديث|"
    r"وفي البخاري|وفي المتفق|وفي الصحيح|وله\b|ولها\b|ولهما\b|ولهم\b)")

# Grading / authentication vocabulary — a residual block carrying these is a
# source/hukm note (takhrij-like), not a fresh hadith.
_GRADING_VOCAB = {_norm(w) for w in
                  ["صححه", "صحح", "ضعفه", "ضعيف", "موقوفا", "موقوف", "مرفوعا",
                   "مرفوع", "معلقا", "معلق", "بسند", "إسناده", "حسنه", "وصححه",
                   # cross-reference "similarly/likewise" notes (variant citations)
                   "نحوه", "بنحوه", "مثله", "بمثله", "بمعناه", "مثل"]}


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
        tok = norm_tokens[i]
        if (tok in PROPHETIC_INTRODUCERS or _deconj(tok) in PROPHETIC_INTRODUCERS) \
                and _is_prophetic_subject(norm_tokens, i + 1):
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


def _takhrij_end(toks, start: int, n: int) -> int:
    """End index of a takhrij clause — capped at the first sentence terminator
    (. / » / ؛) or just before a NEW cross-reference variant, not the block end,
    so a trailing variant report isn't swallowed into the source attribution."""
    for k in range(start, n):
        t = toks[k].text.rstrip()
        if t.endswith((".", "»", "؛")):
            return k
        if k > start and _CROSSREF_RE.match(t):
            return k - 1
    return n - 1


# Narrator hinge (normalized): the report verb / complementizer that ends the
# isnad in a marker-less hadith ("عن X قال: …" / "عن X أن Y …").
_QAL_HINGE = {_norm(w) for w in ["قال", "قالت", "أن", "أنه", "أنها", "أنهم"]}
# Subset whose token introduces the matn (goes IN the matn), vs قال/قالت which
# end the isnad (stay in isnad).
_AN_HINGE = {_norm(w) for w in ["أن", "أنه", "أنها", "أنهم"]}


def _detect_ranges(toks, norm):
    """Compute (isnad, matn, takhrij, conf) ranges over a token list, or None.
    Ranges are inclusive (start, end) index pairs in `toks` coords, or None."""
    b = _find_prophetic_marker(norm)
    if b is not None:
        return _ranges_from_marker(toks, norm, b)
    return (_ranges_from_quote(toks, norm)
            or _ranges_from_narrator_qal(toks, norm)
            or _ranges_from_crossref(toks, norm))


def _ranges_from_marker(toks, norm, b):
    n = len(toks)
    takhrij_idx = next((j for j in range(b + 1, n) if norm[j] in TAKHRIJ_NORM), None)
    quote_close = None
    if any("«" in toks[k].text for k in range(b, n)):
        quote_close = next((k for k in range(b, n) if "»" in toks[k].text), None)
    cands = [n - 1]
    if takhrij_idx is not None:
        cands.append(takhrij_idx - 1)
    if quote_close is not None:
        cands.append(quote_close)
    matn_end = min(cands)
    if matn_end < b:
        return None
    conf = HIGH_CONF if (takhrij_idx is not None or quote_close is not None) else LOW_CONF
    isnad = (0, b - 1) if b > 0 else None
    takhrij = (takhrij_idx, _takhrij_end(toks, takhrij_idx, n)) if takhrij_idx is not None else None
    return (isnad, (b, matn_end), takhrij, conf)


def _ranges_from_quote(toks, norm):
    n = len(toks)
    q_open = next((k for k in range(n) if "«" in toks[k].text), None)
    if q_open is None:
        return None
    q_close = next((k for k in range(q_open, n) if "»" in toks[k].text), None)
    if q_close is None:
        return None
    if not any(norm[k] in _TRANSMISSIONS for k in range(q_open)):
        return None
    takhrij_idx = next((j for j in range(q_close + 1, n) if norm[j] in TAKHRIJ_NORM), None)
    isnad = (0, q_open - 1) if q_open > 0 else None
    takhrij = (takhrij_idx, _takhrij_end(toks, takhrij_idx, n)) if takhrij_idx is not None else None
    return (isnad, (q_open, q_close), takhrij, LOW_CONF)


def _ranges_from_narrator_qal(toks, norm):
    n = len(toks)
    if n < 3:
        return None
    first = next((x for x in norm if x), "")
    if first not in _TRANSMISSIONS:
        return None
    hinge = next((j for j in range(1, n)
                  if norm[j] in _QAL_HINGE or _deconj(norm[j]) in _QAL_HINGE
                  or toks[j].text.rstrip().endswith(":")), None)
    if hinge is None or hinge == 0:
        return None
    is_an = norm[hinge] in _AN_HINGE or _deconj(norm[hinge]) in _AN_HINGE
    matn_start = hinge if is_an else hinge + 1
    isnad_end = hinge - 1 if is_an else hinge
    if matn_start >= n or isnad_end < 0:
        return None
    takhrij_idx = next((j for j in range(matn_start + 1, n) if norm[j] in TAKHRIJ_NORM), None)
    matn_end = (takhrij_idx - 1) if takhrij_idx is not None else (n - 1)
    if matn_end < matn_start:
        return None
    takhrij = (takhrij_idx, _takhrij_end(toks, takhrij_idx, n)) if takhrij_idx is not None else None
    return ((0, isnad_end), (matn_start, matn_end), takhrij, LOW_CONF)


def _ranges_from_crossref(toks, norm):
    raw = " ".join(t.text for t in toks)
    if not (_CROSSREF_RE.match(raw) or any(x in _GRADING_VOCAB for x in norm)):
        return None
    n = len(toks)
    q_open = next((k for k in range(n) if "«" in toks[k].text), None)
    q_close = next((k for k in range(q_open, n) if "»" in toks[k].text), None) if q_open is not None else None
    if q_open is not None and q_close is not None and q_open > 0:
        return (None, (q_open, q_close), (0, q_open - 1), LOW_CONF)
    colon = next((k for k in range(n) if toks[k].text.rstrip().endswith(":")), None)
    if colon is not None and colon + 1 < n:
        rest0 = colon + 1
        rest_is_source = (norm[rest0] in _TRANSMISSIONS
                          or " ".join(t.text for t in toks[rest0:rest0 + 2]).startswith(("من حديث", "من رواية")))
        if not rest_is_source:
            tk = next((j for j in range(rest0, n) if norm[j] in TAKHRIJ_NORM), None)
            matn_end = (tk - 1) if tk is not None else (n - 1)
            if matn_end >= rest0:
                return (None, (rest0, matn_end), (0, colon), LOW_CONF)
    return (None, None, (0, n - 1), LOW_CONF)


def _detect_block(block, stats: dict) -> None:
    toks = block.tokens
    ranges = _detect_ranges(toks, [_norm(t.text) for t in toks])
    if ranges is not None:
        isnad, matn, takhrij, conf = ranges
        _emit(block, toks, isnad, matn, takhrij, conf, stats)
