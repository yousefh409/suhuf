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
    FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN,
    make_sukoon_variant, generate_i3rab_alternatives,
    generate_tashkeel_alternatives,
    get_final_diacritic, strip_diacritics,
)

# Diacritic comparison groups for per-char analysis
_SHORT_VOWELS = frozenset({FATHA, DAMMA, KASRA})
_TANWEEN = frozenset({FATHATAN, DAMMATAN, KASRATAN})
_DIAC_SET = _SHORT_VOWELS | _TANWEEN
_TANWEEN_TO_SHORT = {FATHATAN: FATHA, DAMMATAN: DAMMA, KASRATAN: KASRA}
_DIAC_NAMES = {
    FATHA: "fatha", DAMMA: "damma", KASRA: "kasra",
    FATHATAN: "fathatan", DAMMATAN: "dammatan", KASRATAN: "kasratan",
}


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


def _word_match(a, b):
    """Check if two words match: exact for short words, fuzzy for longer ones."""
    if a == b:
        return True
    # Short words (1-3 chars) must match exactly to avoid false positives
    # on common Arabic function words (و, في, من, أما, لله, etc.)
    if len(a) < 4 or len(b) < 4:
        return False
    return _lcs_ratio(list(a), list(b)) > 0.6


def _phrase_coverage(greedy_words, phrase_words):
    """Fraction of phrase words covered by greedy (order-preserving).

    Unlike _lcs_ratio which penalises extra greedy words, this only asks
    'what fraction of this phrase appeared in the greedy output?'
    Uses safe fuzzy matching (exact for short words, fuzzy for longer ones).
    """
    if not phrase_words or not greedy_words:
        return 0.0
    m, n = len(greedy_words), len(phrase_words)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if _word_match(greedy_words[i - 1], phrase_words[j - 1]):
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n] / n  # normalise by phrase length only


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

        # Lazy-load MixGoP scorer if GMMs exist
        self._mixgop_scorer = None
        gmm_dir = model_path.parent / "gmm"
        if gmm_dir.exists() and (gmm_dir / "gmms.pkl").exists():
            try:
                from scorer import MixGoPScorer
                self._mixgop_scorer = MixGoPScorer(gmm_dir)
                print(f"MixGoP GMMs loaded from {gmm_dir}")
            except Exception as e:
                print(f"Warning: could not load MixGoP GMMs: {e}")

        # Whisper (lazy-loaded on first streaming session)
        self._whisper_model = None
        self._whisper_processor = None

    # ------------------------------------------------------------------
    # Whisper ASR (for position tracking in streaming)
    # ------------------------------------------------------------------

    def _ensure_whisper(self):
        """Download and load Whisper model on first use."""
        if self._whisper_model is not None:
            return
        from transformers import WhisperForConditionalGeneration, WhisperProcessor
        print("Loading Whisper model (first time may download ~500 MB)...")
        self._whisper_processor = WhisperProcessor.from_pretrained(
            "openai/whisper-small"
        )
        self._whisper_model = WhisperForConditionalGeneration.from_pretrained(
            "openai/whisper-small"
        )
        self._whisper_model.eval()
        self._whisper_model.to(torch.device("cpu"))
        print("Whisper model ready.")

    def whisper_transcribe(self, audio_np):
        """Transcribe audio using Whisper. Returns list of word strings.

        Args:
            audio_np: numpy float32 array, 16 kHz mono

        Returns:
            list[str]: word strings (undiacritized Arabic)
        """
        self._ensure_whisper()
        inputs = self._whisper_processor(
            audio_np, sampling_rate=16000, return_tensors="pt",
        )
        input_features = inputs.input_features.to(self._whisper_model.device)

        with torch.no_grad():
            generated = self._whisper_model.generate(
                input_features,
                language="ar",
                task="transcribe",
                return_timestamps=True,
            )

        # Decode to text
        text = self._whisper_processor.batch_decode(
            generated, skip_special_tokens=True,
        )[0].strip()
        if not text:
            return []
        return text.split()

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
    def get_model_outputs(self, waveform, output_hidden_states=False):
        """Run model -> dict with log_probs, logits, and optionally hidden_states.

        Returns dict with keys:
          'log_probs': (T, V) tensor — log-softmax probabilities
          'logits': (T, V) tensor — raw logits before softmax
          'hidden_states': tuple of (T, H) tensors per layer (only if requested)
        """
        inputs = self.feature_extractor(
            waveform.numpy(), sampling_rate=16000,
            return_tensors="pt", padding=True,
        )
        input_values = inputs.input_values.to(self.device)
        with torch.no_grad():
            outputs = self.model(
                input_values,
                output_hidden_states=output_hidden_states,
            )
        logits = outputs.logits.squeeze(0).cpu()  # (T, V)
        log_probs = F.log_softmax(logits, dim=-1)

        result = {'log_probs': log_probs, 'logits': logits}
        if output_hidden_states and outputs.hidden_states is not None:
            result['hidden_states'] = tuple(
                h.squeeze(0).cpu() for h in outputs.hidden_states
            )
        return result

    def get_log_probs(self, waveform):
        """Run model -> (T, V) log-probabilities."""
        return self.get_model_outputs(waveform)['log_probs']

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

        # Skip when reader clearly paused (waqf): sukoon form scored
        # *significantly* better than canonical. Require a margin to
        # overcome CTC's systematic sukoon length bias (~0.05-0.30).
        if sukoon_score > expected_score + 0.25:
            skip_i3rab = True

        # Skip for very short words (1-2 consonants) — too noisy
        if len(consonants_only) <= 2:
            skip_i3rab = True

        # Quality gate: skip only for very poor alignment
        # (relaxed from -2.0 — the model discriminates diacritics well
        # even at moderate eff; per-frame signals handle quality internally)
        if effective_score < -5.0:
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
        best_sukoon_name = None
        best_sukoon_score = -999.0
        skip_tashkeel = False

        # Same gates as i3rab
        if len(consonants_only) <= 2:
            skip_tashkeel = True
        if effective_score < -5.0:
            skip_tashkeel = True

        if not skip_tashkeel:
            tashkeel_alts = generate_tashkeel_alternatives(expected_word)
            for name, alt_word in tashkeel_alts.items():
                s = self.score_hypothesis(log_probs_segment, alt_word)
                # Separate sukoon alternatives (CTC has length bias toward sukoon)
                if 'sukoon' in name:
                    if s > best_sukoon_score:
                        best_sukoon_score = s
                        best_sukoon_name = name
                else:
                    if s > best_tashkeel_score:
                        best_tashkeel_score = s
                        best_tashkeel_name = name
                        best_tashkeel_word = alt_word

        # Per-diacritic CTC scoring for shadda positions
        # (CTC hypothesis scoring skips shadda'd consonants, but we can
        # score individual diacritic swaps at those positions for targeted detection)
        best_shadda_name = None
        best_shadda_score = -999.0
        if not skip_tashkeel:
            tokens = self.text_to_tokens(expected_word)
            for ti, tok in enumerate(tokens):
                ch = self.id2char.get(tok, '')
                if ch not in _SHORT_VOWELS:
                    continue
                # Check if this vowel is adjacent to a shadda
                # Arabic token order: consonant → vowel → shadda (or consonant → shadda → vowel)
                # So we must check BOTH directions from the vowel
                near_shadda = False
                # Look backward
                for tj in range(ti - 1, max(ti - 3, -1), -1):
                    pch = self.id2char.get(tokens[tj], '')
                    if pch == SHADDA:
                        near_shadda = True
                        break
                    if pch not in {FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SUKOON}:
                        break
                # Look forward
                if not near_shadda:
                    for tj in range(ti + 1, min(ti + 3, len(tokens))):
                        pch = self.id2char.get(tokens[tj], '')
                        if pch == SHADDA:
                            near_shadda = True
                            break
                        if pch not in {FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SUKOON}:
                            break
                if not near_shadda:
                    continue

                # Score swaps at this shadda position
                for alt_ch in _SHORT_VOWELS:
                    if alt_ch == ch:
                        continue
                    alt_id = self.vocab.get(alt_ch)
                    if alt_id is None:
                        continue
                    alt_tokens = list(tokens)
                    alt_tokens[ti] = alt_id
                    T_seg = log_probs_segment.shape[0]
                    if T_seg < len(alt_tokens):
                        continue
                    alt_score = self.ctc_log_prob(log_probs_segment, alt_tokens) / T_seg
                    if alt_score > best_shadda_score:
                        best_shadda_score = alt_score
                        vowel_name = _DIAC_NAMES.get(alt_ch, '?')
                        # Find consonant char for naming
                        for tj in range(ti - 1, -1, -1):
                            pch = self.id2char.get(tokens[tj], '')
                            if pch not in {FATHA, DAMMA, KASRA, FATHATAN, DAMMATAN, KASRATAN, SUKOON, SHADDA}:
                                best_shadda_name = f"shadda_{vowel_name}_on_{pch}"
                                break

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
            "best_sukoon_name": best_sukoon_name,
            "best_sukoon_score": best_sukoon_score,
            "skip_tashkeel": skip_tashkeel,
            "best_shadda_name": best_shadda_name,
            "best_shadda_score": best_shadda_score,
        }

    def per_char_worst_delta(self, log_probs, char_spans, logits=None):
        """Per-character diacritic confidence: worst delta across a word.

        Uses peak-frame selection (CTC models are peaky — discriminative
        info is concentrated in 1-2 frames). Combines peak-frame and
        averaged margins for robustness.

        For each diacritic in the forced-aligned char_spans, compares the
        model's log-prob for the expected diacritic vs the best alternative
        in the same group ({fatha,damma,kasra} or {fathatan,dammatan,kasratan}).

        Returns dict:
          delta: most negative delta (999.0 = no diacritics found)
          expected: name of the expected diacritic at worst position
          heard: name of the best alternative diacritic
        """
        T = log_probs.shape[0]
        worst = 999.0
        worst_expected = None
        worst_heard = None

        for _target_idx, token_id, sf, ef in char_spans:
            char = self.id2char.get(token_id, '')
            if char not in _DIAC_SET:
                continue

            # Determine comparison group + all IDs to check
            if char in _SHORT_VOWELS:
                group = _SHORT_VOWELS
            elif char in _TANWEEN:
                group = _TANWEEN
            else:
                continue

            group_ids = []
            for g_ch in group:
                gid = self.vocab.get(g_ch)
                if gid is not None:
                    group_ids.append((g_ch, gid))

            # Also include tanween<->short vowel comparison
            extra_ids = []
            if char in _TANWEEN_TO_SHORT:
                short_ch = _TANWEEN_TO_SHORT[char]
                sid = self.vocab.get(short_ch)
                if sid is not None:
                    extra_ids.append((short_ch, sid))

            all_compare = [(ch, gid) for ch, gid in group_ids if ch != char] + extra_ids
            if not all_compare:
                continue

            # Widen window: 2 context frames on each side
            context = 2
            frame_start = max(0, sf - context)
            frame_end = min(ef + 1 + context, T)
            if frame_start >= frame_end:
                continue

            # Peak-frame selection: find the frame with maximum total
            # diacritic energy (sum of log-probs for all diacritics in group).
            # CTC models are "peaky" — the discriminative information is
            # concentrated in 1-2 frames rather than spread evenly.
            all_ids = [gid for _, gid in group_ids] + [gid for _, gid in extra_ids]
            frame_range = range(frame_start, frame_end)
            peak_frame = max(
                frame_range,
                key=lambda t: sum(float(log_probs[t, gid]) for gid in all_ids)
            )

            # Also compute weighted average as secondary signal
            frame_indices = list(frame_range)
            weights = np.array([
                1.0 if sf <= f <= ef else 0.5
                for f in frame_indices
            ])
            weights /= weights.sum()
            avg = (log_probs[frame_indices].numpy() * weights[:, None]).sum(axis=0)

            # Use the BETTER of peak-frame margin and averaged margin
            # Peak is more sensitive, average is more stable
            exp_peak = float(log_probs[peak_frame, token_id])
            exp_avg = float(avg[token_id])

            best_alt_peak = -999.0
            best_alt_avg = -999.0
            best_alt_char_peak = None
            best_alt_char_avg = None

            for alt_ch, aid in all_compare:
                alt_peak = float(log_probs[peak_frame, aid])
                alt_avg_val = float(avg[aid])
                if alt_peak > best_alt_peak:
                    best_alt_peak = alt_peak
                    best_alt_char_peak = alt_ch
                if alt_avg_val > best_alt_avg:
                    best_alt_avg = alt_avg_val
                    best_alt_char_avg = alt_ch

            # Compute both deltas and use the more negative one (worst case)
            d_peak = exp_peak - best_alt_peak if best_alt_peak > -900 else 999.0
            d_avg = exp_avg - best_alt_avg if best_alt_avg > -900 else 999.0
            d = min(d_peak, d_avg)
            best_alt_char = best_alt_char_peak if d_peak <= d_avg else best_alt_char_avg

            if d < worst:
                worst = d
                worst_expected = _DIAC_NAMES.get(char)
                worst_heard = _DIAC_NAMES.get(best_alt_char)

        return {"delta": worst, "expected": worst_expected, "heard": worst_heard}

    def frame_scan_diacritics(self, log_probs, word, sf, ef, T):
        """Alignment-robust diacritic evidence scanning.

        Unlike per_char_worst_delta which relies on forced-aligned char_spans
        (inaccurate at low eff), this scans a wide frame region for diacritic
        evidence. For each diacritic in the word, finds the frame in the
        region that most strongly supports (or contradicts) the expected
        diacritic vs alternatives.

        Returns dict with fs_worst_delta (most negative = most suspicious).
        """
        tokens = self.text_to_tokens(word)
        if not tokens:
            return {"fs_worst_delta": 999.0, "fs_expected": None, "fs_heard": None}

        # Wide scan region: word frames ± 15 frames (~0.3s at 50fps)
        margin = 15
        scan_start = max(0, sf - margin)
        scan_end = min(T, ef + margin + 1)

        if scan_start >= scan_end:
            return {"fs_worst_delta": 999.0, "fs_expected": None, "fs_heard": None}

        worst_delta = 999.0
        worst_expected = None
        worst_heard = None

        # Track which diacritic types we've seen to avoid double-counting
        # the same diacritic type at multiple positions
        seen_types = {}  # char -> best delta so far

        for tok in tokens:
            char = self.id2char.get(tok, '')
            if char not in _DIAC_SET:
                continue

            if char in _SHORT_VOWELS:
                group = _SHORT_VOWELS
            elif char in _TANWEEN:
                group = _TANWEEN
            else:
                continue

            all_compare = []
            for alt_ch in group:
                if alt_ch == char:
                    continue
                alt_id = self.vocab.get(alt_ch)
                if alt_id is not None:
                    all_compare.append((alt_ch, alt_id))

            if char in _TANWEEN_TO_SHORT:
                short_ch = _TANWEEN_TO_SHORT[char]
                sid = self.vocab.get(short_ch)
                if sid is not None:
                    all_compare.append((short_ch, sid))

            if not all_compare:
                continue

            # Scan all frames: find the best evidence for correct diacritic
            best_frame_delta = -999.0
            best_frame_alt_char = None

            for t in range(scan_start, scan_end):
                exp_prob = float(log_probs[t, tok])
                # Find best alternative at this frame
                best_alt_prob = -999.0
                best_alt_ch = None
                for alt_ch, aid in all_compare:
                    ap = float(log_probs[t, aid])
                    if ap > best_alt_prob:
                        best_alt_prob = ap
                        best_alt_ch = alt_ch

                delta = exp_prob - best_alt_prob
                if delta > best_frame_delta:
                    best_frame_delta = delta
                    best_frame_alt_char = best_alt_ch

            # For same diacritic type appearing multiple times, keep worst
            if char in seen_types:
                if best_frame_delta >= seen_types[char]:
                    continue  # this position is better, keep the worse one
            seen_types[char] = best_frame_delta

            if best_frame_delta < worst_delta:
                worst_delta = best_frame_delta
                worst_expected = _DIAC_NAMES.get(char)
                worst_heard = _DIAC_NAMES.get(best_frame_alt_char)

        return {"fs_worst_delta": worst_delta,
                "fs_expected": worst_expected, "fs_heard": worst_heard}

    def sf_gop_diacritics(self, log_probs_segment, expected_word):
        """Segmentation-Free GOP: per-diacritic posterior probability.

        For each diacritic position, computes the proper posterior via
        logsumexp over all alternatives: P(correct | audio) =
        exp(CTC(correct)) / sum(exp(CTC(alt)) for all alt).

        Uses the log-posterior as the score (closer to 0 = more confident,
        closer to -inf = wrong diacritic). The worst (most negative)
        posterior across all positions is reported.

        Returns dict:
          sf_worst_delta: worst log-posterior (999.0 = no diacritics)
          sf_worst_expected: diacritic name at worst position
          sf_worst_heard: best alternative diacritic name
        """
        tokens = self.text_to_tokens(expected_word)
        if not tokens:
            return {"sf_worst_delta": 999.0, "sf_worst_expected": None,
                    "sf_worst_heard": None}

        T = log_probs_segment.shape[0]
        if T < len(tokens):
            return {"sf_worst_delta": 999.0, "sf_worst_expected": None,
                    "sf_worst_heard": None}

        canonical_score = self.ctc_log_prob(log_probs_segment, tokens)

        worst_delta = 999.0
        worst_expected = None
        worst_heard = None

        for ti, tok in enumerate(tokens):
            char = self.id2char.get(tok, '')
            if char not in _DIAC_SET:
                continue

            # Determine comparison group
            if char in _SHORT_VOWELS:
                group = _SHORT_VOWELS
            elif char in _TANWEEN:
                group = _TANWEEN
            else:
                continue

            # Score all alternatives at this position
            all_scores = [canonical_score]  # canonical is first
            all_chars = [char]
            best_alt_score = -1e9
            best_alt_char = None

            for alt_ch in group:
                if alt_ch == char:
                    continue
                alt_id = self.vocab.get(alt_ch)
                if alt_id is None:
                    continue
                perturbed = list(tokens)
                perturbed[ti] = alt_id
                if T < len(perturbed):
                    continue
                s = self.ctc_log_prob(log_probs_segment, perturbed)
                all_scores.append(s)
                all_chars.append(alt_ch)
                if s > best_alt_score:
                    best_alt_score = s
                    best_alt_char = alt_ch

            # Also compare tanween vs corresponding short vowel
            if char in _TANWEEN_TO_SHORT:
                short_ch = _TANWEEN_TO_SHORT[char]
                short_id = self.vocab.get(short_ch)
                if short_id is not None:
                    perturbed = list(tokens)
                    perturbed[ti] = short_id
                    if T >= len(perturbed):
                        s = self.ctc_log_prob(log_probs_segment, perturbed)
                        all_scores.append(s)
                        all_chars.append(short_ch)
                        if s > best_alt_score:
                            best_alt_score = s
                            best_alt_char = short_ch

            if len(all_scores) < 2:
                continue

            # Compute log-posterior: log(P(canonical | audio)) =
            # canonical_score - logsumexp(all_scores)
            # This is always <= 0; closer to 0 = more confident
            log_denom = float(torch.logsumexp(
                torch.tensor(all_scores, dtype=torch.float64), dim=0))
            log_posterior = canonical_score - log_denom

            # Also compute simple delta (canonical - best_alt) for
            # backward compatibility with threshold logic
            simple_delta = canonical_score - best_alt_score if best_alt_score > -1e8 else 999.0

            # Use whichever is more informative (more negative = worse)
            delta = min(simple_delta, log_posterior)

            if delta < worst_delta:
                worst_delta = delta
                worst_expected = _DIAC_NAMES.get(char)
                worst_heard = _DIAC_NAMES.get(best_alt_char)

        return {"sf_worst_delta": worst_delta, "sf_worst_expected": worst_expected,
                "sf_worst_heard": worst_heard}

    def mixgop_diacritics(self, hidden_states, char_spans):
        """MixGoP scoring: GMM log-likelihood margin for each diacritic.

        Uses pre-trained per-diacritic GMMs on intermediate SSL layer features.
        Returns dict:
          mg_worst_margin: most negative margin (999.0 = no diacritics / no GMMs)
          mg_worst_expected: diacritic name at worst position
          mg_worst_heard: best alternative diacritic name
        """
        default = {"mg_worst_margin": 999.0, "mg_worst_expected": None,
                    "mg_worst_heard": None}

        if self._mixgop_scorer is None or not self._mixgop_scorer.gmms:
            return default

        from scorer import MixGoPScorer

        worst = 999.0
        worst_expected = None
        worst_heard = None

        for _target_idx, token_id, sf, ef in char_spans:
            char = self.id2char.get(token_id, '')
            if char not in _DIAC_SET:
                continue

            feat = MixGoPScorer.extract_feature(hidden_states, (sf, ef))
            if feat is None:
                continue

            result = self._mixgop_scorer.score_all_alternatives(feat, char)
            if result is None:
                continue

            margin = result["margin"]
            if margin < worst:
                worst = margin
                worst_expected = _DIAC_NAMES.get(char)
                worst_heard = _DIAC_NAMES.get(result["best_alt_char"])

        return {"mg_worst_margin": worst, "mg_worst_expected": worst_expected,
                "mg_worst_heard": worst_heard}

    def greedy_diacritic_mismatch(self, greedy_segment, expected_word):
        """Compare internal diacritics between greedy decode and expected word.

        Parses both into (consonant, vowel, has_shadda) triples, aligns
        consonants via LCS, and compares vowels at matched positions.
        Excludes the last consonant (i3rab) and shadda'd consonants.

        Returns dict:
          count: number of mismatched internal diacritics
          expected: diacritic name at first mismatch (or None)
          heard: diacritic name of what greedy showed (or None)
        """
        def _parse_pairs(word):
            """Parse into list of (consonant, short_vowel_or_None, has_shadda)."""
            chars = list(word)
            pairs = []
            i = 0
            while i < len(chars):
                ch = chars[i]
                if ch in HARAKAT:
                    i += 1
                    continue
                vowel = None
                has_shadda = False
                i += 1
                while i < len(chars) and chars[i] in HARAKAT:
                    d = chars[i]
                    if d == SHADDA:
                        has_shadda = True
                    elif d in _SHORT_VOWELS:
                        vowel = d
                    elif d in _TANWEEN:
                        vowel = _TANWEEN_TO_SHORT.get(d, d)
                    i += 1
                pairs.append((ch, vowel, has_shadda))
            return pairs

        exp_pairs = _parse_pairs(expected_word)
        gre_pairs = _parse_pairs(greedy_segment)

        if not exp_pairs:
            return {"count": 0, "expected": None, "heard": None,
                    "final_mismatch": False, "consonant_match": 1.0}

        # Exclude last consonant (i3rab position)
        exp_internal = exp_pairs[:-1]
        if not exp_internal:
            return {"count": 0, "expected": None, "heard": None,
                    "final_mismatch": False, "consonant_match": 1.0}

        # LCS alignment on consonant characters
        exp_cons = [p[0] for p in exp_internal]
        gre_cons = [p[0] for p in gre_pairs]
        n, m = len(exp_cons), len(gre_cons)

        # Use ALL consonants (including final) for consonant match ratio
        all_exp_cons = [p[0] for p in exp_pairs]
        all_gre_cons = [p[0] for p in gre_pairs]
        consonant_match = _lcs_ratio(all_exp_cons, all_gre_cons)

        if _lcs_ratio(exp_cons, gre_cons) < 0.4:
            return {"count": 0, "expected": None, "heard": None,
                    "final_mismatch": False, "consonant_match": consonant_match}

        dp = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                if exp_cons[i - 1] == gre_cons[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

        matched = []
        i, j = n, m
        while i > 0 and j > 0:
            if exp_cons[i - 1] == gre_cons[j - 1]:
                matched.append((i - 1, j - 1))
                i -= 1
                j -= 1
            elif dp[i - 1][j] >= dp[i][j - 1]:
                i -= 1
            else:
                j -= 1
        matched.reverse()

        count = 0
        first_exp = None
        first_heard = None
        checked = 0  # track how many vowel positions we've compared
        for ei, gi in matched:
            _cons, exp_vowel, exp_shadda = exp_internal[ei]
            _gcons, gre_vowel, _gshadda = gre_pairs[gi]

            if exp_shadda:
                continue  # shadda'd consonants are acoustically ambiguous
            if exp_vowel is None:
                continue
            if gre_vowel is None:
                continue  # greedy didn't produce a vowel here — skip

            checked += 1
            # Skip first vowel position — greedy decode is unreliable there
            # due to connected speech context from previous word (wasla, etc.)
            if checked == 1:
                continue

            if exp_vowel == gre_vowel:
                continue

            count += 1
            if first_exp is None:
                first_exp = _DIAC_NAMES.get(exp_vowel)
                first_heard = _DIAC_NAMES.get(gre_vowel)

        # Also check final consonant separately (for i3rab detection)
        final_mismatch = False
        if len(exp_pairs) >= 1 and len(gre_pairs) >= 1:
            _fc, exp_final_v, _fsh = exp_pairs[-1]
            # Find matching consonant in greedy for the final position
            if exp_pairs[-1][0] == gre_pairs[-1][0] and exp_final_v is not None:
                gre_final_v = gre_pairs[-1][1]
                if gre_final_v is not None and gre_final_v != exp_final_v:
                    final_mismatch = True

        return {
            "count": count, "expected": first_exp, "heard": first_heard,
            "final_mismatch": final_mismatch, "consonant_match": consonant_match,
        }

    # ------------------------------------------------------------------
    # Full phrase scoring
    # ------------------------------------------------------------------
    def _enrich_assessment(self, assessment, word, log_probs,
                           char_spans, sf, ef, T,
                           hidden_states=None, logits=None):
        """Add all per-word scoring signals to an assessment dict."""
        segment_lp = log_probs[max(0, sf - 2): min(T, ef + 3)]

        # Per-char worst delta — use raw logits for better discrimination
        pc = self.per_char_worst_delta(log_probs, char_spans, logits=logits)
        assessment["pc_worst_delta"] = pc["delta"]
        assessment["pc_expected_diac"] = pc["expected"]
        assessment["pc_heard_diac"] = pc["heard"]

        # Greedy decode + diacritic mismatch (existing)
        greedy_seg = self.greedy_decode(log_probs[sf:ef + 1])
        assessment["greedy_segment"] = greedy_seg
        gdm = self.greedy_diacritic_mismatch(greedy_seg, word)
        assessment["greedy_diac_mismatches"] = gdm["count"]
        assessment["greedy_diac_expected"] = gdm["expected"]
        assessment["greedy_diac_heard"] = gdm["heard"]
        assessment["greedy_final_mismatch"] = gdm["final_mismatch"]
        assessment["greedy_consonant_match"] = gdm["consonant_match"]

        # Segmentation-Free GOP (new)
        sf_gop = self.sf_gop_diacritics(segment_lp, word)
        assessment["sf_worst_delta"] = sf_gop["sf_worst_delta"]
        assessment["sf_worst_expected"] = sf_gop["sf_worst_expected"]
        assessment["sf_worst_heard"] = sf_gop["sf_worst_heard"]

        # MixGoP (new — only if hidden states available)
        if hidden_states is not None:
            mg = self.mixgop_diacritics(hidden_states, char_spans)
            assessment["mg_worst_margin"] = mg["mg_worst_margin"]
            assessment["mg_worst_expected"] = mg["mg_worst_expected"]
            assessment["mg_worst_heard"] = mg["mg_worst_heard"]

        # Frame scan diacritics (alignment-robust)
        fs = self.frame_scan_diacritics(log_probs, word, sf, ef, T)
        assessment["fs_worst_delta"] = fs["fs_worst_delta"]
        assessment["fs_expected"] = fs["fs_expected"]
        assessment["fs_heard"] = fs["fs_heard"]

    def _phrase_differential(self, log_probs, phrase_text, words, T,
                              word_bounds=None):
        """Score each word's alternatives at phrase level.

        Instead of scoring alternatives against an isolated word segment,
        this scores the FULL PHRASE with each word's alternative swapped in.
        The raw CTC delta is normalized by the word's frame count (not the
        phrase's frame count) so the signal is comparable to per-word scores.

        Returns dict mapping word_idx -> {pd_i3rab_delta, pd_tashkeel_delta, ...}
        """
        phrase_tokens = self.text_to_tokens(phrase_text)
        base_score = self.ctc_log_prob(log_probs, phrase_tokens)

        # Build word_idx -> frame_count map for normalization
        word_frames = {}
        if word_bounds:
            for wb in word_bounds:
                wi = wb["word_idx"]
                word_frames[wi] = max(1, wb["end_frame"] - wb["start_frame"] + 1)

        results = {}
        for wi, word in enumerate(words):
            consonants = strip_diacritics(word)
            pd = {
                "pd_i3rab_delta": 0.0,
                "pd_i3rab_name": None,
                "pd_tashkeel_delta": 0.0,
                "pd_tashkeel_name": None,
            }

            if len(consonants) <= 2:
                results[wi] = pd
                continue

            # Normalize delta by word frame count (or T/n_words as fallback)
            wf = word_frames.get(wi, max(1, T // max(1, len(words))))

            # I3rab alternatives
            final_mark, _ = get_final_diacritic(word)
            if final_mark != SUKOON:
                i3rab_alts = generate_i3rab_alternatives(word)
                for name, alt_word in i3rab_alts.items():
                    if name == "sukoon":
                        continue
                    alt_words = list(words)
                    alt_words[wi] = alt_word
                    alt_text = " ".join(alt_words)
                    alt_tokens = self.text_to_tokens(alt_text)
                    if T < len(alt_tokens):
                        continue
                    alt_s = self.ctc_log_prob(log_probs, alt_tokens)
                    delta = (alt_s - base_score) / wf
                    if delta > pd["pd_i3rab_delta"]:
                        pd["pd_i3rab_delta"] = delta
                        pd["pd_i3rab_name"] = name

            # Tashkeel alternatives
            tashkeel_alts = generate_tashkeel_alternatives(word)
            for name, alt_word in tashkeel_alts.items():
                if 'sukoon' in name:
                    continue
                alt_words = list(words)
                alt_words[wi] = alt_word
                alt_text = " ".join(alt_words)
                alt_tokens = self.text_to_tokens(alt_text)
                if T < len(alt_tokens):
                    continue
                alt_s = self.ctc_log_prob(log_probs, alt_tokens)
                delta = (alt_s - base_score) / wf
                if delta > pd["pd_tashkeel_delta"]:
                    pd["pd_tashkeel_delta"] = delta
                    pd["pd_tashkeel_name"] = name

            results[wi] = pd

        return results

    def _local_pd(self, log_probs, words, word_bounds, T):
        """Local phrase-differential for low-eff words.

        For each word with eff < -1.5, builds a 3-word sub-phrase and
        computes pd within that local context. The shorter CTC lattice
        is more sensitive to diacritic changes than the full phrase.

        Returns dict mapping word_idx -> {local_pd_i3rab, local_pd_tashkeel}
        """
        results = {}
        n = len(word_bounds)
        for i, wb in enumerate(word_bounds):
            wi = wb["word_idx"]
            if wi >= len(words):
                continue

            sf, ef = wb["start_frame"], wb["end_frame"]
            seg = log_probs[max(0, sf - 2) : min(T, ef + 3)]
            quick_eff = self.score_hypothesis(seg, words[wi])
            if quick_eff > -1.5:
                continue

            consonants = strip_diacritics(words[wi])
            if len(consonants) <= 2:
                continue

            # Build 3-word sub-phrase with generous audio window
            prev_idx = i - 1 if i > 0 else None
            next_idx = i + 1 if i < n - 1 else None

            win_sf = sf
            win_ef = ef
            sub_words = []
            target_idx_in_sub = 0

            if prev_idx is not None:
                win_sf = min(win_sf, word_bounds[prev_idx]["start_frame"])
                sub_words.append(words[word_bounds[prev_idx]["word_idx"]])
                target_idx_in_sub = 1

            sub_words.append(words[wi])

            if next_idx is not None:
                win_ef = max(win_ef, word_bounds[next_idx]["end_frame"])
                sub_words.append(words[word_bounds[next_idx]["word_idx"]])

            margin = 15
            win_sf = max(0, win_sf - margin)
            win_ef = min(T - 1, win_ef + margin)

            sub_text = " ".join(sub_words)
            sub_tokens = self.text_to_tokens(sub_text)
            win_lp = log_probs[win_sf : win_ef + 1]
            T_win = win_lp.shape[0]

            if T_win < len(sub_tokens) + 2:
                continue

            base_score = self.ctc_log_prob(win_lp, sub_tokens)
            wf = max(1, ef - sf + 1)

            lpd = {"local_pd_i3rab": 0.0, "local_pd_tashkeel": 0.0}

            # I3rab alternatives
            word = words[wi]
            final_mark, _ = get_final_diacritic(word)
            if final_mark != SUKOON:
                from arabic import generate_i3rab_alternatives
                for name, alt_word in generate_i3rab_alternatives(word).items():
                    if name == "sukoon":
                        continue
                    alt_sub = list(sub_words)
                    alt_sub[target_idx_in_sub] = alt_word
                    alt_tokens = self.text_to_tokens(" ".join(alt_sub))
                    if T_win < len(alt_tokens):
                        continue
                    alt_s = self.ctc_log_prob(win_lp, alt_tokens)
                    delta = (alt_s - base_score) / wf
                    if delta > lpd["local_pd_i3rab"]:
                        lpd["local_pd_i3rab"] = delta

            # Tashkeel alternatives
            from arabic import generate_tashkeel_alternatives
            for name, alt_word in generate_tashkeel_alternatives(word).items():
                if 'sukoon' in name:
                    continue
                alt_sub = list(sub_words)
                alt_sub[target_idx_in_sub] = alt_word
                alt_tokens = self.text_to_tokens(" ".join(alt_sub))
                if T_win < len(alt_tokens):
                    continue
                alt_s = self.ctc_log_prob(win_lp, alt_tokens)
                delta = (alt_s - base_score) / wf
                if delta > lpd["local_pd_tashkeel"]:
                    lpd["local_pd_tashkeel"] = delta

            results[wi] = lpd

        return results

    def _windowed_rescore(self, log_probs, words, word_bounds, T,
                          hidden_states=None, logits=None):
        """Re-score low-eff words using local 3-word context alignment.

        For words with eff < -1.5, the full-phrase CTC alignment may assign
        wrong frames. Re-aligning a local 3-word sub-phrase on a wider
        window gives the CTC model a simpler lattice, often producing
        better frame boundaries and hence better diacritic discrimination.

        Returns dict mapping word_idx -> updated assessment (or None if
        re-scoring didn't improve eff).
        """
        results = {}
        n = len(word_bounds)
        for i, wb in enumerate(word_bounds):
            wi = wb["word_idx"]
            if wi >= len(words):
                continue

            # Only re-score low-eff words
            sf, ef = wb["start_frame"], wb["end_frame"]
            seg = log_probs[max(0, sf - 2) : min(T, ef + 3)]
            quick_eff = self.score_hypothesis(seg, words[wi])
            if quick_eff > -1.5:
                continue

            # Build 3-word sub-phrase (prev, target, next)
            prev_idx = i - 1 if i > 0 else None
            next_idx = i + 1 if i < n - 1 else None

            # Determine audio window from neighbor bounds with generous margin
            win_sf = sf
            win_ef = ef
            sub_words = []
            target_word_idx_in_sub = 0

            if prev_idx is not None:
                win_sf = min(win_sf, word_bounds[prev_idx]["start_frame"])
                sub_words.append(words[word_bounds[prev_idx]["word_idx"]])
                target_word_idx_in_sub = 1

            sub_words.append(words[wi])

            if next_idx is not None:
                win_ef = max(win_ef, word_bounds[next_idx]["end_frame"])
                sub_words.append(words[word_bounds[next_idx]["word_idx"]])

            # Add generous margin (15 frames ~= 0.3s at 50fps)
            margin = 15
            win_sf = max(0, win_sf - margin)
            win_ef = min(T - 1, win_ef + margin)

            sub_text = " ".join(sub_words)
            sub_tokens = self.text_to_tokens(sub_text)
            win_lp = log_probs[win_sf : win_ef + 1]

            if win_lp.shape[0] < len(sub_tokens) + 2:
                continue

            # Re-align the sub-phrase locally
            local_spans = self.forced_align(win_lp, sub_tokens)
            local_bounds = self.word_boundaries_from_alignment(
                local_spans, sub_tokens)

            # Find the target word in local bounds
            target_wb = None
            for lb in local_bounds:
                if lb["word_idx"] == target_word_idx_in_sub:
                    target_wb = lb
                    break

            if target_wb is None:
                continue

            # Extract the target word's locally-aligned segment
            local_sf = target_wb["start_frame"]
            local_ef = target_wb["end_frame"]
            m2 = 2
            seg_sf = max(0, local_sf - m2)
            seg_ef = min(win_lp.shape[0] - 1, local_ef + m2)
            local_seg = win_lp[seg_sf : seg_ef + 1]

            if local_seg.shape[0] < 3:
                continue

            # Re-score
            new_assessment = self.assess_word(local_seg, words[wi])

            # Only use re-scored result if eff improved
            if new_assessment["effective_score"] <= quick_eff:
                continue

            # Translate local frame indices back to global
            global_sf = win_sf + local_sf
            global_ef = win_sf + local_ef

            # Translate local char_spans to global frame coordinates
            global_char_spans = [
                (tidx, tok_id, csf + win_sf, cef + win_sf)
                for tidx, tok_id, csf, cef in target_wb["char_spans"]
            ]

            # Re-compute enrichment with global coords
            self._enrich_assessment(
                new_assessment, words[wi], log_probs,
                global_char_spans, global_sf, global_ef, T,
                hidden_states, logits=logits)
            new_assessment["word_idx"] = wi
            new_assessment["word"] = words[wi]
            new_assessment["start_frame"] = global_sf
            new_assessment["end_frame"] = global_ef
            new_assessment["frame_count"] = global_ef - global_sf + 1
            new_assessment["rescored"] = True

            results[wi] = new_assessment

        return results

    def score_phrase(self, waveform, phrase_text, compute_pd=True, model_out=None):
        """Score an entire phrase.

        Args:
            waveform: audio tensor
            phrase_text: diacritized Arabic text
            compute_pd: whether to compute phrase-differential signals
                (expensive for long texts, skip for alignment-only passes)
            model_out: optional precomputed get_model_outputs() result for this
                waveform. When the same audio is scored against many texts (e.g.
                eval mutations), pass it to skip the repeated model forward pass.
                Must include hidden_states. Results are identical to recomputing.

        Returns:
            results: list of per-word assessment dicts
            greedy: greedy decoded text
            alignment_score: overall forced-alignment score (normalised)
        """
        if model_out is None:
            model_out = self.get_model_outputs(waveform, output_hidden_states=True)
        log_probs = model_out['log_probs']
        logits = model_out['logits']
        hidden_states = model_out.get('hidden_states')
        greedy = self.greedy_decode(log_probs)

        words = phrase_text.split()
        tokens = self.text_to_tokens(phrase_text)

        # Full-phrase CTC score
        T = log_probs.shape[0]
        full_score = self.ctc_log_prob(log_probs, tokens) / T

        # Forced alignment
        spans = self.forced_align(log_probs, tokens)
        word_bounds = self.word_boundaries_from_alignment(spans, tokens)

        # Phrase-differential scoring (full-phrase context)
        # Skip for very long texts (alignment-only passes)
        pd_results = None
        if compute_pd and len(words) <= 30:
            pd_results = self._phrase_differential(
                log_probs, phrase_text, words, T, word_bounds)

        # Assess each word
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
            self._enrich_assessment(
                assessment, words[wi], log_probs,
                wb["char_spans"], sf, ef, T,
                hidden_states, logits=logits)
            assessment["word_idx"] = wi
            assessment["word"] = words[wi]
            assessment["start_frame"] = sf
            assessment["end_frame"] = ef
            assessment["frame_count"] = ef - sf + 1

            # Add phrase-differential signals
            if pd_results and wi in pd_results:
                assessment.update(pd_results[wi])

            results.append(assessment)

        # Windowed re-scoring for low-eff words:
        # Don't replace assessments (re-scored diacritic signals have high FP).
        # Instead, add rescored_eff as an additional signal — only used for
        # gating in classify_words when the original eff is too low.
        if compute_pd:
            rescored = self._windowed_rescore(
                log_probs, words, word_bounds, T,
                hidden_states, logits)
            for i, r in enumerate(results):
                wi = r["word_idx"]
                if wi in rescored:
                    rs = rescored[wi]
                    r["rescored_eff"] = rs["effective_score"]
                    r["rescored_i3rab_delta"] = (
                        rs["best_alt_score"] - rs["effective_score"]
                        if rs["best_alt_score"] > -900 else 0.0)
                    r["rescored_tash_delta"] = (
                        rs["best_tashkeel_score"] - rs["effective_score"]
                        if rs["best_tashkeel_score"] > -900 else 0.0)
                    r["rescored_gfm"] = rs.get("greedy_final_mismatch", False)
                    r["rescored_sf"] = rs.get("sf_worst_delta", 999.0)
                    r["rescored_pc"] = rs.get("pc_worst_delta", 999.0)

            # Local phrase-differential for low-eff words
            local_pd = self._local_pd(log_probs, words, word_bounds, T)
            for i, r in enumerate(results):
                wi = r["word_idx"]
                if wi in local_pd:
                    r["local_pd_i3rab"] = local_pd[wi]["local_pd_i3rab"]
                    r["local_pd_tashkeel"] = local_pd[wi]["local_pd_tashkeel"]

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
        model_out = self.get_model_outputs(waveform, output_hidden_states=True)
        log_probs = model_out['log_probs']
        logits = model_out['logits']
        hidden_states = model_out.get('hidden_states')
        greedy = self.greedy_decode(log_probs)
        T = log_probs.shape[0]

        # Build a map from phrase_idx -> global word offset
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
                self._enrich_assessment(
                    assessment, words[wi], log_probs,
                    wb["char_spans"], sf, ef, T,
                    hidden_states, logits=logits)
                assessment["word_idx"] = matched_offset + wi  # global index
                assessment["word"] = words[wi]
                assessment["start_frame"] = sf
                assessment["end_frame"] = ef
                assessment["frame_count"] = ef - sf + 1
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
                 window_secs=8.0, lookahead=5):
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

        # Pre-compute stripped phrase words for matching
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
        self.min_match_sim = 0.25

        # Whisper caching: skip re-running if not enough new audio
        self._last_whisper_bytes = 0
        self._cached_whisper_words = []
        self._best_spoken = {}  # {phrase_idx: max spoken_up_to seen}

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

    # ------------------------------------------------------------------
    # Scoring cycle
    # ------------------------------------------------------------------

    def score_cycle(self, final=False):
        """Run one scoring cycle: Whisper for position, CTC for scoring.

        Returns the full scored_words dict (global_word_idx -> assessment)
        or None if there isn't enough audio yet.
        """
        min_secs = 1.0
        if len(self.audio_ring) < self.SAMPLE_RATE * self.BYTES_PER_SAMPLE * min_secs:
            return None

        audio_np = np.frombuffer(self.audio_ring, dtype=np.float32).copy()

        # --- Phase 1: Position tracking via Whisper ---
        whisper_words = self._get_whisper_words(audio_np)
        if not whisper_words:
            return self.scored_words  # silence or no speech detected

        # Match against candidate phrases
        candidates = self._get_candidates()
        best_idx, best_sim, scores = self._match_phrase(whisper_words, candidates)

        if best_sim < self.min_match_sim:
            return self.scored_words  # no match yet

        # Determine how many words were spoken
        phrase_text = self.phrases[best_idx]
        words = phrase_text.split()
        phrase_stripped = [strip_diacritics(w) for w in words]
        spoken_up_to = self._spoken_word_count(whisper_words, phrase_stripped)

        # Incremental continuation: if we already matched N words from the
        # start in a previous cycle, try continuing from position N forward.
        # This handles the case where the start of the phrase has left the
        # sliding Whisper window but we still remember it was spoken.
        prev_high = self._best_spoken.get(best_idx, 0)
        if prev_high > 0 and spoken_up_to < prev_high:
            remaining = phrase_stripped[prev_high:]
            if remaining:
                extra = self._spoken_word_count(whisper_words, remaining)
                spoken_up_to = max(spoken_up_to, prev_high + extra)
        if spoken_up_to > prev_high:
            self._best_spoken[best_idx] = spoken_up_to

        if spoken_up_to <= 1:
            return self.scored_words

        if final:
            spoken_up_to = len(words)

        # --- Phase 2: CTC scoring ---
        waveform = torch.from_numpy(audio_np)
        model_out = self.engine.get_model_outputs(
            waveform, output_hidden_states=final)
        log_probs = model_out['log_probs']
        logits = model_out['logits']
        hidden_states = model_out.get('hidden_states') if final else None
        T = log_probs.shape[0]

        partial_words = words[:spoken_up_to]
        partial_text = " ".join(partial_words)
        tokens = self.engine.text_to_tokens(partial_text)

        if not tokens or T < len(tokens):
            return self.scored_words

        spans = self.engine.forced_align(log_probs, tokens)
        word_bounds = self.engine.word_boundaries_from_alignment(spans, tokens)
        if not word_bounds:
            return self.scored_words

        global_offset = self.phrase_word_offsets[best_idx]

        for wb in word_bounds:
            wi = wb["word_idx"]
            if wi >= len(partial_words):
                continue

            sf, ef = wb["start_frame"], wb["end_frame"]
            margin = 2
            segment = log_probs[max(0, sf - margin): min(T, ef + margin + 1)]

            assessment = self.engine.assess_word(segment, partial_words[wi])
            self.engine._enrich_assessment(
                assessment, partial_words[wi], log_probs,
                wb["char_spans"], sf, ef, T,
                hidden_states, logits=logits)
            assessment["frame_count"] = ef - sf + 1
            gw = global_offset + wi
            assessment["word_idx"] = gw
            assessment["word"] = partial_words[wi]

            existing = self.scored_words.get(gw)

            if final:
                self.scored_words[gw] = assessment
            elif existing is None:
                assessment["_score_count"] = 1
                self.scored_words[gw] = assessment
            elif not existing.get("_locked"):
                count = existing.get("_score_count", 1) + 1
                if assessment["effective_score"] > existing["effective_score"]:
                    assessment["_score_count"] = count
                    self.scored_words[gw] = assessment
                else:
                    existing["_score_count"] = count
                if count >= 3:
                    self.scored_words[gw]["_locked"] = True

        # --- Phase 2b: Whisper per-word match ---
        if whisper_words and partial_words:
            wmatch = self._whisper_word_matches(whisper_words, partial_words)
            for wi in range(len(partial_words)):
                gw = global_offset + wi
                if gw in self.scored_words:
                    self.scored_words[gw]["whisper_match"] = wmatch[wi] if wi < len(wmatch) else True

        # --- Phase 3: Cursor retreat for re-reading ---
        # If Whisper matched a phrase 1-2 behind the cursor with a significantly
        # higher score than the current cursor phrase, retreat so the re-read
        # phrase gets fresh CTC scoring.
        if (best_idx < self.cursor_phrase
                and best_idx >= self.cursor_phrase - 2):
            cursor_sim = scores.get(self.cursor_phrase, 0.0)
            if best_sim - cursor_sim >= self.RETREAT_MARGIN:
                self._retreat_to(best_idx)

        # --- Phase 3b: Cursor advance (trust Whisper) ---
        # Cap to +1 per cycle to prevent wild jumps from common-word matches
        # Mutually exclusive with retreat: if we retreated above, best_idx is
        # no longer > cursor_phrase so this elif is a safety net.
        elif best_idx > self.cursor_phrase:
            self.cursor_phrase = min(best_idx, self.cursor_phrase + 1)

        # Advance past current phrase if we have data about it:
        # (a) most words are scored, OR
        # (b) at least half the current phrase is spoken AND next phrase started
        # Only apply when best_idx == cursor (data is for the right phrase)
        if best_idx == self.cursor_phrase and self.cursor_phrase < len(self.phrases) - 1:
            nearly_done = spoken_up_to >= max(len(words) - 1, len(words) * 3 // 4)
            half_done = spoken_up_to >= max(2, len(words) // 2)
            next_started = half_done and self._next_phrase_started(whisper_words)
            if nearly_done or next_started:
                self.cursor_phrase += 1

        return self.scored_words

    # ------------------------------------------------------------------
    # Phrase extension (sliding-window growth)
    # ------------------------------------------------------------------

    def extend_phrases(self, new_phrases: list) -> None:
        """Append new phrases to the session without resetting any state.

        Filters out non-string and empty/whitespace-only entries before
        appending.  Cursor, audio buffer, and accumulated scores are
        left untouched so recitation can continue seamlessly.
        """
        valid = [p for p in new_phrases if isinstance(p, str) and p.strip()]
        if not valid:
            return

        offset = len(self.all_words)
        for ph in valid:
            self.phrases.append(ph)
            self.phrase_word_offsets.append(offset)
            words = ph.split()
            self.all_words.extend(words)
            offset += len(words)
            self._stripped_phrases.append(strip_diacritics(ph).split())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _whisper_word_matches(whisper_words, phrase_words):
        """Check which phrase words appear in the Whisper output.

        Returns list[bool], one per phrase word. Uses unordered matching
        with fuzzy comparison (LCS ratio > 0.6). Single-char words are
        always marked as matched (too common for reliable detection).
        """
        matches = []
        for pw in phrase_words:
            pw_stripped = strip_diacritics(pw)
            if len(pw_stripped) <= 1:
                matches.append(True)
                continue
            found = any(
                ww == pw_stripped or _lcs_ratio(list(ww), list(pw_stripped)) > 0.6
                for ww in whisper_words
            )
            matches.append(found)
        return matches

    def _get_whisper_words(self, audio_np):
        """Get Whisper transcription, with caching and silence check."""
        # Skip if not enough new audio since last Whisper call
        new_bytes = self.total_audio_bytes - self._last_whisper_bytes
        min_new = int(0.5 * self.SAMPLE_RATE * self.BYTES_PER_SAMPLE)
        if new_bytes < min_new and self._cached_whisper_words:
            return self._cached_whisper_words

        # Silence check: skip Whisper if audio is too quiet
        rms = float(np.sqrt(np.mean(audio_np ** 2)))
        if rms < 0.005:
            return []

        # Use last 5s of audio for Whisper to reduce old-phrase contamination
        max_whisper_samples = int(5.0 * self.SAMPLE_RATE)
        if len(audio_np) > max_whisper_samples:
            whisper_audio = audio_np[-max_whisper_samples:]
        else:
            whisper_audio = audio_np

        words = self.engine.whisper_transcribe(whisper_audio)
        self._last_whisper_bytes = self.total_audio_bytes
        self._cached_whisper_words = words
        return words

    def _next_phrase_started(self, whisper_words):
        """Check if words from the next phrase appear in the Whisper output."""
        nxt = self.cursor_phrase + 1
        if nxt >= len(self.phrases):
            return False
        next_stripped = self._stripped_phrases[nxt]
        if len(next_stripped) < 2:
            return False
        # Check via fuzzy phrase coverage OR spoken_word_count
        cov = _phrase_coverage(whisper_words, next_stripped)
        if cov >= 0.2:
            return True
        phrase_words = [strip_diacritics(w) for w in self.phrases[nxt].split()]
        spoken = self._spoken_word_count(whisper_words, phrase_words)
        return spoken >= 2

    def _get_candidates(self):
        """Return phrase indices: two behind cursor + forward lookahead.

        Including cursor-1 and cursor-2 prevents old audio still in the ring
        buffer from falsely matching a distant future phrase that shares words,
        and also exposes re-read phrases to the retreat-detection logic.
        """
        lo = max(0, self.cursor_phrase - 2)
        hi = min(len(self.phrases) - 1, self.cursor_phrase + self.lookahead)
        return list(range(lo, hi + 1))

    # Retreat threshold: retreating phrase must beat cursor phrase by this margin.
    RETREAT_MARGIN = 0.20

    def _phrase_word_range(self, phrase_idx: int) -> tuple:
        """Return (start, end) global word indices for phrase_idx (end exclusive)."""
        start = self.phrase_word_offsets[phrase_idx]
        if phrase_idx + 1 < len(self.phrase_word_offsets):
            end = self.phrase_word_offsets[phrase_idx + 1]
        else:
            end = len(self.all_words)
        return start, end

    def _retreat_to(self, target_phrase_idx: int) -> None:
        """Retreat cursor to target_phrase_idx and unlock that phrase's words.

        Forward _best_spoken watermarks are preserved so the user doesn't lose
        progress on phrases they've already passed.  No-ops if target is not
        strictly behind the current cursor.
        """
        if target_phrase_idx >= self.cursor_phrase:
            return
        first, last = self._phrase_word_range(target_phrase_idx)
        for wi in list(self.scored_words.keys()):
            if first <= wi < last:
                del self.scored_words[wi]
        self._best_spoken[target_phrase_idx] = 0
        self.cursor_phrase = target_phrase_idx

    def _match_phrase(self, whisper_words, candidate_indices):
        """Find closest phrase match from candidates using phrase coverage.

        Prefers the nearest phrase (closest to cursor) that exceeds the
        match threshold, preventing false jumps on common Arabic words.

        Returns (best_idx, best_sim, scores) where scores maps each evaluated
        candidate index to its coverage score.
        """
        # candidates are sorted low→high (nearest first)
        scores = {}
        for idx in candidate_indices:
            sim = _phrase_coverage(whisper_words, self._stripped_phrases[idx])
            scores[idx] = sim
            if sim >= self.min_match_sim:
                return idx, sim, scores
        return self.cursor_phrase, 0.0, scores

    @staticmethod
    def _spoken_word_count(whisper_words, phrase_words):
        """Count how many phrase words appear in the Whisper output.

        Walks through phrase_words in order, fuzzy-matching each against
        the Whisper transcript.  Returns the index of the last matched + 1.
        """
        def _match_forward(w_words, p_words):
            spoken = 0
            w_idx = 0
            misses = 0
            for p_idx, pw in enumerate(p_words):
                matched = False
                scan_end = min(w_idx + 3, len(w_words))
                for wi in range(w_idx, scan_end):
                    ww = w_words[wi]
                    if ww == pw or _lcs_ratio(list(ww), list(pw)) > 0.5:
                        spoken = p_idx + 1
                        w_idx = wi + 1
                        matched = True
                        # Skip repeated words
                        while w_idx < len(w_words):
                            nw = w_words[w_idx]
                            if nw == pw or _lcs_ratio(list(nw), list(pw)) > 0.5:
                                w_idx += 1
                            else:
                                break
                        misses = 0
                        break
                if not matched:
                    misses += 1
                    if misses >= 2:
                        break
            return spoken

        result = _match_forward(whisper_words, phrase_words)

        # Pass 2: skip first few Whisper words (previous phrase bleed)
        if result == 0 and len(whisper_words) > 1:
            for skip in range(1, min(4, len(whisper_words))):
                r = _match_forward(whisper_words[skip:], phrase_words)
                if r > 0:
                    result = r
                    break

        # Pass 3: find first phrase word anywhere in Whisper output
        if result == 0 and len(whisper_words) > 4:
            pw0 = phrase_words[0]
            for skip in range(4, len(whisper_words)):
                ww = whisper_words[skip]
                if ww == pw0 or _lcs_ratio(list(ww), list(pw0)) > 0.5:
                    r = _match_forward(whisper_words[skip:], phrase_words)
                    if r > result:
                        result = r
                    break

        return result
