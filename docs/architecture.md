# Architecture Overview

## Module Responsibilities

- `config.py`: AppConfig dataclass holding runtime configuration (quality order, concurrency, output path, interactive flag, audio_only).
- `models.py`: Core dataclasses (VideoItem, CaptionTrack) and related typed structures for manifest/report.
- `naming.py`: Filename template expansion and sanitization.
- `filtering.py`: Title substring OR filtering and inclusive index range slicing.
- `manifest.py`: Load/update manifest JSON, compute skip logic for resume.
- `captions.py`: Manual and automatic caption retrieval (selection, SRT/VTT style content production).
- `planner.py`: Dry-run plan object generation (lightweight representation without network calls currently placeholder for future expansion).
- `downloader.py`: Orchestrates playlist vs single video downloads, integrates naming, filtering, captions, manifest, batching, and force behavior.
- `reporting.py`: Builds structured summary dictionaries; future extended detailed reporting hooks.
- `plugins.py`: Minimal plugin manager allowing future extensibility hooks post processing.
- `logging_utils.py`: Central logger factory.

## Data Flow (Happy Path)

1. TUI collects user input -> builds AppConfig.
2. For each URL target: decide playlist vs single video.
3. Playlist path: filtering + manifest skip -> concurrent downloads -> captions selection -> filename templating -> manifest update.
4. Results aggregated; optional JSON structured summary printed.
5. Dry-run short-circuits before network, emitting plan skeleton.

## Manifest & Resume

Manifest entries track status per video id with basic metadata. On resume, existing successful entries plus file existence determine skips unless --force is set.

## Captions Strategy

Manual captions (yt-dlp) preferred. If unavailable and --captions-auto provided, attempt auto transcript via youtube-transcript-api. Stored tracks attach to VideoItem for future report enrichment.

## Concurrency & Batching

Downloader batches futures to limit memory and optional backpressure (batch size = concurrency \* 2). Simplified thread-based approach.

## Filename Templates

Python format string tokens validated; unknown tokens trigger warning. Sanitization ensures cross-platform safe names.

## Reporting

Currently emits summary counts (success/failed). `reporting.py` structured builder prepared for deeper drill-down later.

## Extensibility Points

- Plugins: Post-target hook receives playlist_url and results.
- Planner: Can be extended to estimate sizes & durations.
- Reporting: Extend to full JSON artifact persisted to disk.

## Future Enhancements

- Persist full report artifact with per-video quality/caption details.
- More robust error classification & retry policy.
- Async IO or process-based parallelism for performance.
- Configuration file support.
