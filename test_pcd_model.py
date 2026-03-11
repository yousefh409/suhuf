#!/usr/bin/env python3
"""Quick test: load the fine-tuned PCD model and transcribe test recordings."""

import io
import json
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf


def read_audio(filepath: Path) -> np.ndarray:
    """Read audio file (webm/wav) to float32 numpy at 16kHz."""
    audio_bytes = filepath.read_bytes()
    try:
        audio_data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
    except Exception:
        import av
        container = av.open(io.BytesIO(audio_bytes))
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        frames = []
        for frame in container.decode(audio=0):
            for r in resampler.resample(frame):
                frames.append(r.to_ndarray().flatten())
        container.close()
        audio_data = np.concatenate(frames).astype(np.float32) / 32768.0
        return audio_data

    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)
    if sr != 16000:
        from scipy.signal import resample
        num_samples = int(len(audio_data) * 16000 / sr)
        audio_data = resample(audio_data, num_samples).astype(np.float32)
    return audio_data


def audio_to_wav_path(audio: np.ndarray, tmpdir: str) -> str:
    """Save numpy audio to a temp WAV file (NeMo needs file paths)."""
    path = tempfile.mktemp(suffix=".wav", dir=tmpdir)
    sf.write(path, audio, 16000)
    return path


def count_diacritics(text: str) -> int:
    return sum(1 for ch in text if "\u064B" <= ch <= "\u0652")


def strip_harakat(text: str) -> str:
    return "".join(ch for ch in text if not ("\u064B" <= ch <= "\u0652"))


def main():
    import nemo.collections.asr as nemo_asr

    model_path = "models/pcd_clartts_final.nemo"
    print(f"Loading PCD model from {model_path}...")
    model = nemo_asr.models.EncDecHybridRNNTCTCBPEModel.restore_from(model_path)
    model.eval()
    model.change_decoding_strategy(decoder_type="ctc")
    print("Model loaded!\n")

    # Load test manifest
    test_dir = Path("test_data")
    manifest = json.loads((test_dir / "manifest.json").read_text())

    sentences = [e for e in manifest if e.get("type") == "sentence"]

    print("=" * 70)
    print(f"Testing PCD model on {len(sentences)} sentence recordings")
    print("=" * 70)

    total_diac = 0
    total_ref_diac = 0
    total_words = 0
    correct_words = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        for entry in sentences:
            filepath = test_dir / entry["filename"]
            if not filepath.exists():
                print(f"  SKIP {entry['id']}: file not found")
                continue

            # Convert webm -> wav for NeMo
            audio = read_audio(filepath)
            wav_path = audio_to_wav_path(audio, tmpdir)

            # Transcribe
            result = model.transcribe([wav_path])[0]
            transcription = result.text if hasattr(result, "text") else str(result)

            ref = entry["text_diacritized"]
            hyp_diac = count_diacritics(transcription)
            ref_diac = count_diacritics(ref)
            total_diac += hyp_diac
            total_ref_diac += ref_diac

            # Word-level comparison
            ref_words = ref.split()
            hyp_words = transcription.split()
            for rw in ref_words:
                rw_base = strip_harakat(rw)
                total_words += 1
                for hw in hyp_words:
                    hw_base = strip_harakat(hw)
                    if rw_base == hw_base and rw == hw:
                        correct_words += 1
                        break

            mark = "DIAC" if hyp_diac > 0 else "PLAIN"
            print(f"\n[{mark}] {entry['id']} (diacritics: {hyp_diac}/{ref_diac})")
            print(f"  ref:  {ref[:100]}")
            print(f"  pred: {transcription[:100]}")

    print(f"\n{'=' * 70}")
    print(f"Total diacritics in output: {total_diac}")
    print(f"Total diacritics in reference: {total_ref_diac}")
    if total_ref_diac > 0:
        print(f"Diacritic coverage: {100 * total_diac / total_ref_diac:.1f}%")
    if total_words > 0:
        print(f"Word accuracy (exact diacritics match): {correct_words}/{total_words} ({100 * correct_words / total_words:.1f}%)")


if __name__ == "__main__":
    main()
