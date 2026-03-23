"""Multi-LLM i3rab analysis pipeline.

Uses a hybrid approach for maximum accuracy:
1. CATT auto-diacritization (baseline)
2. CAMeL Tools morphological analysis (features)
3. GPT-4o primary agent (sentence-level i3rab)
4. Claude review agent (cross-validation)
5. Consensus resolution (majority vote)
"""

import asyncio
import json
import os
from dataclasses import asdict

from .models import WordI3rab, SentenceAnalysis, DocumentAnalysis
from .arabic import strip_harakat, split_sentences, normalize_arabic
from .cache import AnalysisCache


# ── System Prompts ──────────────────────────────────────────────────────────

PRIMARY_AGENT_SYSTEM = """You are an expert Arabic grammarian (نحوي متخصص). Your task is to provide the complete i3rab (إعراب) analysis for each word in an Arabic sentence.

You will receive:
1. The sentence to analyze
2. CATT auto-diacritization result (if available)
3. CAMeL Tools morphological analyses (if available)

RULES YOU MUST FOLLOW:
- Every فعل (verb) must have a فاعل (subject) — identify it
- After حروف الجر (في، من، على، عن، إلى، الباء، اللام، الكاف) → the noun is مجرور (genitive)
- After إنَّ وأخواتها (إنَّ، أنَّ، لكنَّ، كأنَّ، ليتَ، لعلَّ) → the subject (اسم إنَّ) is منصوب (accusative), the predicate (خبر إنَّ) is مرفوع (nominative)
- After كان وأخواتها (كان، أصبح، أمسى، ظلَّ، بات، صار، ليس، ما زال، ما دام) → the subject (اسم كان) is مرفوع, the predicate (خبر كان) is منصوب
- المفعول به (direct object) is منصوب
- المبتدأ والخبر (subject and predicate of nominal sentence) are both مرفوع
- الحال (adverbial of state) is منصوب
- التمييز (specification) is منصوب
- المضاف إليه (possessive complement) is مجرور
- النعت (adjective) follows its described noun in case, gender, number, and definiteness
- المعطوف (coordinated word) follows the case of المعطوف عليه
- الأسماء الخمسة (five nouns: أب، أخ، حم، فو، ذو) are declined with letters: nom=و, acc=ا, gen=ي
- الممنوع من الصرف (diptotes) take فتحة instead of كسرة in genitive
- الأفعال الخمسة are declined by adding/removing ن
- المثنى (dual) and جمع المذكر السالم (sound masculine plural) have special markers
- Indeclinable words (مبني): particles, demonstratives, relative pronouns, past tense verbs, imperative verbs

OUTPUT FORMAT: Return a JSON object with a "words" array. Each word must have:
{
  "words": [
    {
      "word": "الكلمة بدون تشكيل",
      "diacritized": "الكَلِمَةُ مع التشكيل الكامل",
      "pos": "noun|verb|particle|adjective|adverb|pronoun|preposition|conjunction",
      "syntactic_role": "subject|predicate|object|adverbial|possessive|adjective|coordinated|prepositional_phrase|...",
      "case": "nom|acc|gen|jussive|indeclinable",
      "case_reason": "السبب بالعربية",
      "i3rab_full": "الإعراب الكامل بالعربية (مثل: فاعل مرفوع وعلامة رفعه الضمة الظاهرة على آخره)",
      "translation_word": "English dictionary meaning",
      "translation_contextual": "meaning in this sentence's context"
    }
  ]
}

Be precise with the diacritization. Include ALL harakat (tashkeel) on every letter."""

REVIEW_AGENT_SYSTEM = """You are a senior Arabic grammar reviewer (مراجع نحوي أقدم). Your task is to review an i3rab analysis for errors and provide corrections.

Check for:
1. Subject-verb agreement (تطابق الفعل والفاعل) — gender and number
2. Incorrect case endings after governing particles (عوامل)
3. Idafa chain errors (أخطاء الإضافة) — المضاف must lose tanween, المضاف إليه must be مجرور
4. Missing or incorrect nunation (تنوين)
5. Diptote errors (الممنوع من الصرف) — takes فتحة instead of كسرة in genitive
6. Five nouns errors (الأسماء الخمسة)
7. Dual/plural marker errors
8. Adjective agreement errors (تطابق النعت والمنعوت)
9. Coordination case errors (case of معطوف must match معطوف عليه)
10. Internal consistency — if marked as فاعل, the case MUST be مرفوع

For each word, indicate if the analysis is correct or provide a correction.

OUTPUT FORMAT: Return a JSON object:
{
  "corrections": [
    {
      "word_index": 0,
      "is_correct": true,
      "corrected_case": null,
      "corrected_role": null,
      "corrected_diacritized": null,
      "corrected_i3rab_full": null,
      "reason": null,
      "confidence": "high|medium|low"
    }
  ]
}

Only include entries where is_correct is false OR where you want to confirm with high confidence.
If everything is correct, return {"corrections": []} with entries for each word with is_correct=true."""


