"""Command-line interface orchestration (interactive & plugins)."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from rich import print as rprint
from .config import AppConfig
from .downloader import PlaylistDownloader
from .plugins import PluginManager
from .logging_utils import get_logger
from .reporting import build_session_report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="YouTube Playlist / Video Downloader")
    p.add_argument(
        "urls",
        nargs="+",
        help="One or more playlist or single video URLs (mix allowed)",
    )
    p.add_argument("-q", "--quality", default="720p", help="Preferred quality")
    p.add_argument("-a", "--audio", action="store_true", help="Audio only mode")
    p.add_argument("-o", "--output", default="downloads", help="Output directory")
    p.add_argument("-j", "--jobs", type=int, default=4, help="Max parallel downloads")
    p.add_argument("--interactive", action="store_true", help="Interactive mode")
    p.add_argument("--captions", action="store_true", help="Fetch manual captions if available")
    p.add_argument("--captions-auto", action="store_true", help="Allow auto (ASR) captions fallback or only if requested without manual")
    p.add_argument(
        "--caption-langs",
        default="en",
        help="Comma-separated caption language preference order (default: en)",
    )
    p.add_argument("--dry-run", action="store_true", help="Plan only; no downloads performed")
    p.add_argument(
        "--filter",
        dest="filters",
        action="append",
        default=[],
        help="Case-insensitive substring filter on title (repeatable)",
    )
    p.add_argument(
        "--index-range",
        help="Index slice start:end (1-based inclusive). Examples: 5:10, :20, 10:",
    )
    p.add_argument("--resume", action="store_true", help="Resume using manifest.json in output dir")
    p.add_argument(
        "--report-format",
        choices=["json", "none"],
        default="none",
        help="Generate session report (json). For dry-run prints to stdout",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if manifest marks success (future)",
    )
    p.add_argument(
        "--naming-template",
        default="{index:03d}-{title}",
        help="Filename template tokens: {index},{title},{quality},{video_id},{date},{audio_only}",
    )
    return p


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Validate index-range basic pattern early (keep contract loose)
    if args.index_range and not re.match(r"^\d*:\d*$", args.index_range):
        parser.error("Invalid --index-range format; expected start:end with digits")

    config = AppConfig(
        quality_order=[args.quality]
        + [
            q
            for q in ["1080p", "720p", "480p", "360p", "240p", "144p"]
            if q != args.quality
        ],
        max_concurrency=args.jobs,
        audio_only=args.audio,
        output_dir=args.output,
        interactive=args.interactive,
    )

    log = get_logger()
    log.info("Starting session (interactive=%s)", config.interactive)
    plugin_manager = PluginManager()  # Placeholder for future dynamic discovery
    downloader = PlaylistDownloader(config)
    all_results = []
    targets = args.urls
    if args.dry_run:
        # Produce a minimal plan stub (no network)
        plan = {
            "schemaVersion": "1.0.0",
            "generated": datetime.utcnow().isoformat() + "Z",
            "mode": "dry-run",
            "playlistUrl": targets[0] if targets else None,
            "videos": [],  # placeholder list to satisfy contract shape
            "qualityOrder": config.quality_order,
            "filters": args.filters,
            "indexRange": args.index_range,
            "resume": args.resume,
            "captions": {
                "manual": args.captions,
                "auto": args.captions_auto,
                "langs": args.caption_langs.split(",") if args.caption_langs else [],
            },
            "namingTemplate": args.naming_template,
        }
        if args.report_format == "json":
            # Print raw JSON only (tests expect last line parsable)
            print(json.dumps(plan))
        else:
            rprint("[bold]Dry-run plan[/bold] targets=" + str(len(targets)) + "\nProcessing playlist (simulated)")
        return 0

    sessions_reports = []
    for idx, url in enumerate(targets, start=1):
        rprint(
            f"[cyan]Processing target {idx}/{len(targets)} (playlist or video):[/] {url}"
        )
        if config.interactive:
            if not _interactive_confirm(url):
                rprint("[yellow]Skipped by user[/]")
                continue
        # Dispatch: playlist vs single video
        if ("watch?v=" in url and "list=" not in url) or "/shorts/" in url:
            single = downloader.download_video(
                url,
                audio_only=config.audio_only,
            )
            res = [single] if single else []
        else:
            res = downloader.download_playlist(
                url,
                audio_only=config.audio_only,
                resume=args.resume,
                filters=args.filters,
                index_range=args.index_range,
                captions=args.captions,
                captions_auto=args.captions_auto,
                caption_langs=args.caption_langs.split(",") if args.caption_langs else ["en"],
                force=args.force,
            )
        all_results.append((url, res))
        plugin_manager.run_all({"playlist_url": url, "results": res})
        # Build ad-hoc session-like summary for structured logging (placeholder until session object externally exposed)
        if args.report_format == "json":
            # Minimal session dict (counts computed from res)
            counts = {
                "total": len(res),
                "success": sum(1 for v in res if v.status == "success"),
                "failed": sum(1 for v in res if v.status == "failed"),
            }
            counts["skipped"] = 0
            counts["fallbacks"] = sum(1 for v in res if getattr(v, "fallback_applied", False))
            sessions_reports.append(
                {
                    "playlistUrl": url,
                    "counts": counts,
                }
            )

    # Simple summary
    total_videos = sum(len(r) for _, r in all_results)
    successes = sum(1 for _, r in all_results for v in r if v.status == "success")
    failures = total_videos - successes
    rprint(f"[bold green]Completed[/] videos: {successes} / {total_videos}")
    if failures:
        rprint(f"[bold red]Failures:[/] {failures}")
    if args.report_format == "json" and sessions_reports:
        summary_line = json.dumps({
            "summary": {
                "targets": len(sessions_reports),
                "totalVideos": total_videos,
                "success": successes,
                "failed": failures,
            }
        })
        print(summary_line)
    return 0 if failures == 0 else 1


def _interactive_confirm(url: str) -> bool:
    try:
        ans = input(f"Download playlist '{url}'? [Y/n]: ").strip().lower()
        return ans in ("", "y", "yes")
    except KeyboardInterrupt:  # pragma: no cover
        return False
