"""RoutedEnsemble — decorrelated agreement ensemble for error scoring (Phase 4).

Wraps N diacritized-char CTC RecitationEngines (the "members"). For each word it
scores every member on the SAME base word-boundaries and flags an error type only
when **>= k members agree** (each above its own FP-safe threshold). Agreement is
the false-positive control; decorrelated members (different objectives/seeds) are
the whole point. See ARCHITECTURE.md and experiments.md (Phase 3-4).

Design:
- The PRIMARY member (base) owns alignment/position; its forced-align word spans
  are reused by every member so margins are directly comparable.
- A CONSONANT channel is added here (the engine's assess_word does i3rab+tashkeel
  only); it scores makhraj-confusable single-consonant swaps the same way.
- Output is the same per-word `results` shape score_phrase returns, with three
  extra booleans: ensemble_i3rab / ensemble_tashkeel / ensemble_consonant.
  classify_words uses those when present, else the existing single-model logic.

Config (ensemble_config.json) — base-only by default (== current behavior):
  {
    "primary": "base",
    "members": { "base": "models/ssl_xls_r_v5", "i3rab_v2": "models/xlsr_i3rab_v2", ... },
    "routing": {
      "i3rab":     { "members": ["base","i3rab_v2"], "k": 2, "thresholds": {"base": 0.0, "i3rab_v2": 0.01} },
      "tashkeel":  { ... },
      "consonant": { ... }
    }
  }
PROVISIONAL: the member set + thresholds are pending validation on a larger /
more general dataset (the careful-sessions picks are overfit to ~206 words).
"""
import json
import os

# Makhraj-confusable consonant groups (same/adjacent place of articulation) — the
# realistic substitution errors. Mirrors recitation eval mutations.consonant.
_CONS_GROUPS = ["سصث", "تط", "دض", "ذظزص", "حهخ", "قك", "عءأإ", "صض"]
CONFUSE = {}
for _g in _CONS_GROUPS:
    for _c in _g:
        CONFUSE.setdefault(_c, set()).update(x for x in _g if x != _c)


def consonant_alternatives(word):
    """All single-consonant-swap variants of `word` to a confusable consonant."""
    out = {}
    for i, ch in enumerate(word):
        for alt in CONFUSE.get(ch, ()):
            w = word[:i] + alt + word[i + 1:]
            if w != word:
                out[(i, alt)] = w
    return out


def _i3rab_margin(a):
    if a.get("skip_i3rab") or a.get("best_alt_score", -999.0) <= -900:
        return None
    return a["best_alt_score"] - a["effective_score"]


def _tashkeel_margin(a):
    if a.get("skip_tashkeel"):
        return None
    best = max(a.get("best_tashkeel_score", -999.0), a.get("best_addvowel_score", -999.0))
    if best <= -900:
        return None
    return best - a["effective_score"]


def _consonant_margin(engine, segment, word, eff, cap=6):
    alts = list(consonant_alternatives(word).values())
    if not alts:
        return None
    if len(alts) > cap:
        alts = alts[:cap]
    best = max(engine.score_hypothesis(segment, w) for w in alts)
    return best - eff


def agrees(margins_by_member, route):
    """True if >= k members fire (margin present and > their threshold)."""
    if not route:
        return None
    k = route.get("k", 1)
    thr = route.get("thresholds", {})
    fired = 0
    for name in route.get("members", []):
        m = margins_by_member.get(name)
        if m is not None and m > thr.get(name, 0.0):
            fired += 1
    return fired >= k


