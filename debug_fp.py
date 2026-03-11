#!/usr/bin/env python3
import sys, os, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else '.')

import numpy as np
import soundfile as sf
from pathlib import Path
from i3rab.config import Config
from i3rab.pipeline import I3rabPipeline
from i3rab.book import Book
from i3rab.tracker import PositionTracker


def read_audio(filepath: Path) -> np.ndarray:
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


config = Config()
config.rnnt_weight = 0.0

sentences = {
    "rec_031": "قَرَأَ الطَّالِبُ الكِتَابَ فِي المَكْتَبَةِ وَكَتَبَ الدَّرْسَ بِقَلَمٍ جَدِيدٍ ثُمَّ ذَهَبَ إِلَى البَيْتِ مَعَ أَصْدِقَائِهِ",
    "rec_038": "دَخَلَ المُعَلِّمُ الفَصْلَ وَسَلَّمَ عَلَى الطُّلَّابِ ثُمَّ بَدَأَ الدَّرْسَ بِقِرَاءَةِ آيَاتٍ مِنَ القُرْآنِ الكَرِيمِ وَشَرَحَ لَهُمُ الدَّرْسَ الجَدِيدَ بِأُسْلُوبٍ سَهْلٍ وَوَاضِحٍ",
}

for rec_id, text in sentences.items():
    audio_file = Path(f"test_data/{rec_id}.webm")
    if not audio_file.exists():
        print(f"  {rec_id}: audio not found")
        continue
    audio = read_audio(audio_file)

    book = Book.from_sentence(text)
    pipeline = I3rabPipeline(book, config)
    pipeline.tracker = PositionTracker(book, config)
    result = pipeline.evaluate_pcd_live(audio)

    print(f"\n=== {rec_id} ===")
    found_errors = False
    for sw in result["scored_words"]:
        if sw["kind"] != "correct" and sw["kind"] != "pausal_ok":
            found_errors = True
            print(f"  [{sw['kind']}] idx={sw['index']} ref={sw['ref_word']} hyp={sw['hyp_word']} conf={sw['confidence']}")
            if sw.get("haraka_diffs"):
                for hd in sw["haraka_diffs"]:
                    print(f"    position {hd['position']}: expected={hd['expected']} got={hd['got']} is_irab={hd['is_irab']}")
    if not found_errors:
        print("  All words correct or pausal_ok")
