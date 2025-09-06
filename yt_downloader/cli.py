"""Command-line interface orchestration (interactive & plugins)."""

from __future__ import annotations

import argparse
from rich import print as rprint
from .config import AppConfig
from .downloader import PlaylistDownloader
from .plugins import PluginManager
from .logging_utils import get_logger


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="YouTube Playlist Downloader (modular)")
    p.add_argument("playlist_url", nargs="+", help="One or more playlist URLs")
    p.add_argument("-q", "--quality", default="720p", help="Preferred quality")
    p.add_argument("-a", "--audio", action="store_true", help="Audio only mode")
    p.add_argument("-o", "--output", default="downloads", help="Output directory")
    p.add_argument("-j", "--jobs", type=int, default=4, help="Max parallel downloads")
    p.add_argument("--interactive", action="store_true", help="Interactive mode")
    return p


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

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
    for idx, url in enumerate(args.playlist_url, start=1):
        rprint(f"[cyan]Processing playlist {idx}/{len(args.playlist_url)}:[/] {url}")
        if config.interactive:
            if not _interactive_confirm(url):
                rprint("[yellow]Skipped by user[/]")
                continue
        res = downloader.download_playlist(url)
        all_results.append((url, res))
        plugin_manager.run_all({"playlist_url": url, "results": res})

    # Simple summary
    total_videos = sum(len(r) for _, r in all_results)
    successes = sum(1 for _, r in all_results for v in r if v.status == "success")
    failures = total_videos - successes
    rprint(f"[bold green]Completed[/] videos: {successes} / {total_videos}")
    if failures:
        rprint(f"[bold red]Failures:[/] {failures}")
    return 0 if failures == 0 else 1


def _interactive_confirm(url: str) -> bool:
    try:
        ans = input(f"Download playlist '{url}'? [Y/n]: ").strip().lower()
        return ans in ("", "y", "yes")
    except KeyboardInterrupt:  # pragma: no cover
        return False
