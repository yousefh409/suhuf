"""Core CTC scoring engine for Arabic recitation assessment."""

import json
import subprocess
import numpy as np
import torch
import torch.nn.functional as F
from pathlib import Path
from transformers import Wav2Vec2ForCTC, Wav2Vec2FeatureExtractor

from arabic import (
    SUKOON, HARAKAT, SHADDA,
    make_sukoon_variant, generate_i3rab_alternatives,
    generate_tashkeel_alternatives,
    get_final_diacritic, replace_final_diacritic, strip_diacritics,
)


def _lcs_ratio(a, b):
    """Longest common subsequence ratio between two lists."""
    if not a or not b:
        return 0.0
    m, n = len(a), len(b)
    # O(m*n) DP — fine for short phrase word lists
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs_len = dp[m][n]
    return 2.0 * lcs_len / (m + n)


class RecitationEngine:
    def __init__(self, model_path):
        model_path = Path(model_path)
        print(f"Loading model from {model_path}...")

        self.feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(
            str(model_path), local_files_only=True,
        )
        self.model = Wav2Vec2ForCTC.from_pretrained(
            str(model_path), local_files_only=True,
        )
        self.model.eval()

        with open(model_path / "vocab.json") as f:
            self.vocab = json.load(f)
        self.id2char = {v: k for k, v in self.vocab.items()}

        self.blank_id = self.vocab.get("<pad>", 0)
        self.word_delim_id = self.vocab.get("|", 4)

        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device = torch.device("cpu")  # MPS can be flaky with wav2vec2
        else:
            self.device = torch.device("cpu")

        self.model.to(self.device)
        print(f"Model loaded on {self.device}")

    # ------------------------------------------------------------------
    # Audio loading
    # ------------------------------------------------------------------
    def load_audio(self, audio_path, target_sr=16000):
        """Load audio from any format via ffmpeg -> raw float32 16 kHz mono."""
        cmd = [
            "ffmpeg", "-i", str(audio_path),
            "-f", "f32le", "-acodec", "pcm_f32le",
            "-ac", "1", "-ar", str(target_sr),
            "-v", "quiet", "-",
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg error on {audio_path}: {result.stderr.decode()}")
        audio = np.frombuffer(result.stdout, dtype=np.float32)
        return torch.from_numpy(audio.copy())

    # ------------------------------------------------------------------
    # Model inference
    # ------------------------------------------------------------------
    def get_log_probs(self, waveform):
        """Run model -> (T, V) log-probabilities."""
        inputs = self.feature_extractor(
            waveform.numpy(), sampling_rate=16000,
            return_tensors="pt", padding=True,
        )
        input_values = inputs.input_values.to(self.device)
        with torch.no_grad():
            logits = self.model(input_values).logits
        log_probs = F.log_softmax(logits, dim=-1)
        return log_probs.squeeze(0).cpu()  # (T, V)

    # ------------------------------------------------------------------
    # Tokenisation
    # ------------------------------------------------------------------
    def text_to_tokens(self, text):
        """Convert diacritized Arabic text -> list of token IDs."""
        tokens = []
        for ch in text:
            if ch == " ":
                tokens.append(self.word_delim_id)
            elif ch in self.vocab:
                tokens.append(self.vocab[ch])
        return tokens

    def tokens_to_text(self, token_ids):
        """Token IDs -> string."""
        chars = []
        for tid in token_ids:
            ch = self.id2char.get(tid, "")
            if ch == "|":
                chars.append(" ")
            else:
                chars.append(ch)
        return "".join(chars)

    # ------------------------------------------------------------------
    # Greedy decode
    # ------------------------------------------------------------------
    def greedy_decode(self, log_probs):
        """Greedy CTC decoding -> string."""
        pred_ids = log_probs.argmax(dim=-1).tolist()
        collapsed = []
        prev = -1
        for idx in pred_ids:
            if idx != prev:
                if idx != self.blank_id:
                    collapsed.append(idx)
                prev = idx
        return self.tokens_to_text(collapsed)

    # ------------------------------------------------------------------
    # CTC scoring  (uses PyTorch's optimised C++ implementation)
    # ------------------------------------------------------------------
    def ctc_log_prob(self, log_probs, targets):
        """CTC log-probability: log P(targets | log_probs).

        Uses torch.nn.functional.ctc_loss (C++ implementation, fast).

        Args:
            log_probs: (T, V) tensor
            targets: list[int] -- label sequence (no blanks)
        Returns:
            float -- log probability (higher = better match)
        """
        if not isinstance(log_probs, torch.Tensor):
            log_probs = torch.tensor(log_probs, dtype=torch.float32)

        T, V = log_probs.shape
        U = len(targets)

        if U == 0:
            return float(log_probs[:, self.blank_id].sum())
        if T < U:
            return -1e9  # too few frames for the label sequence

        # ctc_loss expects (T, N, C)
        lp = log_probs.unsqueeze(1).float()  # (T, 1, C)
        tgt = torch.tensor([targets], dtype=torch.long)  # (1, U)
        il = torch.tensor([T], dtype=torch.long)
        tl = torch.tensor([U], dtype=torch.long)

        neg_log_prob = F.ctc_loss(
            lp, tgt, il, tl,
            blank=self.blank_id, reduction="none", zero_infinity=True,
        )
        return float(-neg_log_prob.item())

    # ------------------------------------------------------------------
    # CTC Viterbi forced alignment
    # ------------------------------------------------------------------
    def forced_align(self, log_probs, targets):
        """Viterbi CTC alignment.

        Returns list of (target_idx, token_id, start_frame, end_frame).
        """
        if isinstance(log_probs, torch.Tensor):
            lp = log_probs.numpy().astype(np.float64)
        else:
            lp = np.asarray(log_probs, dtype=np.float64)

        T, _V = lp.shape
        U = len(targets)
        blank = self.blank_id

        if U == 0:
            return []

        S = 2 * U + 1
        ext = [0] * S
        for u in range(U):
            ext[2 * u] = blank
            ext[2 * u + 1] = targets[u]
        ext[S - 1] = blank

        NEG_INF = -1e30
        viterbi = np.full((T, S), NEG_INF, dtype=np.float64)
        backptr = np.zeros((T, S), dtype=np.int32)

        viterbi[0, 0] = lp[0, ext[0]]
        if S > 1:
            viterbi[0, 1] = lp[0, ext[1]]

        for t in range(1, T):
            for s in range(S):
                best_val = viterbi[t - 1, s]
                best_s = s

                if s > 0 and viterbi[t - 1, s - 1] > best_val:
                    best_val = viterbi[t - 1, s - 1]
                    best_s = s - 1

                if s > 1 and ext[s] != ext[s - 2] and viterbi[t - 1, s - 2] > best_val:
                    best_val = viterbi[t - 1, s - 2]
                    best_s = s - 2

                viterbi[t, s] = best_val + lp[t, ext[s]]
                backptr[t, s] = best_s

        # Backtrace
        s = S - 1 if viterbi[T - 1, S - 1] >= viterbi[T - 1, S - 2] else S - 2
        path = [0] * T
        path[T - 1] = s
        for t in range(T - 2, -1, -1):
            s = int(backptr[t + 1, s])
            path[t] = s

        # Collect spans
        spans = []
        cur_s = path[0]
        start = 0
        for t in range(1, T):
            if path[t] != cur_s:
                if ext[cur_s] != blank:
                    spans.append((cur_s // 2, ext[cur_s], start, t - 1))
                cur_s = path[t]
                start = t
        if ext[cur_s] != blank:
            spans.append((cur_s // 2, ext[cur_s], start, T - 1))

        return spans

    # ------------------------------------------------------------------
    # Word-boundary extraction from alignment
    # ------------------------------------------------------------------
    def word_boundaries_from_alignment(self, spans, tokens):
        """Group character-level spans into word boundaries.

        Returns list of dicts:
          {word_idx, start_frame, end_frame, char_spans}
        """
        word_idx = 0
        token_to_word = {}
        for i, tok in enumerate(tokens):
            if tok == self.word_delim_id:
                word_idx += 1
            else:
                token_to_word[i] = word_idx

        words = {}
        for target_idx, token_id, sf, ef in spans:
            if token_id == self.word_delim_id:
                continue
            wi = token_to_word.get(target_idx, -1)
            if wi < 0:
                continue
            if wi not in words:
                words[wi] = {"word_idx": wi, "start_frame": sf, "end_frame": ef, "char_spans": []}
            words[wi]["end_frame"] = max(words[wi]["end_frame"], ef)
            words[wi]["start_frame"] = min(words[wi]["start_frame"], sf)
            words[wi]["char_spans"].append((target_idx, token_id, sf, ef))

        return [words[k] for k in sorted(words.keys())]

    # ------------------------------------------------------------------
    # Per-word scoring with hypothesis testing
    # ------------------------------------------------------------------
    def score_hypothesis(self, log_probs_segment, text):
        """Score a text hypothesis against an audio segment.
        Returns normalised log-prob (per frame).
        """
        tokens = self.text_to_tokens(text)
        if not tokens:
            return -999.0
        T = log_probs_segment.shape[0]
        if T < 2:
            return -999.0
        raw = self.ctc_log_prob(log_probs_segment, tokens)
        return raw / T

    def assess_word(self, log_probs_segment, expected_word):
        """Assess a single word: expected text vs alternatives.

        Returns dict with scoring info for error classification.
        """
        expected_score = self.score_hypothesis(log_probs_segment, expected_word)

        # Sukoon variant is always acceptable
        sukoon_word = make_sukoon_variant(expected_word)
        sukoon_score = self.score_hypothesis(log_probs_segment, sukoon_word)

        # If sukoon form scores better, treat as correct (waqf)
        effective_score = max(expected_score, sukoon_score)

        # Decide whether to test i3rab alternatives
        final_mark, _ = get_final_diacritic(expected_word)
        consonants_only = strip_diacritics(expected_word)
        skip_i3rab = False

        # Skip i3rab alternatives for words that already end in sukoon
        # (indeclinable particles like مِنْ, عَنْ, بِقَدْ, etc.)
        if final_mark == SUKOON:
            skip_i3rab = True

        # Skip for very short words (1-2 consonants) — too noisy
        if len(consonants_only) <= 2:
            skip_i3rab = True

        # Quality gate: skip if alignment quality is poor
        # (very low scores indicate bad alignment, not real errors)
        if effective_score < -2.0:
            skip_i3rab = True

        best_alt_name = None
        best_alt_word = None
        best_alt_score = -999.0

        if not skip_i3rab:
            i3rab_alts = generate_i3rab_alternatives(expected_word)
            for name, alt_word in i3rab_alts.items():
                if name == "sukoon":
                    continue  # Already handled
                s = self.score_hypothesis(log_probs_segment, alt_word)
                if s > best_alt_score:
                    best_alt_score = s
                    best_alt_name = name
                    best_alt_word = alt_word

        # Tashkeel (internal vowel) alternatives
        best_tashkeel_name = None
        best_tashkeel_word = None
        best_tashkeel_score = -999.0
        skip_tashkeel = False

        # Same gates as i3rab
        if len(consonants_only) <= 2:
            skip_tashkeel = True
        if effective_score < -2.0:
            skip_tashkeel = True

        if not skip_tashkeel:
            tashkeel_alts = generate_tashkeel_alternatives(expected_word)
            for name, alt_word in tashkeel_alts.items():
                s = self.score_hypothesis(log_probs_segment, alt_word)
                if s > best_tashkeel_score:
                    best_tashkeel_score = s
                    best_tashkeel_name = name
                    best_tashkeel_word = alt_word

        return {
            "expected": expected_word,
            "expected_score": expected_score,
            "sukoon_score": sukoon_score,
            "effective_score": effective_score,
            "best_alt_name": best_alt_name,
            "best_alt_word": best_alt_word,
            "best_alt_score": best_alt_score,
            "skip_i3rab": skip_i3rab,
            "best_tashkeel_name": best_tashkeel_name,
            "best_tashkeel_word": best_tashkeel_word,
            "best_tashkeel_score": best_tashkeel_score,
            "skip_tashkeel": skip_tashkeel,
        }

    # ------------------------------------------------------------------
    # Full phrase scoring
    # ------------------------------------------------------------------
    def score_phrase(self, waveform, phrase_text):
        """Score an entire phrase.

        Returns:
            results: list of per-word assessment dicts
            greedy: greedy decoded text
            alignment_score: overall forced-alignment score (normalised)
        """
        log_probs = self.get_log_probs(waveform)
        greedy = self.greedy_decode(log_probs)

        words = phrase_text.split()
        tokens = self.text_to_tokens(phrase_text)

        # Full-phrase CTC score
        T = log_probs.shape[0]
        full_score = self.ctc_log_prob(log_probs, tokens) / T

        # Forced alignment
        spans = self.forced_align(log_probs, tokens)
        word_bounds = self.word_boundaries_from_alignment(spans, tokens)

        # Assess each word
        results = []
        for wb in word_bounds:
            wi = wb["word_idx"]
            if wi >= len(words):
                continue
            sf, ef = wb["start_frame"], wb["end_frame"]
            # Add small margin around the word for context
            margin = 2
            sf_m = max(0, sf - margin)
            ef_m = min(T - 1, ef + margin)
            segment = log_probs[sf_m : ef_m + 1]

            assessment = self.assess_word(segment, words[wi])
            assessment["word_idx"] = wi
            assessment["word"] = words[wi]
            assessment["start_frame"] = sf
            assessment["end_frame"] = ef
            results.append(assessment)

        return results, greedy, full_score

    # ------------------------------------------------------------------
    # Locate audio within a full passage and score it
    # ------------------------------------------------------------------
    def locate_and_score(self, waveform, full_text, phrases):
        """Locate which part of the passage the audio matches, then score it.

        Computes log_probs once, scores each phrase candidate via CTC,
        picks the best match, then runs word-level scoring on that phrase.

        Args:
            waveform: audio tensor
            full_text: the complete passage text (joined)
            phrases: list of phrase strings (splits of full_text)

        Returns:
            word_results: list of per-word assessments with global word indices
            greedy: greedy decoded text
            matched_phrase_idx: which phrase was matched
            full_score: CTC score of matched phrase
        """
        log_probs = self.get_log_probs(waveform)
        greedy = self.greedy_decode(log_probs)
        T = log_probs.shape[0]

        # Build a map from phrase_idx -> global word offset
        all_words = full_text.split()
        phrase_offsets = []  # (global_start_word_idx, phrase_text)
        offset = 0
        for ph in phrases:
            pw = ph.split()
            phrase_offsets.append((offset, ph))
            offset += len(pw)

        # Match phrase via greedy decode similarity (robust to length bias).
        greedy_stripped = strip_diacritics(greedy).split()

        scored_phrases = []
        for i, (_, ph) in enumerate(phrase_offsets):
            ph_stripped = strip_diacritics(ph).split()
            sim = _lcs_ratio(greedy_stripped, ph_stripped)
            scored_phrases.append((sim, i))
        scored_phrases.sort(reverse=True)  # best first

        # Try candidates in order until one produces a valid alignment
        for best_sim, best_idx in scored_phrases:
            matched_offset, matched_phrase = phrase_offsets[best_idx]
            words = matched_phrase.split()
            tokens = self.text_to_tokens(matched_phrase)

            if not tokens or T < len(tokens):
                continue

            spans = self.forced_align(log_probs, tokens)
            word_bounds = self.word_boundaries_from_alignment(spans, tokens)

            if not word_bounds:
                continue  # alignment failed, try next candidate

            results = []
            for wb in word_bounds:
                wi = wb["word_idx"]
                if wi >= len(words):
                    continue
                sf, ef = wb["start_frame"], wb["end_frame"]
                margin = 2
                sf_m = max(0, sf - margin)
                ef_m = min(T - 1, ef + margin)
                segment = log_probs[sf_m : ef_m + 1]

                assessment = self.assess_word(segment, words[wi])
                assessment["word_idx"] = matched_offset + wi  # global index
                assessment["word"] = words[wi]
                assessment["start_frame"] = sf
                assessment["end_frame"] = ef
                results.append(assessment)

            return results, greedy, best_idx, best_sim

        # Fallback: nothing aligned — return empty
        return [], greedy, 0, 0.0


# ======================================================================
# Streaming session — sliding window + position tracking for long books
# ======================================================================

class StreamingSession:
    """Manages state for one streaming reading session.

    Uses a bounded audio ring buffer (default 15 s) so model inference
    cost is constant regardless of total reading duration.  A position
    cursor tracks which phrase the reader is on and limits phrase
    matching to a small neighborhood.
    """

    SAMPLE_RATE = 16000
    BYTES_PER_SAMPLE = 4  # float32

    def __init__(self, engine, phrases,
                 window_secs=15.0, lookahead=2, lookbehind=1):
        self.engine = engine
        self.phrases = phrases

        # Pre-compute global word offsets per phrase
        self.phrase_word_offsets = []
        self.all_words = []
        offset = 0
        for ph in phrases:
            self.phrase_word_offsets.append(offset)
            words = ph.split()
            self.all_words.extend(words)
            offset += len(words)

        # Pre-compute stripped phrase words for LCS matching
        self._stripped_phrases = [
            strip_diacritics(ph).split() for ph in phrases
        ]

        # Position state
        self.cursor_phrase = 0
        self.scored_words = {}  # global_word_idx -> assessment dict

        # Audio ring buffer (bounded)
        self.window_bytes = int(window_secs * self.SAMPLE_RATE * self.BYTES_PER_SAMPLE)
        self.audio_ring = bytearray()
        self.total_audio_bytes = 0

        # Tuning
        self.lookahead = lookahead
        self.lookbehind = lookbehind
        self.min_match_sim = 0.25
        self.low_match_streak = 0
        self.recovery_threshold = 5  # cycles before recovery scan

    # ------------------------------------------------------------------
    # Audio management
    # ------------------------------------------------------------------

    def append_audio(self, pcm_bytes):
        """Append raw PCM float32 bytes; trim to window size."""
        self.audio_ring.extend(pcm_bytes)
        self.total_audio_bytes += len(pcm_bytes)
        excess = len(self.audio_ring) - self.window_bytes
        if excess > 0:
            del self.audio_ring[:excess]

    @property
    def total_audio_secs(self):
        return self.total_audio_bytes / (self.SAMPLE_RATE * self.BYTES_PER_SAMPLE)

    # ------------------------------------------------------------------
    # Scoring cycle
    # ------------------------------------------------------------------

    def score_cycle(self):
        """Run one scoring cycle on the current audio window.

        Returns the full scored_words dict (global_word_idx -> assessment)
        or None if there isn't enough audio yet.
        """
        if len(self.audio_ring) < self.SAMPLE_RATE * self.BYTES_PER_SAMPLE * 2:
            return None  # need at least 2 s

        audio_np = np.frombuffer(self.audio_ring, dtype=np.float32).copy()
        waveform = torch.from_numpy(audio_np)

        log_probs = self.engine.get_log_probs(waveform)
        greedy = self.engine.greedy_decode(log_probs)
        greedy_stripped = strip_diacritics(greedy).split()
        T = log_probs.shape[0]

        # --- Phase 1: match phrase in cursor neighborhood ---
        candidates = self._get_candidates()
        best_idx, best_sim = self._match_phrase(greedy_stripped, candidates)

        if best_sim < self.min_match_sim:
            self.low_match_streak += 1
            if self.low_match_streak >= self.recovery_threshold:
                rec_idx, rec_sim = self._recovery_scan(greedy_stripped)
                if rec_idx is not None:
                    best_idx, best_sim = rec_idx, rec_sim
                    self.low_match_streak = 0
            if best_sim < self.min_match_sim:
                return self.scored_words  # no good match yet
        else:
            self.low_match_streak = 0

        # --- Phase 2: forced alignment on matched phrase ---
        phrase_text = self.phrases[best_idx]
        tokens = self.engine.text_to_tokens(phrase_text)

        if not tokens or T < len(tokens):
            return self.scored_words

        spans = self.engine.forced_align(log_probs, tokens)
        word_bounds = self.engine.word_boundaries_from_alignment(spans, tokens)
        if not word_bounds:
            return self.scored_words

        # --- Phase 3: per-word assessment ---
        words = phrase_text.split()
        global_offset = self.phrase_word_offsets[best_idx]

        for wb in word_bounds:
            wi = wb["word_idx"]
            if wi >= len(words):
                continue
            sf, ef = wb["start_frame"], wb["end_frame"]
            margin = 2
            segment = log_probs[max(0, sf - margin): min(T, ef + margin + 1)]

            assessment = self.engine.assess_word(segment, words[wi])
            gw = global_offset + wi
            assessment["word_idx"] = gw
            assessment["word"] = words[wi]
            self.scored_words[gw] = assessment

        # --- Phase 4: advance cursor ---
        if best_idx >= self.cursor_phrase:
            self.cursor_phrase = best_idx
        elif best_idx >= self.cursor_phrase - self.lookbehind:
            self.cursor_phrase = best_idx

        return self.scored_words

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_candidates(self):
        """Return phrase indices in the cursor neighborhood."""
        lo = max(0, self.cursor_phrase - self.lookbehind)
        hi = min(len(self.phrases) - 1, self.cursor_phrase + self.lookahead)
        return list(range(lo, hi + 1))

    def _match_phrase(self, greedy_words, candidate_indices):
        """Find best phrase match from candidates using LCS ratio."""
        best_idx = self.cursor_phrase
        best_sim = 0.0
        for idx in candidate_indices:
            sim = _lcs_ratio(greedy_words, self._stripped_phrases[idx])
            if sim > best_sim:
                best_sim = sim
                best_idx = idx
        return best_idx, best_sim

    def _recovery_scan(self, greedy_words):
        """Scan ALL phrases to re-acquire position (expensive, rare)."""
        best_idx = None
        best_sim = 0.0
        for i, stripped in enumerate(self._stripped_phrases):
            sim = _lcs_ratio(greedy_words, stripped)
            if sim > best_sim:
                best_sim = sim
                best_idx = i
        if best_sim >= self.min_match_sim:
            self.cursor_phrase = best_idx
            return best_idx, best_sim
        return None, 0.0
