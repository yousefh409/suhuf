#!/usr/bin/env python3
"""i3rab web server - FastAPI backend for Arabic recitation correction."""

import os
import io
import json
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

import numpy as np
import soundfile as sf
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from i3rab.models import DiffKind, Confidence
from i3rab.arabic import normalize_arabic, format_haraka_list
from i3rab.book import Book
from i3rab.pipeline import I3rabPipeline
from i3rab.config import Config

load_dotenv()

SAMPLE_RATE = 16000

# Default reference paragraph
DEFAULT_REFERENCE = (
    "قَرَأَ الطَّالِبُ الكِتَابَ فِي المَكْتَبَةِ"
    " وَكَتَبَ المُعَلِّمُ الدَّرْسَ عَلَى السَّبُّورَةِ"
    " ثُمَّ سَأَلَ الطُّلَّابُ عَنِ القَوَاعِدِ النَّحْوِيَّةِ"
    " فَشَرَحَ المُعَلِّمُ الإِجَابَةَ بِوُضُوحٍ"
)

# ── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(title="i3rab")

# CORS for Expo dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline: I3rabPipeline | None = None
openai_client = None
current_book: Book | None = None

# PDF pipeline state
pdf_documents: dict[str, dict] = {}  # doc_id -> {path, hash, pages, analysis_status, ...}
analysis_progress: dict[str, dict] = {}  # doc_id -> {current, total, status}
analysis_cache = None


@app.on_event("startup")
async def startup():
    global pipeline, openai_client, current_book, analysis_cache

    config = Config()

    # Create upload and cache directories
    Path(config.pdf_upload_dir).mkdir(exist_ok=True)
    Path(config.cache_dir).mkdir(exist_ok=True)

    # Initialize analysis cache
    from i3rab.cache import AnalysisCache
    analysis_cache = AnalysisCache(config.cache_dir)

    # Create default book from reference sentence
    current_book = Book.from_sentence(DEFAULT_REFERENCE)
    pipeline = I3rabPipeline(current_book, config)
    pipeline.load_models()

    # Optional: OpenAI for i3rab explanations
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        from openai import OpenAI
        openai_client = OpenAI(api_key=api_key)
        print("OpenAI client ready (for i3rab explanations).")
    else:
        print("WARNING: No OPENAI_API_KEY — i3rab explanations will not work.")


# ── API models ───────────────────────────────────────────────────────────────


class ExplainRequest(BaseModel):
    word: str
    sentence: str


class LoadBookRequest(BaseModel):
    text: str
    title: str = ""


class SwitchModelRequest(BaseModel):
    model_type: str  # "pcd" or "ssl"
    model_path: str = ""  # specific model path/dir (optional)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _read_audio(audio_bytes: bytes) -> np.ndarray:
    """Read audio bytes into float32 numpy array at 16kHz.

    Supports WAV (via soundfile) and webm/ogg/mp3 (via PyAV).
    """
    # Try soundfile first (WAV, FLAC, OGG)
    try:
        audio_data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    except Exception:
        # Fallback to PyAV for webm/opus/mp3
        import av
        container = av.open(io.BytesIO(audio_bytes))
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        frames = []
        for frame in container.decode(audio=0):
            for r in resampler.resample(frame):
                frames.append(r.to_ndarray().flatten())
        container.close()
        if not frames:
            raise ValueError("No audio data decoded")
        audio_data = np.concatenate(frames).astype(np.float32) / 32768.0
        return audio_data

    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)
    if sr != SAMPLE_RATE:
        from scipy.signal import resample
        num_samples = int(len(audio_data) * SAMPLE_RATE / sr)
        audio_data = resample(audio_data, num_samples).astype(np.float32)
    return audio_data


def _serialize_results(results, transcript, score):
    """Serialize evaluation results to JSON."""
    results_json = []
    for wd in results:
        haraka_diffs = []
        for hd in wd.haraka_diffs:
            haraka_diffs.append({
                "letter": hd.letter,
                "position": hd.position,
                "expected": format_haraka_list(hd.expected),
                "got": format_haraka_list(hd.got),
                "is_irab": hd.is_irab,
            })
        results_json.append({
            "kind": wd.kind.value,
            "ref_word": wd.ref_word,
            "hyp_word": wd.hyp_word,
            "haraka_diffs": haraka_diffs,
            "confidence": wd.confidence.value if isinstance(wd.confidence, Confidence) else "high",
            "detected_case": wd.detected_case,
            "expected_case": wd.expected_case,
        })

    return {
        "transcript": transcript,
        "results": results_json,
        "score": score,
    }


