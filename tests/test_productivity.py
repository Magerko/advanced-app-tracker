from app_tracker.core.productivity import Productivity


def test_enum_values_are_stable():
    assert int(Productivity.UNKNOWN) == 0
    assert int(Productivity.PRODUCTIVE) == 1
    assert int(Productivity.UNPRODUCTIVE) == 2


def test_from_value_accepts_ints_and_strings():
    assert Productivity.from_value(1) is Productivity.PRODUCTIVE
    assert Productivity.from_value("2") is Productivity.UNPRODUCTIVE


def test_from_value_falls_back_to_unknown():
    assert Productivity.from_value(99) is Productivity.UNKNOWN
    assert Productivity.from_value(None) is Productivity.UNKNOWN


def test_label_and_rgb():
    assert Productivity.PRODUCTIVE.label == "Продуктивно"
    assert Productivity.UNPRODUCTIVE.rgb == (255, 180, 180)
