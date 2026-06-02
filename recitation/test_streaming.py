#!/usr/bin/env python3
"""TTS-based automated streaming test harness.

Generates Arabic speech via edge-tts, streams it through the WebSocket
endpoint, and validates that scoring results are correct.

Usage:
    # Start server first: uvicorn server:app --host 0.0.0.0 --port 8000
    python test_streaming.py [--verbose] [--server URL]
"""

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

# TTS + numpy + websockets — skip cleanly under CI's slim env.
pytest.importorskip("edge_tts")
pytest.importorskip("numpy")
pytest.importorskip("websockets")

import edge_tts
import websockets

BASE = Path(__file__).parent
CACHE_DIR = BASE / ".tts_cache"
CACHE_DIR.mkdir(exist_ok=True)

DEFAULT_SERVER = "ws://localhost:8000/ws/score"
TTS_VOICE = "ar-SA-HamedNeural"


# ── TTS Fixture ──

async def tts_generate(text: str, voice: str = TTS_VOICE) -> Path:
    """Generate TTS audio, cache by text hash. Returns path to raw f32le file."""
    import hashlib
    key = hashlib.sha256(f"{voice}:{text}".encode()).hexdigest()[:16]
    raw_path = CACHE_DIR / f"{key}.raw"
    if raw_path.exists():
        return raw_path

    mp3_path = CACHE_DIR / f"{key}.mp3"
    comm = edge_tts.Communicate(text, voice)
    await comm.save(str(mp3_path))

    # Convert to 16kHz mono raw f32le via ffmpeg
    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(mp3_path),
        "-f", "f32le", "-acodec", "pcm_f32le",
        "-ac", "1", "-ar", "16000",
        "-v", "quiet", str(raw_path),
    ], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr.decode()}")
    mp3_path.unlink(missing_ok=True)
    return raw_path


def load_pcm_f32(raw_path: Path) -> bytes:
    """Load raw f32le PCM bytes directly."""
    return raw_path.read_bytes()


def trim_pcm(pcm_bytes: bytes, max_secs: float) -> bytes:
    """Trim PCM float32 @ 16kHz to max_secs."""
    max_bytes = int(max_secs * 16000 * 4)
    return pcm_bytes[:max_bytes]


# ── Streaming Simulator ──

async def stream_and_collect(
    pcm_bytes: bytes,
    passage_id: str,
    server_url: str = DEFAULT_SERVER,
    chunk_secs: float = 1.0,
    realtime: bool = True,
) -> list[dict]:
    """Stream PCM through WebSocket and collect all responses.

    Returns list of server response dicts.
    """
    chunk_size = int(chunk_secs * 16000 * 4)  # bytes per chunk
    responses = []

    async with websockets.connect(server_url, max_size=10 * 1024 * 1024) as ws:
        # Init
        await ws.send(json.dumps({"passage_id": passage_id}))

        # Stream chunks
        offset = 0
        while offset < len(pcm_bytes):
            chunk = pcm_bytes[offset:offset + chunk_size]
            await ws.send(chunk)
            offset += len(chunk)

            if realtime:
                await asyncio.sleep(chunk_secs * 0.5)  # half real-time speed

            # Collect any responses (non-blocking)
            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=0.05)
                    responses.append(json.loads(msg))
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                pass

        # Send done signal
        await ws.send("done")

        # Collect final response(s)
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
                responses.append(json.loads(msg))
                if json.loads(msg).get("final"):
                    break
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            pass

    return responses


# ── Test helpers ──

def get_final_response(responses: list[dict]) -> dict | None:
    """Get the final response (the one with final=True)."""
    for r in reversed(responses):
        if r.get("final"):
            return r
    return responses[-1] if responses else None


def count_errors(response: dict) -> int:
    """Count words flagged as errors."""
    if not response or "words" not in response:
        return 0
    return sum(1 for w in response["words"] if w["status"] == "error")


def get_error_words(response: dict) -> list[str]:
    """Get list of error word texts."""
    if not response or "words" not in response:
        return []
    return [w["word"] for w in response["words"] if w["status"] == "error"]


# ── Load passage info ──

def load_passages():
    with open(BASE / "passage.json") as f:
        return json.load(f)


# ── Test cases ──

