from __future__ import annotations

import json
import os
import threading
from typing import Any

from app.config.logger import logger

# PaddleOCR 3.x on CPU can hit a PIR/oneDNN conversion bug. These must be
# present before Paddle/PaddleOCR is imported. We also pin a known-compatible
# PaddleOCR release in requirements.txt.
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")


class OCRError(Exception):
    """Base OCR error."""


class OCRUnavailableError(OCRError):
    """OCR engine is unavailable."""


class OCRProcessingError(OCRError):
    """OCR processing failed."""


_engine: Any = None
_engine_lock = threading.Lock()


def _get_engine() -> Any:
    global _engine

    if _engine is not None:
        return _engine

    with _engine_lock:
        if _engine is not None:
            return _engine

        try:
            from paddleocr import PaddleOCR

            # CPU-only, legacy-IR-safe configuration. Do not use the
            # document-unwarping/orientation pipeline for this feature: the
            # academic calendar only needs ordinary text recognition and the
            # extra models increase startup time and memory use.
            _engine = PaddleOCR(
                lang="en",
                device="cpu",
                enable_mkldnn=False,
                # This feature only needs ordinary OCR. Disabling the
                # document-orientation/unwarping stages avoids unnecessary
                # model downloads and keeps scanned-calendar processing
                # lightweight and predictable on CPU.
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        except Exception as exc:
            logger.exception("Failed to initialize PaddleOCR")
            raise OCRUnavailableError("OCR engine is unavailable.") from exc

    return _engine


def run_ocr(image_bytes: bytes) -> str:
    if not image_bytes:
        raise OCRProcessingError("Empty image data.")

    try:
        import cv2
        import numpy as np

        array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)

        if image is None:
            raise OCRProcessingError("Unable to decode OCR image.")
    except OCRProcessingError:
        raise
    except Exception as exc:
        logger.exception("Failed to decode OCR image")
        raise OCRProcessingError("Unable to prepare image for OCR.") from exc

    engine = _get_engine()

    try:
        # PaddleOCR 3.x uses predict(); the fallback keeps the service
        # compatible with older supported 3.x builds used by deployments.
        if hasattr(engine, "predict"):
            results = engine.predict(image)
        else:
            results = engine.ocr(image)
    except Exception as exc:
        logger.exception("PaddleOCR inference failed")
        raise OCRProcessingError("OCR processing failed.") from exc

    return _extract_text_from_result(results)


def _extract_text_from_result(results: Any) -> str:
    lines: list[str] = []

    def visit(value: Any) -> None:
        if value is None:
            return

        if hasattr(value, "json"):
            try:
                data = value.json
                if callable(data):
                    data = data()
                if isinstance(data, str):
                    data = json.loads(data)
                visit(data)
                return
            except Exception:
                pass

        if isinstance(value, dict):
            texts = value.get("rec_texts")
            if texts:
                lines.extend(
                    str(text).strip()
                    for text in texts
                    if str(text).strip()
                )
            # Some PaddleOCR result objects expose nested dictionaries.
            for key, nested in value.items():
                if key != "rec_texts" and isinstance(nested, (dict, list, tuple)):
                    visit(nested)
            return

        if isinstance(value, (list, tuple)):
            if len(value) == 2:
                second = value[1]
                if (
                    isinstance(second, (list, tuple))
                    and second
                    and isinstance(second[0], str)
                ):
                    text = second[0].strip()
                    if text:
                        lines.append(text)
                    return
            for nested in value:
                visit(nested)

    visit(results)

    output: list[str] = []
    seen: set[str] = set()
    for line in lines:
        line = " ".join(line.split())
        if line and line not in seen:
            seen.add(line)
            output.append(line)

    return "\n".join(output).strip()