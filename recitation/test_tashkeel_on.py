#!/usr/bin/env python3
"""Quick test: run 286-word test set with tashkeel detection ON.

Wrapper around run_tests_pcd.py --tashkeel-on --verbose.
"""
import subprocess
import sys

sys.exit(
    subprocess.call(
        [sys.executable, "run_tests_pcd.py", "--tashkeel-on", "--verbose"],
    )
)