# ── Routes ───────────────────────────────────────────────────────────────────


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/api/reference")
async def get_reference():
    """Get current reference text with indexed words."""
    if current_book and current_book.phrases:
        ref = " ".join(p.text for p in current_book.phrases)
        words = [{"index": w.index, "text": w.correct_diac} for w in current_book.words]
    else:
        ref = normalize_arabic(DEFAULT_REFERENCE)
        words = [{"index": i, "text": w} for i, w in enumerate(ref.split())]
    return {
        "reference": ref,
        "words": words,
        "title": current_book.title if current_book else "",
        "num_phrases": len(current_book.phrases) if current_book else 1,
    }


@app.post("/api/book/load")
async def load_book(req: LoadBookRequest):
    """Load a new book text for assessment."""
    global current_book, pipeline

    current_book = Book.from_text(req.text, title=req.title)
    pipeline = I3rabPipeline(current_book, Config())
    pipeline.load_models()

    return {
        "title": current_book.title,
        "num_words": len(current_book.words),
        "num_phrases": len(current_book.phrases),
        "phrases": [
            {
                "idx": i,
                "text": p.text,
                "num_words": len(p.words),
                "start_idx": p.start_idx,
                "end_idx": p.end_idx,
            }
            for i, p in enumerate(current_book.phrases)
        ],
    }


@app.get("/api/book/phrase/{phrase_idx}")
async def get_phrase(phrase_idx: int):
    """Get a specific phrase from the book."""
    if not current_book or phrase_idx >= len(current_book.phrases):
        return {"error": "Phrase not found"}

    phrase = current_book.phrases[phrase_idx]
    return {
        "idx": phrase_idx,
        "text": phrase.text,
        "words": [
            {
                "index": w.index,
                "base": w.base,
                "diacritized": w.correct_diac,
                "num_hypotheses": len(w.hypotheses),
                "allows_pausal": w.allows_pausal,
            }
            for w in phrase.words
        ],
    }


@app.post("/api/transcribe")
async def transcribe_audio_endpoint(audio: UploadFile = File(...)):
    """Transcribe and evaluate audio against current book/reference.

    Uses hypothesis scoring: for each word, scores all possible
    diacritizations against the audio and picks the best match.
    """
    if not pipeline:
        return {"error": "Pipeline not loaded."}

    audio_bytes = await audio.read()
    audio_data = _read_audio(audio_bytes)

    # Use the pipeline's evaluate method
    if current_book and len(current_book.words) > 1:
        result = pipeline.evaluate_phrase(audio_data)
    else:
        result = pipeline.evaluate_simple(audio_data, DEFAULT_REFERENCE)

    return _serialize_results(
        result["results"],
        result["transcript"],
        result["score"],
    )


@app.post("/api/transcribe/position")
async def transcribe_position(audio: UploadFile = File(...)):
    """Quick transcription to track reading position during recording.

    Returns which reference words have been read so far, without scoring.
    Does NOT advance the tracker — safe for repeated calls during recording.
    """
    if not pipeline or not current_book:
        return {"matched_indices": []}

    audio_bytes = await audio.read()
    audio_data = _read_audio(audio_bytes)

    transcript = pipeline.scorer.transcribe(audio_data)
    transcript_normalized = normalize_arabic(transcript)

    if not transcript_normalized.strip():
        return {"transcript": "", "matched_indices": []}

    # Match against book without advancing tracker position
    saved_pos = pipeline.tracker.current_position
    _, _, matched_pairs = pipeline.tracker.locate(transcript_normalized)
    pipeline.tracker.current_position = saved_pos

    matched_indices = [bw.index for bw, _ in matched_pairs]

    return {
        "transcript": transcript_normalized,
        "matched_indices": matched_indices,
    }


