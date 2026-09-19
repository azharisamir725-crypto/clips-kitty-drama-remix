#!/usr/bin/env python3
"""Apply the short-drama remix feature to a clean Clips Kitty v1.2.0 checkout."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

PATCH_ROOT = Path(__file__).resolve().parent


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Patch marker not found in {path}: {old[:90]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def copy_new(src_rel: str, root: Path) -> None:
    src = PATCH_ROOT / src_rel
    dst = root / src_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python apply_patch.py <clips-studio-v1.2.0-folder>")
        return 2
    root = Path(sys.argv[1]).resolve()
    if not (root / "server" / "api.py").exists() or not (root / "ui" / "src").exists():
        raise RuntimeError("That folder does not look like a Clips Kitty source checkout")

    for rel in (
        "drama/__init__.py",
        "drama/planner.py",
        "drama/process.py",
        "config/prompts/drama_remix.txt",
        "tests/test_drama_planner.py",
        "ui/src/renderer/src/pages/DramaRemix.tsx",
    ):
        copy_new(rel, root)

    # FFmpeg 9 removed the legacy -vsync option. Clips Kitty v1.2.0 still
    # emits it in two places, which makes every render fail before encoding.
    # Use the modern -fps_mode equivalents so the bundled FFmpeg 9.0.1 works.
    cutter_py = root / "video" / "cutter.py"
    replace_once(
        cutter_py,
        '        "-vsync", "cfr",\n',
        '        "-fps_mode", "cfr",\n',
    )

    encoding_py = root / "video" / "encoding.py"
    replace_once(
        encoding_py,
        '        "-vsync", "0",              # keep the selected frames, do not resample\n',
        '        "-fps_mode", "passthrough",   # keep the selected frames, do not resample\n',
    )

    # PyInstaller + torchvision 0.29 on Windows can miss the native C++
    # extensions (_C/_C_stable). When that happens torchvision imports far
    # enough to register meta kernels, then crashes with:
    #   RuntimeError: operator torchvision::nms does not exist
    # Force the wheel's native extension files into the frozen backend and
    # add a frozen-runtime smoke test so this cannot ship unnoticed again.
    spec_py = root / "clips-studio.spec"
    replace_once(
        spec_py,
        'import os\nimport shutil\nimport sys\nfrom functools import cache\nfrom pathlib import Path\n' if False else 'from pathlib import Path\n\nfrom PyInstaller.utils.hooks import collect_all, collect_submodules\n',
        'from pathlib import Path\nimport importlib.util\n\nfrom PyInstaller.utils.hooks import collect_all, collect_submodules\n',
    )
    replace_once(
        spec_py,
        'for package in ("yt_dlp", "ultralytics", "faster_whisper", "ctranslate2",\n                "curl_cffi", "piper", "onnxruntime"):\n',
        'for package in ("yt_dlp", "ultralytics", "faster_whisper", "ctranslate2",\n                "curl_cffi", "piper", "onnxruntime", "torchvision"):\n',
    )
    replace_once(
        spec_py,
        '# uvicorn picks its event loop, HTTP parser and websocket implementation at\n',
        '# TorchVision 0.29 split its native ops into wheel-side extension files.\n'
        '# PyInstaller 6.22 can report torchvision._C as a missing hidden import\n'
        '# even though the wheel contains the .pyd. Collect every root extension\n'
        '# explicitly so NMS and the stable ABI ops exist in the installed app.\n'
        'try:\n'
        '    _tv_spec = importlib.util.find_spec("torchvision")\n'
        '    if _tv_spec and _tv_spec.submodule_search_locations:\n'
        '        _tv_dir = Path(next(iter(_tv_spec.submodule_search_locations)))\n'
        '        for _ext in _tv_dir.glob("*.pyd"):\n'
        '            binaries += [(str(_ext), "torchvision")]\n'
        'except Exception:\n'
        '    pass\n\n'
        '# uvicorn picks its event loop, HTTP parser and websocket implementation at\n',
    )

    main_py = root / "main.py"
    replace_once(
        main_py,
        '    sub.add_parser("status", help="Show processing/scheduling state")\n',
        '    sub.add_parser("status", help="Show processing/scheduling state")\n'
        '    sub.add_parser("vision-check", help=argparse.SUPPRESS)\n',
    )
    replace_once(
        main_py,
        '        if args.command == "status":\n            _print_status(db)\n            return 0\n\n',
        '        if args.command == "status":\n            _print_status(db)\n            return 0\n\n'
        '        if args.command == "vision-check":\n'
        '            import torch\n'
        '            import torchvision\n'
        '            from torchvision.ops import nms\n\n'
        '            boxes = torch.tensor([[0., 0., 10., 10.], [1., 1., 9., 9.]])\n'
        '            scores = torch.tensor([0.9, 0.8])\n'
        '            kept = nms(boxes, scores, 0.5)\n'
        '            print(f"vision ops ok: torch={torch.__version__} torchvision={torchvision.__version__} kept={kept.tolist()}")\n'
        '            return 0\n\n',
    )

    build_py = root / "scripts" / "build_installer.py"
    replace_once(
        build_py,
        '    print(f"    engine runs (exit 0, {len(output)} bytes of output)")\n\n',
        '    print(f"    engine runs (exit 0, {len(output)} bytes of output)")\n\n'
        '    vision = subprocess.run([str(exe), "vision-check"], capture_output=True, text=True,\n'
        '                            timeout=300, cwd=ROOT)\n'
        '    vision_output = (vision.stdout or "") + (vision.stderr or "")\n'
        '    if vision.returncode != 0:\n'
        '        print(vision_output[-4000:])\n'
        '        sys.exit("\\nFrozen TorchVision ops failed. Do not package this build.")\n'
        '    print(f"    vision ops run ({vision_output.strip()})")\n\n',
    )

    api_py = root / "server" / "api.py"
    replace_once(
        api_py,
        '    podcast: bool | None = None   # multi-cam podcast: letterbox, no subject tracking\n',
        '    podcast: bool | None = None   # multi-cam podcast: letterbox, no subject tracking\n'
        '    drama: dict | None = None     # one-output short-drama remix settings\n',
    )
    replace_once(
        api_py,
        '    podcast: bool | None = None\n    # Options to drop back to the app-wide default. Needed because null means\n',
        '    podcast: bool | None = None\n'
        '    drama: dict | None = None\n'
        '    # Options to drop back to the app-wide default. Needed because null means\n',
    )
    replace_once(
        api_py,
        '    podcast: bool | None = None\n\n\nclass BatchJobIn(BaseModel):\n',
        '    podcast: bool | None = None\n'
        '    drama: dict | None = None\n\n\nclass BatchJobIn(BaseModel):\n',
    )
    replace_once(
        api_py,
        '    max_clips: int | None = None\n    force: bool = False\n\n\nclass RenderIn(BaseModel):\n',
        '    max_clips: int | None = None\n'
        '    drama: dict | None = None\n'
        '    force: bool = False\n\n\nclass RenderIn(BaseModel):\n',
    )
    replace_once(
        api_py,
        '    if getattr(body, "podcast", None):\n        payload["podcast"] = True\n    if getattr(body, "longform", None):\n',
        '    if getattr(body, "podcast", None):\n        payload["podcast"] = True\n'
        '    if getattr(body, "drama", None):\n        payload["drama"] = body.drama\n'
        '    if getattr(body, "longform", None):\n',
    )
    replace_once(
        api_py,
        '            payload = _process_options(body, {"url": f"local:{vid}"})\n',
        '            payload = _process_options(\n'
        '                body, {"url": f"local:{vid}", "force": bool(body.force)}\n'
        '            )\n',
    )

    jobs_py = root / "server" / "jobs.py"
    replace_once(
        jobs_py,
        '                    if payload.get("longform"):\n'
        '                        # Separate longform system (1920x1080 horizontal),\n'
        '                        # built on the same stages — Shorts path untouched.\n'
        '                        from longform.process import process_longform\n\n'
        '                        process_longform(payload["url"], cfg, db, payload["longform"])\n'
        '                    else:\n'
        '                        process_video(payload["url"], cfg, db, force=payload.get("force", False))\n',
        '                    if payload.get("drama"):\n'
        '                        from drama.process import process_drama\n\n'
        '                        drama_opts = dict(payload["drama"])\n'
        '                        drama_opts["captions"] = cfg["clips"].get("captions", True)\n'
        '                        if payload.get("caption_style"):\n'
        '                            drama_opts["caption_style"] = payload["caption_style"]\n'
        '                        if payload.get("filter"):\n'
        '                            drama_opts["filter"] = payload["filter"]\n'
        '                        process_drama(\n'
        '                            payload["url"], cfg, db, drama_opts,\n'
        '                            force=payload.get("force", False),\n'
        '                        )\n'
        '                    elif payload.get("longform"):\n'
        '                        from longform.process import process_longform\n\n'
        '                        process_longform(payload["url"], cfg, db, payload["longform"])\n'
        '                    else:\n'
        '                        process_video(payload["url"], cfg, db, force=payload.get("force", False))\n',
    )

    types_ts = root / "ui" / "src" / "renderer" / "src" / "lib" / "types.ts"
    replace_once(
        types_ts,
        '  longform?: { mode: string } | null\n  watermark_profile_id?: number | null\n',
        '  longform?: { mode: string } | null\n'
        '  drama?: { target_min_seconds: number; target_max_seconds: number } | null\n'
        '  watermark_profile_id?: number | null\n',
    )
    replace_once(
        types_ts,
        '  edit?: EditData | null\n  profile?: string // longform rendering profile (16:9); absent = vertical Short\n',
        '  edit?: EditData | null\n'
        '  drama_mode?: { target_min_seconds?: number; target_max_seconds?: number; planned_seconds?: number; summary?: string } | null\n'
        '  profile?: string // longform rendering profile (16:9); absent = vertical Short\n',
    )

    api_ts = root / "ui" / "src" / "renderer" / "src" / "lib" / "api.ts"
    replace_once(
        api_ts,
        '        longform: opts.longform ?? null,\n        watermark_profile_id: opts.watermark_profile_id ?? null,\n',
        '        longform: opts.longform ?? null,\n'
        '        drama: opts.drama ?? null,\n'
        '        watermark_profile_id: opts.watermark_profile_id ?? null,\n',
    )

    queue_ts = root / "ui" / "src" / "renderer" / "src" / "lib" / "queue.ts"
    replace_once(
        queue_ts,
        "  if (o.podcast) chips.push('Podcast')\n  if (o.longform) chips.push(`Longform · ${String(o.longform.mode ?? '').replace(/_/g, ' ')}`)\n",
        "  if (o.podcast) chips.push('Podcast')\n"
        "  if (o.drama) chips.push(`短剧二创 · ${Math.round(o.drama.target_min_seconds / 60)}-${Math.round(o.drama.target_max_seconds / 60)}分钟`)\n"
        "  if (o.longform) chips.push(`Longform · ${String(o.longform.mode ?? '').replace(/_/g, ' ')}`)\n",
    )

    clip_card = root / "ui" / "src" / "renderer" / "src" / "components" / "ClipCard.tsx"
    replace_once(
        clip_card,
        '  const duration = Math.round(clip.end_s - clip.start_s)\n',
        '  const duration = Math.round(clip.render_opts?.drama_mode?.planned_seconds ?? (clip.end_s - clip.start_s))\n',
    )

    app_tsx = root / "ui" / "src" / "renderer" / "src" / "App.tsx"
    replace_once(
        app_tsx,
        "import Settings from './pages/Settings'\n",
        "import Settings from './pages/Settings'\nimport DramaRemix from './pages/DramaRemix'\n",
    )
    replace_once(
        app_tsx,
        "type Page = 'dashboard' | 'queue' | 'studio' | 'creators' | 'models' | 'settings'\n",
        "type Page = 'dashboard' | 'drama' | 'queue' | 'studio' | 'creators' | 'models' | 'settings'\n",
    )
    replace_once(
        app_tsx,
        "  { id: 'dashboard', label: 'Dashboard', icon: '◧' },\n  { id: 'queue', label: 'Queue', icon: '≡' },\n",
        "  { id: 'dashboard', label: 'Dashboard', icon: '◧' },\n"
        "  { id: 'drama', label: '短剧二创', icon: '◆' },\n"
        "  { id: 'queue', label: 'Queue', icon: '≡' },\n",
    )
    replace_once(
        app_tsx,
        "        {page === 'dashboard' && <Dashboard onOpenInStudio={openInStudio} />}\n        {page === 'queue' && <Queue onOpenInStudio={(videoId) => openInStudio(videoId)} />}\n",
        "        {page === 'dashboard' && <Dashboard onOpenInStudio={openInStudio} />}\n"
        "        {page === 'drama' && <DramaRemix />}\n"
        "        {page === 'queue' && <Queue onOpenInStudio={(videoId) => openInStudio(videoId)} />}\n",
    )

    print("Short-drama remix patch applied successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
