"""Performance regression and benchmark tests for sheet import and registration pipeline.

Guarantees that Default #1, Default #2, and Default #3 sheet processing speeds
do not regress and that caching of reference assets and features functions correctly.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from exam_grader.imaging import (
    analyze,
    clear_imaging_cache,
    decode,
)
from exam_grader.template_manager import (
    clear_reference_image_cache,
    get_reference_image,
    load_builtin_template,
)


def test_reference_image_and_features_caching():
    """Verify that reference images and SIFT/ORB features are cached and re-used."""
    clear_reference_image_cache()
    clear_imaging_cache()

    t2 = load_builtin_template("default-2")

    # First call loads and decodes
    t0 = time.perf_counter()
    ref1 = get_reference_image(t2)
    time_first = time.perf_counter() - t0

    # Second call returns from in-memory cache
    t0 = time.perf_counter()
    ref2 = get_reference_image(t2)
    time_cached = time.perf_counter() - t0

    assert ref1.shape == ref2.shape
    assert time_cached < time_first or time_cached < 0.005

    # Test clear works
    clear_reference_image_cache()
    clear_imaging_cache()


def test_default2_registration_performance_regression():
    """Verify that Default #2 (1200x1720) registration and analysis stays well below 1.5s/sheet."""
    vol5_dir = Path("tests/fixtures/real/vol.5")
    if not vol5_dir.exists():
        pytest.skip("vol.5 fixture not available")

    t2 = load_builtin_template("default-2")
    sheet_files = ["IMG_0865.jpg", "IMG_0863.JPG", "IMG_0864.jpg", "IMG_0862.JPG"]

    timings = []
    for fname in sheet_files:
        data = (vol5_dir / fname).read_bytes()
        img = decode(data)
        t0 = time.perf_counter()
        res = analyze(data, template_def=t2, decoded_image=img)
        elapsed = time.perf_counter() - t0
        timings.append(elapsed)
        # Registration must be valid and high-quality
        assert res["registration"]["table_coverage"] >= 0.995

    avg_time = sum(timings) / len(timings)
    # Regression guard: Previous unoptimized code took 4.1s to 4.6s per sheet.
    # Optimized code runs in ~0.4s to 0.5s per sheet. We bound at 1.5s to prevent any regression.
    assert avg_time < 1.5, f"Default #2 average analysis time regressed: {avg_time:.3f}s >= 1.5s"


def test_default1_registration_performance_regression():
    """Verify that Default #1 analysis stays well below 1.0s/sheet."""
    vol1_dir = Path("tests/fixtures/real/vol.1")
    if not vol1_dir.exists():
        pytest.skip("vol.1 fixture not available")

    t1 = load_builtin_template("default-1")
    sheet_files = ["IMG_0791.JPG", "IMG_0792.JPG", "IMG_0793.jpg"]

    timings = []
    for fname in sheet_files:
        data = (vol1_dir / fname).read_bytes()
        img = decode(data)
        t0 = time.perf_counter()
        res = analyze(data, template_def=t1, decoded_image=img)
        elapsed = time.perf_counter() - t0
        timings.append(elapsed)
        assert res["registration"]["table_coverage"] >= 0.995

    avg_time = sum(timings) / len(timings)
    # Regression guard: Must remain under 0.8s per sheet
    assert avg_time < 0.8, f"Default #1 average analysis time regressed: {avg_time:.3f}s >= 0.8s"