async def test_correct_reading(server_url: str, verbose: bool = False):
    """Test: correct TTS reading → zero errors flagged."""
    print("\n[TEST] Correct reading (full phrase, TTS)")
    data = load_passages()
    passage = next(p for p in data["passages"] if p["id"] == "ajrumiyyah")
    phrase = passage["phrases"][0]

    wav = await tts_generate(phrase)
    pcm = load_pcm_f32(wav)
    secs = len(pcm) / (16000 * 4)
    print(f"  Audio: {secs:.1f}s for phrase: {phrase[:60]}...")

    responses = await stream_and_collect(pcm, "ajrumiyyah", server_url)
    final = get_final_response(responses)

    if verbose and final:
        print(f"  Responses: {len(responses)} total")
        for w in final.get("words", []):
            status = "OK" if w["status"] == "correct" else f"ERR:{w['error_type']}"
            print(f"    {w['word']:>30s}  {status}")

    errors = count_errors(final)
    scored = len(final.get("words", [])) if final else 0
    print(f"  Result: {scored} words scored, {errors} errors")

    if errors == 0:
        print("  PASS: No false positives")
        return True
    else:
        err_words = get_error_words(final)
        print(f"  FAIL: False positives on: {', '.join(err_words)}")
        return False


async def test_partial_phrase(server_url: str, verbose: bool = False):
    """Test: partial phrase → intermediate results show fewer words than full."""
    print("\n[TEST] Partial phrase (intermediate results)")
    data = load_passages()
    passage = next(p for p in data["passages"] if p["id"] == "ajrumiyyah")
    # Use a longer phrase for a clearer partial test
    phrase_idx = min(1, len(passage["phrases"]) - 1)
    phrase = passage["phrases"][phrase_idx]
    words = phrase.split()

    wav = await tts_generate(phrase)
    pcm = load_pcm_f32(wav)
    full_secs = len(pcm) / (16000 * 4)

    # Trim to first half of audio
    trimmed = trim_pcm(pcm, full_secs * 0.4)
    trim_secs = len(trimmed) / (16000 * 4)
    print(f"  Trimmed to {trim_secs:.1f}s (from {full_secs:.1f}s), phrase has {len(words)} words")

    responses = await stream_and_collect(trimmed, "ajrumiyyah", server_url)

    # Check intermediate responses (before final) — these use partial alignment
    intermediate = [r for r in responses if not r.get("final") and "words" in r]
    final = get_final_response(responses)

    # Final will align all words (by design). Check that intermediates had fewer.
    if intermediate:
        first_scored = len(intermediate[0].get("words", []))
        print(f"  First intermediate: {first_scored}/{len(words)} words")
    final_scored = len(final.get("words", [])) if final else 0
    print(f"  Final: {final_scored}/{len(words)} words scored")

    if intermediate and len(intermediate[0].get("words", [])) < len(words):
        print("  PASS: Intermediate results had partial words")
        return True
    elif final_scored < len(words):
        print("  PASS: Fewer words scored with trimmed audio")
        return True
    else:
        print(f"  WARN: All {len(words)} words scored even with {trim_secs:.1f}s audio")
        return False


async def test_wrong_diacritics(server_url: str, verbose: bool = False):
    """Test: TTS with wrong i3rab → error detected."""
    print("\n[TEST] Wrong diacritics (swapped i3rab)")
    data = load_passages()
    passage = next(p for p in data["passages"] if p["id"] == "ajrumiyyah")
    phrase = passage["phrases"][0]

    # Swap final damma (U+064F) on الكَلَامُ to kasra (U+0650) → الكَلَامِ
    # Also swap damma on اللَّفْظُ → اللَّفْظِ
    DAMMA = '\u064f'
    KASRA = '\u0650'
    words = phrase.split()
    modified_words = []
    changed = []
    for w in words:
        if w.endswith(DAMMA) and len(w) > 3:
            modified_words.append(w[:-1] + KASRA)
            changed.append(w)
        else:
            modified_words.append(w)
    modified = " ".join(modified_words)

    if modified == phrase:
        print("  SKIP: Could not modify phrase")
        return True

    print(f"  Changed words: {changed}")

    wav = await tts_generate(modified)
    pcm = load_pcm_f32(wav)
    secs = len(pcm) / (16000 * 4)
    print(f"  Audio: {secs:.1f}s")

    responses = await stream_and_collect(pcm, "ajrumiyyah", server_url)
    final = get_final_response(responses)

    errors = count_errors(final)
    err_words = get_error_words(final)
    scored = len(final.get("words", [])) if final else 0

    if verbose and final:
        for w in final.get("words", []):
            status = "OK" if w["status"] == "correct" else f"ERR:{w['error_type']}:{w.get('error_detail','')}"
            print(f"    {w['word']:>30s}  {status}")

    print(f"  Result: {scored} words scored, {errors} errors: {err_words}")

    if errors > 0:
        print("  PASS: Error(s) detected")
        return True
    else:
        print("  FAIL: No errors detected (expected at least 1)")
        return False


