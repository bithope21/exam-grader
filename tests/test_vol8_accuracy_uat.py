from tools.uat.vol8_accuracy_uat import compare_photo


def test_accuracy_comparison_catches_wrong_multi_blank_and_uncertainty():
    photo = {
        "source": "sample.jpg",
        "student_number": {"value": "1", "state": "clear"},
        "answers": {"1": ["B"], "2": ["C"], "3": ["D", "E"]},
        "uncertain_questions": [4],
    }
    prediction = {
        "student_number_observation": {"candidate": "1", "requires_review": True},
        "registration": {},
        "answers": [
            {"question": 1, "classification": "single_mark", "selected": ["A"]},
            {"question": 2, "classification": "multiple", "selected": ["B", "C"]},
            {"question": 3, "classification": "uncertain", "selected": []},
            {"question": 4, "classification": "single_mark", "selected": ["A"]},
            {"question": 5, "classification": "blank", "selected": []},
        ],
    }

    result = compare_photo(photo, prediction, question_count=5)

    assert result["human_resolved_questions"] == 4
    assert result["human_ambiguous_questions"] == 1
    assert result["wrong"] == 1
    assert result["false_multi"] == 1
    assert result["machine_uncertain"] == 1
    assert result["unsafe_decision_on_ambiguous"] == 1


def test_accuracy_comparison_treats_omitted_reference_answers_as_blank():
    photo = {
        "source": "sample.jpg",
        "student_number": {"value": None, "state": "blank_review"},
        "answers": {"1": ["A", "B"]},
        "uncertain_questions": [],
    }
    prediction = {
        "student_number_observation": {"candidate": None, "requires_review": True},
        "registration": {},
        "answers": [
            {"question": 1, "classification": "multiple", "selected": ["A", "B"]},
            {"question": 2, "classification": "blank", "selected": []},
        ],
    }

    result = compare_photo(photo, prediction, question_count=2)

    assert result["exact_match"] == 2
    assert result["false_blank"] == 0
    assert result["student_number"]["exact_primary_candidate"] is True
