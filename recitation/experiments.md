# Scoring Pipeline Experiments Log

## Baseline (2026-04-01)

| Metric | Target | Baseline |
|---|---|---|
| FP rate | <2% | 5.2% (17/326) |
| I3rab detection | >90% | 51% (126/246) |
| Tashkeel detection | >90% | 61% (161/266) |
| Word detection | >95% | 52% (32/62) |
| Correct type overall | — | 50.2% (288/574) |

### Key observations
- daa-dawa passage is much worse (7.1% FP vs 3.5% for ajrumiyyah)
- 120 missed i3rab mutations, 105 missed tashkeel, 30 missed word
- Many misses have very negative `eff` scores (< -2.0), which means the quality gate (`effective_score < -2.0`) is suppressing detection
- Wrong word detection at 52% — consonant_match threshold of 0.4 is too strict, and frame_count filter blocks many
- Many i3rab false negatives: `skip_i3rab=True` when `sukoon_score > expected_score` blocks most i3rab testing

## Experiment History

(entries below)