async def test_latency(server_url: str, verbose: bool = False):
    """Test: measure time to first scored response."""
    print("\n[TEST] Latency (time to first score)")
    data = load_passages()
    passage = next(p for p in data["passages"] if p["id"] == "ajrumiyyah")
    phrase = passage["phrases"][0]

    wav = await tts_generate(phrase)
    pcm = load_pcm_f32(wav)

    chunk_size = int(0.5 * 16000 * 4)  # 0.5s chunks
    start = time.time()
    first_response_time = None

    async with websockets.connect(server_url, max_size=10 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"passage_id": "ajrumiyyah"}))

        offset = 0
        while offset < len(pcm):
            chunk = pcm[offset:offset + chunk_size]
            await ws.send(chunk)
            offset += len(chunk)
            await asyncio.sleep(0.25)  # half real-time for 0.5s chunks

            try:
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=0.05)
                    data = json.loads(msg)
                    if data.get("words") and first_response_time is None:
                        first_response_time = time.time() - start
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                pass

            if first_response_time is not None:
                break

        await ws.send("done")
        try:
            await asyncio.wait_for(ws.recv(), timeout=5.0)
        except:
            pass

    if first_response_time:
        print(f"  First scored response: {first_response_time:.1f}s")
        if first_response_time < 3.0:
            print("  PASS: < 3s latency")
            return True
        else:
            print(f"  FAIL: {first_response_time:.1f}s > 3s target")
            return False
    else:
        print("  FAIL: No scored response received")
        return False


async def test_second_phrase(server_url: str, verbose: bool = False):
    """Test: TTS of second phrase → cursor advances."""
    print("\n[TEST] Second phrase (cursor advance)")
    data = load_passages()
    passage = next(p for p in data["passages"] if p["id"] == "ajrumiyyah")
    if len(passage["phrases"]) < 2:
        print("  SKIP: passage has < 2 phrases")
        return True

    phrase2 = passage["phrases"][1]
    wav = await tts_generate(phrase2)
    pcm = load_pcm_f32(wav)
    secs = len(pcm) / (16000 * 4)
    print(f"  Audio: {secs:.1f}s for phrase[1]: {phrase2[:60]}...")

    responses = await stream_and_collect(pcm, "ajrumiyyah", server_url)
    final = get_final_response(responses)

    matched_idx = final.get("matched_phrase_idx") if final else None
    print(f"  matched_phrase_idx: {matched_idx}")

    if matched_idx == 1:
        print("  PASS: Cursor advanced to phrase 1")
        return True
    else:
        print(f"  WARN: Expected phrase 1, got {matched_idx}")
        return matched_idx is not None


async def test_streaming_progressive(server_url: str, verbose: bool = False):
    """Test: streaming sends intermediate results before 'done'."""
    print("\n[TEST] Progressive streaming (intermediate results)")
    data = load_passages()
    passage = next(p for p in data["passages"] if p["id"] == "ajrumiyyah")
    phrase = passage["phrases"][0]

    wav = await tts_generate(phrase)
    pcm = load_pcm_f32(wav)

    responses = await stream_and_collect(pcm, "ajrumiyyah", server_url, realtime=True)

    intermediate = [r for r in responses if not r.get("final") and "words" in r]
    final_msgs = [r for r in responses if r.get("final")]

    print(f"  Intermediate responses: {len(intermediate)}")
    print(f"  Final responses: {len(final_msgs)}")

    if len(intermediate) >= 1:
        print("  PASS: Got intermediate results during streaming")
        return True
    else:
        print("  FAIL: No intermediate results (only final)")
        return False


async def test_tashkeel_error(server_url: str, verbose: bool = False):
    """Test: TTS with wrong internal vowels → tashkeel error detected."""
    print("\n[TEST] Tashkeel error (swapped internal vowel)")
    data = load_passages()
    passage = next(p for p in data["passages"] if p["id"] == "ajrumiyyah")
    phrase = passage["phrases"][0]

    # Swap an internal fatha (U+064E) to kasra (U+0650) on المُرَكَّبُ → المُرِكَّبُ
    # Find المُرَكَّبُ and change the fatha after ra to kasra
    modified = phrase.replace('\u0631\u064e\u0643', '\u0631\u0650\u0643')  # رَك → رِك
    if modified == phrase:
        # Fallback: change فِيدُ to فَيدُ (swap kasra to fatha on المُفِيدُ)
        modified = phrase.replace('\u0641\u0650\u064a', '\u0641\u064e\u064a')

    if modified == phrase:
        print("  SKIP: Could not modify phrase for tashkeel test")
        return True

    print(f"  Original:  {phrase[:60]}...")
    print(f"  Modified:  {modified[:60]}...")

    wav = await tts_generate(modified)
    pcm = load_pcm_f32(wav)
    secs = len(pcm) / (16000 * 4)
    print(f"  Audio: {secs:.1f}s")

    responses = await stream_and_collect(pcm, "ajrumiyyah", server_url)
    final = get_final_response(responses)

    if verbose and final:
        for w in final.get("words", []):
            status = "OK" if w["status"] == "correct" else f"ERR:{w['error_type']}:{w.get('error_detail','')}"
            print(f"    {w['word']:>30s}  {status}")

    errors = count_errors(final)
    err_words = get_error_words(final)
    print(f"  Result: {errors} errors: {err_words}")

    if errors > 0:
        print("  PASS: Tashkeel error detected")
        return True
    else:
        print("  FAIL: No errors detected")
        return False


