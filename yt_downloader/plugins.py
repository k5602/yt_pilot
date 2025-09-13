"""Plugin system for extensibility."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

from .config import AppConfig
from .logging_utils import get_logger
from .models import PlaylistSession, VideoItem


class Plugin(Protocol):
    """Plugin interface defining hooks for various download stages."""

    name: str

    def on_playlist_start(self, context: dict[str, Any]) -> None:
        """Called when a playlist download is about to start."""
        ...

    def on_video_downloaded(self, context: dict[str, Any]) -> None:
        """Called after a video has been successfully downloaded."""
        ...

    def on_playlist_complete(self, context: dict[str, Any]) -> None:
        """Called when a playlist download has completed."""
        ...


@dataclass
class PluginResult:
    name: str
    status: str
    error: str | None = None


class PluginManager:
    def __init__(self, config: AppConfig):
        self._config = config
        self._plugins: list[Plugin] = []
        self._log = get_logger()

    def load_plugins(self) -> None:
        """Loads plugins from the user's plugin directory."""
        if not self._config.enable_plugins:
            return

        plugin_dir = Path.home() / ".config" / "yt-pilot" / "plugins"
        if not plugin_dir.exists():
            return

        for file_path in plugin_dir.glob("*.py"):
            try:
                spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[file_path.stem] = module
                    spec.loader.exec_module(module)
                    for obj_name in dir(module):
                        obj = getattr(module, obj_name)
                        if (
                            isinstance(obj, type)
                            and issubclass(obj, Plugin)
                            and obj is not Plugin
                        ):
                            self.register(obj())
            except Exception as e:
                self._log.error(f"Failed to load plugin from {file_path}: {e}")

    def register(self, plugin: Plugin) -> None:
        """Registers a plugin."""
        self._plugins.append(plugin)
        self._log.info(f"Registered plugin: {plugin.name}")

    def _run_hook(self, hook_name: str, context: dict[str, Any]) -> list[PluginResult]:
        """Runs a specific hook on all registered plugins."""
        results: list[PluginResult] = []
        for plugin in self._plugins:
            try:
                hook = getattr(plugin, hook_name, None)
                if hook:
                    self._log.debug(
                        f"Running hook '{hook_name}' on plugin: {plugin.name}"
                    )
                    hook(context)
                    results.append(PluginResult(name=plugin.name, status="success"))
            except Exception as e:
                self._log.error(f"Plugin {plugin.name} failed on hook {hook_name}: {e}")
                results.append(
                    PluginResult(name=plugin.name, status="failed", error=str(e))
                )
        return results

    def on_playlist_start(self, playlist: PlaylistSession) -> None:
        self._run_hook(
            "on_playlist_start", {"playlist": playlist, "config": self._config}
        )

    def on_video_downloaded(self, video: VideoItem) -> None:
        self._run_hook("on_video_downloaded", {"video": video, "config": self._config})

    def on_playlist_complete(self, playlist: PlaylistSession) -> None:
        self._run_hook(
            "on_playlist_complete", {"playlist": playlist, "config": self._config}
        )
