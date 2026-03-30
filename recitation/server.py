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

TEST_DIR = BASE_DIR / "test_data" / "recordings"
MANIFEST = BASE_DIR / "test_data" / "manifest.jsonl"
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


I3RAB_THRESHOLD = 0.08
TASHKEEL_THRESHOLD = 0.15


def classify_words(word_results, all_words):
    """Turn raw engine results into classified word dicts."""
    scored = []
    for wr in word_results:
        wi = wr["word_idx"]
        eff = wr["effective_score"]
        status = "correct"
        error_type = None
        error_detail = None

        alt = wr["best_alt_score"]
        if alt > -900 and alt > eff + I3RAB_THRESHOLD:
            status = "error"
            error_type = "i3rab"
            error_detail = wr["best_alt_name"]

        if status == "correct":
            tash = wr.get("best_tashkeel_score", -999.0)
            if tash > -900 and tash > eff + TASHKEEL_THRESHOLD:
                status = "error"
                error_type = "tashkeel"
                error_detail = wr.get("best_tashkeel_name")

        scored.append({
            "idx": wi,
            "word": all_words[wi] if wi < len(all_words) else "",
            "status": status,
            "error_type": error_type,
            "error_detail": error_detail,
            "expected_word": wr.get("best_alt_word") or wr.get("best_tashkeel_word"),
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

    last_scored_bytes = 0
    BYTES_PER_SEC = 16000 * 4  # float32 @ 16 kHz
    MIN_NEW_SECS = 1.0
    scoring_lock = asyncio.Lock()

    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                break

            raw = msg.get("bytes")
            text = msg.get("text")

            # "done" signal from client → final scoring
            if text == "done":
                loop = asyncio.get_event_loop()
                scored = await loop.run_in_executor(None, session.score_cycle)
                if scored:
                    words = classify_words(list(scored.values()), all_words)
                    await websocket.send_json({
                        "words": words,
                        "matched_phrase_idx": session.cursor_phrase,
                        "final": True,
                    })
                break

            if not raw:
                continue

            session.append_audio(raw)
            new_bytes = session.total_audio_bytes - last_scored_bytes

            if session.total_audio_secs < 2.0:
                continue

            if new_bytes < MIN_NEW_SECS * BYTES_PER_SEC:
                continue

            if scoring_lock.locked():
                continue  # skip if still scoring previous chunk

            async with scoring_lock:
                snap = session.total_audio_bytes
                loop = asyncio.get_event_loop()
                scored = await loop.run_in_executor(None, session.score_cycle)
                last_scored_bytes = snap

                if scored:
                    words = classify_words(list(scored.values()), all_words)
                    await websocket.send_json({
                        "words": words,
                        "matched_phrase_idx": session.cursor_phrase,
                    })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass



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
