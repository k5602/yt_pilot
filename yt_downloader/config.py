"""Configuration management for the YouTube downloader.

(High-level; no persistence backend decisions embedded.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

DEFAULT_QUALITY_ORDER = ["1080p", "720p", "480p", "360p", "240p", "144p"]


@dataclass
class AppConfig:
    quality_order: List[str] = field(
        default_factory=lambda: DEFAULT_QUALITY_ORDER.copy()
    )
    max_concurrency: int = 4
    timeout_seconds: int = 10
    output_dir: Path = Path("downloads")
    audio_only: bool = False
    retry_attempts: int = 2
    interactive: bool = False
    enable_plugins: bool = True
    naming_template: str = "{index:03d}-{title}"

    def preferred(self) -> str:
        return self.quality_order[0]