class RoutedEnsemble:
    """Loads member engines and produces per-word results with agreement flags.

    Falls back to single-model behavior when no `routing` is configured (the
    safe default) — in that case it's just the primary RecitationEngine.
    """

    def __init__(self, config, engine_factory):
        """config: dict (see module docstring). engine_factory: callable(path)->RecitationEngine
        (passed in so this module doesn't import the heavy engine at import time)."""
        self.routing = config.get("routing", {}) or {}
        member_paths = config.get("members", {})
        self.primary_name = config.get("primary", next(iter(member_paths), "base"))
        # Only load members that some route actually uses (+ the primary).
        used = {self.primary_name}
        for r in self.routing.values():
            used.update(r.get("members", []))
        self.members = {name: engine_factory(member_paths[name])
                        for name in used if name in member_paths}
        if self.primary_name not in self.members:
            raise ValueError(f"primary '{self.primary_name}' not in members {list(self.members)}")
        self.primary = self.members[self.primary_name]

    @classmethod
    def from_config_file(cls, path, engine_factory):
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f), engine_factory)

    # delegate the interface server.py uses to the primary engine
    def __getattr__(self, name):
        return getattr(self.__dict__["members"][self.__dict__["primary_name"]], name)

    def _flags_by_local_idx(self, waveform, phrase_text):
        """Per-word ensemble agreement flags keyed by LOCAL word index within
        `phrase_text`. Shared by score_phrase (WS) and locate_and_score (REST)
        so both entrypoints get identical ensemble behavior."""
        words = phrase_text.split()
        lp_p = self.primary.get_log_probs(waveform)
        tokens = self.primary.text_to_tokens(phrase_text)
        if not tokens:
            return {}
        spans = self.primary.forced_align(lp_p, tokens)
        wbs = self.primary.word_boundaries_from_alignment(spans, tokens)
        # per-member log-probs (one forward each)
        member_lp = {name: (lp_p if name == self.primary_name else eng.get_log_probs(waveform))
                     for name, eng in self.members.items()}
        T = {name: lp.shape[0] for name, lp in member_lp.items()}

        by_idx = {}
        for wb in wbs:
            wi = wb["word_idx"]
            if wi >= len(words):
                continue
            sf, ef = wb["start_frame"], wb["end_frame"]
            i3, ta, co = {}, {}, {}
            for name, eng in self.members.items():
                seg = member_lp[name][max(0, sf - 2):min(T[name] - 1, ef + 2) + 1]
                if seg.shape[0] < 3:
                    continue
                a = eng.assess_word(seg, words[wi])
                i3[name] = _i3rab_margin(a)
                ta[name] = _tashkeel_margin(a)
                co[name] = _consonant_margin(eng, seg, words[wi], a["effective_score"])
            by_idx[wi] = {
                "ensemble_i3rab": agrees(i3, self.routing.get("i3rab")),
                "ensemble_tashkeel": agrees(ta, self.routing.get("tashkeel")),
                "ensemble_consonant": agrees(co, self.routing.get("consonant")),
            }
        return by_idx

    def score_phrase(self, waveform, phrase_text, **kw):
        """Same return as RecitationEngine.score_phrase, with ensemble_* flags
        added per word. Members share the primary's word boundaries."""
        results, greedy, full_score = self.primary.score_phrase(waveform, phrase_text, **kw)
        if not self.routing:
            return results, greedy, full_score  # single-model fallback
        by_idx = self._flags_by_local_idx(waveform, phrase_text)  # local == result word_idx
        for r in results:
            r.update(by_idx.get(r.get("word_idx"), {}))
        return results, greedy, full_score

    def locate_and_score(self, waveform, full_text, phrases):
        """REST entrypoint. The primary locates the matched phrase and returns
        results with GLOBAL word indices; we add ensemble flags by mapping the
        matched phrase's LOCAL indices back to global (local + phrase offset)."""
        results, greedy, matched_idx, full_score = \
            self.primary.locate_and_score(waveform, full_text, phrases)
        if not self.routing or not results or not (0 <= matched_idx < len(phrases)):
            return results, greedy, matched_idx, full_score
        offset = sum(len(p.split()) for p in phrases[:matched_idx])
        by_local = self._flags_by_local_idx(waveform, phrases[matched_idx])
        for r in results:
            gi = r.get("word_idx")
            if gi is not None:
                r.update(by_local.get(gi - offset, {}))
        return results, greedy, matched_idx, full_score


def load_ensemble_or_engine(engine_factory, model_path, config_path="ensemble_config.json"):
    """Return a RoutedEnsemble iff `config_path` has routing AND every member
    weight it needs is present on disk; otherwise a plain RecitationEngine.

    Safe by construction:
      - no config / no routing  -> single model (unchanged default)
      - routing but member dirs missing (e.g. weights still on a remote volume)
        -> single model, with a log line. The SAME config auto-activates the
        full ensemble once those dirs are placed next to it. Never crashes a
        working server just because optional member weights aren't there yet.
    Member paths in the config are resolved relative to the config file."""
    if not (config_path and os.path.exists(config_path)):
        return engine_factory(model_path)
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("routing"):
        return engine_factory(model_path)

    base = os.path.dirname(os.path.abspath(config_path))
    members = dict(cfg.get("members", {}))
    primary = cfg.get("primary", next(iter(members), "base"))
    used = {primary}
    for r in cfg["routing"].values():
        used.update(r.get("members", []))

    resolved, missing = {}, []
    for name in used:
        p = members.get(name)
        ap = (p if os.path.isabs(p) else os.path.join(base, p)) if p else None
        if ap and os.path.exists(ap):
            resolved[name] = ap
        else:
            missing.append(name)
    if missing:
        print(f"[ensemble] member weights missing {sorted(set(missing))} "
              f"-> single-model fallback (config stays inert until present)", flush=True)
        return engine_factory(model_path)

    cfg["members"] = {**members, **resolved}
    print(f"[ensemble] active: primary={primary}, members={sorted(resolved)}", flush=True)
    return RoutedEnsemble(cfg, engine_factory)
