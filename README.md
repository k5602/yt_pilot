# yt_pilot

Modular YouTube Playlist Downloader supporting playlist batch operations, quality fallback, audio-only mode, interactive confirmations, and an extensible plugin hook system.

## Current Core Features

- Parallel downloads with configurable workers
- Visual progress via rich progress bars
- Quality preference & fallback order (1080p → 144p)
- Audio-only extraction mode
- Batch processing of multiple playlist URLs
- Interactive confirmation mode (`--interactive`)
- Simple plugin manager scaffold (post-playlist hooks)
- Central logging utilities

## Roadmap (See spec `specs/001-refactor-app-into/spec.md`)
- Resume / session manifest
- JSON & human-readable reports
- Advanced interactive controls (skip, filter, quality adjust pre-start)
- Filename templating & filtering
- Configurable plugin auto-discovery
- Dry-run analysis mode

## Installation 🛠️

1. **Clone Repository**
```bash
git clone https://github.com/yourusername/youtube-playlist-downloader.git
cd youtube-playlist-downloader
```

2. **Install Dependencies**
```bash
pip install -r requirements.txt
```

## Usage 🚀

Entrypoint remains `main.py` for backwards compatibility.

### Basic
```bash
python main.py "https://youtube.com/playlist?list=PL..."
```

### Multiple Playlists
```bash
python main.py URL1 URL2 URL3 -q 1080p -j 8
```

### Audio Only
```bash
python main.py URL -a
```

### Interactive Confirmation
```bash
python main.py URL1 URL2 --interactive
```

### Help
```bash
python main.py --help
```

## Technical Implementation 💻

### Core Technologies
- **Python 3.9+** - Type hinted codebase
- **pytube** - YouTube content retrieval
- **rich** - Terminal formatting and progress
- **concurrent.futures** - Parallel processing

### Package Structure
```
yt_downloader/
    config.py        # AppConfig dataclass
    downloader.py    # Core playlist/video handling
    cli.py           # CLI + interactive prompts
    plugins.py       # Plugin protocol & manager
    logging_utils.py # Logger setup
    __init__.py      # Public exports
```

`main.py` delegates to `yt_downloader.cli.run_cli`.


## License 📄

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Developed with ❤️ by [Khaled]**

