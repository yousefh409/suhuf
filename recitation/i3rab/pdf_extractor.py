"""PDF text extraction with word-level bounding boxes.

Supports:
- Digital (text-based) PDFs via PyMuPDF
- Scanned PDFs via Surya OCR fallback
"""

import re
from pathlib import Path

from .models import PDFWord, PDFPage, PDFDocument
from .arabic import normalize_arabic, strip_harakat


def _is_arabic(text: str) -> bool:
    """Check if text contains Arabic characters."""
    return bool(re.search(r'[\u0600-\u06FF]', text))


def _clean_word(text: str) -> str:
    """Clean extracted word text, keeping Arabic chars and diacritics."""
    # Remove surrounding punctuation but keep Arabic chars + harakat
    text = text.strip()
    # Strip leading/trailing non-Arabic, non-harakat chars
    text = re.sub(r'^[^\u0600-\u06FF\u064B-\u0652]+', '', text)
    text = re.sub(r'[^\u0600-\u06FF\u064B-\u0652]+$', '', text)
    return text


def _extract_digital(pdf_path: str) -> PDFDocument:
    """Extract text and word bounding boxes from a digital PDF using PyMuPDF."""
    import fitz

    doc = fitz.open(pdf_path)
    pages = []
    all_text_parts = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        rect = page.rect
        page_width = rect.width
        page_height = rect.height

        # get_text("words") returns list of (x0, y0, x1, y1, word, block_no, line_no, word_no)
        raw_words = page.get_text("words")

        pdf_words = []
        for x0, y0, x1, y1, word_text, block_no, line_no, word_no in raw_words:
            cleaned = _clean_word(word_text)
            if not cleaned or not _is_arabic(cleaned):
                continue

            pdf_words.append(PDFWord(
                text=cleaned,
                page_num=page_num,
                bbox=(x0, y0, x1, y1),
                line_num=line_no,
                word_idx_in_line=word_no,
                confidence=1.0,
            ))

        if pdf_words:
            all_text_parts.append(" ".join(w.text for w in pdf_words))

        pages.append(PDFPage(
            page_num=page_num,
            width=page_width,
            height=page_height,
            words=pdf_words,
            is_scanned=False,
        ))

    doc.close()

    title = Path(pdf_path).stem
    return PDFDocument(
        pages=pages,
        title=title,
        full_text=" ".join(all_text_parts),
    )


def _is_scanned_page(page) -> bool:
    """Detect if a PDF page is scanned (image-based, no selectable text)."""
    text = page.get_text("text").strip()
    # If very little text but page has images, it's likely scanned
    if len(text) < 10:
        images = page.get_images()
        if images:
            return True
    return False


def _extract_scanned(pdf_path: str) -> PDFDocument:
    """Extract text from scanned PDF pages using Surya OCR."""
    import fitz
    from surya.recognition import RecognitionPredictor
    from surya.detection import DetectionPredictor
    from PIL import Image
    import io

    doc = fitz.open(pdf_path)
    pages = []
    all_text_parts = []

    # Initialize Surya models
    det_predictor = DetectionPredictor()
    rec_predictor = RecognitionPredictor()

    for page_num in range(len(doc)):
        page = doc[page_num]
        rect = page.rect
        page_width = rect.width
        page_height = rect.height

        # Render page to image for OCR
        pix = page.get_pixmap(dpi=300)
        img_bytes = pix.tobytes("png")
        image = Image.open(io.BytesIO(img_bytes))

        # Run Surya OCR
        from surya.recognition import run_recognition
        from surya.detection import run_detection

        det_results = run_detection([image], det_predictor)
        rec_results = run_recognition(
            [image], [det_results[0]], rec_predictor, ["ar"]
        )

        pdf_words = []
        line_num = 0

        for text_line in rec_results[0].text_lines:
            line_text = text_line.text
            line_bbox = text_line.bbox  # [x0, y0, x1, y1]

            # Split line into words and interpolate bboxes
            words = line_text.split()
            if not words:
                continue

            line_width = line_bbox[2] - line_bbox[0]
            total_chars = sum(len(w) for w in words)

            # Approximate word bboxes by character proportion (RTL)
            current_x = line_bbox[2]  # Start from right for RTL
            for word_idx, word in enumerate(words):
                cleaned = _clean_word(word)
                if not cleaned or not _is_arabic(cleaned):
                    continue

                word_width = (len(word) / max(total_chars, 1)) * line_width
                word_x1 = current_x
                word_x0 = current_x - word_width
                current_x = word_x0 - (line_width * 0.02)  # Small gap

                # Scale from image coords (300 DPI) to PDF coords (72 DPI)
                scale = 72.0 / 300.0
                bbox = (
                    word_x0 * scale,
                    line_bbox[1] * scale,
                    word_x1 * scale,
                    line_bbox[3] * scale,
                )

                pdf_words.append(PDFWord(
                    text=cleaned,
                    page_num=page_num,
                    bbox=bbox,
                    line_num=line_num,
                    word_idx_in_line=word_idx,
                    confidence=text_line.confidence if hasattr(text_line, 'confidence') else 0.9,
                ))

            line_num += 1

        if pdf_words:
            all_text_parts.append(" ".join(w.text for w in pdf_words))

        pages.append(PDFPage(
            page_num=page_num,
            width=page_width,
            height=page_height,
            words=pdf_words,
            is_scanned=True,
        ))

    doc.close()

    title = Path(pdf_path).stem
    return PDFDocument(
        pages=pages,
        title=title,
        full_text=" ".join(all_text_parts),
    )


