"""One-output short-drama remix pipeline."""

from __future__ import annotations

import copy
import time
from pathlib import Path

from analysis.metadata import ClipMetadata
from core import cancel, progress
from core.models import ClipCandidate, RenderedClip
from core.state import StateDB
from drama.planner import build_prompt, fit_target, parse_plan, snap_to_dialogue, total_duration
from llm.registry import create_backend
from transcription.transcriber import detected_language, transcribe


def process_drama(
    url: str,
    config: dict,
    db: StateDB,
    options: dict | None = None,
    *,
    force: bool = False,
) -> list[RenderedClip]:
    """Make ONE 9:16 narrative remix, normally 3-4 minutes long."""
    from core.pipeline import (
        _cached_or_download,
        _register_clip,
        _render_files,
        _safe_name,
        _with_usable_model,
    )

    options = options or {}
    data_dir = Path(config["paths"]["data_dir"])
    target_min = max(30.0, float(options.get("target_min_seconds", 180)))
    target_max = max(target_min + 5.0, float(options.get("target_max_seconds", 240)))
    started = time.monotonic()

    config = copy.deepcopy(config)
    config.setdefault("clips", {})["outro"] = False

    print(f"[1/4] Loading source for short-drama remix: {url}")
    progress.emit(stage="download", message=url)
    video = _cached_or_download(url, data_dir, db)
    progress.emit(stage="downloaded", video_id=video.video_id, title=video.title, duration=video.duration)

    target_max = min(target_max, max(5.0, video.duration))
    target_min = min(target_min, max(5.0, target_max - 5.0))

    cancel.clear(video.video_id)
    db.upsert_video(video.video_id, title=video.title, channel_name=video.channel, duration=video.duration)
    if db.video_status(video.video_id) == "done" and not force:
        print("      Already processed. Re-run with force to make a new drama remix.")
        return []
    db.set_video_status(video.video_id, "downloaded")
    cancel.check(video.video_id)

    print("[2/4] Transcribing dialogue...")
    progress.emit(stage="transcribe", video_id=video.video_id, title=video.title)
    forced_lang = (config.get("content_language") or "auto").lower()
    segments = transcribe(
        video.path,
        video.video_id,
        data_dir / "transcripts",
        model_size=config["whisper"]["model"],
        device=config["whisper"]["device"],
        language=None if forced_lang == "auto" else forced_lang,
    )
    content_lang = forced_lang if forced_lang != "auto" else detected_language(
        video.video_id, data_dir / "transcripts"
    )
    db.set_video_status(video.video_id, "transcribed")
    cancel.check(video.video_id)

    print(f"[3/4] Planning one coherent {target_min:.0f}-{target_max:.0f}s drama edit...")
    progress.emit(stage="analyze", video_id=video.video_id)
    llm = create_backend(_with_usable_model(config["llm"]))
    raw = llm.generate(build_prompt(segments, video.duration, target_min, target_max), json_mode=True)
    summary, keep = parse_plan(raw, video.duration)
    keep = snap_to_dialogue(keep, segments, video.duration)
    keep = fit_target(keep, segments, video.duration, target_min, target_max)
    if not keep:
        raise RuntimeError("AI could not build a usable short-drama edit plan")

    final_seconds = total_duration(keep)
    print(f"      Story plan: {len(keep)} kept section(s), about {final_seconds:.0f}s total")

    candidate = ClipCandidate(
        start=0.0,
        end=video.duration,
        score=100,
        hook="短剧二创",
        reason="single coherent short-drama remix",
        source="transcript",
    )
    edit = {
        "keep": [[round(r.start, 2), round(r.end, 2)] for r in keep],
        "mutes": [],
        "muted_words": [],
        "volume": 1.0,
        "mute_all": False,
        "fade_in": 0.0,
        "fade_out": 0.0,
        "speed": 1.0,
        "hook": None,
        "music": None,
    }
    render_opts: dict = {
        "edit": edit,
        "captions": bool(options.get("captions", True)),
        "drama_mode": {
            "target_min_seconds": target_min,
            "target_max_seconds": target_max,
            "planned_seconds": round(final_seconds, 2),
            "summary": summary,
        },
    }
    if options.get("caption_style"):
        render_opts["caption_style"] = options["caption_style"]
    if options.get("filter"):
        render_opts["filter"] = options["filter"]

    clip_dir = (
        data_dir
        / "clips"
        / _safe_name(video.channel, "unknown-channel")
        / f"{_safe_name(video.title, video.video_id)} [{video.video_id}]"
        / "Drama Remix"
    )
    print("[4/4] Rendering ONE final drama remix...")
    progress.emit(stage="render", video_id=video.video_id, clip=1, total=1)
    final_path, render_opts_json = _render_files(
        video.path,
        candidate,
        segments,
        clip_dir,
        config,
        render_opts,
        content_lang,
    )

    meta = ClipMetadata(
        title=f"{video.title} · 短剧二创",
        description=summary or "AI 自动压缩并保持剧情连续的一条短剧二创成片。",
        hashtags=[],
    )
    rendered = _register_clip(db, video.video_id, candidate, final_path, meta, render_opts_json, config)
    db.set_video_status(video.video_id, "done")
    elapsed = time.monotonic() - started
    db.set_process_seconds(video.video_id, elapsed)
    progress.emit(stage="done", video_id=video.video_id, clips=1, seconds=round(elapsed, 1))
    print(f"      Drama remix done in {elapsed / 60:.1f} min -> {final_path.name}")
    return [rendered] if rendered is not None else []
