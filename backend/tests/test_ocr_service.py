import pytest

from app.services import ocr_service
from app.services.ocr_service import OCRProcessingError, OCRUnavailableError


def test_parse_v3_result_shape():
    raw = [{"rec_texts": ["Unit 1: Introduction", "Topic A"]}]
    assert ocr_service._extract_text_from_result(raw) == "Unit 1: Introduction\nTopic A"


def test_parse_v2_result_shape():
    raw = [[
        [[[0, 0], [1, 0], [1, 1], [0, 1]], ("Unit 1: Introduction", 0.99)],
        [[[0, 2], [1, 2], [1, 3], [0, 3]], ("Topic A", 0.97)],
    ]]
    assert ocr_service._extract_text_from_result(raw) == "Unit 1: Introduction\nTopic A"


def test_parse_empty_result():
    assert ocr_service._extract_text_from_result(None) == ""
    assert ocr_service._extract_text_from_result([]) == ""


def test_run_ocr_success(monkeypatch):
    class FakeCV2:
        IMREAD_COLOR = 1
        def imdecode(self, array, flag):
            return object()

    class FakeNP:
        uint8 = object()
        @staticmethod
        def frombuffer(data, dtype):
            return object()

    class FakeEngine:
        def predict(self, image):
            return [{"rec_texts": ["Hello", "World"]}]

    monkeypatch.setitem(__import__("sys").modules, "cv2", FakeCV2())
    monkeypatch.setitem(__import__("sys").modules, "numpy", FakeNP())
    monkeypatch.setattr(ocr_service, "_get_engine", lambda: FakeEngine())

    assert ocr_service.run_ocr(b"fake-image") == "Hello\nWorld"


def test_run_ocr_empty_input():
    with pytest.raises(OCRProcessingError):
        ocr_service.run_ocr(b"")


def test_run_ocr_engine_error(monkeypatch):
    class FakeCV2:
        IMREAD_COLOR = 1
        def imdecode(self, array, flag):
            return object()

    class FakeNP:
        uint8 = object()
        @staticmethod
        def frombuffer(data, dtype):
            return object()

    class Boom:
        def predict(self, image):
            raise RuntimeError("engine failure")

    monkeypatch.setitem(__import__("sys").modules, "cv2", FakeCV2())
    monkeypatch.setitem(__import__("sys").modules, "numpy", FakeNP())
    monkeypatch.setattr(ocr_service, "_get_engine", lambda: Boom())

    with pytest.raises(OCRProcessingError):
        ocr_service.run_ocr(b"fake-image")


def test_ocr_unavailable_propagates(monkeypatch):
    class FakeCV2:
        IMREAD_COLOR = 1
        def imdecode(self, array, flag):
            return object()

    class FakeNP:
        uint8 = object()
        @staticmethod
        def frombuffer(data, dtype):
            return object()

    monkeypatch.setitem(__import__("sys").modules, "cv2", FakeCV2())
    monkeypatch.setitem(__import__("sys").modules, "numpy", FakeNP())
    monkeypatch.setattr(
        ocr_service,
        "_get_engine",
        lambda: (_ for _ in ()).throw(OCRUnavailableError("missing")),
    )
    with pytest.raises(OCRUnavailableError):
        ocr_service.run_ocr(b"fake-image")
