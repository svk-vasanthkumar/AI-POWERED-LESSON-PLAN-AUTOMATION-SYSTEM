import subprocess
import sys

# Test modules mapped from your tests/ directory
TEST_MODULES = [
    ("Auth & Security APIs", "tests/test_auth_security.py"),
    ("AI Service & Prompts", "tests/test_ai_service.py"),
    ("Lesson Plan & ACE Export", "tests/test_ace_lesson_plan_export.py"),
    ("Academic Calendar API & Parser", "tests/test_academic_calendar.py"),
    ("Academic Calendar Date Parser", "tests/test_academic_calendar_parser.py"),
    ("Timetable & Period Management", "tests/test_timetable.py"),
    ("Scheduler Engine", "tests/test_scheduler_engine.py"),
    ("Scheduler Engine Periods", "tests/test_scheduler_engine_periods.py"),
    ("Scheduler Service", "tests/test_scheduler_service.py"),
    ("Scheduler Service Periods", "tests/test_scheduler_service_periods.py"),
    ("Resource Lifecycle (Faculty/Course)", "tests/test_resource_lifecycle.py"),
    ("Progress Engine & Tracking", "tests/test_progress.py"),
    ("Progress Execution", "tests/test_progress_execution.py"),
    ("Text Extraction Service", "tests/test_text_extraction.py"),
    ("OCR Service", "tests/test_ocr_service.py"),
    ("Export Service", "tests/test_export_service.py"),
    ("Database Health", "tests/test_database_health.py"),
    ("Database Integrity", "tests/test_database_integrity.py"),
    ("Task Management", "tests/test_task8_management.py"),
]

def main():
    print("\n=======================================================")
    print("      RUNNING FULL PROJECT AUTOMATED API AUDIT        ")
    print("=======================================================\n")

    results = []

    for name, path in TEST_MODULES:
        print(f"Testing: {name} ({path})...", end=" ", flush=True)
        res = subprocess.run(
            [sys.executable, "-m", "pytest", path, "-q"],
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            print("[PASSED]")
            results.append((name, "PASSED", ""))
        else:
            print("[FAILED]")
            results.append((name, "FAILED", res.stdout + "\n" + res.stderr))

    print("\n=======================================================")
    print("                  TEST SUMMARY RESULTS                ")
    print("=======================================================")
    print(f"{'API / Component':<35} | {'Status':<10}")
    print("-" * 50)
    for name, status, _ in results:
        print(f"{name:<35} | {status:<10}")
    print("=======================================================\n")

    failures = [r for r in results if r[1] == "FAILED"]
    if failures:
        print(f"Total Failures Detected: {len(failures)}\n")
        for name, _, err in failures:
            print(f"--- FAILURE DETAILS: {name} ---")
            print(err[:600] + ("\n... [truncated]" if len(err) > 600 else ""))
            print("-" * 50)
    else:
        print("All API endpoints and services passed successfully!")

if __name__ == "__main__":
    main()