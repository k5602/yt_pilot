
# YouTube  🎥➡️📁
A high-performance Python utility for downloading YouTube playlists with parallel downloads and quality selection. Perfect for content archivists, educators, and media enthusiasts.
Modular YouTube Playlist & Single Video Downloader supporting playlist batch operations, captions (manual + auto), resume via manifest, dry-run planning, reporting, quality fallback, audio-only mode, interactive confirmations, filtering, filename templating, and an extensible plugin hook system.

**Built with yt-dlp** for reliable YouTube downloads and support for thousands of video sites.

## Features

- Playlist & single video URLs (mixed targets)
- Parallel downloads (--jobs)
- Quality preference & fallback order
- Audio-only extraction (-a / --audio)
- Resume with manifest (--resume)
- Force re-download (--force)
- Dry-run planning (--dry-run) with optional JSON output (--report-format json)
- JSON report summary output & structured logging
- Captions: manual (--captions) + auto fallback (--captions-auto) with language preference (--caption-langs "en,es")
- Title filtering (repeatable --filter substr)
- Index slicing (--index-range start:end inclusive)
- Filename templating (--naming-template)
- Interactive confirmation (--interactive)
- Plugin manager scaffold for post-processing
- Powered by yt-dlp for robust YouTube API compatibility

## Installation

```bash
pip install .[dev]
```

Or build & install wheel:

```bash
python -m build
pip install dist/yt_downloader-*.whl
```

After installation a console script `yt-downloader` is available.

## CLI Usage

yt-downloader URL [URL ...] [options]
```bash
yt-downloader URL [URL ...] [options]
```

### Common Options

| Flag | Description |
|------|-------------|
| -q / --quality | Primary preferred quality (fallback chain auto-extends) |
| -a / --audio | Audio-only mode |
| -j / --jobs | Max parallel worker threads |
| --dry-run | Plan only; no downloads |
| --report-format json| Emit JSON session summary (dry-run prints plan JSON if also --dry-run) |
| --filter SUBSTR | Case-insensitive title substring filter (repeatable OR) |
| --index-range s:e | 1-based inclusive slice (e.g. 5:10, :20, 10:) |
| --resume | Skip already successful items found in manifest.json |
| --force | Re-download even if manifest marks success |
| --captions | Download manual captions if available |
| --captions-auto | Allow automatic (ASR) captions if manual missing (or when only auto desired) |
| --caption-langs CSV | Preference order (default: en) |
| --naming-template T | Filename pattern tokens: {index},{title},{quality},{video_id},{date},{audio_only} |
| --interactive | Ask confirmation per target |

### Examples

Dry-run with JSON plan:
yt-downloader --dry-run --report-format json "https://youtube.com/playlist?list=PL123" > plan.json
```bash
yt-downloader --dry-run --report-format json "<https://youtube.com/playlist?list=PL123>" > plan.json
```

Download a single video with captions (manual then auto fallback):
yt-downloader --captions --captions-auto "https://www.youtube.com/watch?v=VIDEO_ID"
```bash
yt-downloader --captions --captions-auto "<https://www.youtube.com/watch?v=VIDEO_ID>"
```

Playlist subset, filter titles containing "python" across indices 10–25, audio only:
yt-downloader -a --filter python --index-range 10:25 "https://youtube.com/playlist?list=PL123"
```bash
yt-downloader -a --filter python --index-range 10:25 "<https://youtube.com/playlist?list=PL123>"
```

Force re-download ignoring previous successes:
yt-downloader --force --resume "https://youtube.com/playlist?list=PL123"
```bash
yt-downloader --force --resume "<https://youtube.com/playlist?list=PL123>"
```

Custom naming template:
yt-downloader --naming-template "{index:03d}-{title}-{quality}" URL
```bash
yt-downloader --naming-template "{index:03d}-{title}-{quality}" URL
```

## Reporting

When `--report-format json` a final summary line is emitted to stdout as JSON:
```json
{"summary":{"targets":1,"totalVideos":12,"success":12,"failed":0}}
```
Integrations can parse this line for automation. Per-target lightweight report files are written to the output directory as `report.json` (single target) or `report-<n>.json` when multiple targets are processed.
(Full detailed per-video report plumbing is prepared in `reporting.py`).

## Architecture Overview
See `docs/architecture.md` for module responsibilities.

## Development

Run tests:
```bash
pytest -q
```

## License
MIT - see `LICENSE`.

**Developed with ❤️ by [Khaled]**  
