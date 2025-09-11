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
from .reporting import build_session_report, write_report


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
    p.add_argument(
        "--captions", action="store_true", help="Fetch manual captions if available"
    )
    p.add_argument(
        "--captions-auto",
        action="store_true",
        help="Allow auto (ASR) captions fallback or only if requested without manual",
    )
    p.add_argument(
        "--caption-langs",
        default="en",
        help="Comma-separated caption language preference order (default: en)",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Plan only; no downloads performed"
    )
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
    p.add_argument(
        "--resume", action="store_true", help="Resume using manifest.json in output dir"
    )
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
    p.add_argument(
        "--sub-langs",
        dest="sub_langs",
        default=None,
        help="Comma-separated subtitle languages overriding --caption-langs for manual subtitle download (e.g. en,es,fr)",
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
    # Effective caption/subtitle languages: --sub-langs overrides --caption-langs for manual subtitles
    effective_caption_langs = (
        args.sub_langs.split(",")
        if args.sub_langs
        else (args.caption_langs.split(",") if args.caption_langs else ["en"])
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
                "langs": effective_caption_langs,
                "override": bool(args.sub_langs),
            },
            "namingTemplate": args.naming_template,
        }
        if args.report_format == "json":
            # Print raw JSON only (tests expect last line parsable)
            print(json.dumps(plan))
        else:
            rprint(
                "[bold]Dry-run plan[/bold] targets="
                + str(len(targets))
                + "\nProcessing playlist (simulated)"
            )
        return 0

    sessions_reports = []
    written_reports = []
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
                caption_langs=effective_caption_langs,
                force=args.force,
            )
        all_results.append((url, res))
        plugin_manager.run_all({"playlist_url": url, "results": res})
        # Full session / single-target reporting
        if args.report_format == "json":
            if downloader.last_session and len(res) > 0 and len(res) >= 1 and any(
                v for v in res
            ):
                # Use the real playlist session produced by downloader (playlist path)
                session = downloader.last_session
                # Ensure ended timestamp
                if session and session.ended is None:
                    from datetime import datetime as _dt
                    session.ended = _dt.utcnow()
                session_report = build_session_report(session)
                counts = session_report.get("counts", {})
            else:
                # Synthetic single-video session report
                from datetime import datetime as _dt
                vid_entries = []
                fallbacks = []
                failures = []
                for v in res:
                    vid_entries.append(
                        {
                            "videoId": getattr(v, "url", "unknown").split("v=")[-1][:11],
                            "title": v.title,
                            "status": v.status,
                            "quality": getattr(v, "quality", None),
                            "fallback": getattr(v, "fallback_applied", False),
                            "retries": 0,
                            "sizeBytes": None,
                        }
                    )
                    if getattr(v, "fallback_applied", False):
                        fallbacks.append(
                            {
                                "videoId": vid_entries[-1]["videoId"],
                                "from": config.quality_order[0],
                                "to": getattr(v, "quality", None),
                            }
                        )
                    if v.status == "failed":
                        failures.append(
                            {
                                "videoId": vid_entries[-1]["videoId"],
                                "reason": getattr(v, "failure_reason", "unknown"),
                            }
                        )
                counts = {
                    "total": len(res),
                    "success": sum(1 for v in res if v.status == "success"),
                    "failed": sum(1 for v in res if v.status == "failed"),
                    "skipped": 0,
                    "fallbacks": sum(
                        1 for v in res if getattr(v, "fallback_applied", False)
                    ),
                }
                session_report = {
                    "schemaVersion": "1.0.0",
                    "playlistUrl": url,
                    "sessionId": f"single-{idx}",
                    "started": datetime.utcnow().isoformat(),
                    "ended": datetime.utcnow().isoformat(),
                    "qualityOrder": config.quality_order,
                    "configSnapshot": config.__dict__,
                    "counts": counts,
                    "failures": failures,
                    "fallbacks": fallbacks,
                    "videos": vid_entries,
                }
            # Append lightweight summary for aggregate summary output
            sessions_reports.append({"playlistUrl": url, "counts": counts})
            # Determine per-target report path
            report_path = config.output_dir / (
                f"report-{idx}.json" if len(targets) > 1 else "report.json"
            )
            report_path.write_text(json.dumps(session_report, indent=2))
            written_reports.append(str(report_path))

    # Simple summary
    total_videos = sum(len(r) for _, r in all_results)
    successes = sum(1 for _, r in all_results for v in r if v.status == "success")
    failures = total_videos - successes
    rprint(f"[bold green]Completed[/] videos: {successes} / {total_videos}")
    if failures:
        rprint(f"[bold red]Failures:[/] {failures}")
        # Detailed failure reasons
        for url, res in all_results:
            for v in res:
                if v.status == "failed":
                    reason = getattr(v, "failure_reason", "unknown")
                    display_title = v.title
                    if display_title.startswith("http"):
                        vid_id = display_title.split("v=")[-1].split("&")[0]
                        display_title = f"video:{vid_id}"
                    rprint(
                        f"  [red]- {display_title}[/red] ([dim]{url}[/dim]) -> {reason}"
                    )
    if args.report_format == "json" and sessions_reports:
        summary_line = json.dumps(
            {
                "summary": {
                    "targets": len(sessions_reports),
                    "totalVideos": total_videos,
                    "success": successes,
                    "failed": failures,
                    "reports": written_reports,
                }
            }
        )
        print(summary_line)
    return 0 if failures == 0 else 1


def _interactive_confirm(url: str) -> bool:
    try:
        ans = input(f"Download playlist '{url}'? [Y/n]: ").strip().lower()
        return ans in ("", "y", "yes")
    except KeyboardInterrupt:  # pragma: no cover
        return False
