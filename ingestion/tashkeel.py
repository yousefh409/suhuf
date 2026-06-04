from __future__ import annotations
import logging
from typing import Protocol
from ingestion.models import Token, Block, Page

logger = logging.getLogger(__name__)

DIACRITIC_CODEPOINTS = {
    "\u064B", "\u064C", "\u064D", "\u064E", "\u064F",
    "\u0650", "\u0651", "\u0652",  # fathatan through sukun
}
DIACRITIC_RATIO_THRESHOLD = 0.15


class TashkeelEngine(Protocol):
    def diacritize(self, text: str) -> str: ...


def has_diacritics(text: str) -> bool:
    """Check if text has sufficient diacritical marks (ratio > threshold)."""
    if not text:
        return False
    total = sum(1 for c in text if c.isalpha() or c in DIACRITIC_CODEPOINTS)
    if total == 0:
        return False
    diac_count = sum(1 for c in text if c in DIACRITIC_CODEPOINTS)
    return (diac_count / total) > DIACRITIC_RATIO_THRESHOLD


def _block_text(block: Block) -> str:
    """Get all text from a block as a single string."""
    if block.type == "poetry":
        words = []
        for verse in block.hemistichs:
            for hemistich in verse:
                words.extend(t.text for t in hemistich)
        return " ".join(words)
    return " ".join(t.text for t in block.tokens)


def _diacritize_block(block: Block, engine: TashkeelEngine | None, page_num: int) -> Block:
    """Diacritize a single block. Returns a new Block with updated tokens."""
    text = _block_text(block)
    if not text or has_diacritics(text) or engine is None:
        return block

    try:
        result = engine.diacritize(text)
    except Exception as e:
        logger.warning(f"Tashkeel failed for block {block.key} on page {page_num}: {e}")
        return block

    result_words = result.split()

    if block.type == "poetry":
        original_words = []
        for verse in block.hemistichs:
            for hemistich in verse:
                original_words.extend(t.text for t in hemistich)

        if len(result_words) != len(original_words):
            logger.warning(
                f"Token count mismatch in poetry block {block.key} on page {page_num}: "
                f"expected {len(original_words)}, got {len(result_words)}. Keeping original."
            )
            return block

        idx = 0
        new_hemistichs = []
        for verse in block.hemistichs:
            new_verse = []
            for hemistich in verse:
                new_h = []
                for token in hemistich:
                    w = result_words[idx]
                    new_h.append(Token(
                        id=token.id,
                        text=w,
                        text_raw=token.text if token.text != w else None,
                    ))
                    idx += 1
                new_verse.append(new_h)
            new_hemistichs.append(new_verse)

        return Block(key=block.key, type=block.type, hemistichs=new_hemistichs, metadata=block.metadata)

    # Non-poetry blocks
    if len(result_words) != len(block.tokens):
        logger.warning(
            f"Token count mismatch in block {block.key} on page {page_num}: "
            f"expected {len(block.tokens)}, got {len(result_words)}. Keeping original."
        )
        return block

    new_tokens = [
        Token(id=t.id, text=w, text_raw=t.text if t.text != w else None)
        for t, w in zip(block.tokens, result_words)
    ]
    return Block(key=block.key, type=block.type, tokens=new_tokens, metadata=block.metadata)


def diacritize_blocks(pages: list[Page], engine: TashkeelEngine | None) -> list[Page]:
    """Diacritize all blocks in all pages. Returns new Page objects."""
    result = []
    for page in pages:
        new_blocks = [_diacritize_block(b, engine, page.page_number) for b in page.content_blocks]
        result.append(Page(page_number=page.page_number, volume=page.volume, content_blocks=new_blocks))
    return result


class _ShakkalaEngine:
    """Shakkala diacritization via arabic_vocalizer ONNX runtime."""

    def diacritize(self, text: str) -> str:
        from arabic_vocalizer import vocalize
        return vocalize(text, model="shakkala")


class _FlanT5Engine:
    """FLAN-T5 Arabic tashkeel via HuggingFace transformers."""

    def __init__(self):
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

        model_path = "Abdou/arabic-tashkeel-flan-t5-small"
        self._tokenizer = AutoTokenizer.from_pretrained(model_path)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(model_path)
        self._model.eval()
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)

    def diacritize(self, text: str) -> str:
        return self.diacritize_batch([text])[0]

    def diacritize_batch(self, texts: list[str]) -> list[str]:
        import torch

        # Dynamic padding (to the longest in the batch, not a fixed 256) makes
        # short hadith blocks far cheaper than padding="max_length".
        inputs = self._tokenizer(
            texts, return_tensors="pt", max_length=256, truncation=True, padding=True,
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self._model.generate(**inputs, max_length=256, num_beams=4, early_stopping=True)
        return [self._tokenizer.decode(o, skip_special_tokens=True) for o in outputs]


def load_engine(name: str = "shakkala") -> TashkeelEngine | None:
    """Load a tashkeel engine by name. Returns None if loading fails.

    Available engines:
        shakkala  -- Shakkala ONNX via arabic_vocalizer (fast, recommended)
        flan-t5   -- Abdou/arabic-tashkeel-flan-t5-small (slower, higher quality on classical)
        sadeed    -- Alias for shakkala (Sadeed weights not yet public)
    """
    # sadeed falls through to shakkala until model weights are published
    if name == "sadeed":
        logger.info("Sadeed weights not yet public; falling back to Shakkala.")
        name = "shakkala"

    if name == "shakkala":
        try:
            logger.info("Loading Shakkala tashkeel engine (ONNX)...")
            engine = _ShakkalaEngine()
            # Warm up with a short test
            engine.diacritize("بسم الله")
            logger.info("Shakkala loaded.")
            return engine
        except Exception as e:
            logger.warning(f"Failed to load Shakkala: {e}. Trying flan-t5 fallback.")
            return load_engine("flan-t5")
    elif name == "flan-t5":
        try:
            logger.info("Loading FLAN-T5 tashkeel engine...")
            engine = _FlanT5Engine()
            logger.info("FLAN-T5 loaded.")
            return engine
        except Exception as e:
            logger.warning(f"Failed to load FLAN-T5: {e}")
            return None
    else:
        logger.error(f"Unknown tashkeel engine: {name}")
        return None