# ── CATT + CAMeL helpers ───────────────────────────────────────────────────

def _get_catt_diacritization(text: str) -> str | None:
    """Get CATT auto-diacritization for text."""
    try:
        from catt_tashkeel import CATTEncoderDecoder
        catt = CATTEncoderDecoder()
        sentences = split_sentences(text)
        if not sentences:
            sentences = [text]
        results = catt.do_tashkeel_batch(sentences, verbose=False)
        return " ".join(results)
    except (ImportError, Exception):
        return None


def _get_camel_analysis(text: str) -> list[dict] | None:
    """Get CAMeL Tools morphological analysis for each word."""
    try:
        from camel_tools.morphology.database import MorphologyDB
        from camel_tools.morphology.analyzer import Analyzer

        db = MorphologyDB.builtin_db()
        analyzer = Analyzer(db)

        words = strip_harakat(text).split()
        results = []
        for word in words:
            analyses = analyzer.analyze(word)
            word_analyses = []
            for a in analyses[:5]:  # Top 5 analyses
                word_analyses.append({
                    "diac": a.get("diac", ""),
                    "pos": a.get("pos", ""),
                    "cas": a.get("cas", ""),
                    "gloss": a.get("gloss", ""),
                })
            results.append({"word": word, "analyses": word_analyses})
        return results
    except (ImportError, Exception):
        return None


# ── LLM Calls ──────────────────────────────────────────────────────────────

async def _call_openai(sentence: str, catt_result: str | None, camel_result: list[dict] | None) -> dict | None:
    """Call GPT-4o for primary i3rab analysis."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key)

    user_content = f"Sentence to analyze:\n{sentence}\n"
    if catt_result:
        user_content += f"\nCATT auto-diacritization:\n{catt_result}\n"
    if camel_result:
        user_content += f"\nCAMeL Tools morphological analyses:\n{json.dumps(camel_result, ensure_ascii=False, indent=2)}\n"
    user_content += "\nProvide the complete i3rab analysis for each word."

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": PRIMARY_AGENT_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
        max_tokens=4000,
    )

    try:
        return json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, IndexError):
        return None


async def _call_claude_review(sentence: str, primary_analysis: dict) -> dict | None:
    """Call Claude to review the primary i3rab analysis."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    import anthropic
    client = anthropic.AsyncAnthropic(api_key=api_key)

    user_content = (
        f"The sentence:\n{sentence}\n\n"
        f"The i3rab analysis to review:\n{json.dumps(primary_analysis, ensure_ascii=False, indent=2)}\n\n"
        "Review this analysis and check for errors. Return your review as JSON."
    )

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        system=REVIEW_AGENT_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )

    # Extract JSON from response
    text = response.content[0].text
    # Try to parse directly
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code block
        import re
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    return None


