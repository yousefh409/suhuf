#!/usr/bin/env python3
"""Build MixGoP GMMs from TTS reference audio.

Generates TTS audio for each phrase in passage.json, runs the model with
hidden_states=True, extracts features at forced-aligned diacritic positions,
and fits per-diacritic GMMs. Saves to models/gmm/.

Usage:
    python build_gmm.py [--components 4] [--voices ar-SA-HamedNeural,ar-SA-ZariyahNeural]
"""

import sys
import json
import asyncio
import hashlib
import subprocess
import numpy as np
import torch
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

from engine import RecitationEngine
from scorer import MixGoPScorer, _ALL_DIACS, _DIAC_NAMES
from arabic import HARAKAT, SHADDA

CACHE_DIR = BASE / ".tts_cache"
CACHE_DIR.mkdir(exist_ok=True)
MODEL_PATH = BASE / "models" / "ssl_xls_r_v5"
GMM_DIR = BASE / "models" / "gmm"
PASSAGES_FILE = BASE / "passage.json"

DEFAULT_VOICES = [
    # 8 diverse Arabic voices (4M + 4F, different regions)
    "ar-SA-HamedNeural",      # Saudi male
    "ar-SA-ZariyahNeural",    # Saudi female
    "ar-EG-ShakirNeural",     # Egyptian male
    "ar-EG-SalmaNeural",      # Egyptian female
    "ar-AE-HamdanNeural",     # Emirati male
    "ar-JO-SanaNeural",       # Jordanian female
    "ar-SY-LaithNeural",      # Syrian male
    "ar-KW-NouraNeural",      # Kuwaiti female
]

# Short diacritized phrases targeting underrepresented diacritics.
# These supplement passage.json to balance the training data —
# damma and tanween are rare in natural text.
TARGETED_PHRASES = [
    # Damma-heavy (raf3 markers, damma on internal consonants)
    "كُتُبٌ مُفِيدَةٌ",
    "يَكْتُبُ الطُّلَّابُ دُرُوسَهُمْ",
    "يُحِبُّ المُسْلِمُونَ الخُلُقَ",
    "أُمُورٌ مُهِمَّةٌ جُمِعَتْ",
    "خُطُوَاتٌ مُبَارَكَةٌ",
    "دُرُوسٌ مُتَنَوِّعَةٌ",
    "عُلُومٌ نَافِعَةٌ كَثِيرَةٌ",
    "فُنُونٌ مُخْتَلِفَةٌ",
    "شُرُوطٌ لَازِمَةٌ",
    "حُقُوقٌ مَحْفُوظَةٌ",
    # Tanween-heavy (fathatan, dammatan, kasratan)
    "رَأَيْتُ كِتَابًا جَدِيدًا",
    "هَذَا عَمَلٌ صَالِحٌ",
    "جَاءَ رَجُلٌ كَرِيمٌ",
    "مَرَرْتُ بِمَسْجِدٍ كَبِيرٍ",
    "سَمِعْتُ خَبَرًا سَارًّا",
    "كَانَ يَوْمًا حَارًّا جِدًّا",
    "قَرَأْتُ شَيْئًا مُفِيدًا",
    "وَجَدْتُ حَلًّا مُنَاسِبًا",
    "ذَهَبَ طَالِبٌ مُجْتَهِدٌ",
    "فِي بَيْتٍ وَاسِعٍ جَمِيلٍ",
    "عَلَى طَرِيقٍ طَوِيلٍ",
    "مِنْ كِتَابٍ قَدِيمٍ",
    "رَجُلًا صَادِقًا أَمِينًا",
    "فَتًى شُجَاعًا قَوِيًّا",
    "رِسَالَةً طَوِيلَةً مُؤَثِّرَةً",
]


async def tts_generate(text, voice="ar-SA-HamedNeural"):
    """Generate TTS audio and return as float32 numpy array."""
    import edge_tts

    key = hashlib.sha256(f"{voice}:{text}".encode()).hexdigest()[:16]
    raw_path = CACHE_DIR / f"{key}.raw"

    if not raw_path.exists():
        mp3_path = CACHE_DIR / f"{key}.mp3"
        comm = edge_tts.Communicate(text, voice)
        await comm.save(str(mp3_path))
        subprocess.run([
            "ffmpeg", "-y", "-i", str(mp3_path),
            "-f", "f32le", "-acodec", "pcm_f32le",
            "-ar", "16000", "-ac", "1", str(raw_path),
        ], capture_output=True)
        mp3_path.unlink(missing_ok=True)

    audio = np.fromfile(str(raw_path), dtype=np.float32)
    return audio


