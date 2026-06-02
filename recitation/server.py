"""Recitation assessment server — serves the UI and scores audio."""
import asyncio
import json
import logging
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from arabic import strip_diacritics
from auth import verify as verify_auth_token

AUTH_SECRET = os.getenv("RECITATION_AUTH_SECRET")
ALLOWED_ORIGINS = (
    [o.strip() for o in os.getenv("RECITATION_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    or None
)
ALLOW_DEBUG = os.getenv("RECITATION_ALLOW_DEBUG") == "1"
MAX_SESSION_SEC = int(os.getenv("RECITATION_MAX_SESSION_SEC", "600"))

LOG_STREAMING = os.getenv("LOG_STREAMING") == "1"
log = logging.getLogger("recitation")
logging.basicConfig(format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":%(message)s}',
                    level=logging.INFO)


def jlog(event: str, **fields):
    if LOG_STREAMING:
        log.info(json.dumps({"event": event, **fields}, ensure_ascii=False))

# ── Error classifier (GBM) for low-eff fallback ──
_error_classifier = None
_type_classifier = None

def _load_error_classifier():
    global _error_classifier
    if _error_classifier is not None:
        return _error_classifier
    clf_path = BASE_DIR / "models" / "error_classifier.pkl"
    if not clf_path.exists():
        _error_classifier = False  # Sentinel: not available
        return False
    import pickle
    with open(clf_path, "rb") as f:
        _error_classifier = pickle.load(f)
    return _error_classifier

def _load_type_classifier():
    global _type_classifier
    if _type_classifier is not None:
        return _type_classifier
    clf_path = BASE_DIR / "models" / "type_classifier.pkl"
    if not clf_path.exists():
        _type_classifier = False
        return False
    import pickle
    with open(clf_path, "rb") as f:
        _type_classifier = pickle.load(f)
    return _type_classifier

def _classify_with_gbm(wr, word_text):
    """Use GBM classifier as fallback for undetected words.
    Returns (probability, error_type) or (0.0, None) if unavailable."""
    clf = _load_error_classifier()
    if clf is False:
        return 0.0, None

    s = wr
    eff = s["effective_score"]
    feature_keys = clf["feature_keys"]

    def safe_val(key):
        # Map signal_dump keys to word_result keys
        key_map = {
            "eff": "effective_score",
            "sf": "sf_worst_delta",
            "pc": "pc_worst_delta",
            "mg": "mg_worst_margin",
            "pd_i3rab": "pd_i3rab_delta",
            "pd_tashkeel": "pd_tashkeel_delta",
            "i3rab_delta": None,  # computed
            "tash_delta": None,   # computed
            "consonant_match": "greedy_consonant_match",
            "frame_count": "frame_count",
            "fs_worst_delta": "fs_worst_delta",
            "local_pd_i3rab": "local_pd_i3rab",
            "local_pd_tashkeel": "local_pd_tashkeel",
        }
        if key == "i3rab_delta":
            alt = s.get("best_alt_score", -999)
            return (alt - eff) if alt > -900 else 0.0
        elif key == "tash_delta":
            tash = s.get("best_tashkeel_score", -999)
            return (tash - eff) if tash > -900 else 0.0
        else:
            mapped = key_map.get(key, key)
            v = s.get(mapped, 0.0)
            if v is None or v == 999 or v == 999.0:
                return 0.0
            return float(v)

    feats = [safe_val(k) for k in feature_keys]
    feats = np.array(feats).reshape(1, -1)
    feats = np.nan_to_num(feats, nan=0.0, posinf=0.0, neginf=0.0)

    # Scale
    mean = np.array(clf["scaler_mean"])
    scale = np.array(clf["scaler_scale"])
    feats_scaled = (feats - mean) / scale

    prob = clf["model"].predict_proba(feats_scaled)[0, 1]

    # Determine error type using trained type classifier
    type_clf = _load_type_classifier()
    if type_clf and type_clf is not False:
        type_keys = type_clf["feature_keys"]

        def type_safe(key):
            key_map = {
                "eff": "effective_score",
                "sf": "sf_worst_delta",
                "pc": "pc_worst_delta",
                "mg": "mg_worst_margin",
                "pd_i3rab": "pd_i3rab_delta",
                "pd_tashkeel": "pd_tashkeel_delta",
                "consonant_match": "greedy_consonant_match",
                "frame_count": "frame_count",
                "fs_worst_delta": "fs_worst_delta",
                "local_pd_i3rab": "local_pd_i3rab",
                "local_pd_tashkeel": "local_pd_tashkeel",
                "gfm": "greedy_final_mismatch",
                "gdm": "greedy_diac_mismatches",
            }
            if key == "i3rab_delta":
                alt = s.get("best_alt_score", -999)
                return (alt - eff) if alt > -900 else 0.0
            elif key == "tash_delta":
                tash = s.get("best_tashkeel_score", -999)
                return (tash - eff) if tash > -900 else 0.0
            elif key == "sukoon_delta":
                sukoon = s.get("best_sukoon_score", -999)
                return (sukoon - eff) if sukoon > -900 else 0.0
            else:
                mapped = key_map.get(key, key)
                v = s.get(mapped, 0.0)
                if v is None or v == 999 or v == 999.0:
                    return 0.0
                if isinstance(v, bool):
                    return 1.0 if v else 0.0
                return float(v)

        type_feats = np.array([type_safe(k) for k in type_keys]).reshape(1, -1)
        type_feats = np.nan_to_num(type_feats, nan=0.0, posinf=0.0, neginf=0.0)
        type_mean = np.array(type_clf["scaler_mean"])
        type_scale = np.array(type_clf["scaler_scale"])
        type_feats_scaled = (type_feats - type_mean) / type_scale
        type_pred = type_clf["model"].predict(type_feats_scaled)[0]
        error_type = type_clf["type_names"][type_pred]
    else:
        # Fallback: simple heuristic
        cm = safe_val("consonant_match")
        pd_i = safe_val("pd_i3rab")
        pd_t = safe_val("pd_tashkeel")
        if cm <= 0.3:
            error_type = "wrong"
        elif pd_t > pd_i:
            error_type = "tashkeel"
        else:
            error_type = "i3rab"

    return prob, error_type

TEST_DIR = BASE_DIR / "test_data" / "recordings"
MANIFEST = BASE_DIR / "test_data" / "manifest.jsonl"
SESSION_LOG_DIR = BASE_DIR / "test_data" / "sessions"
MODEL_PATH = BASE_DIR / "models" / "ssl_xls_r_v5"
PASSAGES_FILE = BASE_DIR / "passage.json"

app = FastAPI()
TEST_DIR.mkdir(parents=True, exist_ok=True)

# ── Load engine at startup ──
engine = None


@app.on_event("startup")
async def load_engine():
    global engine
    from engine import RecitationEngine
    engine = RecitationEngine(str(MODEL_PATH))


def load_passages():
    with open(PASSAGES_FILE) as f:
        return json.load(f)


def parse_ws_init(init: dict, load_passages_fn) -> tuple:
    """Parse the WebSocket init message and return (phrases, log_info).

    Accepts two forms:
      - Inline:   {"passage": {"id": "...", "phrases": [...]}}
      - Stored:   {"passage_id": "..."}

    Returns:
      phrases   — list of non-empty phrase strings
      log_info  — dict with keys: log_label, passage_id, inline_id

    Raises ValueError with a descriptive message on any validation failure.
    """
    inline = init.get("passage")
    passage_id = init.get("passage_id")

    if inline and isinstance(inline, dict) and isinstance(inline.get("phrases"), list):
        # Inline form
        phrases = [str(p) for p in inline["phrases"]
                   if isinstance(p, str) and p.strip()]
        if not phrases:
            raise ValueError("Inline passage has no phrases")
        inline_id = inline.get("id")
        log_label = inline_id or "inline"
        log_info = {
            "log_label": log_label,
            "passage_id": None,
            "inline_id": inline_id,
        }
        return phrases, log_info

    elif passage_id:
        # Stored passage_id form
        data = load_passages_fn()
        passage = next((p for p in data.get("passages", [])
                        if p["id"] == passage_id), None)
        if not passage or "phrases" not in passage:
            raise ValueError("Passage not found")
        phrases = passage["phrases"]
        log_info = {
            "log_label": passage_id,
            "passage_id": passage_id,
            "inline_id": None,
        }
        return phrases, log_info

    else:
        raise ValueError("Init must include 'passage' or 'passage_id'")


# ── Pages ──

@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/record")
async def record_page():
    return FileResponse(BASE_DIR / "static" / "record.html")


# ── API ──

@app.get("/api/passages")
async def get_passages():
    return load_passages()


@app.post("/api/score")
async def score_audio(
    audio: UploadFile = File(...),
    passage_id: str = Form(...),
):
    """Score audio against a passage. Auto-detects which part was read."""
    data = load_passages()
    passage = next((p for p in data["passages"] if p["id"] == passage_id), None)
    if not passage or "phrases" not in passage:
        return JSONResponse({"error": "Passage not found or has no phrases"}, 400)

    phrases = passage["phrases"]
    full_text = " ".join(phrases)
    all_words = full_text.split()

    # Save to temp file for ffmpeg
    audio_bytes = await audio.read()
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        waveform = engine.load_audio(tmp_path)
        word_results, greedy, matched_phrase_idx, full_score = \
            engine.locate_and_score(waveform, full_text, phrases)
    except Exception as e:
        return JSONResponse({"error": str(e)}, 500)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    scored_words = classify_words(word_results, all_words)

    return {
        "greedy_decode": greedy,
        "full_score": full_score,
        "matched_phrase_idx": matched_phrase_idx,
        "words": scored_words,
    }


# ── Tiered classification with eff-adaptive thresholds ──
#
# Calibrated on 326 correct + 574 mutated words from 2 sessions.
#
# Key insights from signal analysis:
#   - gfm (greedy final mismatch) is near-perfect for i3rab: 44.7%
#     detection at 0.3% FP. Used standalone — no vote corroboration needed.
#   - tash_delta discrimination varies dramatically by eff range:
#     eff > -0.5: 1%FP threshold = 0.234
#     eff -1.0 to -0.5: 1%FP threshold = 0.059 (92% detection!)
#     eff -1.5 to -1.0: 1%FP threshold = 0.310
#   - pc < -5.0 at eff > -0.5: 0% FP, catches 17 additional tashkeel
#   - Below eff -1.5: all signals are noise, no detection attempted.
#
# Design: tiered decision tree with explicit eff ranges to prevent
# threshold leaking between strata. Each rule verified for 0% FP
# (or near-0%) on its target eff stratum.


def classify_words(word_results, all_words, streaming=False):
    """Turn raw engine results into classified word dicts.

    Uses tiered eff-adaptive classification: each eff range has its own
    thresholds calibrated from signal distributions. gfm is standalone
    for i3rab (0.3% FP). No diacritic detection below eff -1.5.
    """
    scored = []
    for wr in word_results:
        wi = wr["word_idx"]
        eff = wr["effective_score"]
        status = "correct"
        error_type = None
        error_detail = None
        word_text = wr.get("word", "")
        word_consonants = strip_diacritics(word_text)
        consonant_match = wr.get("greedy_consonant_match", 1.0)
        frame_count = wr.get("frame_count", 999)
        greedy_seg = wr.get("greedy_segment", "")

        # ── Wrong word detection ──
        if (len(word_consonants) >= 3 and eff > -1.0
                and consonant_match < 0.35 and len(greedy_seg) > 0
                and frame_count >= 3 and frame_count <= 50):
            status = "error"
            error_type = "wrong"
            error_detail = greedy_seg

        # Whisper wrong word (low eff)
        whisper_match = wr.get("whisper_match", True)
        if (status == "correct" and not whisper_match
                and eff < -1.6
                and len(word_consonants) >= 3
                and frame_count >= 5):
            status = "error"
            error_type = "wrong"
            error_detail = "whisper_mismatch"

        # Whisper wrong word (higher eff) — requires low cm + high frame count
        if (status == "correct" and not whisper_match
                and eff > -1.0
                and consonant_match <= 0.40
                and frame_count >= 15
                and len(word_consonants) >= 3):
            status = "error"
            error_type = "wrong"
            error_detail = "whisper_cm_fc"

        # Skipped word
        if (status == "correct" and frame_count < 3 and eff < -3.5
                and len(word_consonants) >= 3):
            status = "error"
            error_type = "skipped"
            error_detail = None

        # Low-eff word detection via phrase-differential
        pd_i3_word = wr.get("pd_i3rab_delta", 0.0)
        # Rule A: low consonant match + strong pd signal
        if (status == "correct" and eff <= -1.5
                and len(word_consonants) >= 3
                and consonant_match <= 0.25
                and pd_i3_word >= 0.60
                and frame_count >= 5):
            status = "error"
            error_type = "wrong"
            error_detail = "pd_cm_mismatch"

        # Rule B: very strong pd signal alone (0% FP)
        if (status == "correct" and eff <= -1.5
                and len(word_consonants) >= 3
                and pd_i3_word >= 1.0
                and frame_count >= 5):
            status = "error"
            error_type = "wrong"
            error_detail = "pd_strong"

        # Rule C: low consonant match + moderate pd at -1.5 to -1.0 (0% FP)
        if (status == "correct" and -1.5 < eff <= -1.0
                and len(word_consonants) >= 3
                and consonant_match <= 0.25
                and pd_i3_word >= 0.20
                and frame_count >= 5):
            status = "error"
            error_type = "wrong"
            error_detail = "pd_cm_moderate"

        # ── Rescued low-eff diacritic detection ──
        # Words at eff <= -1.5 that windowed re-scoring pushes above -1.5
        # have recognizable content despite poor initial alignment.
        # Use only high-confidence signals (rescored gfm, pd + rescored combo).
        rescored_eff = wr.get("rescored_eff")
        if (status == "correct" and eff <= -1.5
                and rescored_eff is not None and rescored_eff > -1.5):
            r_gfm = wr.get("rescored_gfm", False)
            r_i3d = wr.get("rescored_i3rab_delta", 0.0)
            r_td = wr.get("rescored_tash_delta", 0.0)
            pd_i3_rescue = wr.get("pd_i3rab_delta", 0.0)
            pd_t_rescue = wr.get("pd_tashkeel_delta", 0.0)

            # I3rab: rescored gfm (0% FP on rescued subset)
            if r_gfm:
                status = "error"
                error_type = "i3rab"
                error_detail = wr.get("best_alt_name") or "rescue_gfm"

            # I3rab: rescored delta + pd corroboration (0% FP)
            if (status == "correct"
                    and r_i3d >= 0.10 and pd_i3_rescue >= 0.15):
                status = "error"
                error_type = "i3rab"
                error_detail = wr.get("best_alt_name") or "rescue_pd"

            # Tashkeel: rescored delta (0% FP on rescued subset)
            if status == "correct" and r_td >= 0.10:
                status = "error"
                error_type = "tashkeel"
                error_detail = wr.get("best_tashkeel_name") or "rescue_td"

            # Tashkeel: strong pd signal (0% FP on rescued subset)
            if status == "correct" and pd_t_rescue >= 0.30:
                status = "error"
                error_type = "tashkeel"
                error_detail = wr.get("pd_tashkeel_name") or "rescue_pd"

        # ── Low-eff triple-signal detection (eff <= -1.5) ──
        # When all three independent signals agree, even low-eff words
        # can be classified. 1 FP on 111 correct in this range.
        if (status == "correct" and eff <= -1.5):
            td_low = wr.get("best_tashkeel_score", -999.0)
            td_low_delta = (td_low - eff) if td_low > -900 else 0.0
            pd_i3_low = wr.get("pd_i3rab_delta", 0.0)
            pd_t_low = wr.get("pd_tashkeel_delta", 0.0)
            if (td_low_delta >= 0.05
                    and pd_i3_low >= 0.20
                    and pd_t_low >= 0.20):
                # Classify based on dominant pd signal
                if pd_t_low > pd_i3_low:
                    status = "error"
                    error_type = "tashkeel"
                    error_detail = wr.get("best_tashkeel_name") or "low_eff_triple"
                else:
                    status = "error"
                    error_type = "i3rab"
                    error_detail = wr.get("best_alt_name") or "low_eff_triple"

        # ── Local phrase-differential detection (eff <= -1.5) ──
        # Uses 3-word sub-phrase CTC scoring for better discrimination.
        if status == "correct" and eff <= -1.5:
            lpd_i = wr.get("local_pd_i3rab", 0.0)
            lpd_t = wr.get("local_pd_tashkeel", 0.0)
            pd_t_lpd = wr.get("pd_tashkeel_delta", 0.0)

            # local_pd_t + full pd_t corroboration
            if lpd_t >= 0.70 and pd_t_lpd >= 0.15:
                if lpd_t > lpd_i:
                    status = "error"
                    error_type = "tashkeel"
                    error_detail = wr.get("best_tashkeel_name") or "local_pd_t"
                else:
                    status = "error"
                    error_type = "i3rab"
                    error_detail = wr.get("best_alt_name") or "local_pd_i"

        # ── Frame-scan diacritic detection (eff <= -1.5) ──
        # Alignment-robust: scans wide frame region for diacritic evidence.
        if status == "correct" and eff <= -1.5:
            fs_delta = wr.get("fs_worst_delta", 999.0)
            sf_fs = wr.get("sf_worst_delta", 999.0)
            # Tier 1: frame_scan + sf corroboration (strong evidence)
            if fs_delta < -2.0 and sf_fs < -4.0:
                sf_expected = wr.get("sf_worst_expected")
                sf_heard = wr.get("sf_worst_heard")
                if sf_expected and sf_heard:
                    if sf_expected in ("damma", "kasra", "fatha",
                                       "dammatan", "kasratan", "fathatan"):
                        status = "error"
                        error_type = "tashkeel"
                        error_detail = f"fs_{sf_expected}_{sf_heard}"
                    else:
                        status = "error"
                        error_type = "i3rab"
                        error_detail = f"fs_{sf_expected}_{sf_heard}"
                else:
                    status = "error"
                    error_type = "tashkeel"
                    error_detail = "fs_sf_combo"


        # ── Diacritic error detection (eff-adaptive tiers) ──
        # Below eff -1.5: signals are noise, skip entirely.
        if status == "correct" and eff > -1.5:
            alt = wr["best_alt_score"]
            i3rab_delta = (alt - eff) if alt > -900 else 0.0
            tash = wr.get("best_tashkeel_score", -999.0)
            tash_delta = (tash - eff) if tash > -900 else 0.0
            pc = wr.get("pc_worst_delta", 999.0)
            sf_delta = wr.get("sf_worst_delta", 999.0)
            gfm = wr.get("greedy_final_mismatch", False)
            gdm_count = wr.get("greedy_diac_mismatches", 0)

            # ── I3RAB DETECTION ──
            # Tier 1: gfm standalone (0% FP at eff > -1.5)
            if gfm:
                status = "error"
                error_type = "i3rab"
                error_detail = wr.get("best_alt_name") or "greedy_final"

            # Tier 2: i3rab_delta eff-adaptive (0% FP per stratum)
            if status == "correct" and alt > -900:
                if eff > -0.5 and i3rab_delta >= 0.10:
                    status = "error"
                    error_type = "i3rab"
                    error_detail = wr["best_alt_name"]
                elif -1.0 < eff <= -0.5 and i3rab_delta >= 0.18:
                    status = "error"
                    error_type = "i3rab"
                    error_detail = wr["best_alt_name"]
                elif -1.5 < eff <= -1.0 and i3rab_delta >= 0.12:
                    status = "error"
                    error_type = "i3rab"
                    error_detail = wr["best_alt_name"]

            # Tier 3: i3rab_delta + pc corroboration (eff -1.0 to -0.5)
            if (status == "correct" and alt > -900
                    and -1.0 < eff <= -0.5
                    and i3rab_delta >= 0.05 and pc < -5.0):
                status = "error"
                error_type = "i3rab"
                error_detail = wr["best_alt_name"]

            # Tier 4: i3rab_delta + strong corroboration (eff > -1.0)
            if (status == "correct" and alt > -900
                    and i3rab_delta >= 0.15 and eff > -1.0):
                if (pc < -5.0 or sf_delta < -5.0):
                    status = "error"
                    error_type = "i3rab"
                    error_detail = wr["best_alt_name"]

            # Tier 5: i3rab_delta + sf corroboration (0% FP)
            # Only when i3rab signal dominates tashkeel to avoid mistyping
            # Restricted to eff > -1.3 to avoid FP at lower eff
            if (status == "correct" and alt > -900
                    and eff > -1.3
                    and i3rab_delta >= 0.03 and sf_delta < -3.0
                    and (tash_delta <= 0 or i3rab_delta >= tash_delta)):
                status = "error"
                error_type = "i3rab"
                error_detail = wr.get("best_alt_name") or "sf_corr"

            # ── TASHKEEL DETECTION ──
            # Tier 1: tash_delta eff-adaptive (explicit ranges, no leaking)
            if status == "correct" and tash > -900:
                if eff > -0.5 and tash_delta >= 0.25:
                    status = "error"
                    error_type = "tashkeel"
                    error_detail = wr.get("best_tashkeel_name")
                elif -1.0 < eff <= -0.5 and tash_delta >= 0.06:
                    status = "error"
                    error_type = "tashkeel"
                    error_detail = wr.get("best_tashkeel_name")
                elif -1.5 < eff <= -1.0 and tash_delta >= 0.35:
                    status = "error"
                    error_type = "tashkeel"
                    error_detail = wr.get("best_tashkeel_name")

            # Tier 2: pc standalone (0% FP, eff-adaptive thresholds)
            if status == "correct" and pc < 900:
                if eff > -0.5 and pc < -5.0:
                    status = "error"
                    error_type = "tashkeel"
                    error_detail = f"pc_{wr.get('pc_expected_diac', '?')}_{wr.get('pc_heard_diac', '?')}"
                elif -1.0 < eff <= -0.5 and pc < -5.0:
                    status = "error"
                    error_type = "tashkeel"
                    error_detail = f"pc_{wr.get('pc_expected_diac', '?')}_{wr.get('pc_heard_diac', '?')}"
                elif -1.5 < eff <= -1.0 and pc < -4.0:
                    status = "error"
                    error_type = "tashkeel"
                    error_detail = f"pc_{wr.get('pc_expected_diac', '?')}_{wr.get('pc_heard_diac', '?')}"

            # Tier 3: gdm + tash_delta agreement (0% FP)
            if (status == "correct" and gdm_count >= 1
                    and eff > -0.5 and tash > -900 and tash_delta >= 0.10):
                status = "error"
                error_type = "tashkeel"
                error_detail = f"greedy_{wr.get('greedy_diac_expected', '?')}_{wr.get('greedy_diac_heard', '?')}"

            # Tier 4: tash_delta + strong corroboration (eff > -1.0)
            if (status == "correct" and tash > -900
                    and tash_delta >= 0.15 and eff > -1.0):
                if (pc < -5.0 or sf_delta < -5.0):
                    status = "error"
                    error_type = "tashkeel"
                    error_detail = wr.get("best_tashkeel_name")

            # Tier 5: Strong pc+sf agreement (both frame-level signals)
            if (status == "correct" and pc < -6.0 and sf_delta < -6.0
                    and eff > -1.0):
                status = "error"
                error_type = "tashkeel"
                error_detail = f"pc_sf_{wr.get('pc_expected_diac', '?')}_{wr.get('pc_heard_diac', '?')}"

            # Tier 6: sf + moderate tash_delta (0% FP, eff > -0.5)
            # td in [0.03, 0.20) avoids FP from correct words with
            # high td (~0.21-0.23) that happen to have sf<-3
            if (status == "correct" and tash > -900
                    and eff > -0.5
                    and sf_delta < -3.0
                    and tash_delta >= 0.03 and tash_delta < 0.20):
                status = "error"
                error_type = "tashkeel"
                error_detail = wr.get("best_tashkeel_name") or "sf_td"

            # Tier 7: tash_delta + sukoon_delta agreement (0% FP)
            sukoon_d = wr.get("best_sukoon_score", -999.0)
            sukoon_delta = (sukoon_d - eff) if sukoon_d > -900 else -999.0
            if (status == "correct" and tash > -900
                    and tash_delta >= 0.03
                    and sukoon_delta >= 0.15):
                status = "error"
                error_type = "tashkeel"
                error_detail = wr.get("best_tashkeel_name") or "sukoon_corr"

            # ── PHRASE-DIFFERENTIAL (pd) TIERS ──
            # pd uses full-phrase CTC context (more discriminative than per-word)
            pd_i3 = wr.get("pd_i3rab_delta", 0.0)
            pd_t = wr.get("pd_tashkeel_delta", 0.0)

            # pd i3rab: eff-adaptive thresholds (0% FP per stratum)
            if status == "correct" and pd_i3 > 0:
                if eff > -0.5 and pd_i3 >= 0.14:
                    status = "error"
                    error_type = "i3rab"
                    error_detail = wr.get("pd_i3rab_name") or "pd"
                elif -1.5 < eff <= -1.0 and pd_i3 >= 0.20:
                    status = "error"
                    error_type = "i3rab"
                    error_detail = wr.get("pd_i3rab_name") or "pd"

            # pd i3rab + per-word corroboration (0% FP)
            if (status == "correct"
                    and -1.0 < eff <= -0.5
                    and (wr["best_alt_score"] - eff if wr["best_alt_score"] > -900 else 0) >= 0.10
                    and pd_i3 >= 0.16):
                status = "error"
                error_type = "i3rab"
                error_detail = wr.get("best_alt_name") or "pd_corr"

            # pd tashkeel: eff-adaptive thresholds (0% FP per stratum)
            if status == "correct" and pd_t > 0:
                if -1.0 < eff <= -0.5 and pd_t >= 0.10:
                    status = "error"
                    error_type = "tashkeel"
                    error_detail = wr.get("pd_tashkeel_name") or "pd"
                elif -1.5 < eff <= -1.0 and pd_t >= 0.45:
                    status = "error"
                    error_type = "tashkeel"
                    error_detail = wr.get("pd_tashkeel_name") or "pd"

            # pd tashkeel + per-word corroboration at -1.5 to -1.0
            if (status == "correct"
                    and -1.5 < eff <= -1.0
                    and tash_delta >= 0.10
                    and pd_t >= 0.15):
                status = "error"
                error_type = "tashkeel"
                error_detail = wr.get("best_tashkeel_name") or "pd_corr"

            # pd i3rab + per-word corroboration at -1.5 to -1.0
            if (status == "correct"
                    and -1.5 < eff <= -1.0
                    and (wr["best_alt_score"] - eff if wr["best_alt_score"] > -900 else 0) >= 0.08
                    and pd_i3 >= 0.08):
                status = "error"
                error_type = "i3rab"
                error_detail = wr.get("best_alt_name") or "pd_corr"

            # Streaming penalty: require stronger signals
            if streaming and status == "error" and error_type in ("i3rab", "tashkeel"):
                # In streaming mode, only trust the strongest signals
                strong = (gfm
                          or (i3rab_delta >= 0.25 and error_type == "i3rab")
                          or (tash_delta >= 0.20 and error_type == "tashkeel")
                          or pc < -6.0)
                if not strong:
                    status = "correct"
                    error_type = None
                    error_detail = None

        # ── GBM fallback classifier ──
        # For words not caught by hand-tuned rules, use the trained GBM
        # with a high threshold to catch remaining errors.
        if status == "correct" and not streaming:
            gbm_prob, gbm_type = _classify_with_gbm(wr, word_text)
            if gbm_prob >= 0.75:
                status = "error"
                error_type = gbm_type
                error_detail = f"gbm_{gbm_prob:.2f}"

        scored.append({
            "idx": wi,
            "word": all_words[wi] if wi < len(all_words) else "",
            "status": status,
            "error_type": error_type,
            "error_detail": error_detail,
            "expected_word": wr.get("best_alt_word") or wr.get("best_tashkeel_word"),
            "greedy": wr.get("greedy_segment", ""),
            # Raw scores for debug overlay
            "debug": {
                "eff": round(eff, 3),
                "i3rab_delta": round(wr["best_alt_score"] - eff, 3) if wr["best_alt_score"] > -900 else None,
                "i3rab_name": wr.get("best_alt_name"),
                "tash_delta": round(wr.get("best_tashkeel_score", -999) - eff, 3) if wr.get("best_tashkeel_score", -999) > -900 else None,
                "tash_name": wr.get("best_tashkeel_name"),
                "sukoon_delta": round(wr.get("best_sukoon_score", -999) - eff, 3) if wr.get("best_sukoon_score", -999) > -900 else None,
                "sukoon_name": wr.get("best_sukoon_name"),
                "pc": round(wr.get("pc_worst_delta", 999), 2) if wr.get("pc_worst_delta", 999) < 900 else None,
                "shadda_delta": round(wr.get("best_shadda_score", -999) - eff, 3) if wr.get("best_shadda_score", -999) > -900 else None,
                "gdm": wr.get("greedy_diac_mismatches", 0),
                "gfm": wr.get("greedy_final_mismatch", False),
                "consonant_match": round(wr.get("greedy_consonant_match", 1.0), 2),
                "frame_count": wr.get("frame_count", 0),
                "sf_gop": round(wr.get("sf_worst_delta", 999), 3) if wr.get("sf_worst_delta", 999) < 900 else None,
                "mg": round(wr.get("mg_worst_margin", 999), 2) if wr.get("mg_worst_margin", 999) < 900 else None,
                "local_pd_i": round(wr.get("local_pd_i3rab", 0.0), 4),
                "local_pd_t": round(wr.get("local_pd_tashkeel", 0.0), 4),
                "fs": round(wr.get("fs_worst_delta", 999), 3) if wr.get("fs_worst_delta", 999) < 900 else None,
                "rescored_sf": round(wr.get("rescored_sf", 999), 3) if wr.get("rescored_sf", 999) < 900 else None,
                "rescored_pc": round(wr.get("rescored_pc", 999), 2) if wr.get("rescored_pc", 999) < 900 else None,
            },
        })
    scored.sort(key=lambda x: x["idx"])
    return scored


# ── WebSocket streaming endpoint ──

@app.websocket("/ws/score")
async def ws_score(websocket: WebSocket):
    """Stream audio as raw PCM float32 @ 16 kHz, get scored words back live."""
    await websocket.accept()

    # Origin check (if allowlist set)
    origin = websocket.headers.get("origin")
    if ALLOWED_ORIGINS is not None and origin not in ALLOWED_ORIGINS:
        await websocket.send_json({"type": "error", "code": "origin_denied",
                                   "message": f"origin not allowed: {origin}"})
        await websocket.close(1008)
        return

    # First message: JSON with passage_id
    try:
        init = await websocket.receive_json()
    except Exception:
        await websocket.close(1008, "Expected JSON init message")
        return

    # Auth check (if secret set)
    if AUTH_SECRET:
        token = init.get("auth_token")
        if not token or not verify_auth_token(AUTH_SECRET, token, expected_origin=origin):
            await websocket.send_json({"type": "error", "code": "auth_failed",
                                       "message": "invalid or expired auth_token"})
            await websocket.close(1008)
            return

    # Debug gate
    if init.get("debug") and not ALLOW_DEBUG:
        init["debug"] = False

    # Accept either inline {passage: {phrases: [...]}} or stored {passage_id: "..."}
    try:
        phrases, log_info = parse_ws_init(init, load_passages)
    except ValueError as exc:
        await websocket.send_json({"error": str(exc)})
        await websocket.close(1008)
        return

    all_words = " ".join(phrases).split()

    from engine import StreamingSession
    session = StreamingSession(engine, phrases)

    # Session logging: save audio + scores for offline analysis
    log_enabled = init.get("debug", False)
    log_dir = None
    audio_log = None
    score_log = []
    if log_enabled:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_label = log_info["log_label"]
        log_dir = SESSION_LOG_DIR / f"{ts}_{log_label}"
        log_dir.mkdir(parents=True, exist_ok=True)
        audio_log = open(log_dir / "audio.raw", "wb")
        # Save session metadata
        (log_dir / "meta.json").write_text(json.dumps({
            "passage_id": log_info["passage_id"],
            "inline_id": log_info["inline_id"],
            "phrases": phrases,
            "timestamp": ts,
        }, ensure_ascii=False, indent=2))

    last_scored_bytes = 0
    BYTES_PER_SEC = 16000 * 4  # float32 @ 16 kHz
    first_score_sent = False
    scoring_lock = asyncio.Lock()
    session_start = time.time()
    session_id = uuid.uuid4().hex[:8]
    PING_INTERVAL = 30
    IDLE_TIMEOUT = 60

    jlog("session_start", session_id=session_id, origin=origin, passage_phrases=len(phrases))

    async def pinger():
        while True:
            await asyncio.sleep(PING_INTERVAL)
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break

    ping_task = asyncio.create_task(pinger())

    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive(), timeout=IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                # Client idle for IDLE_TIMEOUT seconds; close the connection.
                try:
                    await websocket.close(1008)
                finally:
                    break
            if msg["type"] == "websocket.disconnect":
                break

            # Session cap check
            if time.time() - session_start > MAX_SESSION_SEC:
                await websocket.send_json({"type": "error", "code": "session_too_long",
                                           "message": "max session duration exceeded"})
                await websocket.close(1008)
                break

            raw = msg.get("bytes")
            text = msg.get("text")

            # Client pong → noop
            if text == "pong":
                continue

            # "done" signal from client → final scoring with batch thresholds
            if text == "done":
                loop = asyncio.get_event_loop()
                scored = await loop.run_in_executor(
                    None, lambda: session.score_cycle(final=True))
                if scored:
                    words = classify_words(list(scored.values()), all_words,
                                           streaming=False)
                    resp = {
                        "words": words,
                        "matched_phrase_idx": session.cursor_phrase,
                        "final": True,
                    }
                    await websocket.send_json(resp)
                    if log_dir:
                        score_log.append({"type": "final", "response": resp})
                break

            # append_phrases: extend the phrase list mid-session
            if text:
                try:
                    msg = json.loads(text)
                except (ValueError, TypeError):
                    msg = None
                if isinstance(msg, dict) and msg.get("type") == "append_phrases":
                    new_phrases = msg.get("phrases", [])
                    if isinstance(new_phrases, list):
                        session.extend_phrases(new_phrases)
                        # Refresh all_words to reflect the extended list
                        all_words = session.all_words
                    continue

            if not raw:
                continue

            session.append_audio(raw)
            if audio_log:
                audio_log.write(raw)

            new_bytes = session.total_audio_bytes - last_scored_bytes

            # Throttle: faster for first score, slower after
            min_new = 0.5 if not first_score_sent else 0.75
            if new_bytes < min_new * BYTES_PER_SEC:
                continue

            if scoring_lock.locked():
                continue  # skip if still scoring previous chunk

            async with scoring_lock:
                snap = session.total_audio_bytes
                loop = asyncio.get_event_loop()
                scored = await loop.run_in_executor(None, session.score_cycle)
                last_scored_bytes = snap

                if scored:
                    words = classify_words(list(scored.values()), all_words,
                                           streaming=True)
                    resp = {
                        "words": words,
                        "matched_phrase_idx": session.cursor_phrase,
                    }
                    await websocket.send_json(resp)
                    jlog("score_cycle", session_id=session_id,
                         audio_bytes=session.total_audio_bytes,
                         cursor=session.cursor_phrase)
                    if log_dir:
                        score_log.append({
                            "type": "streaming",
                            "audio_bytes": snap,
                            "response": resp,
                        })
                    first_score_sent = True

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass
    finally:
        ping_task.cancel()
        jlog("session_end", session_id=session_id,
             duration_sec=int(time.time() - session_start))
        if audio_log:
            audio_log.close()
        if log_dir and score_log:
            (log_dir / "scores.json").write_text(
                json.dumps(score_log, ensure_ascii=False, indent=2))



@app.post("/api/save")
async def save(
    audio: UploadFile = File(...),
    passage_id: str = Form(...),
    phrase_idx: int = Form(0),
    notes: str = Form(""),
):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_p{phrase_idx}.webm"
    (TEST_DIR / filename).write_bytes(await audio.read())

    with open(MANIFEST, "a") as f:
        f.write(json.dumps({
            "file": f"recordings/{filename}",
            "passage_id": passage_id,
            "phrase_idx": phrase_idx,
            "notes": notes,
            "timestamp": ts,
        }, ensure_ascii=False) + "\n")

    return {"saved": filename}


@app.get("/api/recordings")
async def list_recordings():
    if not MANIFEST.exists():
        return {"recordings": []}
    entries = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    return {"recordings": entries}


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