@app.post("/api/transcribe/live")
async def transcribe_live(
    audio: UploadFile = File(...),
    scored_indices: str = Form(""),
):
    """Live transcription + scoring during recording.

    Returns position tracking AND scoring results for newly-read words.
    Already-scored word indices can be passed to avoid re-scoring.
    Does NOT advance the tracker — safe for repeated calls during recording.
    """
    if not pipeline or not current_book:
        return {"matched_indices": [], "scored_words": []}

    audio_bytes = await audio.read()
    audio_data = _read_audio(audio_bytes)

    # Parse already-scored indices
    already_scored = set()
    if scored_indices:
        already_scored = {int(x) for x in scored_indices.split(",") if x.strip()}

    # Transcribe
    transcript = pipeline.scorer.transcribe(audio_data)
    transcript_normalized = normalize_arabic(transcript)

    if not transcript_normalized.strip():
        return {"transcript": "", "matched_indices": [], "scored_words": []}

    # Match against book without advancing tracker
    saved_pos = pipeline.tracker.current_position
    _, _, matched_pairs = pipeline.tracker.locate(transcript_normalized)
    pipeline.tracker.current_position = saved_pos

    matched_indices = [bw.index for bw, _ in matched_pairs]

    # Score only new (unscored) words
    new_pairs = [(bw, hyp) for bw, hyp in matched_pairs if bw.index not in already_scored]
    scored_words = []

    if new_pairs:
        all_matched_words = [bw for bw, _ in matched_pairs]
        encoder_outputs = pipeline.scorer._get_encoder_output(audio_data)

        for book_word, hyp_text in new_pairs:
            scored = pipeline.scorer.score_word_in_context(
                audio_data, book_word, all_matched_words, encoder_outputs
            )
            diff = pipeline._build_word_diff(book_word, hyp_text, scored)

            haraka_diffs_json = []
            for hd in diff.haraka_diffs:
                haraka_diffs_json.append({
                    "letter": hd.letter,
                    "position": hd.position,
                    "expected": format_haraka_list(hd.expected),
                    "got": format_haraka_list(hd.got),
                    "is_irab": hd.is_irab,
                })

            scored_words.append({
                "index": book_word.index,
                "kind": diff.kind.value,
                "ref_word": diff.ref_word,
                "hyp_word": diff.hyp_word,
                "haraka_diffs": haraka_diffs_json,
                "confidence": diff.confidence.value if isinstance(diff.confidence, Confidence) else "high",
                "detected_case": diff.detected_case,
                "expected_case": diff.expected_case,
            })

    return {
        "transcript": transcript_normalized,
        "matched_indices": matched_indices,
        "scored_words": scored_words,
    }


@app.post("/api/transcribe/stream")
async def transcribe_audio_stream(audio: UploadFile = File(...)):
    """Stream transcription and word-by-word evaluation results via SSE."""
    if not pipeline:
        return {"error": "Pipeline not loaded."}

    # Reset tracker for fresh evaluation
    pipeline.tracker.reset()

    audio_bytes = await audio.read()
    audio_data = _read_audio(audio_bytes)

    def event_generator():
        try:
            for ev in pipeline.evaluate_phrase_streaming(audio_data):
                event_type = ev["event"]
                payload = {k: v for k, v in ev.items() if k != "event"}
                data_json = json.dumps(payload, ensure_ascii=False)
                yield f"event: {event_type}\ndata: {data_json}\n\n"
        except Exception as e:
            error_json = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_json}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/transcribe/pcd")
async def transcribe_pcd_endpoint(audio: UploadFile = File(...)):
    """Transcribe and evaluate using PCD model (direct diacritized transcription).

    The PCD model outputs fully diacritized Arabic text, which is then
    compared word-by-word against the reference.
    """
    if not pipeline:
        return {"error": "Pipeline not loaded."}

    audio_bytes = await audio.read()
    audio_data = _read_audio(audio_bytes)

    try:
        result = pipeline.evaluate_pcd(audio_data)
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}

    response = _serialize_results(
        result["results"],
        result["transcript"],
        result["score"],
    )
    response["mode"] = "pcd"
    response["words_assessed"] = result.get("words_assessed", [])
    return response


@app.post("/api/transcribe/pcd/live")
async def transcribe_pcd_live(
    audio: UploadFile = File(...),
    scored_indices: str = Form(""),
):
    """Live PCD transcription + scoring during recording.

    Like /api/transcribe/live but uses the PCD model for diacritized output.
    Does NOT advance the tracker — safe for repeated calls.
    """
    if not pipeline or not current_book:
        return {"matched_indices": [], "scored_words": []}

    audio_bytes = await audio.read()
    audio_data = _read_audio(audio_bytes)

    already_scored = set()
    if scored_indices:
        already_scored = {int(x) for x in scored_indices.split(",") if x.strip()}

    try:
        return pipeline.evaluate_pcd_live(audio_data, already_scored)
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}


@app.post("/api/phrase/evaluate")
async def evaluate_phrase_endpoint(
    audio: UploadFile = File(...),
    phrase_idx: int = Form(0),
):
    """Evaluate audio for a specific phrase in the book."""
    if not pipeline or not current_book:
        return {"error": "No book loaded."}

    if phrase_idx >= len(current_book.phrases):
        return {"error": "Phrase index out of range."}

    audio_bytes = await audio.read()
    audio_data = _read_audio(audio_bytes)

    result = pipeline.evaluate_phrase(audio_data)

    response = _serialize_results(
        result["results"],
        result["transcript"],
        result["score"],
    )
    response["phrase_idx"] = result.get("phrase_idx")
    response["words_assessed"] = result.get("words_assessed", [])
    return response


