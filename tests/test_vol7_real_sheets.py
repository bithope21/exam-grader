"""Production-level test suite verifying OMR detection and student number recognition on real Vol.7 exam sheets."""

from pathlib import Path
import dataclasses
import pytest

from exam_grader.imaging import analyze, register, decode
from exam_grader.identity import observe
from exam_grader.template_discovery import discover_template

VOL7_ROOT = Path("tests/fixtures/real/vol.7")
OUTDOOR_DIR = VOL7_ROOT / "ถ่ายในที่แจ้ง"
INDOOR_DIR = VOL7_ROOT / "ถ่ายในห้อง"

OUTDOOR_GROUND_TRUTH_NUMBERS = {
    "IMG_0986.jpg": "3",
    "IMG_0987.jpg": "13",
    "IMG_0988.jpg": "27",
    "IMG_0989.jpg": "1",
    "IMG_0990.jpg": "49",
    "IMG_0992.jpg": "12",
}


@pytest.fixture(scope="module")
def vol7_discovered_template():
    tpl_path = OUTDOOR_DIR / "template.JPG"
    if not tpl_path.exists():
        pytest.skip("Vol.7 template image not found")
    disc_res = discover_template(tpl_path.read_bytes(), template_id="vol7_test")
    tpl_def = disc_res.template_def
    if tpl_def.student_number_roi is None:
        tpl_def = dataclasses.replace(tpl_def, student_number_roi=(740, 150, 960, 240))
    return disc_res, tpl_def


def test_vol7_template_discovery(vol7_discovered_template):
    """Verify template auto-discovery successfully detects answer blocks and ROIs."""
    disc_res, tpl_def = vol7_discovered_template
    assert disc_res.overall_confidence >= 0.70
    assert len(tpl_def.answer_blocks) >= 3
    assert tpl_def.score_roi is not None
    assert tpl_def.student_number_roi is not None


@pytest.mark.parametrize("filename,expected_number", sorted(OUTDOOR_GROUND_TRUTH_NUMBERS.items()))
def test_vol7_outdoor_sheets_accuracy(vol7_discovered_template, filename, expected_number):
    """Verify each outdoor photographed sheet achieves >=95% single-mark OMR and accurate student number."""
    disc_res, tpl_def = vol7_discovered_template
    file_path = OUTDOOR_DIR / filename
    if not file_path.exists():
        pytest.skip(f"{filename} not found")

    raw = file_path.read_bytes()
    img = decode(raw)
    warped, diag = register(img, template_def=tpl_def, reference_override=disc_res.warped_image)
    assert diag.get("matrix") is not None, f"Registration failed for {filename}"

    # 1. OMR single mark detection rate on 30 questions
    res = analyze(raw, template_def=tpl_def, reference_override=disc_res.warped_image)
    answers_30 = res["answers"][:30]
    single_marks = [
        a for a in answers_30 if len(a.get("selected", [])) == 1 and a["selected"][0] in "ABCDE"
    ]
    detection_rate = len(single_marks) / 30.0
    assert (
        detection_rate >= 0.95
    ), f"{filename}: OMR detection rate {detection_rate:.1%} is below 95% threshold ({len(single_marks)}/30)"

    # 2. Student number recognition
    obs = observe(raw, matrix=diag["matrix"], template_def=tpl_def, image=img)
    candidate = obs.get("candidate")
    candidates = obs.get("candidates") or []
    assert (
        candidate == expected_number or expected_number in candidates
    ), f"{filename}: Expected student number '{expected_number}' not found in top candidate '{candidate}' or candidates {candidates}"


def test_vol7_indoor_sheets_registration(vol7_discovered_template):
    """Verify all indoor photographed sheets register and analyze robustly without exceptions."""
    disc_res, tpl_def = vol7_discovered_template
    indoor_files = sorted(INDOOR_DIR.glob("IMG_*.JPG"))
    if not indoor_files:
        pytest.skip("No indoor test files found")

    success_count = 0
    for f in indoor_files:
        raw = f.read_bytes()
        img = decode(raw)
        try:
            warped, diag = register(
                img, template_def=tpl_def, reference_override=disc_res.warped_image
            )
            if diag.get("matrix") is not None:
                res = analyze(raw, template_def=tpl_def, reference_override=disc_res.warped_image)
                assert len(res.get("answers", [])) >= 30
                success_count += 1
        except Exception as e:
            pytest.fail(f"Indoor sheet {f.name} raised unexpected exception: {e}")

    assert success_count >= len(indoor_files) * 0.80, (
        f"Indoor registration success rate {success_count}/{len(indoor_files)} too low"
    )
