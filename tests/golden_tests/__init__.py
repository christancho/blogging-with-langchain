"""
Golden Test Sets for Blog Generation Pipeline

This package contains golden test cases and validators for the blog generation
system. Golden tests are curated examples that define what "good" output looks like.

Usage:
    pytest tests/golden_tests/test_golden_sets.py

The golden tests validate:
    - Word count meets minimum standards
    - Document structure (H1, H2 sections)
    - Link quality and quantity
    - Overall quality score
    - Tone and engagement appropriateness
"""

from tests.golden_tests.test_golden_sets import (
    GoldenTestLoader,
    GoldenTestValidator,
    load_all_golden_tests,
    validate_all_tests,
)

__all__ = [
    "GoldenTestLoader",
    "GoldenTestValidator",
    "load_all_golden_tests",
    "validate_all_tests",
]