@app.post("/api/explain")
async def explain_irab(req: ExplainRequest):
    """Use GPT-4o to explain the i3rab of a word."""
    if not openai_client:
        return {"explanation": "OpenAI API key not configured."}

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert Arabic grammarian. "
                    "Explain the i3rab of the given word in the context of the sentence. "
                    "Include: its grammatical role, the case marking, and the grammar rule. "
                    "Respond in Arabic with English translations of technical terms in parentheses. "
                    "Be concise."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"The sentence: {req.sentence}\n"
                    f"The word: {req.word}\n\n"
                    "Explain the i3rab of this word."
                ),
            },
        ],
        temperature=0.3,
        max_tokens=500,
    )
    return {"explanation": response.choices[0].message.content}


@app.get("/api/config/models")
async def list_available_models():
    """List all available PCD and SSL models."""
    models_dir = Path("models")
    pcd_models = []
    ssl_models = []

    if models_dir.exists():
        for f in sorted(models_dir.iterdir()):
            if f.suffix == ".nemo":
                pcd_models.append({"name": f.stem, "path": str(f)})
            elif f.is_dir() and (f / "config.json").exists():
                ssl_models.append({"name": f.name, "path": str(f)})

    # Determine active model
    active_type = "pcd"
    active_path = pipeline.config.pcd_model_path if pipeline else ""
    if pipeline and pipeline.config.ssl_model_dir:
        active_type = "ssl"
        active_path = pipeline.config.ssl_model_dir

    return {
        "pcd_models": pcd_models,
        "ssl_models": ssl_models,
        "active": {"type": active_type, "path": active_path},
    }


@app.post("/api/config/model")
async def switch_model(req: SwitchModelRequest):
    """Switch between PCD (NeMo) and SSL (XLS-R) models at runtime."""
    global pipeline

    if not pipeline:
        return {"error": "Pipeline not loaded"}

    if req.model_type == "ssl":
        model_dir = req.model_path or "models/ssl_xls_r_16k"
        if not Path(model_dir).exists():
            return {"error": f"SSL model not found: {model_dir}"}
        pipeline.config.ssl_model_dir = model_dir
    elif req.model_type == "pcd":
        model_path = req.model_path or "models/pcd_clartts_v4.nemo"
        if not Path(model_path).exists():
            return {"error": f"PCD model not found: {model_path}"}
        pipeline.config.ssl_model_dir = ""
        pipeline.config.pcd_model_path = model_path
    else:
        return {"error": f"Unknown model type: {req.model_type}"}

    # Clear cached transcriber so it reloads with new config
    pipeline._pcd_transcriber = None

    active_type = "ssl" if pipeline.config.ssl_model_dir else "pcd"
    active_path = pipeline.config.ssl_model_dir or pipeline.config.pcd_model_path

    return {
        "status": "ok",
        "active": {"type": active_type, "path": active_path},
    }


@app.post("/api/reset")
async def reset_tracker():
    """Reset the position tracker to the beginning."""
    if pipeline:
        pipeline.reset()
    return {"status": "ok"}


# ── Test dataset endpoints ───────────────────────────────────────────────────

TEST_DATA_DIR = Path("test_data")
MANIFEST_PATH = TEST_DATA_DIR / "manifest.json"


def _load_manifest() -> list[dict]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return []


def _save_manifest(manifest: list[dict]):
    TEST_DATA_DIR.mkdir(exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))


@app.get("/test")
async def test_page():
    return FileResponse("static/test.html")


@app.post("/api/test/record")
async def test_record(
    audio: UploadFile = File(...),
    word_diacritized: str = Form(""),
    intended_case: str = Form(""),
    sentence_context: str = Form(""),
    rec_type: str = Form("word"),
    text_diacritized: str = Form(""),
):
    """Save a test recording to disk with its label.

    For word recordings: word_diacritized + intended_case required.
    For sentence recordings: text_diacritized required (full diacritized sentence).
    """
    manifest = _load_manifest()
    existing_nums = []
    for e in manifest:
        try:
            existing_nums.append(int(e["id"].split("_")[1]))
        except (IndexError, ValueError):
            pass
    rec_num = (max(existing_nums) + 1) if existing_nums else 1
    rec_id = f"rec_{rec_num:03d}"

    # Determine file extension from upload
    ext = "webm"
    if audio.content_type and "wav" in audio.content_type:
        ext = "wav"
    elif audio.content_type and "mp4" in audio.content_type:
        ext = "mp4"

    filename = f"{rec_id}.{ext}"
    TEST_DATA_DIR.mkdir(exist_ok=True)
    filepath = TEST_DATA_DIR / filename

    audio_bytes = await audio.read()
    filepath.write_bytes(audio_bytes)

    from i3rab.arabic import strip_harakat

    if rec_type == "sentence":
        entry = {
            "id": rec_id,
            "filename": filename,
            "type": "sentence",
            "text_diacritized": text_diacritized,
            "text_base": strip_harakat(text_diacritized),
            "recorded_at": datetime.now().isoformat(),
        }
    else:
        entry = {
            "id": rec_id,
            "filename": filename,
            "type": "word",
            "word_diacritized": word_diacritized,
            "word_base": strip_harakat(word_diacritized),
            "intended_case": intended_case,
            "sentence_context": sentence_context,
            "recorded_at": datetime.now().isoformat(),
        }

    manifest.append(entry)
    _save_manifest(manifest)

    return entry