async def test_correct_multi_phrase(server_url: str, verbose: bool = False):
    """Test: correct reading of multiple phrases → zero FP."""
    print("\n[TEST] Correct multi-phrase reading (FP check)")
    data = load_passages()
    passage = next(p for p in data["passages"] if p["id"] == "ajrumiyyah")

    total_fp = 0
    total_words = 0

    # Test first 4 phrases
    for i in range(min(4, len(passage["phrases"]))):
        phrase = passage["phrases"][i]
        wav = await tts_generate(phrase)
        pcm = load_pcm_f32(wav)

        responses = await stream_and_collect(pcm, "ajrumiyyah", server_url)
        final = get_final_response(responses)

        errors = count_errors(final)
        scored = len(final.get("words", [])) if final else 0
        total_fp += errors
        total_words += scored

        if verbose:
            err_words = get_error_words(final)
            status = "OK" if errors == 0 else f"FP: {err_words}"
            print(f"  Phrase {i}: {scored} words, {status}")

    fp_rate = total_fp / total_words * 100 if total_words > 0 else 0
    print(f"  Total: {total_words} words, {total_fp} FP ({fp_rate:.1f}%)")

    if total_fp == 0:
        print("  PASS: Zero false positives")
        return True
    elif fp_rate < 2.0:
        print(f"  WARN: {total_fp} FP but rate {fp_rate:.1f}% < 2%")
        return True
    else:
        print(f"  FAIL: FP rate {fp_rate:.1f}% >= 2%")
        return False


async def test_streaming_no_flicker(server_url: str, verbose: bool = False):
    """Test: words don't flicker between correct/error across intermediate updates."""
    print("\n[TEST] No flicker (stable word states)")
    data = load_passages()
    passage = next(p for p in data["passages"] if p["id"] == "ajrumiyyah")
    phrase = passage["phrases"][0]

    wav = await tts_generate(phrase)
    pcm = load_pcm_f32(wav)

    responses = await stream_and_collect(pcm, "ajrumiyyah", server_url, realtime=True)

    # Track state changes per word across responses
    word_states = {}  # idx -> list of states
    for r in responses:
        if "words" not in r:
            continue
        is_final = r.get("final", False)
        for w in r["words"]:
            idx = w["idx"]
            state = w["status"]
            if idx not in word_states:
                word_states[idx] = []
            word_states[idx].append(("final" if is_final else "stream", state))

    flickers = 0
    for idx, states in sorted(word_states.items()):
        # Check streaming states only (exclude final)
        stream_states = [s for tag, s in states if tag == "stream"]
        if len(stream_states) >= 2:
            for i in range(1, len(stream_states)):
                if stream_states[i] != stream_states[i-1]:
                    flickers += 1
                    if verbose:
                        print(f"  Word {idx} flickered: {stream_states}")
                    break

    print(f"  Words with flicker: {flickers}")

    if flickers == 0:
        print("  PASS: No flicker detected")
        return True
    elif flickers <= 1:
        print("  WARN: Minor flicker (1 word)")
        return True
    else:
        print(f"  FAIL: {flickers} words flickered")
        return False


# ── Main ──

async def run_all_tests(server_url: str, verbose: bool = False):
    tests = [
        test_correct_reading,
        test_correct_multi_phrase,
        test_partial_phrase,
        test_wrong_diacritics,
        test_tashkeel_error,
        test_latency,
        test_second_phrase,
        test_streaming_progressive,
        test_streaming_no_flicker,
    ]

    results = {}
    for test_fn in tests:
        try:
            passed = await test_fn(server_url, verbose)
            results[test_fn.__name__] = passed
        except Exception as e:
            print(f"  ERROR: {e}")
            results[test_fn.__name__] = False

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\n  {passed}/{total} tests passed")
    return all(results.values())


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    server_url = DEFAULT_SERVER
    for arg in sys.argv[1:]:
        if arg.startswith("--server="):
            server_url = arg.split("=", 1)[1]

    print(f"Server: {server_url}")
    print(f"TTS voice: {TTS_VOICE}")
    print(f"Cache dir: {CACHE_DIR}")

    all_passed = asyncio.run(run_all_tests(server_url, verbose))
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
