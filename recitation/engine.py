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
    get_final_diacritic, replace_final_diacritic, strip_diacritics,
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
        best_sukoon_name = None
        best_sukoon_score = -999.0
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

    def per_char_worst_delta(self, log_probs, char_spans):
        """Per-character diacritic confidence: worst delta across a word.

        For each diacritic in the forced-aligned char_spans, compares the
        model's log-prob for the expected diacritic vs the best alternative
        in the same group ({fatha,damma,kasra} or {fathatan,dammatan,kasratan}).
        Also compares tanween vs its corresponding short vowel (missing-tanween).

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

            # Determine comparison group
            if char in _SHORT_VOWELS:
                group = _SHORT_VOWELS
            elif char in _TANWEEN:
                group = _TANWEEN
            else:
                continue

            # Widen window: include 2 context frames on each side (weighted)
            context = 2
            frame_indices = list(range(max(0, sf - context), min(ef + 1 + context, T)))
            if not frame_indices:
                continue

            weights = np.array([
                1.0 if sf <= f <= ef else 0.5
                for f in frame_indices
            ])
            weights /= weights.sum()
            avg = (log_probs[frame_indices].numpy() * weights[:, None]).sum(axis=0)  # (V,)
            exp_lp = float(avg[token_id])

            best_alt = -999.0
            best_alt_char = None
            for alt_ch in group:
                if alt_ch == char:
                    continue
                aid = self.vocab.get(alt_ch)
                if aid is not None and float(avg[aid]) > best_alt:
                    best_alt = float(avg[aid])
                    best_alt_char = alt_ch

            # Tanween vs corresponding short vowel (detects missing tanween)
            if char in _TANWEEN_TO_SHORT:
                short_ch = _TANWEEN_TO_SHORT[char]
                sid = self.vocab.get(short_ch)
                if sid is not None and float(avg[sid]) > best_alt:
                    best_alt = float(avg[sid])
                    best_alt_char = short_ch

            if best_alt > -900:
                d = exp_lp - best_alt  # negative = alt is more likely
                if d < worst:
                    worst = d
                    worst_expected = _DIAC_NAMES.get(char)
                    worst_heard = _DIAC_NAMES.get(best_alt_char)

        return {"delta": worst, "expected": worst_expected, "heard": worst_heard}

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
        for ei, gi in matched:
            _cons, exp_vowel, exp_shadda = exp_internal[ei]
            _gcons, gre_vowel, _gshadda = gre_pairs[gi]

            if exp_shadda:
                continue  # shadda'd consonants are acoustically ambiguous
            if exp_vowel is None:
                continue
            if gre_vowel is None:
                continue  # greedy didn't produce a vowel here — skip
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
            pc = self.per_char_worst_delta(log_probs, wb["char_spans"])
            assessment["pc_worst_delta"] = pc["delta"]
            assessment["pc_expected_diac"] = pc["expected"]
            assessment["pc_heard_diac"] = pc["heard"]
            greedy_seg = self.greedy_decode(log_probs[sf:ef + 1])
            assessment["greedy_segment"] = greedy_seg
            gdm = self.greedy_diacritic_mismatch(greedy_seg, words[wi])
            assessment["greedy_diac_mismatches"] = gdm["count"]
            assessment["greedy_diac_expected"] = gdm["expected"]
            assessment["greedy_diac_heard"] = gdm["heard"]
            assessment["greedy_final_mismatch"] = gdm["final_mismatch"]
            assessment["greedy_consonant_match"] = gdm["consonant_match"]
            assessment["word_idx"] = wi
            assessment["word"] = words[wi]
            assessment["start_frame"] = sf
            assessment["end_frame"] = ef
            assessment["frame_count"] = ef - sf + 1
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
                pc = self.per_char_worst_delta(log_probs, wb["char_spans"])
                assessment["pc_worst_delta"] = pc["delta"]
                assessment["pc_expected_diac"] = pc["expected"]
                assessment["pc_heard_diac"] = pc["heard"]
                greedy_seg = self.greedy_decode(log_probs[sf:ef + 1])
                assessment["greedy_segment"] = greedy_seg
                gdm = self.greedy_diacritic_mismatch(greedy_seg, words[wi])
                assessment["greedy_diac_mismatches"] = gdm["count"]
                assessment["greedy_diac_expected"] = gdm["expected"]
                assessment["greedy_diac_heard"] = gdm["heard"]
                assessment["greedy_final_mismatch"] = gdm["final_mismatch"]
                assessment["greedy_consonant_match"] = gdm["consonant_match"]
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

    @property
    def total_audio_secs(self):
        return self.total_audio_bytes / (self.SAMPLE_RATE * self.BYTES_PER_SAMPLE)

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
        best_idx, best_sim = self._match_phrase(whisper_words, candidates)

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
        log_probs = self.engine.get_log_probs(waveform)
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
            pc = self.engine.per_char_worst_delta(log_probs, wb["char_spans"])
            assessment["pc_worst_delta"] = pc["delta"]
            assessment["pc_expected_diac"] = pc["expected"]
            assessment["pc_heard_diac"] = pc["heard"]
            greedy_seg = self.engine.greedy_decode(log_probs[sf:ef + 1])
            assessment["greedy_segment"] = greedy_seg
            gdm = self.engine.greedy_diacritic_mismatch(greedy_seg, partial_words[wi])
            assessment["greedy_diac_mismatches"] = gdm["count"]
            assessment["greedy_diac_expected"] = gdm["expected"]
            assessment["greedy_diac_heard"] = gdm["heard"]
            assessment["greedy_final_mismatch"] = gdm["final_mismatch"]
            assessment["greedy_consonant_match"] = gdm["consonant_match"]
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

        # --- Phase 3: Cursor advance (trust Whisper) ---
        # Cap to +1 per cycle to prevent wild jumps from common-word matches
        if best_idx > self.cursor_phrase:
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
    # Helpers
    # ------------------------------------------------------------------

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
        """Return phrase indices: one behind cursor + forward lookahead.

        Including cursor-1 prevents old audio still in the ring buffer
        from falsely matching a distant future phrase that shares words.
        """
        lo = max(0, self.cursor_phrase - 1)
        hi = min(len(self.phrases) - 1, self.cursor_phrase + self.lookahead)
        return list(range(lo, hi + 1))

    def _match_phrase(self, whisper_words, candidate_indices):
        """Find closest phrase match from candidates using phrase coverage.

        Prefers the nearest phrase (closest to cursor) that exceeds the
        match threshold, preventing false jumps on common Arabic words.
        """
        # candidates are sorted low→high (nearest first)
        for idx in candidate_indices:
            sim = _phrase_coverage(whisper_words, self._stripped_phrases[idx])
            if sim >= self.min_match_sim:
                return idx, sim
        return self.cursor_phrase, 0.0

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