@app.get("/api/test/recordings")
async def test_list_recordings():
    """List all saved test recordings."""
    return _load_manifest()


def _run_word_test(entry: dict, audio_data):
    """Run scorer on a single-word recording. Returns result dict."""
    from i3rab.book import Book

    word_book = Book.from_sentence(entry["word_diacritized"])
    if not word_book.words:
        return {**entry, "error": "no words generated"}

    book_word = word_book.words[0]
    scored = pipeline.scorer.score_word(audio_data, book_word)

    detected_case = scored.detected_hyp.case if scored.detected_hyp else None
    detected_diac = scored.detected_hyp.diacritized if scored.detected_hyp else None
    is_match = detected_case == entry["intended_case"]

    # Get all hypothesis scores for debugging
    hyp_scores = []
    encoder_out = pipeline.scorer._get_encoder_output(audio_data)
    for hyp in book_word.hypotheses:
        score = pipeline.scorer._score_text(encoder_out, hyp.diacritized)
        hyp_scores.append({
            "diacritized": hyp.diacritized,
            "case": hyp.case,
            "score": round(score, 4),
            "is_correct": hyp.is_correct,
        })
    hyp_scores.sort(key=lambda x: x["score"], reverse=True)

    return {
        **entry,
        "detected_case": detected_case,
        "detected_diacritized": detected_diac,
        "is_match": is_match,
        "confidence": scored.confidence.value,
        "score_gap": round(scored.score_gap, 4),
        "hypothesis_scores": hyp_scores,
    }


def _run_sentence_test(entry: dict, audio_data):
    """Run full pipeline on a sentence recording. Returns result dict."""
    from i3rab.book import Book
    from i3rab.pipeline import I3rabPipeline

    text = entry["text_diacritized"]
    sentence_book = Book.from_sentence(text)
    if not sentence_book.words:
        return {**entry, "error": "no words generated"}

    sentence_pipeline = I3rabPipeline(sentence_book, Config())
    sentence_pipeline.scorer = pipeline.scorer  # reuse loaded model

    result = sentence_pipeline.evaluate_phrase(audio_data)

    # Per-word results
    word_results = []
    correct_count = 0
    for wd in result["results"]:
        is_correct = wd.kind.value in ("correct", "pausal_ok")
        if is_correct:
            correct_count += 1
        word_results.append({
            "ref_word": wd.ref_word,
            "hyp_word": wd.hyp_word,
            "kind": wd.kind.value,
            "is_correct": is_correct,
            "confidence": wd.confidence.value if isinstance(wd.confidence, Confidence) else "high",
            "detected_case": wd.detected_case,
            "expected_case": wd.expected_case,
        })

    total = len(word_results)
    return {
        **entry,
        "transcript": result["transcript"],
        "word_results": word_results,
        "is_match": correct_count == total and total > 0,
        "words_correct": correct_count,
        "words_total": total,
    }


@app.post("/api/test/run")
async def test_run_all():
    """Run the scorer on all saved test recordings."""
    if not pipeline:
        return {"error": "Pipeline not loaded"}

    manifest = _load_manifest()
    results = []
    correct_words = 0
    total_words = 0

    for entry in manifest:
        filepath = TEST_DATA_DIR / entry["filename"]
        if not filepath.exists():
            results.append({**entry, "error": "file not found"})
            continue

        audio_data = _read_audio(filepath.read_bytes())
        rec_type = entry.get("type", "word")

        if rec_type == "sentence":
            result = _run_sentence_test(entry, audio_data)
            if "error" not in result:
                correct_words += result["words_correct"]
                total_words += result["words_total"]
        else:
            result = _run_word_test(entry, audio_data)
            if "error" not in result:
                total_words += 1
                if result["is_match"]:
                    correct_words += 1

        results.append(result)

    return {
        "results": results,
        "summary": {
            "correct": correct_words,
            "total": total_words,
            "accuracy": round(correct_words / total_words * 100, 1) if total_words > 0 else 0,
        },
    }


