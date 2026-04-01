"""Recitation assessment server — serves the UI and scores audio."""
import asyncio
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import torch

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from arabic import strip_diacritics

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


# Batch thresholds (full recording, "done" signal)
BATCH_I3RAB = 0.10
BATCH_TASHKEEL = 0.12
BATCH_PC_TIER1_DELTA = -4.5
BATCH_PC_TIER1_EFF = -0.7
BATCH_PC_TIER2_DELTA = -2.5
BATCH_PC_TIER2_EFF = -0.3

# Streaming thresholds (partial audio, more conservative)
STREAM_I3RAB = 0.15
STREAM_TASHKEEL = 0.20
STREAM_PC_TIER1_DELTA = -6.0
STREAM_PC_TIER1_EFF = -0.7
STREAM_PC_TIER2_DELTA = -3.5
STREAM_PC_TIER2_EFF = -0.3

# Per-char tier 3 (wider eff gate for very negative pc values)
BATCH_PC_TIER3_DELTA = -3.5
BATCH_PC_TIER3_EFF = -0.7
STREAM_PC_TIER3_DELTA = -5.0
STREAM_PC_TIER3_EFF = -0.7

# SF-GOP thresholds (standalone — confirmation below)
BATCH_SF_GOP_DELTA = -6.0
BATCH_MG_MARGIN = -8.0
STREAM_SF_GOP_DELTA = -8.0
STREAM_MG_MARGIN = -10.0


