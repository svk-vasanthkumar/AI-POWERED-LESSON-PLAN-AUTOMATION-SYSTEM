import sys
import os
import traceback

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.timetable_cv_parser import TimetableOCR, OCRConfig

def main():
    try:
        config = OCRConfig()
        pipeline = TimetableOCR(config)
        image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "uploads", "e55265d205cf407cb908cdd21b95d8a3.png")
        print(f"Processing image {image_path}")
        result = pipeline.process_to_schema(image_path)
        print("Success! Result:")
        print(result)
    except Exception as e:
        print("Error occurred!")
        traceback.print_exc()

if __name__ == "__main__":
    main()