@app.post("/api/test/run-one/{rec_id}")
async def test_run_one(rec_id: str):
    """Run the scorer on a single saved recording."""
    if not pipeline:
        return {"error": "Pipeline not loaded"}

    manifest = _load_manifest()
    entry = next((e for e in manifest if e["id"] == rec_id), None)
    if not entry:
        return {"error": "Recording not found"}

    filepath = TEST_DATA_DIR / entry["filename"]
    if not filepath.exists():
        return {"error": "Audio file not found"}

    audio_data = _read_audio(filepath.read_bytes())
    rec_type = entry.get("type", "word")

    if rec_type == "sentence":
        return _run_sentence_test(entry, audio_data)
    else:
        return _run_word_test(entry, audio_data)


@app.delete("/api/test/recordings/{rec_id}")
async def test_delete_recording(rec_id: str):
    """Delete a saved test recording."""
    manifest = _load_manifest()
    entry = next((e for e in manifest if e["id"] == rec_id), None)
    if not entry:
        return {"error": "Recording not found"}

    filepath = TEST_DATA_DIR / entry["filename"]
    if filepath.exists():
        filepath.unlink()

    manifest = [e for e in manifest if e["id"] != rec_id]
    _save_manifest(manifest)
    return {"status": "deleted", "id": rec_id}


# ── PDF Pipeline Endpoints ───────────────────────────────────────────────────


class AnalyzeWordRequest(BaseModel):
    word: str
    sentence: str