async def _call_openai_review(sentence: str, primary_analysis: dict) -> dict | None:
    """Call GPT-4o as a fallback reviewer when Claude is unavailable."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key)

    user_content = (
        f"The sentence:\n{sentence}\n\n"
        f"The i3rab analysis to review:\n{json.dumps(primary_analysis, ensure_ascii=False, indent=2)}\n\n"
        "Review this analysis carefully and check for errors."
    )

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": REVIEW_AGENT_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
        max_tokens=4000,
    )

    try:
        return json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, IndexError):
        return None


# ── Consensus Resolution ───────────────────────────────────────────────────

def _resolve_consensus(
    primary: dict,
    review: dict | None,
    catt_result: str | None,
) -> list[WordI3rab]:
    """Merge primary analysis, review corrections, and CATT diacritization.

    Confidence levels:
    - HIGH: primary + reviewer + CATT all agree (or reviewer confirms)
    - MEDIUM: 2 of 3 agree
    - LOW: disagreement, using primary as default
    """
    words = primary.get("words", [])
    corrections = {}
    if review and "corrections" in review:
        for c in review["corrections"]:
            idx = c.get("word_index", -1)
            corrections[idx] = c

    # Parse CATT diacritization into per-word case endings
    catt_cases = {}
    if catt_result:
        from .arabic import get_last_letter_harakat
        from .book import HARAKA_TO_CASE
        catt_words = catt_result.split()
        for i, cw in enumerate(catt_words):
            last_h = get_last_letter_harakat(cw)
            case_h = [h for h in last_h if h != "\u0651"]
            if case_h and case_h[-1] in HARAKA_TO_CASE:
                catt_cases[i] = HARAKA_TO_CASE[case_h[-1]]

    results = []
    for i, w in enumerate(words):
        correction = corrections.get(i)
        primary_case = w.get("case", "unknown")

        # Determine confidence based on agreement
        sources = {"llm_primary": primary_case}

        if i in catt_cases:
            sources["catt"] = catt_cases[i]

        if correction:
            if correction.get("is_correct", True):
                sources["llm_reviewer"] = primary_case
                confidence = "high" if len(set(sources.values())) == 1 else "medium"
            else:
                corrected_case = correction.get("corrected_case", primary_case)
                sources["llm_reviewer"] = corrected_case

                # Use reviewer's correction if it agrees with CATT
                if catt_cases.get(i) == corrected_case:
                    # Reviewer + CATT agree, override primary
                    w["case"] = corrected_case
                    if correction.get("corrected_diacritized"):
                        w["diacritized"] = correction["corrected_diacritized"]
                    if correction.get("corrected_i3rab_full"):
                        w["i3rab_full"] = correction["corrected_i3rab_full"]
                    if correction.get("corrected_role"):
                        w["syntactic_role"] = correction["corrected_role"]
                    confidence = "medium"
                else:
                    # Disagreement — keep primary but flag as low confidence
                    confidence = "low"
        else:
            # No review correction
            if i in catt_cases and catt_cases[i] == primary_case:
                confidence = "high"
            elif i in catt_cases:
                confidence = "medium"
            else:
                confidence = "medium"

        results.append(WordI3rab(
            word_index=i,
            word_base=w.get("word", ""),
            word_diacritized=w.get("diacritized", ""),
            pos=w.get("pos", ""),
            syntactic_role=w.get("syntactic_role", ""),
            case=w.get("case", ""),
            case_reason=w.get("case_reason", ""),
            i3rab_full=w.get("i3rab_full", ""),
            translation_word=w.get("translation_word", ""),
            translation_contextual=w.get("translation_contextual", ""),
            confidence=confidence,
            sources=sources,
        ))

    return results


# ── Main Analysis Functions ────────────────────────────────────────────────

async def analyze_sentence(
    sentence: str,
    sentence_index: int = 0,
    cache: AnalysisCache | None = None,
) -> SentenceAnalysis:
    """Run full i3rab analysis pipeline on a single sentence.

    Steps:
    1. Check cache
    2. CATT diacritization
    3. CAMeL morphological analysis
    4. GPT-4o primary analysis
    5. Claude review
    6. Consensus resolution
    """
    # Check cache first
    if cache:
        cached = cache.get_sentence(sentence)
        if cached:
            cached.sentence_index = sentence_index
            return cached

    # Step 1: CATT diacritization (runs synchronously)
    catt_result = await asyncio.to_thread(_get_catt_diacritization, sentence)

    # Step 2: CAMeL analysis (runs synchronously)
    camel_result = await asyncio.to_thread(_get_camel_analysis, sentence)

    # Step 3: Primary LLM analysis (GPT-4o)
    primary = await _call_openai(sentence, catt_result, camel_result)

    if not primary or "words" not in primary:
        # Fallback: construct basic analysis from CATT or raw text
        words_text = sentence.split()
        primary = {"words": [
            {
                "word": strip_harakat(w),
                "diacritized": w,
                "pos": "unknown",
                "syntactic_role": "unknown",
                "case": "unknown",
                "case_reason": "تحليل غير متوفر",
                "i3rab_full": "لم يتم التحليل",
                "translation_word": "",
                "translation_contextual": "",
            }
            for w in words_text
        ]}

    # Step 4: Review (Claude preferred, GPT-4o fallback)
    review = await _call_claude_review(sentence, primary)
    if review is None:
        review = await _call_openai_review(sentence, primary)

    # Step 5: Consensus resolution
    words = _resolve_consensus(primary, review, catt_result)

    analysis = SentenceAnalysis(
        sentence_text=sentence,
        sentence_index=sentence_index,
        words=words,
    )

    # Cache the result
    if cache:
        cache.put_sentence(analysis)

    return analysis


async def analyze_document(
    text: str,
    document_id: str = "",
    title: str = "",
    cache: AnalysisCache | None = None,
    progress_callback=None,
) -> DocumentAnalysis:
    """Run full i3rab analysis on an entire document.

    Processes sentence by sentence, calling progress_callback(current, total)
    after each sentence.
    """
    sentences = split_sentences(text)
    if not sentences:
        sentences = [text]

    total = len(sentences)
    all_analyses = []
    total_words = 0

    for i, sentence in enumerate(sentences):
        if not sentence.strip():
            continue

        analysis = await analyze_sentence(sentence, sentence_index=i, cache=cache)
        all_analyses.append(analysis)
        total_words += len(analysis.words)

        if progress_callback:
            progress_callback(i + 1, total)

    doc_analysis = DocumentAnalysis(
        document_id=document_id,
        title=title,
        sentences=all_analyses,
        total_words=total_words,
        analyzed_words=total_words,
    )

    # Cache the full document
    if cache and document_id:
        cache.put_document(document_id, doc_analysis)

    return doc_analysis
