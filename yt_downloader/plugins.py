"""Minimal plugin system abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, List, Any, Iterable

from .logging_utils import get_logger


class Plugin(Protocol):  # structural typing
    name: str

    def run(self, context: dict) -> None: ...  # noqa: D401


@dataclass
class PluginResult:
    name: str
    status: str
    error: str | None = None


class PluginManager:
    def __init__(self, plugins: Iterable[Plugin] | None = None):
        self._plugins: List[Plugin] = list(plugins or [])

    def register(self, plugin: Plugin) -> None:
        self._plugins.append(plugin)

    def run_all(self, context: dict) -> list[PluginResult]:
        log = get_logger()
        results: list[PluginResult] = []
        for plugin in self._plugins:
            try:
                log.info(
                    "Running plugin: %s",
                    getattr(plugin, "name", plugin.__class__.__name__),
                )
                plugin.run(context)
                results.append(PluginResult(name=plugin.name, status="success"))
            except Exception as e:  # pragma: no cover - defensive
                log.error("Plugin failed: %s", e)
                results.append(
                    PluginResult(
                        name=getattr(plugin, "name", "unknown"),
                        status="failed",
                        error=str(e),
                    )
                )
        return results
