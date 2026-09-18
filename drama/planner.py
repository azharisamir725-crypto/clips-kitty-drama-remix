"""Transcript-aware planning for the short-drama remix mode.

The planner keeps plot order by default.  It removes low-value material and
returns chronological source ranges that will be stitched into ONE finished
video.  It deliberately does not randomise shots: for narrative content,
causality matters more than novelty.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class KeepRange:
    start: float
    end: float
    reason: str = ""
    importance: int = 3

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def transcript_for_prompt(segments: Iterable, *, max_chars: int = 26000) -> str:
    lines: list[str] = []
    used = 0
    for s in segments:
        line = f"[{float(s.start):.1f}-{float(s.end):.1f}] {str(s.text).strip()}"
        if used + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def build_prompt(segments: Iterable, duration: float, target_min: float, target_max: float) -> str:
    transcript = transcript_for_prompt(segments)
    return f"""你是一名短剧剪辑师。请把下面这条 {duration:.0f} 秒的短剧，压缩成一条完整的二创成片。

目标：最终成片 {target_min:.0f}-{target_max:.0f} 秒，只输出一条视频。

规则：
1. 必须让第一次看的人能看懂人物关系、冲突起因、发展和结果/悬念。
2. 默认保持原剧情时间顺序，不要为了“变化”而乱序。只有在不破坏因果关系时才允许调整。
3. 优先删除：重复对白、无信息停顿、重复反应镜头、空镜、拖沓转场、已经由后一句解释掉的前一句。
4. 尽量保留：关键冲突、人物动机、重要转折、能承接下一段的对白、结尾悬念。
5. 不要从一句话中间切入，也不要在一句话没说完时切走。
6. 单个保留段尽量不少于 3 秒；相邻且间隔很短的保留段应合并。
7. 总时长必须尽量落在目标范围内。
8. 输出必须是 JSON，不要解释，不要 Markdown。

JSON 格式：
{{
  "summary": "一句话概括剧情",
  "sequence": [
    {{"start": 0.0, "end": 25.0, "importance": 5, "reason": "为什么保留"}}
  ]
}}

原视频字幕时间轴：
{transcript}
"""


def _json_object(text: str) -> dict:
    text = text.strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def parse_plan(raw: str, duration: float) -> tuple[str, list[KeepRange]]:
    obj = _json_object(raw)
    summary = str(obj.get("summary") or "").strip()
    items = obj.get("sequence") or obj.get("keep") or []
    out: list[KeepRange] = []
    if not isinstance(items, list):
        return summary, out
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            start = max(0.0, min(float(duration), float(item.get("start"))))
            end = max(0.0, min(float(duration), float(item.get("end"))))
        except (TypeError, ValueError):
            continue
        if end - start < 1.0:
            continue
        try:
            importance = max(1, min(5, int(item.get("importance", 3))))
        except (TypeError, ValueError):
            importance = 3
        out.append(
            KeepRange(start=start, end=end, reason=str(item.get("reason") or "").strip(), importance=importance)
        )
    out.sort(key=lambda r: (r.start, r.end))
    return summary, merge_ranges(out)


def merge_ranges(ranges: list[KeepRange], gap: float = 0.45) -> list[KeepRange]:
    if not ranges:
        return []
    merged: list[KeepRange] = []
    for r in sorted(ranges, key=lambda x: (x.start, x.end)):
        if merged and r.start <= merged[-1].end + gap:
            prev = merged[-1]
            merged[-1] = KeepRange(
                prev.start,
                max(prev.end, r.end),
                reason=prev.reason or r.reason,
                importance=max(prev.importance, r.importance),
            )
        else:
            merged.append(r)
    return merged


def snap_to_dialogue(ranges: list[KeepRange], segments: Iterable, duration: float) -> list[KeepRange]:
    """Move cut points to nearby transcript boundaries so words are not cut."""
    segs = list(segments)
    if not segs:
        return ranges
    starts = [float(s.start) for s in segs]
    ends = [float(s.end) for s in segs]

    def nearest(values: list[float], x: float, limit: float = 1.8) -> float:
        best = min(values, key=lambda v: abs(v - x))
        return best if abs(best - x) <= limit else x

    snapped: list[KeepRange] = []
    for r in ranges:
        a = max(0.0, nearest(starts, r.start))
        b = min(duration, nearest(ends, r.end))
        if b - a >= 1.0:
            snapped.append(KeepRange(a, b, r.reason, r.importance))
    return merge_ranges(snapped)


def total_duration(ranges: list[KeepRange]) -> float:
    return sum(r.duration for r in ranges)


def fit_target(
    ranges: list[KeepRange],
    segments: Iterable,
    duration: float,
    target_min: float,
    target_max: float,
) -> list[KeepRange]:
    """Best-effort duration guard while preserving narrative order."""
    ranges = merge_ranges(ranges)
    if not ranges:
        return fallback_plan(segments, duration, target_min, target_max)

    while len(ranges) > 1 and total_duration(ranges) > target_max + 5:
        removable = sorted(
            range(len(ranges)),
            key=lambda i: (ranges[i].importance, ranges[i].duration),
        )
        removed = False
        for i in removable:
            candidate = ranges[:i] + ranges[i + 1 :]
            if total_duration(candidate) >= target_min - 5:
                ranges = candidate
                removed = True
                break
        if not removed:
            break

    if total_duration(ranges) < target_min:
        deficit = target_min - total_duration(ranges)
        pad_each = min(8.0, max(1.0, deficit / max(1, len(ranges)) / 2.0))
        expanded = [
            KeepRange(max(0.0, r.start - pad_each), min(duration, r.end + pad_each), r.reason, r.importance)
            for r in ranges
        ]
        ranges = merge_ranges(expanded)

    if total_duration(ranges) > target_max + 8:
        seg_ends = sorted(float(s.end) for s in segments)
        excess = total_duration(ranges) - target_max
        last = ranges[-1]
        desired = last.end - excess
        candidates = [x for x in seg_ends if last.start + 2.0 <= x <= last.end and x <= desired + 1.5]
        cut = max(candidates) if candidates else max(last.start + 2.0, desired)
        ranges[-1] = KeepRange(last.start, cut, last.reason, last.importance)
        ranges = merge_ranges(ranges)

    return ranges


def fallback_plan(segments: Iterable, duration: float, target_min: float, target_max: float) -> list[KeepRange]:
    """No-LLM fallback: keep dialogue islands plus context, then fit target."""
    segs = list(segments)
    if not segs:
        return [KeepRange(0.0, min(duration, target_max), "fallback", 3)]
    ranges = [
        KeepRange(max(0.0, float(s.start) - 0.8), min(duration, float(s.end) + 1.0), "dialogue", 3)
        for s in segs
        if float(s.end) - float(s.start) > 0.1
    ]
    ranges = merge_ranges(ranges, gap=1.5)
    if total_duration(ranges) > target_max:
        ends = [float(s.end) for s in segs if float(s.end) <= target_max]
        end = max(ends) if ends else min(duration, target_max)
        return [KeepRange(0.0, end, "fallback-continuity", 3)]
    if total_duration(ranges) < target_min:
        return [KeepRange(0.0, min(duration, target_max), "fallback-continuity", 3)]
    return ranges