def extract_diac_features(engine, waveform, phrase_text):
    """Run model, forced-align, extract features at diacritic positions.

    Returns dict {diac_char: list of feature vectors}.
    """
    model_out = engine.get_model_outputs(waveform, output_hidden_states=True)
    log_probs = model_out['log_probs']
    hidden_states = model_out.get('hidden_states')

    if hidden_states is None:
        return {}

    tokens = engine.text_to_tokens(phrase_text)
    T = log_probs.shape[0]
    if not tokens or T < len(tokens):
        return {}

    spans = engine.forced_align(log_probs, tokens)
    word_bounds = engine.word_boundaries_from_alignment(spans, tokens)

    words = phrase_text.split()
    features_by_diac = defaultdict(list)

    for wb in word_bounds:
        wi = wb["word_idx"]
        if wi >= len(words):
            continue
        word = words[wi]

        # Find last consonant index to skip final diacritics (i3rab)
        chars = list(word)
        for i in range(len(chars) - 1, -1, -1):
            if chars[i] not in HARAKAT:
                break

        # Map each char position in the word to its token index in char_spans
        for _target_idx, token_id, sf, ef in wb["char_spans"]:
            char_at = engine.id2char.get(token_id, '')
            if char_at not in _ALL_DIACS:
                continue

            # Skip final diacritics (i3rab — handled by other signals)
            # We track position in the word by counting non-diacritic chars
            # For simplicity, skip if this is the last diacritic cluster
            # Heuristic: check if token_id corresponds to a diacritic
            # after the last consonant in the aligned span list
            is_after_last_cons = True
            for later_tidx, later_tid, _, _ in wb["char_spans"]:
                if later_tidx > _target_idx and engine.id2char.get(later_tid, '') not in HARAKAT:
                    is_after_last_cons = False
                    break
            if is_after_last_cons:
                continue

            # Skip shadda-adjacent (acoustically ambiguous)
            has_shadda = False
            for near_tidx, near_tid, _, _ in wb["char_spans"]:
                if abs(near_tidx - _target_idx) <= 1 and engine.id2char.get(near_tid, '') == SHADDA:
                    has_shadda = True
                    break
            if has_shadda:
                continue

            feat = MixGoPScorer.extract_feature(hidden_states, (sf, ef))
            if feat is not None:
                features_by_diac[char_at].append(feat)

    return features_by_diac


async def main():
    n_components = 4
    voices = DEFAULT_VOICES

    for arg in sys.argv[1:]:
        if arg.startswith("--components="):
            n_components = int(arg.split("=")[1])
        elif arg.startswith("--voices="):
            voices = arg.split("=")[1].split(",")

    # Load passages
    with open(PASSAGES_FILE) as f:
        data = json.load(f)

    all_phrases = []
    for passage in data["passages"]:
        if "phrases" in passage:
            all_phrases.extend(passage["phrases"])

    # Add targeted phrases for diacritic balancing
    all_phrases.extend(TARGETED_PHRASES)
    print(f"Found {len(all_phrases)} phrases ({len(all_phrases) - len(TARGETED_PHRASES)} from passages + {len(TARGETED_PHRASES)} targeted)")
    print(f"Using {len(voices)} voices")

    # Load model
    engine = RecitationEngine(str(MODEL_PATH))

    # Collect features
    all_features = defaultdict(list)
    total_generated = 0

    for vi, voice in enumerate(voices):
        print(f"\n--- Voice {vi+1}/{len(voices)}: {voice} ---")
        for pi, phrase in enumerate(all_phrases):
            print(f"  [{pi+1}/{len(all_phrases)}] {phrase[:50]}...", end=" ", flush=True)
            try:
                audio = await tts_generate(phrase, voice)
                waveform = torch.from_numpy(audio)
                feats = extract_diac_features(engine, waveform, phrase)
                for diac, flist in feats.items():
                    all_features[diac].extend(flist)
                n_feats = sum(len(v) for v in feats.values())
                print(f"({n_feats} features)")
                total_generated += 1
            except Exception as e:
                print(f"ERROR: {e}")

    # Also process correct test recordings if available
    manifest_file = BASE / "test_data" / "manifest.jsonl"
    if manifest_file.exists():
        print("\n--- Processing correct test recordings ---")
        with open(PASSAGES_FILE) as f:
            pdata = json.load(f)
        test_phrases = []
        for p in pdata["passages"]:
            if p["id"] == "ajrumiyyah" and "phrases" in p:
                test_phrases = p["phrases"]
                break

        with open(manifest_file) as f:
            entries = [json.loads(line) for line in f if line.strip()]

        correct_entries = [e for e in entries if
                          e.get("notes", "").lower().strip() in
                          ("correct reading", "correct ereading", "test")]

        for entry in correct_entries:
            phrase_idx = entry.get("phrase_idx", -1)
            if phrase_idx < 0 or phrase_idx >= len(test_phrases):
                continue
            audio_path = BASE / "test_data" / entry["file"]
            if not audio_path.exists():
                continue

            phrase = test_phrases[phrase_idx]
            print(f"  {entry['file']}: {phrase[:40]}...", end=" ", flush=True)
            try:
                waveform = engine.load_audio(str(audio_path))
                feats = extract_diac_features(engine, waveform, phrase)
                for diac, flist in feats.items():
                    all_features[diac].extend(flist)
                n_feats = sum(len(v) for v in feats.values())
                print(f"({n_feats} features)")
            except Exception as e:
                print(f"ERROR: {e}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Feature collection complete. Total phrases processed: {total_generated}")
    for diac in sorted(all_features.keys(), key=lambda d: _DIAC_NAMES.get(d, d)):
        flist = all_features[diac]
        print(f"  {_DIAC_NAMES.get(diac, repr(diac)):>10s}: {len(flist)} samples")

    # Convert to arrays
    features_arrays = {}
    for diac, flist in all_features.items():
        if flist:
            features_arrays[diac] = np.stack(flist)

    # Fit GMMs
    print(f"\nFitting GMMs (n_components={n_components})...")
    scorer = MixGoPScorer()
    scorer.fit(features_arrays, n_components=n_components)

    # Save
    scorer.save(GMM_DIR)
    print(f"\nSaved GMMs to {GMM_DIR}")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
