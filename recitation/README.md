# i3rab - Arabic Diacritization Assessment Tool

Listens to your Arabic recitation and checks your diacritics (tashkeel/harakat) — including **i3rab (grammatical case endings)** — against a known text. Uses a fine-tuned **XLS-R 300M + CTC** model to score pronunciation against all valid diacritized forms of each word.

**97.5% accuracy** on real user recordings (286-word test suite).

## How It Works

1. Load a book or sentence (fully diacritized Arabic text)
2. The system pre-computes all valid i3rab hypotheses per word (nominative, accusative, genitive, pausal)
3. You read aloud phrase by phrase
4. Audio is encoded by XLS-R and scored via CTC forced alignment against each hypothesis
5. Differences between your pronunciation and the correct diacritization are highlighted

### Architecture

```
Known text → hypothesis generation (all valid i3rab forms per word)
                                                    ↓
User audio → XLS-R encoder → CTC log-probs → forced alignment → word boundaries
                                                    ↓
                    Per-word: score each hypothesis via CTC log-likelihood
                                                    ↓
                              Best match = what they pronounced
                              Compare to correct = find errors
```

## Accuracy

| Metric | Score |
|--------|-------|
| User recordings (286 words) | **275/282 (97.5%)** |
| ClArTTS error recall (test) | 548/572 (95.8%) |
| False positive rate | 2.17% |
| i3rab recall | 88.5% |
| Tashkeel recall | 100.0% (303/303) |
| Wrong word recall | 93.5% |

## Setup

### Prerequisites

- Python 3.10+
- macOS with Apple Silicon (tested on M4 Pro) or CUDA GPU
- Microphone access
- OpenAI API key (optional, for i3rab grammar explanations)

### Install

```bash
cd i3rab/recitation
python3 -m venv ../venv
source ../venv/bin/activate

pip install -r requirements.txt
```

### Models

The production model is **XLS-R v5** (`models/ssl_xls_r_v5/`). It must be downloaded separately (1.2GB):

```bash
# Place model files in recitation/models/ssl_xls_r_v5/
# Required files: config.json, model.safetensors, processor_config.json,
#                 tokenizer_config.json, vocab.json
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

Optional — without it, i3rab grammar explanations are disabled.

## Usage

### CLI Mode

```bash
cd recitation

# Single sentence (default)
python main.py --ssl-model models/ssl_xls_r_v5 --ssl-training-sr 16000

# Load a book file
python main.py books/sample.txt --ssl-model models/ssl_xls_r_v5 --ssl-training-sr 16000

# Inline text
python main.py "قَرَأَ الطَّالِبُ الكِتَابَ فِي المَكْتَبَةِ" --ssl-model models/ssl_xls_r_v5 --ssl-training-sr 16000
```

### Web Mode

```bash
cd recitation
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

### CTC Hypothesis Scoring

For each word in the text, the system:
1. Generates all valid diacritized forms (e.g., الكتابُ / الكتابَ / الكتابِ)
2. Encodes audio with XLS-R and produces CTC log-probabilities over 58 Arabic character tokens
3. Uses forced alignment to find word boundaries in the audio
4. Scores each hypothesis via CTC log-likelihood over the word's audio segment
5. Picks the highest-scoring hypothesis = what you most likely said
6. Compares to the correct form

### Result Categories

- **Correct** — diacritics match the reference
- **Pausal OK** — pausal form (dropped case ending) at a phrase boundary, grammatically acceptable
- **Wrong i3rab** — case ending error (e.g., said damma where fatha was expected)
- **Wrong tashkeel** — internal vowel error (e.g., said كُتِبَ instead of كَتَبَ)
- **Wrong word** — different base letters entirely
- **Missing / Extra** — word alignment issues

### Confidence Levels

Each assessment includes a confidence indicator based on the CTC score gap:
- **High** — large gap between best and second-best hypothesis; reliable
- **Medium** — moderate gap; likely correct
- **Low** — small gap; ambiguous (reverted to "correct" if below threshold)

## Testing

```bash
cd recitation

# 286-word user recording test (word + sentence recordings)
python run_tests_pcd.py --ssl-model models/ssl_xls_r_v5 --ssl-training-sr 16000 --tashkeel-on

# ClArTTS error recall evaluation (injected errors on synthetic speech)
python eval_recall.py --ssl-model models/ssl_xls_r_v5 --ssl-training-sr 16000 --tashkeel-on --split test
```

## Project Structure

```
i3rab/
├── recitation/                  # Main application
│   ├── main.py                  # CLI entry point
│   ├── server.py                # FastAPI web server
│   ├── requirements.txt
│   ├── static/
│   │   └── index.html           # Web UI
│   ├── books/
│   │   └── sample.txt           # Sample diacritized text
│   ├── i3rab/                   # Core package
│   │   ├── models.py            # Data types (BookWord, WordDiff, etc.)
│   │   ├── arabic.py            # Arabic text utilities
│   │   ├── config.py            # Settings
│   │   ├── book.py              # Book loading + hypothesis generation
│   │   ├── tracker.py           # Position tracking
│   │   ├── scorer.py            # Whisper-based hypothesis scoring (legacy)
│   │   ├── ssl_transcriber.py   # XLS-R CTC transcriber (production)
│   │   ├── pcd_transcriber.py   # NeMo PCD transcriber (legacy)
│   │   ├── pipeline.py          # Orchestrator (CTC scoring pipeline)
│   │   ├── aligner.py           # CTC forced alignment
│   │   ├── cache.py             # Audio/result caching
│   │   ├── irab_agent.py        # GPT-4o grammar explanations
│   │   └── pdf_extractor.py     # PDF text extraction
│   ├── models/                  # Model weights (not in git)
│   │   ├── ssl_xls_r_v5/       # Production: XLS-R v5 (best)
│   │   ├── ssl_xls_r_v3/       # Previous best SSL model
│   │   └── pcd_clartts_v4.nemo # Legacy NeMo PCD model
│   ├── training/                # Model training scripts
│   │   ├── finetune_ssl_ctc.py  # XLS-R CTC fine-tuning
│   │   ├── finetune_pcd.py      # NeMo PCD fine-tuning
│   │   ├── prepare_data.py      # ClArTTS data preparation
│   │   ├── generate_contrastive_data.py
│   │   └── ...
│   ├── test_data/               # Test recordings (38 entries, 286 words)
│   │   ├── manifest.json
│   │   └── rec_*.webm
│   ├── eval_recall.py           # ClArTTS error recall evaluation
│   └── run_tests_pcd.py         # User recording test suite
└── venv/                        # Python virtual environment
```

## Model History

| Model | Architecture | 286-word | ClArTTS Recall | FP Rate |
|-------|-------------|----------|----------------|---------|
| Whisper (original) | Whisper decoder scoring | ~85% | N/A | N/A |
| NeMo PCD v4b | FastConformer CTC | 96.5% | ~84% | ~1.9% |
| XLS-R v3 | wav2vec2-xls-r-300m + CTC | 95.7% | 96.2% | 2.55% |
| XLS-R v4 | + online augmentation | 95.0% | 96.2% | 2.17% |
| **XLS-R v5** | **+ contrastive/TTS data (39.5K)** | **97.5%** | **95.8%** | **2.17%** |
