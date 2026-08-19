from pathlib import Path

import fitz
from docx import Document
from docx.document import Document as _DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.config.logger import logger


SUPPORTED_EXTENSIONS = {".pdf", ".docx"}
METHOD_TEXT = "text"
METHOD_OCR = "ocr"


class DocumentExtractionError(Exception):
    """Controlled document extraction error."""


class DocumentOCRUnavailableError(DocumentExtractionError):
    """OCR runtime/model is unavailable."""


class DocumentOCRProcessingError(DocumentExtractionError):
    """OCR was available but failed while processing the document."""



def extract_text_with_method(filepath: str) -> tuple[str, str]:
    extension = Path(filepath).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentExtractionError("Only PDF and DOCX files are supported.")

    if extension == ".pdf":
        return _extract_pdf(filepath)

    return _extract_docx(filepath)


def extract_text(filepath: str) -> str:
    text, _ = extract_text_with_method(filepath)
    return text


def _has_meaningful_text(text: str) -> bool:
    if not text:
        return False
    meaningful_characters = sum(1 for character in text if character.isalnum())
    return meaningful_characters >= 20


def _extract_pdf(filepath: str) -> tuple[str, str]:
    document = None

    try:
        document = fitz.open(filepath)
        native_text_parts: list[str] = []

        for page in document:
            page_text = page.get_text("text").strip()
            if page_text:
                native_text_parts.append(page_text)

        native_text = "\n\n".join(native_text_parts).strip()

        if _has_meaningful_text(native_text):
            return native_text, METHOD_TEXT

        logger.info("PDF has insufficient native text; switching to OCR")

        ocr_text = _extract_pdf_with_ocr(document)

        if not _has_meaningful_text(ocr_text):
            raise DocumentExtractionError(
                "Unable to extract readable text from the PDF."
            )

        return ocr_text, METHOD_OCR

    except DocumentExtractionError:
        raise
    except Exception as exc:
        logger.exception("Academic calendar PDF extraction failed")
        raise DocumentExtractionError(
            "Unable to process the academic calendar PDF."
        ) from exc
    finally:
        if document is not None:
            document.close()


def _render_page_to_image(page) -> bytes:
    """Render a page at a bounded resolution and return an in-memory PNG."""
    # 2.0x is enough for a normal scanned A4/A3 college calendar. The hard
    # cap prevents very large scans from creating 5k+ pixel images and
    # consuming excessive CPU/RAM during OCR.
    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(2.0, 2.0),
        alpha=False,
    )

    max_side = max(pixmap.width, pixmap.height)
    if max_side > 3200:
        scale = 3200.0 / max_side
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(2.0 * scale, 2.0 * scale),
            alpha=False,
        )

    return pixmap.tobytes("png")


def _extract_pdf_with_ocr(document) -> str:
    from app.services.ocr_service import (
        OCRProcessingError,
        OCRUnavailableError,
        run_ocr,
    )

    page_texts: list[str] = []

    for page_number, page in enumerate(document, start=1):
        try:
            image_bytes = _render_page_to_image(page)
            text = run_ocr(image_bytes).strip()

            if text:
                page_texts.append(f"[PAGE {page_number}]\n{text}")

        except OCRUnavailableError as exc:
            logger.exception("OCR engine unavailable on PDF page %s", page_number)
            raise DocumentOCRUnavailableError(
                "OCR engine is unavailable for scanned PDF processing."
            ) from exc
        except OCRProcessingError as exc:
            logger.exception("OCR failed on PDF page %s", page_number)
            raise DocumentOCRProcessingError(
                "OCR processing failed for the uploaded PDF."
            ) from exc

    return "\n\n".join(page_texts).strip()


def _iter_docx_block_items(parent):
    """Yield paragraphs and tables in their actual document order."""
    if isinstance(parent, _DocxDocument):
        parent_elm = parent.element.body
    else:
        parent_elm = parent._tc

    for child in parent_elm.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


def _table_to_lines(table: Table) -> list[str]:
    lines: list[str] = []
    for row in table.rows:
        cells: list[str] = []
        seen_cells: set[int] = set()
        for cell in row.cells:
            cell_id = id(cell._tc)
            if cell_id in seen_cells:
                continue
            seen_cells.add(cell_id)
            value = cell.text.strip()
            if value:
                cells.append(value)
        if cells:
            lines.append(" | ".join(cells))
    return lines


def _extract_docx(filepath: str) -> tuple[str, str]:
    try:
        document = Document(filepath)
        parts: list[str] = []

        for block in _iter_docx_block_items(document):
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if text:
                    parts.append(text)
            elif isinstance(block, Table):
                parts.extend(_table_to_lines(block))

        text = "\n".join(parts).strip()

        if not _has_meaningful_text(text):
            raise DocumentExtractionError(
                "Unable to extract readable text from the DOCX."
            )

        return text, METHOD_TEXT

    except DocumentExtractionError:
        raise
    except Exception as exc:
        logger.exception("Academic calendar DOCX extraction failed")
        raise DocumentExtractionError(
            "Unable to process the academic calendar DOCX."
        ) from exc
