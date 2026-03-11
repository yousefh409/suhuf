#!/usr/bin/env python3
"""i3rab - Arabic recitation correction tool.

Uses hypothesis scoring to detect diacritization errors: for each word,
scores all possible i3rab forms against the audio and picks the best match.
"""

import os
import sys

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv

from i3rab.models import DiffKind, Confidence, HARAKA_NAMES
from i3rab.arabic import normalize_arabic, format_haraka_list
from i3rab.book import Book
from i3rab.pipeline import I3rabPipeline
from i3rab.config import Config

# ── Constants ────────────────────────────────────────────────────────────────

SAMPLE_RATE = 16000
CHANNELS = 1
MIN_AUDIO_SECONDS = 0.5

DEFAULT_REFERENCE = "قَرَأَ الطَّالِبُ الكِتَابَ فِي المَكْتَبَةِ"

# ANSI terminal colors
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_GRAY = "\033[90m"
C_MAGENTA = "\033[95m"
C_CYAN = "\033[96m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"


# ── Audio Recording ──────────────────────────────────────────────────────────


def record_audio() -> np.ndarray | None:
    """Record from microphone until user presses Enter."""
    frames: list[np.ndarray] = []

    def callback(indata, frame_count, time_info, status):
        if status:
            print(f"  [audio warning: {status}]")
        frames.append(indata.copy())

    try:
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=callback,
        )
    except Exception as e:
        print(f"{C_RED}Could not open microphone: {e}{C_RESET}")
        return None

    print(f"\n{C_BOLD}Recording... press Enter to stop{C_RESET}")
    stream.start()
    input()
    stream.stop()
    stream.close()

    if not frames:
        return None

    audio = np.concatenate(frames, axis=0).flatten()

    if len(audio) < SAMPLE_RATE * MIN_AUDIO_SECONDS:
        print(f"{C_YELLOW}Recording too short. Try again.{C_RESET}")
        return None

    return audio


# ── Display ──────────────────────────────────────────────────────────────────


def display_results(results, transcript):
    """Print colored word-by-word comparison to the terminal."""
    print(f"\n{C_BOLD}You said:{C_RESET}  {transcript}")
    print(f"\n{C_BOLD}Word-by-word assessment:{C_RESET}\n")

    for i, wd in enumerate(results, 1):
        conf_tag = ""
        if hasattr(wd, "confidence") and wd.confidence == Confidence.LOW:
            conf_tag = f" {C_GRAY}(low confidence){C_RESET}"
        elif hasattr(wd, "confidence") and wd.confidence == Confidence.MEDIUM:
            conf_tag = f" {C_GRAY}(medium confidence){C_RESET}"

        if wd.kind == DiffKind.CORRECT:
            print(f"  {i}. {C_GREEN}\u2705 {wd.ref_word}{C_RESET}{conf_tag}")
        elif wd.kind == DiffKind.PAUSAL_OK:
            print(f"  {i}. {C_GREEN}\u2705 {wd.ref_word} {C_GRAY}(pausal form OK){C_RESET}")
        elif wd.kind == DiffKind.WRONG_IRAB:
            case_info = ""
            if wd.detected_case and wd.expected_case:
                case_info = f" [{wd.detected_case} instead of {wd.expected_case}]"
            print(f"  {i}. {C_CYAN}\u26a0\ufe0f  {wd.ref_word} \u2192 {wd.hyp_word}{case_info}{C_RESET}{conf_tag}")
        elif wd.kind == DiffKind.WRONG_TASHKEEL:
            print(f"  {i}. {C_YELLOW}\u26a0\ufe0f  {wd.ref_word} \u2192 {wd.hyp_word}{C_RESET}{conf_tag}")
        elif wd.kind == DiffKind.WRONG_WORD:
            print(f"  {i}. {C_RED}\u274c {wd.ref_word} \u2192 {wd.hyp_word}{C_RESET}")
        elif wd.kind == DiffKind.MISSING:
            print(f"  {i}. {C_GRAY}\u2796 {wd.ref_word} (missing){C_RESET}")
        elif wd.kind == DiffKind.EXTRA:
            print(f"  {i}. {C_MAGENTA}\u2795 {wd.hyp_word} (extra){C_RESET}")

    # Detailed diffs
    issues = [wd for wd in results if wd.kind in (DiffKind.WRONG_TASHKEEL, DiffKind.WRONG_IRAB)]
    if issues:
        print(f"\n{C_BOLD}Diacritics details:{C_RESET}")
        for wd in issues:
            label = "i3rab" if wd.kind == DiffKind.WRONG_IRAB else "tashkeel"
            print(f"\n  {C_YELLOW}{wd.ref_word} ({label}):{C_RESET}")
            for hd in wd.haraka_diffs:
                exp = format_haraka_list(hd.expected)
                got = format_haraka_list(hd.got)
                marker = " <-- i3rab" if hd.is_irab else ""
                print(f"    letter '{hd.letter}' (pos {hd.position}): expected {exp}, got {got}{marker}")

    total = len(results)
    correct = sum(1 for wd in results if wd.kind in (DiffKind.CORRECT, DiffKind.PAUSAL_OK))
    print(f"\n{C_BOLD}Score: {correct}/{total} words correct{C_RESET}")


