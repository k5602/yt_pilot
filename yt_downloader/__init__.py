"""YouTube Downloader package root.

Public surface kept intentionally small; internal modules may evolve.
"""

from .config import AppConfig
from .downloader import PlaylistDownloader
from .cli import run_cli
from .plugins import Plugin, PluginManager

__all__ = [
    "AppConfig",
    "PlaylistDownloader",
    "run_cli",
    "Plugin",
    "PluginManager",
]
