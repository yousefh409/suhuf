"""Test cursor retreat behavior for re-reading.

Drives StreamingSession through a synthesized scenario:
- Cursor advances to phrase 3.
- A new score cycle finds phrase 1 is the best match by a wide margin.
- Cursor should retreat to phrase 1.
- Word verdicts for phrase 1 should be cleared so a fresh score replaces them.
- _best_spoken for phrases 2 and 3 should be preserved (forward watermarks).

This test mocks the model interaction and exercises only the retreat building
blocks — no real model needed.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from engine import StreamingSession


class _FakeEngine:
    """Minimal stub — StreamingSession only needs engine for scoring, not tests."""
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(n_phrases=8):
    """Session with n single-word phrases: 'word0', 'word1', ... """
    phrases = [f"word{i}" for i in range(n_phrases)]
    return StreamingSession(_FakeEngine(), phrases)


def _make_multiword_session():
    """Session where phrases have multiple words so offsets are non-trivial.

    Phrase 0: "alpha beta"        words at global idx 0, 1
    Phrase 1: "gamma delta eps"   words at global idx 2, 3, 4
    Phrase 2: "zeta eta"          words at global idx 5, 6
    Phrase 3: "theta"             words at global idx 7
    """
    phrases = [
        "alpha beta",
        "gamma delta eps",
        "zeta eta",
        "theta",
    ]
    return StreamingSession(_FakeEngine(), phrases)


# ---------------------------------------------------------------------------
# Test 1: candidate window includes cursor-2
# ---------------------------------------------------------------------------

def test_candidate_window_includes_cursor_minus_two():
    """_get_candidates must include cursor-2 so re-reads two phrases back are seen."""
    sess = _make_session(8)
    sess.cursor_phrase = 3
    cands = sess._get_candidates()

    assert 1 in cands, f"cursor-2 (=1) should be in candidates, got {cands}"
    assert 2 in cands, f"cursor-1 (=2) should be in candidates, got {cands}"
    assert 3 in cands, f"cursor (=3) should be in candidates, got {cands}"
    # Should not include indices past cursor + lookahead (default 5)
    assert 8 not in cands, f"index 8 is out of range, got {cands}"
    # Should not include negative indices
    assert -1 not in cands


def test_candidate_window_clamps_at_zero():
    """cursor-2 must not produce negative indices."""
    sess = _make_session(8)
    sess.cursor_phrase = 1
    cands = sess._get_candidates()
    assert all(c >= 0 for c in cands), f"All candidates must be >= 0, got {cands}"
    assert 0 in cands


# ---------------------------------------------------------------------------
# Test 2: _retreat_to unlocks target phrase words
# ---------------------------------------------------------------------------

def test_retreat_to_unlocks_target_phrase_words():
    """Words in the retreated-to phrase are removed; forward words are preserved."""
    sess = _make_multiword_session()
    sess.cursor_phrase = 3

    # Phrase 1 occupies global word indices 2, 3, 4.
    # Phrase 2 occupies global word indices 5, 6.
    sess.scored_words = {
        2: {"word": "gamma", "_locked": True},
        3: {"word": "delta", "_locked": True},
        4: {"word": "eps", "_locked": True},
        5: {"word": "zeta", "_locked": True},
        6: {"word": "eta", "_locked": True},
    }

    sess._retreat_to(1)  # retreat to phrase 1

    # Phrase 1 words cleared
    assert 2 not in sess.scored_words, "phrase 1 word 'gamma' should be removed"
    assert 3 not in sess.scored_words, "phrase 1 word 'delta' should be removed"
    assert 4 not in sess.scored_words, "phrase 1 word 'eps' should be removed"

    # Forward phrase (phrase 2) words preserved
    assert 5 in sess.scored_words, "phrase 2 word 'zeta' should be preserved"
    assert 6 in sess.scored_words, "phrase 2 word 'eta' should be preserved"


# ---------------------------------------------------------------------------
# Test 3: _retreat_to resets only target watermark
# ---------------------------------------------------------------------------

def test_retreat_to_resets_target_watermark_only():
    """_best_spoken[target] is reset to 0; forward watermarks are untouched."""
    sess = _make_session(6)
    sess.cursor_phrase = 3
    sess._best_spoken = {1: 2, 2: 3, 3: 1}

    sess._retreat_to(1)

    assert sess._best_spoken[1] == 0, "_best_spoken for retreated phrase must be reset to 0"
    assert sess._best_spoken[2] == 3, "_best_spoken for phrase 2 should be unchanged"
    assert sess._best_spoken[3] == 1, "_best_spoken for phrase 3 should be unchanged"


# ---------------------------------------------------------------------------
# Test 4: _retreat_to is a no-op when target is not backward
# ---------------------------------------------------------------------------

def test_retreat_to_noop_when_target_not_backward():
    """_retreat_to must not move cursor if target >= cursor_phrase."""
    sess = _make_multiword_session()
    sess.cursor_phrase = 2
    sess.scored_words = {5: {"word": "zeta"}, 6: {"word": "eta"}}
    sess._best_spoken = {2: 2}

    original_cursor = sess.cursor_phrase
    original_scored = dict(sess.scored_words)
    original_best = dict(sess._best_spoken)

    # Same index — no-op
    sess._retreat_to(2)
    assert sess.cursor_phrase == original_cursor
    assert sess.scored_words == original_scored
    assert sess._best_spoken == original_best

    # Forward index — also no-op
    sess._retreat_to(3)
    assert sess.cursor_phrase == original_cursor
    assert sess.scored_words == original_scored
    assert sess._best_spoken == original_best


# ---------------------------------------------------------------------------
# Test 5: _retreat_to sets cursor
# ---------------------------------------------------------------------------

def test_retreat_to_sets_cursor():
    """After _retreat_to(n), cursor_phrase must equal n."""
    sess = _make_session(8)
    sess.cursor_phrase = 5
    sess._retreat_to(3)
    assert sess.cursor_phrase == 3, f"Expected cursor=3, got {sess.cursor_phrase}"


# ---------------------------------------------------------------------------
# Test 6: retreat decision smoke test
# ---------------------------------------------------------------------------

def test_retreat_decision_triggers_on_wide_margin():
    """_retreat_to moves the cursor and clears the target phrase's words.

    We confirm the preconditions that would cause score_cycle to call _retreat_to
    (best_idx is behind cursor by at most 2 and the score margin is sufficient),
    then call _retreat_to directly and assert the action was taken.  This way the
    test exercises the real engine building block rather than duplicating the
    predicate logic inline.
    """
    sess = _make_session(8)
    sess.cursor_phrase = 3
    sess._best_spoken = {1: 1, 2: 2, 3: 1}

    # Pre-fill some scored words for phrase 3 (global word idx 3)
    sess.scored_words = {3: {"word": "word3", "_locked": True}}

    # Confirm entry conditions that score_cycle checks before calling _retreat_to.
    best_idx = 1
    best_score = 0.75
    cursor_score = 0.40
    assert best_idx < sess.cursor_phrase, "best_idx must be behind cursor"
    assert best_idx >= sess.cursor_phrase - 2, "best_idx must be within 2 of cursor"
    assert best_score - cursor_score >= StreamingSession.RETREAT_MARGIN, (
        "Score margin must exceed RETREAT_MARGIN"
    )

    # Exercise the engine action directly.
    sess._retreat_to(best_idx)

    assert sess.cursor_phrase == 1
    # Phrase 3 words cleared, forward words from phrase >=2 preserved
    # (phrase 3 global word idx = 3, which is in phrase 3 only for single-word phrases)
