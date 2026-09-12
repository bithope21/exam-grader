from exam_grader import preferences


class FakeSettings:
    values: dict[str, str] = {}

    def __init__(self, *_args):
        pass

    def value(self, key, default="", type=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


class FakeStandardPaths:
    class StandardLocation:
        DocumentsLocation = 1

    @staticmethod
    def writableLocation(_location):
        return "/tmp/Documents"


def test_output_root_preference_round_trips(monkeypatch, tmp_path):
    monkeypatch.setattr(preferences, "QSettings", FakeSettings)
    monkeypatch.setattr(preferences, "QStandardPaths", FakeStandardPaths)
    chosen = tmp_path / "Exam Results"
    preferences.save_output_root(chosen)
    assert preferences.default_output_root() == chosen.resolve()
