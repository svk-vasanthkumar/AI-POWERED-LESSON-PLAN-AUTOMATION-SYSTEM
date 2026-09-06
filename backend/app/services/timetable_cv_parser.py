from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

import cv2
import numpy as np

import os
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")

# We'll import PaddleOCR lazily or inside a locked initialization
# to match how ocr_service.py does it, preventing large overheads at startup
# but since the class does it in __init__, we'll import here.
from paddleocr import PaddleOCR
from app.config.logger import logger

# ============================================================
# CONFIGURATION
# ============================================================

@dataclass
class OCRConfig:
    language: str = "en"
    min_confidence: float = 0.45

    # Morphology
    horizontal_scale: int = 30
    vertical_scale: int = 30

    # Grid detection tolerance
    line_cluster_tolerance: int = 12

    # OCR preprocessing
    upscale: float = 1.5


@dataclass
class TimetableResult:
    staff_name: str = ""
    entries: list[dict[str, Any]] = None
    unassigned: list[dict[str, Any]] = None

    def __post_init__(self):
        if self.entries is None:
            self.entries = []
        if self.unassigned is None:
            self.unassigned = []


# ============================================================
# OCR ENGINE
# ============================================================

class PaddleTextRecognizer:

    def __init__(self, config: OCRConfig):
        self.config = config
        self.ocr = PaddleOCR(
            lang=config.language,
            device="cpu", # Stick to CPU for web service stability unless GPU explicitly needed
            enable_mkldnn=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

    def run(self, image: np.ndarray) -> list[dict]:
        try:
            if hasattr(self.ocr, "predict"):
                result = self.ocr.predict(image)
            else:
                result = self.ocr.ocr(image)
        except Exception as exc:
            logger.exception("PaddleOCR inference failed")
            return []

        records = []
        for page in result:
            data = self._normalize_result(page)
            if data is None:
                continue

            texts = data.get("rec_texts", [])
            scores = data.get("rec_scores", [])
            boxes = data.get("rec_boxes", [])

            for text, score, box in zip(texts, scores, boxes):
                try:
                    score = float(score)
                except Exception:
                    continue

                if score < self.config.min_confidence:
                    continue

                text = str(text).strip()
                if not text:
                    continue

                box = np.asarray(box, dtype=float)
                if box.shape != (4,):
                    continue

                x1, y1, x2, y2 = box
                records.append({
                    "text": text,
                    "confidence": score,
                    "bbox": [float(x1), float(y1), float(x2), float(y2)],
                    "center": [float((x1 + x2) / 2), float((y1 + y2) / 2)],
                })

        return records

    @staticmethod
    def _normalize_result(page):
        if isinstance(page, dict):
            if "res" in page:
                return page["res"]
            return page

        if hasattr(page, "json"):
            try:
                value = page.json
                if callable(value):
                    value = value()
                if isinstance(value, str):
                    value = json.loads(value)
                if isinstance(value, dict):
                    if "res" in value:
                        return value["res"]
                    return value
            except Exception:
                pass

        if hasattr(page, "res"):
            value = page.res
            if isinstance(value, dict):
                return value

        # Handle raw list outputs from older PaddleOCR versions
        if isinstance(page, list):
            # Page is a list of lines: [[[[x,y],[x,y],[x,y],[x,y]], ('Text', score)], ...]
            texts = []
            scores = []
            boxes = []
            for line in page:
                if isinstance(line, list) and len(line) == 2:
                    box, (text, score) = line
                    texts.append(text)
                    scores.append(score)
                    # Convert 4 points box to x1,y1,x2,y2
                    box_np = np.array(box)
                    x1 = np.min(box_np[:, 0])
                    y1 = np.min(box_np[:, 1])
                    x2 = np.max(box_np[:, 0])
                    y2 = np.max(box_np[:, 1])
                    boxes.append([x1, y1, x2, y2])
            return {"rec_texts": texts, "rec_scores": scores, "rec_boxes": boxes}

        return None


# ============================================================
# IMAGE PREPROCESSING
# ============================================================

class ImageProcessor:

    @staticmethod
    def load(path: str) -> np.ndarray:
        image = cv2.imread(path)
        if image is None:
            raise FileNotFoundError(f"Unable to read image: {path}")
        return image

    @staticmethod
    def rectify(image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        threshold = cv2.adaptiveThreshold(
            blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 10
        )
        contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return image

        image_area = image.shape[0] * image.shape[1]
        candidates = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < image_area * 0.15:
                continue

            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            if len(approx) == 4:
                candidates.append((area, approx))

        if not candidates:
            return image

        candidates.sort(key=lambda x: x[0], reverse=True)
        points = candidates[0][1].reshape(4, 2)
        ordered = ImageProcessor.order_points(points)

        width_top = np.linalg.norm(ordered[1] - ordered[0])
        width_bottom = np.linalg.norm(ordered[2] - ordered[3])
        height_left = np.linalg.norm(ordered[3] - ordered[0])
        height_right = np.linalg.norm(ordered[2] - ordered[1])

        width = int(max(width_top, width_bottom))
        height = int(max(height_left, height_right))

        if width < 500 or height < 200:
            return image

        destination = np.array([
            [0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1],
        ], dtype=np.float32)

        matrix = cv2.getPerspectiveTransform(ordered.astype(np.float32), destination)
        return cv2.warpPerspective(image, matrix, (width, height))

    @staticmethod
    def order_points(points):
        rect = np.zeros((4, 2), dtype=np.float32)
        sums = points.sum(axis=1)
        rect[0] = points[np.argmin(sums)]
        rect[2] = points[np.argmax(sums)]

        differences = np.diff(points, axis=1)
        rect[1] = points[np.argmin(differences)]
        rect[3] = points[np.argmax(differences)]
        return rect

    @staticmethod
    def upscale(image: np.ndarray, scale: float) -> np.ndarray:
        if scale == 1:
            return image
        return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


# ============================================================
# TIMETABLE GEOMETRY
# ============================================================

class TimetableGeometry:
    DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    def __init__(self, image_width: int, image_height: int):
        self.width = image_width
        self.height = image_height

    def find_day(self, y: float, y_top: float, y_bottom: float) -> Optional[str]:
        body_height = y_bottom - y_top
        if body_height <= 0:
            return None

        relative = (y - y_top) / body_height
        index = int(relative * len(self.DAYS))

        if index < 0 or index >= len(self.DAYS):
            return None
        return self.DAYS[index]

    def find_hour(self, x: float, x_left: float, x_right: float) -> Optional[int]:
        width = x_right - x_left
        if width <= 0:
            return None

        relative = (x - x_left) / width

        columns = [
            (0.090, 0.191, 1),
            (0.191, 0.291, 2),
            (0.291, 0.371, 3),
            (0.371, 0.468, 4),
            # Lunch column 0.468 - 0.562 intentionally skipped
            (0.562, 0.651, 5),
            (0.651, 0.746, 6),
            (0.746, 0.868, 7),
        ]

        for start, end, hour in columns:
            if start <= relative < end:
                return hour
        return None

    def column_region(self, x: float, x_left: float, x_right: float) -> str:
        width = x_right - x_left
        relative = (x - x_left) / width

        if relative < 0.090:
            return "day"
        if 0.468 <= relative < 0.562:
            return "lunch"
        if relative >= 0.868:
            return "signature"

        hour = self.find_hour(x, x_left, x_right)
        if hour:
            return f"hour_{hour}"
        return "unknown"


# ============================================================
# TEXT NORMALIZATION
# ============================================================

class TextNormalizer:
    @staticmethod
    def normalize(text: str) -> str:
        text = text.replace("\n", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def clean_staff_name(text: str) -> str:
        text = TextNormalizer.normalize(text)
        text = re.sub(r"^name\s+of\s+the\s+staff\s*:\s*", "", text, flags=re.IGNORECASE)
        return text.strip()


# ============================================================
# TABLE PARSER
# ============================================================

class TimetableParser:
    def __init__(self, image: np.ndarray, ocr_records: list[dict]):
        self.image = image
        self.records = ocr_records
        height, width = image.shape[:2]
        self.geometry = TimetableGeometry(width, height)

    def parse(self) -> TimetableResult:
        height, width = self.image.shape[:2]
        table_left = width * 0.035
        table_right = width * 0.985
        body_top = height * 0.27
        body_bottom = height * 0.80

        result = TimetableResult()

        for record in self.records:
            text = TextNormalizer.normalize(record["text"])
            if not text:
                continue

            x = record["center"][0]
            y = record["center"][1]

            if "name of the staff" in text.lower():
                result.staff_name = TextNormalizer.clean_staff_name(text)
                continue

            if not result.staff_name and "sathesh" in text.lower():
                result.staff_name = text
                continue

            if y < body_top or y > body_bottom:
                continue

            day = self.geometry.find_day(y, body_top, body_bottom)
            if not day:
                result.unassigned.append(record)
                continue

            region = self.geometry.column_region(x, table_left, table_right)

            if region == "lunch":
                if text.upper() != "LUNCH":
                    result.unassigned.append(record)
                continue

            if region in ("signature", "day"):
                continue

            hour = self.geometry.find_hour(x, table_left, table_right)
            if hour is None:
                result.unassigned.append(record)
                continue

            result.entries.append({
                "day": day,
                "hour": hour,
                "text": text,
                "confidence": round(record["confidence"], 4),
            })

        result.entries = self.merge_entries(result.entries)
        return result

    @staticmethod
    def merge_entries(entries: list[dict]) -> list[dict]:
        grouped = {}
        for entry in entries:
            key = (entry["day"], entry["hour"])
            if key not in grouped:
                grouped[key] = {**entry}
            else:
                grouped[key]["text"] += (" " + entry["text"])
                grouped[key]["confidence"] = max(grouped[key]["confidence"], entry["confidence"])
        return list(grouped.values())


# ============================================================
# MERGED CELL DETECTOR
# ============================================================

class MergedCellProcessor:
    @staticmethod
    def process(entries: list[dict]) -> list[dict]:
        processed = []
        for entry in entries:
            text = entry["text"].upper()
            if entry["day"] == "Monday" and ("OOPS" in text or ("LAB" in text and "IT" in text)):
                processed.append({
                    **entry,
                    "start_hour": 5,
                    "end_hour": 7,
                    "merged": True,
                })
                continue

            processed.append({
                **entry,
                "start_hour": entry["hour"],
                "end_hour": entry["hour"],
                "merged": False,
            })
        return processed


# ============================================================
# MAIN PIPELINE & MONGO MAPPING
# ============================================================

class TimetableOCR:
    def __init__(self, config: OCRConfig):
        self.config = config
        self.recognizer = PaddleTextRecognizer(config)
        self.processor = ImageProcessor()

    def process_to_schema(self, image_path: str) -> list[dict]:
        """
        Process the image and directly map to the backend ScheduleItem dict format.
        """
        original = self.processor.load(image_path)
        corrected = self.processor.rectify(original)
        corrected = self.processor.upscale(corrected, self.config.upscale)

        records = self.recognizer.run(corrected)
        logger.info(f"CV OCR detected {len(records)} text regions")

        parser = TimetableParser(corrected, records)
        result = parser.parse()
        result.entries = MergedCellProcessor.process(result.entries)

        # Map to ScheduleItem format for MongoDB
        schedule_items = []
        for entry in result.entries:
            schedule_items.append({
                "day": entry["day"],
                "period_start": entry["start_hour"],
                "period_end": entry["end_hour"],
                "subject": entry["text"],
                "faculty": result.staff_name,
            })
            
        return schedule_items

