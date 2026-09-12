"""Synthetic Answer Sheet Dataset Generator CLI.

Produces deterministic synthetic answer sheet image fixtures and ground truth manifests
for testing OMR pipelines without modifying production code or freezing low-res templates.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from tools.synthetic.sheet_builder import (
    CHOICES,
    draw_mark,
    draw_student_number,
    render_blank_sheet,
)
from tools.synthetic.transforms import (
    apply_brightness,
    apply_contrast,
    apply_gaussian_blur,
    apply_jpeg_compression,
    apply_mild_crop,
    apply_motion_blur,
    apply_perspective_skew,
    apply_rotation,
    apply_shadow,
)


def generate_answer_keys(rng: np.random.Generator) -> dict[str, dict[str, str]]:
    """Generates 3 distinct answer keys (key_01, key_02, key_03) with 60 questions each."""
    keys = {}
    for k_idx in range(1, 4):
        key_id = f"key_{k_idx:02d}"
        key_answers = {}
        for q in range(1, 61):
            choice = CHOICES[int(rng.integers(0, 5))]
            key_answers[str(q)] = choice
        keys[key_id] = key_answers
    return keys


def render_answer_key_image(
    key_id: str, key_answers: dict[str, str], rng: np.random.Generator
) -> np.ndarray:
    """Renders an answer key sheet image with marked choices and header label."""
    image = render_blank_sheet(header_title=f"เฉลยคำตอบ - {key_id.upper()}")
    for q_str, choice in key_answers.items():
        q = int(q_str)
        c_idx = CHOICES.index(choice)
        draw_mark(image, q, c_idx, mark_type="x_mark", rng=rng)
    return image


def calculate_score_and_flags(
    sheet_answers: dict[str, list[str]],
    key_answers: dict[str, str],
    raw_flags: list[str],
) -> tuple[int, list[str]]:
    """Computes exact integer score against assigned key and finalized review flags."""
    score = 0
    flags = list(raw_flags)

    for q_str, key_choice in key_answers.items():
        selected = sheet_answers.get(q_str, [])
        if len(selected) == 0:
            if "blank_answer" not in flags:
                flags.append("blank_answer")
        elif len(selected) > 1:
            if "multiple_mark" not in flags:
                flags.append("multiple_mark")
        else:
            if selected[0] == key_choice:
                score += 1

    return score, sorted(list(set(flags)))


def generate_dataset(seed: int, output_dir: Path) -> dict:
    """Generates complete synthetic dataset deterministically."""
    rng = np.random.default_rng(seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    clean_dir = output_dir / "clean"
    degraded_dir = output_dir / "degraded"
    edge_dir = output_dir / "edge_cases"
    expected_dir = output_dir / "expected"

    for d in (clean_dir, degraded_dir, edge_dir, expected_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 1. Answer Keys
    keys = generate_answer_keys(rng)
    key_file = expected_dir / "answer_keys.json"
    key_file.write_text(json.dumps(keys, indent=2, ensure_ascii=False), encoding="utf-8")

    manifest_entries = []

    # Render answer key sheet images
    for key_id, key_answers in keys.items():
        img_key = render_answer_key_image(key_id, key_answers, rng)
        rel_path = f"expected/{key_id}.png"
        file_path = output_dir / rel_path
        cv2.imwrite(str(file_path), img_key)

        formatted_answers = {q: [choice] for q, choice in key_answers.items()}
        manifest_entries.append(
            {
                "filename": rel_path,
                "category": "expected",
                "key_id": key_id,
                "student_no": "KEY_REF",
                "answers": formatted_answers,
                "expected_score": 60,
                "expected_review_flags": [],
                "seed": seed,
                "transforms": [],
            }
        )

    # Helper function to process student sheet
    def create_student_fixture(
        category: str,
        filename: str,
        key_id: str,
        student_no: str | None,
        answers_dict: dict[str, list[str]],
        mark_type: str = "x_mark",
        student_no_mode: str = "clean",
        transforms_list: list[str] | None = None,
        base_flags: list[str] | None = None,
    ) -> None:
        if transforms_list is None:
            transforms_list = []
        if base_flags is None:
            base_flags = []

        img = render_blank_sheet(header_title="กระดาษคำตอบ (Synthetic Probe)")

        # Draw marks for each question
        for q in range(1, 61):
            q_str = str(q)
            choices_marked = answers_dict.get(q_str, [])
            for choice_char in choices_marked:
                c_idx = CHOICES.index(choice_char)
                draw_mark(img, q, c_idx, mark_type=mark_type, rng=rng)

        # Draw student number
        draw_student_number(img, student_no, mode=student_no_mode, rng=rng)

        # Apply transforms
        for transform in transforms_list:
            if transform.startswith("rotation:"):
                angle = float(transform.split(":")[1])
                img = apply_rotation(img, angle)
            elif transform == "perspective_skew":
                img = apply_perspective_skew(img, intensity=0.04, rng=rng)
            elif transform.startswith("brightness:"):
                factor = float(transform.split(":")[1])
                img = apply_brightness(img, factor)
            elif transform == "shadow":
                img = apply_shadow(img)
            elif transform.startswith("contrast:"):
                factor = float(transform.split(":")[1])
                img = apply_contrast(img, factor)
            elif transform.startswith("gaussian_blur:"):
                ksize = int(transform.split(":")[1])
                img = apply_gaussian_blur(img, kernel_size=ksize)
            elif transform == "motion_blur":
                img = apply_motion_blur(img, size=5)
            elif transform.startswith("jpeg_quality:"):
                qual = int(transform.split(":")[1])
                img = apply_jpeg_compression(img, quality=qual)
            elif transform.startswith("crop:"):
                pct = float(transform.split(":")[1])
                img = apply_mild_crop(img, crop_pct=pct)

        score, final_flags = calculate_score_and_flags(answers_dict, keys[key_id], base_flags)

        rel_path = f"{category}/{filename}"
        full_path = output_dir / rel_path
        cv2.imwrite(str(full_path), img)

        manifest_entries.append(
            {
                "filename": rel_path,
                "category": category,
                "key_id": key_id,
                "student_no": student_no,
                "answers": answers_dict,
                "expected_score": score,
                "expected_review_flags": final_flags,
                "seed": seed,
                "transforms": transforms_list,
            }
        )

    # ==========================================
    # 2. Clean Category (15 sheets)
    # ==========================================
    # clean_01: Perfect score (matches key_01)
    k1 = keys["key_01"]
    create_student_fixture(
        "clean",
        "clean_01.png",
        "key_01",
        "650101",
        {q: [c] for q, c in k1.items()},
    )

    # clean_02: Perfect score (matches key_02)
    k2 = keys["key_02"]
    create_student_fixture(
        "clean",
        "clean_02.png",
        "key_02",
        "650102",
        {q: [c] for q, c in k2.items()},
    )

    # clean_03: Zero score (all wrong choices)
    wrong_answers = {q: [CHOICES[(CHOICES.index(c) + 1) % 5]] for q, c in k1.items()}
    create_student_fixture("clean", "clean_03.png", "key_01", "650103", wrong_answers)

    # clean_04: Random score (~35/60 correct)
    rand_answers = {}
    for q in range(1, 61):
        if q <= 35:
            rand_answers[str(q)] = [k1[str(q)]]
        else:
            rand_answers[str(q)] = [CHOICES[(CHOICES.index(k1[str(q)]) + 1) % 5]]
    create_student_fixture("clean", "clean_04.png", "key_01", "650104", rand_answers)

    # clean_05 to clean_09: All A, B, C, D, E
    for idx, choice in enumerate(CHOICES, start=5):
        create_student_fixture(
            "clean",
            f"clean_{idx:02d}.png",
            "key_01",
            f"6501{idx:02d}",
            {str(q): [choice] for q in range(1, 61)},
        )

    # clean_10: Alternating pattern (A, B, C, D, E, A, B, C...)
    alt_1 = {str(q): [CHOICES[(q - 1) % 5]] for q in range(1, 61)}
    create_student_fixture("clean", "clean_10.png", "key_01", "650110", alt_1)

    # clean_11: Alternating pattern 2 (E, D, C, B, A...)
    alt_2 = {str(q): [CHOICES[4 - ((q - 1) % 5)]] for q in range(1, 61)}
    create_student_fixture("clean", "clean_11.png", "key_01", "650111", alt_2)

    # clean_12: Single blank answer (Q30 blank)
    blank_one = {q: [c] for q, c in k1.items()}
    blank_one["30"] = []
    create_student_fixture("clean", "clean_12.png", "key_01", "650112", blank_one)

    # clean_13..15: Standard valid sheets
    for idx in (13, 14, 15):
        create_student_fixture(
            "clean",
            f"clean_{idx:02d}.png",
            "key_01",
            f"6501{idx:02d}",
            {q: [c] for q, c in k1.items()},
        )

    # ==========================================
    # 3. Degraded Category (20 sheets)
    # ==========================================
    perf_ans = {q: [c] for q, c in k1.items()}

    # degraded_01 & 02: Faint marks
    create_student_fixture(
        "degraded",
        "degraded_01.png",
        "key_01",
        "650201",
        perf_ans,
        mark_type="faint_mark",
        base_flags=["faint_mark"],
    )
    create_student_fixture(
        "degraded",
        "degraded_02.png",
        "key_01",
        "650202",
        perf_ans,
        mark_type="faint_mark",
        base_flags=["faint_mark"],
    )

    # degraded_03: Heavy marks
    create_student_fixture(
        "degraded",
        "degraded_03.png",
        "key_01",
        "650203",
        perf_ans,
        mark_type="heavy_mark",
        base_flags=["heavy_mark"],
    )

    # degraded_04: Off-center marks
    create_student_fixture(
        "degraded",
        "degraded_04.png",
        "key_01",
        "650204",
        perf_ans,
        mark_type="off_center_mark",
        base_flags=["off_center_mark"],
    )

    # degraded_05..10: Rotation ±1, ±3, ±5
    rotations = [1.0, -1.0, 3.0, -3.0, 5.0, -5.0]
    for idx, angle in enumerate(rotations, start=5):
        create_student_fixture(
            "degraded",
            f"degraded_{idx:02d}.png",
            "key_01",
            f"6502{idx:02d}",
            perf_ans,
            transforms_list=[f"rotation:{angle}"],
            base_flags=["rotation"],
        )

    # degraded_11: High brightness / washed out
    create_student_fixture(
        "degraded",
        "degraded_11.png",
        "key_01",
        "650211",
        perf_ans,
        transforms_list=["brightness:1.25"],
        base_flags=["lighting_variation"],
    )

    # degraded_12: Low brightness / dark ambient light
    create_student_fixture(
        "degraded",
        "degraded_12.png",
        "key_01",
        "650212",
        perf_ans,
        transforms_list=["brightness:0.75"],
        base_flags=["lighting_variation"],
    )

    # degraded_13: Low contrast paper scan
    create_student_fixture(
        "degraded",
        "degraded_13.png",
        "key_01",
        "650213",
        perf_ans,
        transforms_list=["contrast:0.6"],
        base_flags=["low_contrast"],
    )

    # degraded_14: Gradient shadow across paper
    create_student_fixture(
        "degraded",
        "degraded_14.png",
        "key_01",
        "650214",
        perf_ans,
        transforms_list=["shadow"],
        base_flags=["shadow"],
    )

    # degraded_15: Gaussian blur
    create_student_fixture(
        "degraded",
        "degraded_15.png",
        "key_01",
        "650215",
        perf_ans,
        transforms_list=["gaussian_blur:5"],
        base_flags=["image_blur"],
    )

    # degraded_16: Motion blur
    create_student_fixture(
        "degraded",
        "degraded_16.png",
        "key_01",
        "650216",
        perf_ans,
        transforms_list=["motion_blur"],
        base_flags=["image_blur"],
    )

    # degraded_17: Medium JPEG compression (quality 60)
    create_student_fixture(
        "degraded",
        "degraded_17.png",
        "key_01",
        "650217",
        perf_ans,
        transforms_list=["jpeg_quality:60"],
        base_flags=["jpeg_compression"],
    )

    # degraded_18: Heavy JPEG compression (quality 35)
    create_student_fixture(
        "degraded",
        "degraded_18.png",
        "key_01",
        "650218",
        perf_ans,
        transforms_list=["jpeg_quality:35"],
        base_flags=["jpeg_compression"],
    )

    # degraded_19: Rotation 3° + JPEG compression 50
    create_student_fixture(
        "degraded",
        "degraded_19.png",
        "key_01",
        "650219",
        perf_ans,
        transforms_list=["rotation:3.0", "jpeg_quality:50"],
        base_flags=["rotation", "jpeg_compression"],
    )

    # degraded_20: Combined faint marks + shadow + rotation -1°
    create_student_fixture(
        "degraded",
        "degraded_20.png",
        "key_01",
        "650220",
        perf_ans,
        mark_type="faint_mark",
        transforms_list=["shadow", "rotation:-1.0"],
        base_flags=["faint_mark", "shadow", "rotation"],
    )

    # ==========================================
    # 4. Edge Cases Category (20 sheets)
    # ==========================================
    # edge_case_01: Double mark (Q15 marked A and B)
    double_ans = {q: [c] for q, c in k1.items()}
    double_ans["15"] = ["A", "B"]
    create_student_fixture(
        "edge_cases",
        "edge_case_01.png",
        "key_01",
        "650301",
        double_ans,
        base_flags=["multiple_mark"],
    )

    # edge_case_02: Multiple double marks (Q10, Q25, Q40)
    multi_double = {q: [c] for q, c in k1.items()}
    multi_double["10"] = ["A", "C"]
    multi_double["25"] = ["B", "D"]
    multi_double["40"] = ["C", "E"]
    create_student_fixture(
        "edge_cases",
        "edge_case_02.png",
        "key_01",
        "650302",
        multi_double,
        base_flags=["multiple_mark"],
    )

    # edge_case_03: Check mark (✓)
    create_student_fixture(
        "edge_cases",
        "edge_case_03.png",
        "key_01",
        "650303",
        perf_ans,
        mark_type="check_mark",
        base_flags=["non_standard_mark"],
    )

    # edge_case_04: Slash mark (/)
    create_student_fixture(
        "edge_cases",
        "edge_case_04.png",
        "key_01",
        "650304",
        perf_ans,
        mark_type="slash_mark",
        base_flags=["non_standard_mark"],
    )

    # edge_case_05: Scribble / corrected answer (Q20 scribbled A, marked B)
    create_student_fixture(
        "edge_cases",
        "edge_case_05.png",
        "key_01",
        "650305",
        perf_ans,
        mark_type="scribble",
        base_flags=["scribble_mark"],
    )

    # edge_case_06: Solid filled bubbles (edge case style)
    create_student_fixture(
        "edge_cases",
        "edge_case_06.png",
        "key_01",
        "650306",
        perf_ans,
        mark_type="solid_bubble",
        base_flags=["bubble_fill_style"],
    )

    # edge_case_07 & 08: Rotation ±10°
    create_student_fixture(
        "edge_cases",
        "edge_case_07.png",
        "key_01",
        "650307",
        perf_ans,
        transforms_list=["rotation:10.0"],
        base_flags=["large_rotation"],
    )
    create_student_fixture(
        "edge_cases",
        "edge_case_08.png",
        "key_01",
        "650308",
        perf_ans,
        transforms_list=["rotation:-10.0"],
        base_flags=["large_rotation"],
    )

    # edge_case_09 & 10: Perspective skew
    create_student_fixture(
        "edge_cases",
        "edge_case_09.png",
        "key_01",
        "650309",
        perf_ans,
        transforms_list=["perspective_skew"],
        base_flags=["perspective_skew"],
    )
    create_student_fixture(
        "edge_cases",
        "edge_case_10.png",
        "key_01",
        "650310",
        perf_ans,
        transforms_list=["perspective_skew"],
        base_flags=["perspective_skew"],
    )

    # edge_case_11 & 12: Mild crop / partial sheet
    create_student_fixture(
        "edge_cases",
        "edge_case_11.png",
        "key_01",
        "650311",
        perf_ans,
        transforms_list=["crop:0.04"],
        base_flags=["cropped_sheet"],
    )
    create_student_fixture(
        "edge_cases",
        "edge_case_12.png",
        "key_01",
        "650312",
        perf_ans,
        transforms_list=["crop:0.08"],
        base_flags=["cropped_sheet"],
    )

    # edge_case_13 & 14: Duplicate student number (matching 650115 from clean)
    create_student_fixture(
        "edge_cases",
        "edge_case_13.png",
        "key_01",
        "650115",
        perf_ans,
        base_flags=["duplicate_student_no"],
    )
    create_student_fixture(
        "edge_cases",
        "edge_case_14.png",
        "key_01",
        "650115",
        perf_ans,
        base_flags=["duplicate_student_no"],
    )

    # edge_case_15: Missing student number
    create_student_fixture(
        "edge_cases",
        "edge_case_15.png",
        "key_01",
        None,
        perf_ans,
        student_no_mode="missing",
        base_flags=["missing_student_no"],
    )

    # edge_case_16: Unreadable student number
    create_student_fixture(
        "edge_cases",
        "edge_case_16.png",
        "key_01",
        "UNCERTAIN",
        perf_ans,
        student_no_mode="unreadable",
        base_flags=["unreadable_student_no"],
    )

    # edge_case_17: Multiple blanks (10 questions un-answered)
    ten_blanks = {q: [c] for q, c in k1.items()}
    for q_b in range(51, 61):
        ten_blanks[str(q_b)] = []
    create_student_fixture(
        "edge_cases",
        "edge_case_17.png",
        "key_01",
        "650317",
        ten_blanks,
        base_flags=["blank_answer"],
    )

    # edge_case_18: All 60 questions blank (empty sheet)
    create_student_fixture(
        "edge_cases",
        "edge_case_18.png",
        "key_01",
        "650318",
        {str(q): [] for q in range(1, 61)},
        base_flags=["blank_answer"],
    )

    # edge_case_19: Severe perspective skew + heavy JPEG
    create_student_fixture(
        "edge_cases",
        "edge_case_19.png",
        "key_01",
        "650319",
        perf_ans,
        transforms_list=["perspective_skew", "jpeg_quality:35"],
        base_flags=["perspective_skew", "jpeg_compression"],
    )

    # edge_case_20: Rotation 10° + crop 4% + double mark + faint mark
    combo_ans = {q: [c] for q, c in k1.items()}
    combo_ans["5"] = ["A", "C"]
    create_student_fixture(
        "edge_cases",
        "edge_case_20.png",
        "key_01",
        "650320",
        combo_ans,
        mark_type="faint_mark",
        transforms_list=["rotation:10.0", "crop:0.04"],
        base_flags=["large_rotation", "cropped_sheet", "multiple_mark", "faint_mark"],
    )

    # Write global manifest.json
    manifest_file = output_dir / "manifest.json"
    manifest_data = {
        "dataset_name": "OMR Synthetic Answer Sheet Fixture Dataset",
        "seed": seed,
        "total_fixtures": len(manifest_entries),
        "disclaimer": "SYNTHETIC/PROVISIONAL FIXTURE ONLY. Not for real-world accuracy benchmarking or digit model training.",
        "fixtures": manifest_entries,
    }
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return manifest_data


def main():
    parser = argparse.ArgumentParser(
        description="Generate Synthetic OMR Answer Sheet Fixture Dataset"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for deterministic generation"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/fixtures/synthetic"),
        help="Output directory path for dataset fixtures",
    )
    args = parser.parse_args()

    print(f"Generating synthetic dataset with seed={args.seed} into {args.output_dir}...")
    manifest = generate_dataset(args.seed, args.output_dir)
    print(f"Dataset generated successfully! Total fixtures: {manifest['total_fixtures']}")


if __name__ == "__main__":
    main()