# ── GPT-4o I3rab Explanation ─────────────────────────────────────────────────


def explain_irab(client, word: str, full_sentence: str):
    """Use GPT-4o to explain the i3rab of a word in context."""
    print(f"\n{C_BOLD}Asking GPT-4o about: {word}{C_RESET}\n")

    try:
        response = client.chat.completions.create(
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
                        f"The sentence: {full_sentence}\n"
                        f"The word: {word}\n\n"
                        "Explain the i3rab of this word."
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=500,
        )
        print(response.choices[0].message.content)
    except Exception as e:
        print(f"{C_RED}GPT-4o error: {e}{C_RESET}")


# ── Main Loop ────────────────────────────────────────────────────────────────


def main():
    load_dotenv()

    print(f"\n{C_BOLD}i3rab - Arabic Recitation Correction{C_RESET}")
    print("Using hypothesis scoring for diacritics assessment\n")

    # Check for book file argument
    reference = DEFAULT_REFERENCE
    book_title = ""

    if len(sys.argv) > 1:
        book_path = sys.argv[1]
        if os.path.isfile(book_path):
            print(f"Loading book: {book_path}")
            with open(book_path, "r", encoding="utf-8") as f:
                reference = f.read().strip()
            book_title = os.path.splitext(os.path.basename(book_path))[0]
        else:
            # Treat argument as inline text
            reference = sys.argv[1]

    # Create book and pipeline
    config = Config()
    book = Book.from_text(reference, title=book_title, auto_diacritize=True)
    pipeline = I3rabPipeline(book, config)

    print(f"Loading models...")
    pipeline.load_models()

    # Optional: OpenAI for i3rab explanations
    openai_client = None
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        from openai import OpenAI
        openai_client = OpenAI(api_key=api_key)
        print(f"{C_GREEN}OpenAI available for i3rab explanations.{C_RESET}")
    else:
        print(f"{C_YELLOW}No OPENAI_API_KEY — i3rab explanations disabled.{C_RESET}")

    # Display book info
    print(f"\n{C_BOLD}Book: {book.title or 'Quick Test'}{C_RESET}")
    print(f"Words: {len(book.words)}, Phrases: {len(book.phrases)}")

    phrase_idx = 0

    while phrase_idx < len(book.phrases):
        phrase = book.phrases[phrase_idx]

        print(f"\n{'=' * 60}")
        print(f"{C_BOLD}Phrase {phrase_idx + 1}/{len(book.phrases)}:{C_RESET}")
        print(f"  {phrase.text}")
        print(f"{'=' * 60}")

        input(f"\nPress {C_BOLD}Enter{C_RESET} to start recording...")

        audio_data = record_audio()
        if audio_data is None:
            continue

        try:
            print(f"{C_BOLD}Evaluating with hypothesis scoring...{C_RESET}")
            result = pipeline.evaluate_phrase(audio_data)
        except Exception as e:
            print(f"{C_RED}Evaluation error: {e}{C_RESET}")
            import traceback
            traceback.print_exc()
            continue

        if not result["results"]:
            print(f"{C_YELLOW}Could not understand audio. Try again.{C_RESET}")
            continue

        display_results(result["results"], result["transcript"])

        # I3rab explanation loop
        ref_words = phrase.text.split()
        if openai_client:
            while True:
                choice = input(
                    f"\nType a word number (1-{len(ref_words)}) for i3rab details, "
                    f"'n' for next phrase, or 'r' to retry: "
                ).strip()
                if choice.lower() == "n":
                    phrase_idx += 1
                    break
                if choice.lower() == "r":
                    break
                if choice.lower() == "q":
                    print(f"\n{C_BOLD}Ma'a salama!{C_RESET}")
                    return
                if choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(ref_words):
                        explain_irab(openai_client, ref_words[idx], phrase.text)
                    else:
                        print(f"Pick a number between 1 and {len(ref_words)}.")
        else:
            choice = input(f"\n'n' = next phrase, 'r' = retry, 'q' = quit: ").strip().lower()
            if choice == "n":
                phrase_idx += 1
            elif choice == "q":
                break

    print(f"\n{C_BOLD}Finished all phrases! Ma'a salama!{C_RESET}")


if __name__ == "__main__":
    main()
