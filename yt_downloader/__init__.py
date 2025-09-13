"""YouTube Downloader package root.

Public surface kept intentionally small; internal modules may evolve.
"""

from .config import AppConfig
from .downloader import PlaylistDownloader
from .plugins import Plugin, PluginManager

__all__ = [
    "AppConfig",
    "PlaylistDownloader",
    "Plugin",
    "PluginManager",
]


def main():
    """Launch the Textual UI."""
    from .tui import DownloaderApp

    app = DownloaderApp()
    app.run()
