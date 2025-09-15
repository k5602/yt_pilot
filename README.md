# YouTube Pilot 🎥➡️📁

A high-performance Python utility for downloading YouTube playlists with parallel downloads and quality selection. Perfect for content archivists, educators, and media enthusiasts.
Modular YouTube Playlist & Single Video Downloader supporting playlist batch operations, captions (manual + auto), resume via manifest, dry-run planning, reporting, quality fallback, audio-only mode, interactive confirmations, filtering, filename templating, and an extensible plugin hook system.

**Built with yt-dlp** for reliable YouTube downloads and support for thousands of video sites.

## Features

- **Textual UI:** An intuitive terminal-based graphical interface for configuring and managing downloads with real-time progress tracking and logging.
- **Configuration Management:** Save and load your preferred settings from JSON configuration files.
- **Plugin System:** Extensible architecture allowing custom plugins to enhance functionality.
- **Detailed Reporting:** Automatic generation of structured JSON reports for each download session.
- **Comprehensive Download Options:** Support for playlists and single videos, parallel downloads, quality selection with fallback, audio-only mode, resume functionality, and force re-download.
- **Caption Support:** Download manual captions with automatic fallback to ASR-generated captions, configurable language preferences.
- **Advanced Filtering:** Title-based filtering, index range selection, and custom filename templating.
- **Dry Run Mode:** Preview download plans without performing actual downloads.
- **Powered by yt-dlp:** Leverages yt-dlp for reliable YouTube and other video platform compatibility.

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

## Usage

Launch the Textual UI:

### Examples

Launch the TUI:

```bash
yt-downloader
```

The TUI provides an intuitive interface for configuring and starting downloads. Use the tabs to set options like quality, audio mode, captions, and advanced settings. Click "Dry Run" to preview the download plan or "Start Download" to begin.

## Configuration

You can save your preferred settings to a JSON file and use it with the `--config` flag. To save your current settings, use the `--save-config` flag.

Example `config.json`:

```json
{
  "quality_order": ["1080p", "720p"],
  "max_concurrency": 8,
  "audio_only": false,
  "output_dir": "/path/to/downloads"
}
```

## Reporting

When `--report-format json` is used, a detailed `report.json` file is generated in the output directory for each download session. This file contains information about the downloaded videos, including their quality, size, duration, and any errors that occurred.

## Plugins

YouTube Pilot supports plugins to extend its functionality. Plugins are Python files that are loaded from `~/.config/yt-pilot/plugins`. To create a plugin, you need to create a Python file that defines a class that inherits from the `Plugin` protocol.

Example plugin:

```python
from yt_downloader.plugins import Plugin

class MyPlugin(Plugin):
    name = "MyPlugin"

    def on_video_downloaded(self, context):
        video = context["video"]
        print(f"Downloaded video: {video.title}")
```

## Architecture Overview

See `docs/architecture.md` for module responsibilities.

## Development

Run tests:

```bash
pytest -q
```

## License

MIT - see `LICENSE`.

**Developed with ❤️ by Khaled**