def classify_words(word_results, all_words, streaming=False):
    """Turn raw engine results into classified word dicts."""
    # Select thresholds based on mode
    if streaming:
        i3rab_t, tash_t = STREAM_I3RAB, STREAM_TASHKEEL
        pc1_d, pc1_e = STREAM_PC_TIER1_DELTA, STREAM_PC_TIER1_EFF
        pc2_d, pc2_e = STREAM_PC_TIER2_DELTA, STREAM_PC_TIER2_EFF
        pc3_d, pc3_e = STREAM_PC_TIER3_DELTA, STREAM_PC_TIER3_EFF
        sf_t, mg_t = STREAM_SF_GOP_DELTA, STREAM_MG_MARGIN
    else:
        i3rab_t, tash_t = BATCH_I3RAB, BATCH_TASHKEEL
        pc1_d, pc1_e = BATCH_PC_TIER1_DELTA, BATCH_PC_TIER1_EFF
        pc2_d, pc2_e = BATCH_PC_TIER2_DELTA, BATCH_PC_TIER2_EFF
        pc3_d, pc3_e = BATCH_PC_TIER3_DELTA, BATCH_PC_TIER3_EFF
        sf_t, mg_t = BATCH_SF_GOP_DELTA, BATCH_MG_MARGIN

    scored = []
    for wr in word_results:
        wi = wr["word_idx"]
        eff = wr["effective_score"]
        status = "correct"
        error_type = None
        error_detail = None

        # Signal 0: Wrong word (completely different consonant structure)
        consonant_match = wr.get("greedy_consonant_match", 1.0)
        frame_count = wr.get("frame_count", 999)
        word_text = wr.get("word", "")
        word_consonants = strip_diacritics(word_text)
        greedy_seg = wr.get("greedy_segment", "")
        # Tier 1: decent eff but consonants don't match
        if (len(word_consonants) >= 3 and eff > -1.0
                and consonant_match < 0.4 and len(greedy_seg) > 0
                and frame_count <= 50):
            status = "error"
            error_type = "wrong"
            error_detail = greedy_seg
        # Tier 2: Whisper + CTC wrong word detection.
        # Whisper alone is too noisy (especially on short clips), so require
        # CTC confirmation: word not heard by Whisper AND poor CTC score.
        whisper_match = wr.get("whisper_match", True)
        if (status == "correct" and not whisper_match
                and eff < -1.5
                and len(word_consonants) >= 2
                and frame_count >= 5):
            status = "error"
            error_type = "wrong"
            error_detail = "whisper_mismatch"

        # Signal -1: Skipped word (very few frames + very poor score + not a short word)
        if (status == "correct" and frame_count < 3 and eff < -3.5
                and len(word_consonants) >= 3):
            status = "error"
            error_type = "skipped"
            error_detail = None

        # Signal 1: CTC hypothesis scoring (i3rab)
        if status == "correct":
            alt = wr["best_alt_score"]
            if alt > -900 and alt > eff + i3rab_t:
                status = "error"
                error_type = "i3rab"
                error_detail = wr["best_alt_name"]

        # Signal 2: CTC hypothesis scoring (tashkeel — vowel swap)
        if status == "correct":
            tash = wr.get("best_tashkeel_score", -999.0)
            if tash > -900 and tash > eff + tash_t:
                status = "error"
                error_type = "tashkeel"
                error_detail = wr.get("best_tashkeel_name")

        # Signal 2b: CTC hypothesis scoring (sukoon — higher threshold, CTC length bias)
        if status == "correct":
            sukoon_alt = wr.get("best_sukoon_score", -999.0)
            if sukoon_alt > -900 and sukoon_alt > eff + tash_t + 0.10:
                status = "error"
                error_type = "tashkeel"
                error_detail = wr.get("best_sukoon_name")

        # Signal 3: Per-char diacritic confidence (three-tier quality gate)
        if status == "correct":
            pc = wr.get("pc_worst_delta", 999.0)
            if (pc < pc1_d and eff > pc1_e) or \
               (pc < pc2_d and eff > pc2_e) or \
               (pc < pc3_d and eff > pc3_e):
                status = "error"
                error_type = "diacritic"
                expected = wr.get("pc_expected_diac", "?")
                heard = wr.get("pc_heard_diac", "?")
                error_detail = f"pc_{expected}_{heard}"

        # Signal 4: Shadda-position diacritic scoring (higher threshold)
        if status == "correct":
            shadda_score = wr.get("best_shadda_score", -999.0)
            shadda_thresh = 0.25 if streaming else 0.20
            if shadda_score > -900 and shadda_score > eff + shadda_thresh:
                status = "error"
                error_type = "tashkeel"
                error_detail = wr.get("best_shadda_name")

        # Signal 5: Greedy internal diacritic mismatch (tashkeel)
        # Requires CTC or per-char confirmation to avoid greedy decode noise
        # Streaming uses same gate as batch — greedy is unreliable on partial audio
        greedy_eff_gate = -0.5
        greedy_confirm = 0.05 if not streaming else 0.10
        if status == "correct":
            gdm_count = wr.get("greedy_diac_mismatches", 0)
            if gdm_count >= 1 and eff > greedy_eff_gate:
                tash = wr.get("best_tashkeel_score", -999.0)
                pc = wr.get("pc_worst_delta", 999.0)
                if (tash > -900 and tash > eff + greedy_confirm) or pc < -2.0:
                    status = "error"
                    error_type = "tashkeel"
                    expected = wr.get("greedy_diac_expected", "?")
                    heard = wr.get("greedy_diac_heard", "?")
                    error_detail = f"greedy_{expected}_{heard}"

        # Signal 5b: Confirmed greedy (batch only) — greedy mismatch + stricter
        if status == "correct" and not streaming:
            gdm_count = wr.get("greedy_diac_mismatches", 0)
            if gdm_count >= 1 and -1.5 < eff <= -1.0:
                tash = wr.get("best_tashkeel_score", -999.0)
                pc = wr.get("pc_worst_delta", 999.0)
                if (tash > -900 and tash > eff + 0.03) or pc < -3.0:
                    status = "error"
                    error_type = "tashkeel"
                    expected = wr.get("greedy_diac_expected", "?")
                    heard = wr.get("greedy_diac_heard", "?")
                    error_detail = f"confirmed_greedy_{expected}_{heard}"

        # Signal 6: Greedy final diacritic mismatch (i3rab) + per-char confirmation
        if status == "correct":
            gfm = wr.get("greedy_final_mismatch", False)
            pc = wr.get("pc_worst_delta", 999.0)
            if gfm and pc < -2.0 and eff > -1.6:
                status = "error"
                error_type = "i3rab"
                error_detail = "greedy_final"

        # Signal 7: Segmentation-Free GOP standalone (very conservative)
        if status == "correct":
            sf_delta = wr.get("sf_worst_delta", 999.0)
            if sf_delta < sf_t and eff > -1.6:
                status = "error"
                error_type = "tashkeel"
                error_detail = f"sf_gop_{wr.get('sf_worst_expected', '?')}_{wr.get('sf_worst_heard', '?')}"

        # Signal 7c: Confirmed tashkeel — CTC near-threshold + SF-GOP agrees
        # CTC tashkeel alt is close to threshold; SF-GOP strongly negative
        if status == "correct" and eff > -0.5:
            tash = wr.get("best_tashkeel_score", -999.0)
            sf_delta = wr.get("sf_worst_delta", 999.0)
            half_t = tash_t / 2
            if (tash > -900 and tash > eff + half_t and sf_delta < -3.5):
                status = "error"
                error_type = "tashkeel"
                error_detail = f"confirmed_sf_{wr.get('best_tashkeel_name', '?')}"

        # Signal 8: MixGoP — disabled (GMMs need more training data;
        # 23% of correct words have negative margin, too noisy for use).
        # Infrastructure kept in engine.py for future use.

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
            },
        })
    scored.sort(key=lambda x: x["idx"])
    return scored


# ── WebSocket streaming endpoint ──

@app.websocket("/ws/score")
async def ws_score(websocket: WebSocket):
    """Stream audio as raw PCM float32 @ 16 kHz, get scored words back live."""
    await websocket.accept()

    # First message: JSON with passage_id
    try:
        init = await websocket.receive_json()
    except Exception:
        await websocket.close(1008, "Expected JSON init message")
        return

    passage_id = init.get("passage_id")
    data = load_passages()
    passage = next((p for p in data["passages"] if p["id"] == passage_id), None)
    if not passage or "phrases" not in passage:
        await websocket.send_json({"error": "Passage not found"})
        await websocket.close(1008)
        return

    phrases = passage["phrases"]
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
        log_dir = SESSION_LOG_DIR / f"{ts}_{passage_id}"
        log_dir.mkdir(parents=True, exist_ok=True)
        audio_log = open(log_dir / "audio.raw", "wb")
        # Save session metadata
        (log_dir / "meta.json").write_text(json.dumps({
            "passage_id": passage_id,
            "phrases": phrases,
            "timestamp": ts,
        }, ensure_ascii=False, indent=2))

    last_scored_bytes = 0
    BYTES_PER_SEC = 16000 * 4  # float32 @ 16 kHz
    first_score_sent = False
    scoring_lock = asyncio.Lock()

    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                break

            raw = msg.get("bytes")
            text = msg.get("text")

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