def extract_pdf(pdf_path: str) -> PDFDocument:
    """Extract text from a PDF, auto-detecting digital vs scanned pages.

    For digital PDFs: uses PyMuPDF for fast, accurate extraction.
    For scanned PDFs: falls back to Surya OCR.
    Mixed PDFs: processes each page with the appropriate method.
    """
    import fitz

    doc = fitz.open(pdf_path)

    # Check if any pages are scanned
    has_scanned = False
    has_digital = False
    for page_num in range(len(doc)):
        page = doc[page_num]
        if _is_scanned_page(page):
            has_scanned = True
        else:
            has_digital = True

    doc.close()

    if has_scanned and not has_digital:
        # Fully scanned PDF
        return _extract_scanned(pdf_path)
    elif not has_scanned:
        # Fully digital PDF
        return _extract_digital(pdf_path)
    else:
        # Mixed: extract digital pages with PyMuPDF, scanned with OCR
        return _extract_mixed(pdf_path)


def _extract_mixed(pdf_path: str) -> PDFDocument:
    """Handle PDFs with both digital and scanned pages."""
    import fitz

    doc = fitz.open(pdf_path)
    digital_doc = _extract_digital(pdf_path)

    # Find scanned pages and re-extract with OCR
    scanned_indices = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        if _is_scanned_page(page):
            scanned_indices.append(page_num)
    doc.close()

    if not scanned_indices:
        return digital_doc

    # For scanned pages, use OCR
    try:
        scanned_doc = _extract_scanned(pdf_path)
        # Replace scanned pages in digital doc
        for idx in scanned_indices:
            if idx < len(digital_doc.pages) and idx < len(scanned_doc.pages):
                digital_doc.pages[idx] = scanned_doc.pages[idx]

        # Rebuild full text
        digital_doc.full_text = " ".join(
            " ".join(w.text for w in p.words)
            for p in digital_doc.pages if p.words
        )
    except ImportError:
        print("WARNING: surya-ocr not installed. Scanned pages will have no text.")
        print("Install with: pip install surya-ocr")

    return digital_doc


def render_page_to_png(pdf_path: str, page_num: int, dpi: int = 150) -> bytes:
    """Render a PDF page to PNG bytes for display in the app."""
    import fitz

    doc = fitz.open(pdf_path)
    if page_num >= len(doc):
        doc.close()
        raise ValueError(f"Page {page_num} out of range (document has {len(doc)} pages)")

    page = doc[page_num]
    pix = page.get_pixmap(dpi=dpi)
    png_bytes = pix.tobytes("png")
    doc.close()
    return png_bytes


def get_page_count(pdf_path: str) -> int:
    """Get the number of pages in a PDF."""
    import fitz
    doc = fitz.open(pdf_path)
    count = len(doc)
    doc.close()
    return count
