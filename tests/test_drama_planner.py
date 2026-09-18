from dataclasses import dataclass

from drama.planner import KeepRange, fit_target, parse_plan, snap_to_dialogue, total_duration


@dataclass
class S:
    start: float
    end: float
    text: str = "x"


def test_parse_and_merge():
    raw = '{"summary":"x","sequence":[{"start":20,"end":40,"importance":4},{"start":0,"end":10,"importance":5},{"start":9.8,"end":15,"importance":2}]}'
    summary, ranges = parse_plan(raw, 100)
    assert summary == "x"
    assert [(r.start, r.end) for r in ranges] == [(0, 15), (20, 40)]


def test_snap_to_dialogue_boundaries():
    segs = [S(0, 5), S(5.2, 10), S(10.4, 15)]
    out = snap_to_dialogue([KeepRange(4.8, 10.2)], segs, 15)
    assert out[0].start == 5.2
    assert out[0].end == 10.0


def test_fit_target_removes_low_importance_range():
    segs = [S(i, i + 5) for i in range(0, 300, 5)]
    ranges = [KeepRange(0, 100, importance=5), KeepRange(105, 205, importance=1), KeepRange(210, 300, importance=5)]
    out = fit_target(ranges, segs, 300, 180, 220)
    assert 175 <= total_duration(out) <= 228
    assert all(r.importance >= 5 for r in out)
