# i3rab - Arabic Recitation Correction Tool

Listens to your Arabic recitation and checks your diacritics (tashkeel/harakat) — including **i3rab (grammatical case endings)** — against a known text. Uses **hypothesis scoring**: for each word, scores all possible diacritized forms against your audio and picks the best match.

## How It Works

1. Load a book or sentence (fully diacritized Arabic text)
2. The system pre-computes all valid i3rab hypotheses per word (nominative, accusative, genitive, pausal)
3. You read aloud phrase by phrase
4. For each word, the scorer tests your audio against all hypotheses and detects what you actually said
5. Differences between your pronunciation and the correct diacritization are highlighted
6. Optionally explains the i3rab grammar rule via GPT-4o

### Architecture

```
Known text → hypothesis generation (all valid i3rab forms per word)
                                                    ↓
User audio → Whisper ASR → position tracking → which words are they reading?
                                                    ↓
         Whisper encoder → score audio against each hypothesis per word
                                                    ↓
                              Best match = what they pronounced
                              Compare to correct = find errors
```

## Setup

### Prerequisites

- Python 3.10+
- macOS with Apple Silicon (tested on M4 Pro)
- Microphone access
- OpenAI API key (optional, for i3rab explanations)

### Install

```bash
cd i3rab
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### Optional: Enhanced Diacritization

```bash
# Auto-diacritize undiacritized book text (SOTA accuracy)
pip install catt-tashkeel

# Morphologically-informed hypothesis generation
pip install camel-tools
camel_data -i all
```

### Environment Variables

Create a `.env` file:

```
OPENAI_API_KEY=sk-your-key-here
```

Optional — without it, i3rab explanations are disabled.

## Usage

### CLI Mode

```bash
# Single sentence (default)
python main.py

# Load a book file
python main.py books/sample.txt

# Inline text
python main.py "قَرَأَ الطَّالِبُ الكِتَابَ فِي المَكْتَبَةِ"
```

### Web Mode

```bash
python server.py
# Open http://localhost:8000
```

### API Endpoints

```
GET  /api/reference           # Get current reference text
POST /api/book/load           # Load a new book (JSON: {text, title})
GET  /api/book/phrase/{idx}   # Get phrase details
POST /api/transcribe          # Evaluate audio (multipart: audio file)
POST /api/phrase/evaluate     # Evaluate audio for specific phrase
POST /api/explain             # Get i3rab explanation (JSON: {word, sentence})
POST /api/reset               # Reset position tracker
```

## How the Assessment Works

### Hypothesis Scoring

For each word in the text, the system:
1. Generates all valid diacritized forms (e.g., الكتابُ / الكتابَ / الكتابِ)
2. Encodes your audio with Whisper's encoder
3. Scores each hypothesis using decoder log-likelihoods
4. Picks the highest-scoring hypothesis = what you most likely said
5. Compares to the correct form

### Result Categories

- **Correct** — diacritics match the reference
- **Pausal OK** — you used a pausal form (dropped case ending) at a phrase boundary, which is grammatically correct
- **Wrong i3rab** — case ending error (e.g., said damma where fatha was expected)
- **Wrong tashkeel** — internal vowel error (e.g., said كُتِبَ instead of كَتَبَ)
- **Wrong word** — different base letters entirely
- **Missing / Extra** — word alignment issues

### Confidence Levels

Each assessment includes a confidence indicator:
- **High** — large score gap between hypotheses; detection is reliable
- **Medium** — moderate gap; likely correct but some uncertainty
- **Low** — small gap; ambiguous, may not be reliable

## Project Structure

```
i3rab/
├── main.py              # CLI entry point
├── server.py            # FastAPI web server
├── static/index.html    # Web UI
├── books/               # Book text files
│   └── sample.txt
├── i3rab/               # Core package
│   ├── models.py        # Data types
│   ├── arabic.py        # Arabic text utilities
│   ├── config.py        # Settings
│   ├── book.py          # Book loading + hypothesis generation
│   ├── tracker.py       # Position tracking
│   ├── scorer.py        # Hypothesis scoring (core innovation)
│   └── pipeline.py      # Orchestrator
└── requirements.txt
```
