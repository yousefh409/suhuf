"""Arabic Speech Corpus (Nawar Halabi) loader for eval.py.

MSA, fully diacritized, single speaker — a held-out SECOND speaker relative to
the saved sessions (the existing models were fine-tuned on ClArTTS, not ASC, so
this is leakage-free). Free for research use per the corpus README.

The corpus transcript is in Buckwalter transliteration (with this corpus's
non-standard '^' used for tha instead of the standard 'v'). We convert it to
diacritized Arabic script, normalizing combining-mark order to the project
convention: consonant + vowel + shadda (matches passage.json), NOT the
Buckwalter consonant + shadda + vowel order.

load_corpus_index() yields (utt_id, diacritized_arabic_text, wav_path).
"""
import re
from pathlib import Path

BASE = Path(__file__).parent
ASC_DIR = BASE / "data" / "asc"

# Buckwalter -> Arabic Unicode. '^' is this corpus's variant for tha (U+062B).
_B2A = {
    "'": "\u0621", ">": "\u0623", "&": "\u0624", "<": "\u0625", "}": "\u0626",
    "|": "\u0622", "A": "\u0627", "b": "\u0628", "p": "\u0629", "t": "\u062A",
    "v": "\u062B", "^": "\u062B", "j": "\u062C", "H": "\u062D", "x": "\u062E",
    "d": "\u062F", "*": "\u0630", "r": "\u0631", "z": "\u0632", "s": "\u0633",
    "$": "\u0634", "S": "\u0635", "D": "\u0636", "T": "\u0637", "Z": "\u0638",
    "E": "\u0639", "g": "\u063A", "f": "\u0641", "q": "\u0642", "k": "\u0643",
    "l": "\u0644", "m": "\u0645", "n": "\u0646", "h": "\u0647", "w": "\u0648",
    "Y": "\u0649", "y": "\u064A", "_": "",
    "a": "\u064E", "u": "\u064F", "i": "\u0650", "F": "\u064B", "N": "\u064C",
    "K": "\u064D", "~": "\u0651", "o": "\u0652", "`": "\u0670", "{": "\u0671",
}
_VOWELS = "\u064E\u064F\u0650\u064B\u064C\u064D"
_SHADDA = "\u0651"


def buckwalter_to_arabic(bw):
    """Convert a Buckwalter string to diacritized Arabic (project mark order)."""
    s = "".join(_B2A.get(ch, " " if ch == " " else "") for ch in bw)
    # Buckwalter writes shadda before the vowel; passage.json stores vowel then
    # shadda. Swap so generated i3rab/tashkeel alternatives behave correctly.
    s = re.sub(_SHADDA + "([" + _VOWELS + "])", lambda m: m.group(1) + _SHADDA, s)
    return re.sub(r"\s+", " ", s).strip()


def _clean_bw(bw):
    """Drop standalone pause markers ('-') and collapse whitespace."""
    bw = re.sub(r"(^|\s)-(\s|$)", " ", bw)
    return re.sub(r"\s+", " ", bw).strip()


def load_corpus_index(include_test_set=False):
    """Return list of (utt_id, diacritized_arabic_text, wav_path)."""
    transcripts = list(ASC_DIR.rglob("orthographic-transcript.txt"))
    if not transcripts:
        raise FileNotFoundError(
            f"No orthographic-transcript.txt under {ASC_DIR}. "
            "Download/unzip the Arabic Speech Corpus there first.")
    if not include_test_set:
        # Prefer the main-corpus transcript (the one NOT under a 'test set' dir).
        main = [t for t in transcripts if "test" not in t.parent.name.lower()]
        transcripts = main or transcripts

    items = []
    for transcript in transcripts:
        wav_root = transcript.parent / "wav"
        if not wav_root.exists():
            wav_root = transcript.parent
        for line in transcript.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r'"([^"]+\.wav)"\s+"(.+)"\s*$', line)
            if not m:
                continue
            wav_name, bw = m.group(1), m.group(2)
            text = buckwalter_to_arabic(_clean_bw(bw))
            wav_path = wav_root / wav_name
            if not wav_path.exists():
                hit = next(iter(transcript.parent.rglob(wav_name)), None)
                if hit is None:
                    continue
                wav_path = hit
            if text:
                items.append((wav_name.replace(".wav", "").strip(), text, str(wav_path)))
    if not items:
        raise ValueError("Parsed 0 corpus items — transcript format unexpected.")
    return items
