"""Configuration management for the YouTube downloader."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List

DEFAULT_QUALITY_ORDER = ["1080p", "720p", "480p", "360p", "240p", "144p"]


@dataclass
class AppConfig:
    quality_order: List[str] = field(
        default_factory=lambda: DEFAULT_QUALITY_ORDER.copy()
    )
    max_concurrency: int = 4
    timeout_seconds: int = 10
    output_dir: Path = field(default_factory=lambda: Path.home() / 'Downloads' / 'yt_downloads')
    audio_only: bool = False
    retry_attempts: int = 2
    interactive: bool = False
    enable_plugins: bool = True
    naming_template: str = "{index:03d}-{title}"
    caption_langs: List[str] = field(default_factory=lambda: ["en"])
    captions_enabled: bool = False
    captions_auto_enabled: bool = False
    layout_ratio: int = 60  # percentage of vertical space allocated to form (upper) section

    def __post_init__(self):
        # Ensure output_dir is a Path object
        if not isinstance(self.output_dir, Path):
            self.output_dir = Path(self.output_dir)

    def preferred(self) -> str:
        return self.quality_order[0]

    def save(self, path: Path) -> None:
        """Saves the configuration to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2, cls=PathEncoder)

    @classmethod
    def from_file(cls, path: Path) -> "AppConfig":
        """Loads configuration from a JSON file."""
        if not path.exists():
            return cls()
        with open(path, "r") as f:
            data = json.load(f)
        return cls(**data)


class PathEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Path):
            return str(o)
        return super().default(o)