@app.post("/api/pdf/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload a PDF and extract text with word positions."""
    from i3rab.pdf_extractor import extract_pdf
    from i3rab.cache import AnalysisCache

    config = Config()
    upload_dir = Path(config.pdf_upload_dir)
    upload_dir.mkdir(exist_ok=True)

    doc_id = str(uuid.uuid4())[:8]
    file_ext = Path(file.filename or "doc.pdf").suffix or ".pdf"
    file_path = upload_dir / f"{doc_id}{file_ext}"

    # Save uploaded file
    content = await file.read()
    file_path.write_bytes(content)

    # Extract text and word positions
    try:
        pdf_doc = extract_pdf(str(file_path))
    except Exception as e:
        file_path.unlink(missing_ok=True)
        return {"error": f"Failed to extract PDF: {e}"}

    # Compute file hash for caching
    doc_hash = AnalysisCache.hash_file(str(file_path))

    # Use original filename as title
    original_title = Path(file.filename or "document").stem

    # Store document info
    pdf_documents[doc_id] = {
        "path": str(file_path),
        "hash": doc_hash,
        "title": original_title,
        "num_pages": len(pdf_doc.pages),
        "total_words": pdf_doc.total_words,
        "full_text": pdf_doc.full_text,
        "pages": [
            {
                "page_num": p.page_num,
                "width": p.width,
                "height": p.height,
                "is_scanned": p.is_scanned,
                "num_words": len(p.words),
            }
            for p in pdf_doc.pages
        ],
        "words_by_page": {
            p.page_num: [
                {
                    "text": w.text,
                    "bbox": list(w.bbox),
                    "line_num": w.line_num,
                    "word_idx": w.word_idx_in_line,
                    "confidence": w.confidence,
                }
                for w in p.words
            ]
            for p in pdf_doc.pages
        },
        "analysis_status": "pending",
        "analysis": None,
    }

    # Cache word positions
    if analysis_cache:
        for p in pdf_doc.pages:
            words_data = [
                {
                    "text": w.text,
                    "bbox": list(w.bbox),
                    "line_num": w.line_num,
                    "word_idx": w.word_idx_in_line,
                    "confidence": w.confidence,
                }
                for w in p.words
            ]
            analysis_cache.put_pdf_words(doc_hash, p.page_num, words_data)

    return {
        "doc_id": doc_id,
        "title": pdf_doc.title,
        "num_pages": len(pdf_doc.pages),
        "total_words": pdf_doc.total_words,
        "pages": pdf_documents[doc_id]["pages"],
    }


@app.get("/api/pdf/{doc_id}/page/{page_num}")
async def get_pdf_page_image(doc_id: str, page_num: int):
    """Render a PDF page as PNG for display."""
    if doc_id not in pdf_documents:
        return {"error": "Document not found"}

    from i3rab.pdf_extractor import render_page_to_png
    config = Config()

    try:
        png_bytes = render_page_to_png(
            pdf_documents[doc_id]["path"],
            page_num,
            dpi=config.pdf_render_dpi,
        )
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/pdf/{doc_id}/words/{page_num}")
async def get_pdf_words(doc_id: str, page_num: int):
    """Get word positions for a specific page (for overlay rendering)."""
    if doc_id not in pdf_documents:
        return {"error": "Document not found"}

    doc = pdf_documents[doc_id]
    words = doc["words_by_page"].get(page_num, [])
    page_info = next(
        (p for p in doc["pages"] if p["page_num"] == page_num),
        None,
    )

    return {
        "doc_id": doc_id,
        "page_num": page_num,
        "page_width": page_info["width"] if page_info else 0,
        "page_height": page_info["height"] if page_info else 0,
        "words": words,
    }


@app.get("/api/pdf/{doc_id}/info")
async def get_pdf_info(doc_id: str):
    """Get document info and analysis status."""
    if doc_id not in pdf_documents:
        return {"error": "Document not found"}

    doc = pdf_documents[doc_id]
    return {
        "doc_id": doc_id,
        "title": doc["title"],
        "num_pages": doc["num_pages"],
        "total_words": doc["total_words"],
        "analysis_status": doc["analysis_status"],
        "pages": doc["pages"],
    }


async def _run_page_analysis(doc_id: str, page_num: int):
    """Background task to run i3rab analysis on a single page."""
    from i3rab.irab_agent import analyze_document

    doc = pdf_documents.get(doc_id)
    if not doc:
        return

    # Get text for this page only
    page_words = doc["words_by_page"].get(page_num, [])
    if not page_words:
        return

    page_text = " ".join(w["text"] for w in page_words)
    progress_key = f"{doc_id}:{page_num}"

    doc.setdefault("page_analysis_status", {})[page_num] = "analyzing"
    analysis_progress[progress_key] = {"current": 0, "total": 0, "status": "analyzing"}

    def progress_cb(current, total):
        analysis_progress[progress_key] = {
            "current": current,
            "total": total,
            "status": "analyzing",
        }

    try:
        result = await analyze_document(
            text=page_text,
            document_id=f"{doc_id}_p{page_num}",
            title=f"{doc['title']} - Page {page_num + 1}",
            cache=analysis_cache,
            progress_callback=progress_cb,
        )

        # Store per-page analysis
        page_analysis = {
            "sentences": [
                {
                    "sentence_text": s.sentence_text,
                    "sentence_index": s.sentence_index,
                    "words": [asdict(w) for w in s.words],
                }
                for s in result.sentences
            ],
            "total_words": result.total_words,
        }
        doc.setdefault("page_analyses", {})[page_num] = page_analysis
        doc["page_analysis_status"][page_num] = "complete"
        analysis_progress[progress_key] = {
            "current": len(result.sentences),
            "total": len(result.sentences),
            "status": "complete",
        }
    except Exception as e:
        doc.setdefault("page_analysis_status", {})[page_num] = f"error: {e}"
        analysis_progress[progress_key] = {
            "current": 0,
            "total": 0,
            "status": f"error: {e}",
        }


@app.post("/api/pdf/{doc_id}/analyze")
async def start_analysis(
    doc_id: str,
    background_tasks: BackgroundTasks,
    page_num: int | None = None,
):
    """Start async i3rab analysis for a specific page (or full document if page_num omitted)."""
    if doc_id not in pdf_documents:
        return {"error": "Document not found"}

    doc = pdf_documents[doc_id]

    if page_num is not None:
        # Per-page analysis
        page_status = doc.get("page_analysis_status", {}).get(page_num)

        if page_status == "complete" and doc.get("page_analyses", {}).get(page_num):
            return {"status": "already_complete", "doc_id": doc_id, "page_num": page_num}

        if page_status == "analyzing":
            return {"status": "already_running", "doc_id": doc_id, "page_num": page_num}

        background_tasks.add_task(_run_page_analysis, doc_id, page_num)
        return {"status": "started", "doc_id": doc_id, "page_num": page_num}

    # Full document analysis (kept for backward compat)
    from i3rab.irab_agent import analyze_document

    if doc.get("analysis_status") == "complete" and doc.get("analysis"):
        return {"status": "already_complete", "doc_id": doc_id}

    if doc.get("analysis_status") == "analyzing":
        return {"status": "already_running", "doc_id": doc_id}

    # Analyze all pages sequentially
    async def _run_all_pages():
        for pn in range(doc["num_pages"]):
            await _run_page_analysis(doc_id, pn)
        doc["analysis_status"] = "complete"

    doc["analysis_status"] = "analyzing"
    background_tasks.add_task(_run_all_pages)
    return {"status": "started", "doc_id": doc_id}


@app.get("/api/pdf/{doc_id}/status")
async def get_analysis_status(doc_id: str, page_num: int | None = None):
    """Check analysis progress (per-page or overall)."""
    if doc_id not in pdf_documents:
        return {"error": "Document not found"}

    if page_num is not None:
        progress_key = f"{doc_id}:{page_num}"
        progress = analysis_progress.get(progress_key, {"current": 0, "total": 0, "status": "pending"})
        page_status = pdf_documents[doc_id].get("page_analysis_status", {}).get(page_num, "pending")
        return {
            "doc_id": doc_id,
            "page_num": page_num,
            "analysis_status": page_status,
            **progress,
        }

    # Overall status
    doc = pdf_documents[doc_id]
    total_pages = doc["num_pages"]
    completed_pages = sum(
        1 for s in doc.get("page_analysis_status", {}).values() if s == "complete"
    )
    overall_status = "complete" if completed_pages == total_pages else (
        "analyzing" if any(s == "analyzing" for s in doc.get("page_analysis_status", {}).values()) else "pending"
    )
    return {
        "doc_id": doc_id,
        "analysis_status": overall_status,
        "current": completed_pages,
        "total": total_pages,
        "status": overall_status,
    }


@app.get("/api/pdf/{doc_id}/analysis")
async def get_analysis(doc_id: str):
    """Get the full i3rab analysis results."""
    if doc_id not in pdf_documents:
        return {"error": "Document not found"}

    doc = pdf_documents[doc_id]
    if doc["analysis_status"] != "complete" or not doc["analysis"]:
        return {"error": "Analysis not complete", "status": doc["analysis_status"]}

    return {
        "doc_id": doc_id,
        "title": doc["title"],
        **doc["analysis"],
    }


@app.get("/api/pdf/{doc_id}/word/{word_global_idx}")
async def get_word_analysis(doc_id: str, word_global_idx: int):
    """Get i3rab analysis for a specific word by its global index."""
    if doc_id not in pdf_documents:
        return {"error": "Document not found"}

    doc = pdf_documents[doc_id]
    if not doc["analysis"]:
        return {"error": "Analysis not complete"}

    # Find the word across all sentences
    running_idx = 0
    for sentence in doc["analysis"]["sentences"]:
        for word in sentence["words"]:
            if running_idx == word_global_idx:
                return {
                    "doc_id": doc_id,
                    "word_index": word_global_idx,
                    "sentence": sentence["sentence_text"],
                    **word,
                }
            running_idx += 1

    return {"error": "Word index out of range"}


@app.post("/api/pdf/{doc_id}/word/by-page")
async def get_word_analysis_by_page(
    doc_id: str,
    page_num: int = Form(...),
    word_idx_in_page: int = Form(...),
):
    """Get i3rab analysis for a word identified by page and position."""
    if doc_id not in pdf_documents:
        return {"error": "Document not found"}

    doc = pdf_documents[doc_id]

    # Get the word text from the page data
    page_words = doc["words_by_page"].get(page_num, [])
    if word_idx_in_page >= len(page_words):
        return {"error": "Word index out of range for this page"}

    target_word = page_words[word_idx_in_page]["text"]

    # Check per-page analysis first
    page_analysis = doc.get("page_analyses", {}).get(page_num)
    if page_analysis:
        # Find the word within this page's analysis
        word_counter = 0
        for sentence in page_analysis["sentences"]:
            for word in sentence["words"]:
                if word_counter == word_idx_in_page:
                    return {
                        "doc_id": doc_id,
                        "page_num": page_num,
                        "word_index": word_idx_in_page,
                        "word_text": target_word,
                        "sentence": sentence["sentence_text"],
                        **word,
                    }
                word_counter += 1

    return {
        "doc_id": doc_id,
        "page_num": page_num,
        "word_index": word_idx_in_page,
        "word_text": target_word,
        "status": "analysis_pending",
    }


@app.get("/api/pdf/documents")
async def list_documents():
    """List all uploaded PDF documents."""
    return {
        "documents": [
            {
                "doc_id": doc_id,
                "title": doc["title"],
                "num_pages": doc["num_pages"],
                "total_words": doc["total_words"],
                "analysis_status": doc["analysis_status"],
            }
            for doc_id, doc in pdf_documents.items()
        ]
    }


@app.delete("/api/pdf/{doc_id}")
async def delete_document(doc_id: str):
    """Delete an uploaded PDF document."""
    if doc_id not in pdf_documents:
        return {"error": "Document not found"}

    doc = pdf_documents[doc_id]
    # Delete the file
    path = Path(doc["path"])
    if path.exists():
        path.unlink()

    del pdf_documents[doc_id]
    analysis_progress.pop(doc_id, None)

    return {"status": "deleted", "doc_id": doc_id}


# Mount static files last
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
