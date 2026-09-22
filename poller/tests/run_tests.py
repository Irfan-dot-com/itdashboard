#!/usr/bin/env python3
"""
Minimal test runner, for boxes without pytest installed.

    python3 tests/run_tests.py

Prefer pytest when it is available - it gives better failure output:

    python3 -m pytest tests/ -v
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_mapper  # noqa: E402


def main():
    tests = sorted((n, f) for n, f in vars(test_mapper).items()
                   if n.startswith("test_") and callable(f))
    passed, failed = 0, []
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  PASS  {name}")
        except Exception:
            failed.append(name)
            print(f"  FAIL  {name}")
            print("        " + traceback.format_exc().replace("\n", "\n        ").rstrip())

    print()
    print(f"{passed} passed, {len(failed)} failed, {len(tests)} total")
    if failed:
        print("failed: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
