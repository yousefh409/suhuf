# Runtime

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Live readalong UI (`static/index.html`) |
| GET | `/record` | Test data recorder (`static/record.html`) |
| GET | `/api/passages` | All passages from `passage.json` |
| POST | `/api/score` | Batch score audio file (multipart: `audio` webm + `passage_id`) |
| WS | `/ws/score` | Streaming scoring (init JSON → PCM bytes → scored words) |
| POST | `/api/save` | Save test recording (multipart: `audio`, `passage_id`, `phrase_idx`, `notes`) |
| GET | `/api/recordings` | List saved test recordings from `manifest.jsonl` |

## WebSocket Protocol (`/ws/score`)

1. Client → `{"passage_id": "...", "debug": bool}`
2. Server → confirms or closes 1008
3. Client → raw PCM float32 bytes (16kHz mono, streamed)
4. Server → `{"words": [...], "matched_phrase_idx": N}` every 0.5-0.75s
5. Client → `"done"` text message
6. Server → final scoring with `final: true`

## Response Shape (`/api/score` and `/ws/score`)

```json
{
  "words": [{
    "idx": 0,
    "word": "الكلامُ",
    "status": "correct|error",
    "error_type": "wrong|i3rab|tashkeel|skipped|null",
    "error_detail": "string|null",
    "expected_word": "string|null",
    "greedy": "decoded text",
    "debug": { "eff": -0.5, "i3rab_delta": 0.12, ... }
  }],
  "matched_phrase_idx": 0
}
```

## Environment Variables

- None referenced in Python code (all config is hard-coded or from JSON)
- `.env` exists at project root (likely for future Supabase/RevenueCat keys)

## External Dependencies

| Service | Usage | Required |
|---------|-------|----------|
| ffmpeg | webm → PCM conversion (`engine.load_audio()`) | Yes |
| HuggingFace | Whisper download on first streaming use | First run only |
| PyTorch | CTC inference, alignment | Yes |

## Dev Server

```bash
cd recitation
python -m uvicorn server:app --host 0.0.0.0 --port 8000
# UI at http://localhost:8000
```

## Startup Sequence

1. Load `passage.json` → global passages list
2. `RecitationEngine(models/ssl_xls_r_v5/)` → CTC model on GPU/MPS/CPU
3. Optionally load MixGoP GMMs if `models/gmm/` exists
4. Whisper lazy-loaded on first WebSocket connection (~500MB download)
5. GBM classifiers lazy-loaded on first classification call

## Performance

- Cold start: ~3-5s (model loading)
- Batch scoring: ~0.5s per second of audio (GPU)
- Streaming cycle: 0.5-0.75s throttle
- Memory: ~1GB (XLS-R 600MB + Whisper 400MB + buffers)
- Ring buffer: 8s window (512KB per session)

## Test Commands

```bash
python evaluate.py              # Batch eval on 78 recordings
python test_streaming.py        # Automated streaming tests (needs running server)
python test_mutations.py        # Mutation testing for error detection
python measure_tashkeel.py      # TTS-based tashkeel measurement
```
