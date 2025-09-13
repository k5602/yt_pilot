# tui.py

import json
import os
import subprocess
import threading
from logging import Handler, LogRecord
from pathlib import Path
from typing import cast

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    ProgressBar,
    RichLog,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)

from .config import AppConfig
from .downloader import PlaylistDownloader
from .logging_utils import get_logger


class TuiLogHandler(Handler):
    """A logging handler that sends records to a Textual Log widget.

    Modified to preserve Rich markup by bypassing the standard logging
    Formatter (which would escape or prepend timestamps) and emitting
    the raw message content with optional level-based prefixes that
    themselves use markup.
    """

    def __init__(self, log_widget: RichLog, app: App):
        super().__init__()
        self._log_widget = log_widget
        self._app = app
        self._lock = threading.Lock()

    def emit(self, record: LogRecord):
        """Emit a log record with preserved Rich markup."""
        import logging
        with self._lock:
            try:
                raw = record.getMessage()  # original user / app message (may contain Rich markup)
                # Level-based minimal prefix (also markup-capable)
                if record.levelno >= logging.ERROR:
                    prefix = "[bold red]ERROR[/bold red] "
                elif record.levelno >= logging.WARNING:
                    prefix = "[yellow]WARN[/yellow] "
                elif record.levelno >= logging.INFO:
                    prefix = ""
                else:
                    prefix = "[dim]"
                    raw = raw + "[/dim]"
                line = f"{prefix}{raw}"
                # Maintain internal plain-text buffer WITHOUT markup tags for clipboard plain copy
                self._app._log_buffer.append(record.getMessage())  # type: ignore[attr-defined]
                self._app.call_from_thread(self._log_widget.write, line + "\n")
            except Exception:
                self.handleError(record)


class TUIController:
    """Controller to handle the logic of the TUI, decoupling it from the App."""

    def __init__(self, app: "DownloaderApp"):
        self._app = app
        self._log = get_logger()

    def build_config_from_form(self) -> tuple[AppConfig, dict]:
        """Builds AppConfig and download options from the TUI form.

        Also persists user-facing preferences (caption languages, caption toggles,
        and layout ratio) into a config JSON under ~/.config/yt_pilot/config.json
        so they survive across sessions.
        """
        config = AppConfig()

        # Basic config
        output_dir = self._app.query_one("#output_dir", Input).value
        if output_dir:
            config.output_dir = Path(output_dir)

        quality = self._app.query_one("#quality", Input).value
        if quality:
            config.quality_order = [quality] + [
                q for q in config.quality_order if q != quality
            ]

        jobs = self._app.query_one("#jobs", Input).value
        if jobs:
            try:
                config.max_concurrency = int(jobs)
            except ValueError:
                pass

        naming_template = self._app.query_one("#naming_template", Input).value
        if naming_template:
            config.naming_template = naming_template

        # Switches
        config.audio_only = self._app.query_one("#audio_only", Switch).value
        resume = self._app.query_one("#resume", Switch).value
        captions = self._app.query_one("#captions", Switch).value
        captions_auto = self._app.query_one("#captions_auto", Switch).value
        force = self._app.query_one("#force", Switch).value

        # Caption languages
        caption_langs = self._app.query_one("#caption_langs", Input).value
        if caption_langs:
            langs = caption_langs.split(",")
        else:
            langs = ["en"]

        # Other options
        filters = self._app.query_one("#filters", Input).value
        if filters:
            filters = [filters]  # CLI expects list
        else:
            filters = None

        index_range = self._app.query_one("#index_range", Input).value or None

        options = {
            "resume": resume,
            "captions": captions,
            "captions_auto": captions_auto,
            "caption_langs": langs,
            "force": force,
            "filters": filters,
            "index_range": index_range,
        }

        # Persist extended preferences
        try:
            config.caption_langs = langs
            config.captions_enabled = captions
            config.captions_auto_enabled = captions_auto
            # Pull current layout ratio from app state if present
            if hasattr(self._app, "_layout_ratio"):
                config.layout_ratio = getattr(self._app, "_layout_ratio")
            cfg_path = Path.home() / ".config" / "yt_pilot" / "config.json"
            config.save(cfg_path)
            self._log.debug(f"Persisted config to {cfg_path}")
        except Exception as e:
            self._log.debug(f"Could not persist config: {e}")

        return config, options

    def run_download(self, urls: list[str], dry_run: bool) -> None:
        """Runs the downloader in a background thread."""
        def worker():
            self._log.info(f"Worker starting. Dry run: {dry_run}. Targets: {len(urls)}")
            self._app.call_from_thread(self._app.set_form_disabled, True)
            cast(ProgressBar, self._app.query_one("#progress_bar")).update(
                total=100, progress=0
            )

            try:
                config, options = self.build_config_from_form()
                self._log.info(f"Built config: {config.__dict__}")
                self._log.info(f"Built options: {options}")

                if dry_run:
                    # For dry run, create a simple plan JSON
                    plan = {
                        "schemaVersion": "1.0.0",
                        "generated": "2024-01-01T00:00:00Z",  # placeholder
                        "mode": "dry-run",
                        "playlistUrl": urls[0] if urls else None,
                        "videos": [],  # Would need to extract info
                        "qualityOrder": config.quality_order,
                        "filters": options.get("filters"),
                        "indexRange": options.get("index_range"),
                        "resume": options.get("resume"),
                        "captions": {
                            "manual": options.get("captions", False),
                            "auto": options.get("captions_auto", False),
                            "langs": options.get("caption_langs", ["en"]),
                            "override": False,
                        },
                        "namingTemplate": config.naming_template,
                    }
                    json_output = json.dumps(plan, indent=2)
                    self._app.call_from_thread(self._app.show_dry_run_results, json_output)
                else:
                    def progress_callback(progress):
                        self._app.call_from_thread(cast(ProgressBar, self._app.query_one("#progress_bar")).update, progress=progress)
                    downloader = PlaylistDownloader(config, progress_callback=progress_callback)
                    self._log.info("Created PlaylistDownloader")
                    all_results = []
                    self._log.info(f"Processing {len(urls)} URLs")

                    for url in urls:
                        self._log.info(f"Starting download for URL: {url}")
                        if "list=" in url:
                            results = downloader.download_playlist(
                                url,
                                audio_only=config.audio_only,
                                resume=options.get("resume", False),
                                filters=options.get("filters"),
                                index_range=options.get("index_range"),
                                captions=options.get("captions", False),
                                captions_auto=options.get("captions_auto", False),
                                caption_langs=options.get("caption_langs", ["en"]),
                                force=options.get("force", False),
                            )
                        else:
                            result = downloader.download_video(
                                url, audio_only=config.audio_only,
                                captions=options.get("captions", False),
                                captions_auto=options.get("captions_auto", False),
                                caption_langs=options.get("caption_langs", ["en"])
                            )
                            results = [result] if result else []

                        self._log.info(f"Results for {url}: {len(results)} items")
                        all_results.extend(results)

                    # Report results
                    self._log.info(f"Total all_results: {len(all_results)}")
                    total_videos = len(all_results)
                    successes = sum(1 for r in all_results if r and r.status == "success")
                    self._log.info(f"Completed: {successes}/{total_videos} videos")

                self._log.info("[bold green]All tasks completed![/bold green]")
            except Exception as e:
                self._log.error(f"[bold red]An unexpected error occurred: {e}[/bold red]")
            finally:
                self._app.call_from_thread(self._app.set_form_disabled, False)
                cast(ProgressBar, self._app.query_one("#progress_bar")).update(progress=100)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()


class DownloaderApp(App):
    """A Textual UI for the YouTube Downloader."""

    CSS_PATH = "tui.css"
    TITLE = "YouTube Playlist Downloader"
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("enter", "start_download", "Start Download"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._controller = TUIController(self)
        self._log_buffer: list[str] = []
        # Layout state
        self._advanced_visible: bool = True
        self._layout_ratio: int = 60  # percent for upper section

    def compose(self) -> ComposeResult:
        """Create and arrange the widgets for the app.

        Layout restructuring:
        - Wrap tabs + form content in an upper container
        - Reserve dedicated lower container for progress + logs so they always remain visible
        """
        yield Header()
        with Container(id="main_layout"):
            # Upper section (scrollable forms / tabs)
            with ScrollableContainer(id="upper_section"):
                with TabbedContent(initial="main_tab", id="main_tabs"):
                    with TabPane("Main", id="main_tab"):
                        # URL Input + Clear
                        yield Static("URL(s) (comma-separated):", classes="label")
                        with Horizontal(classes="input_container"):
                            yield Input(placeholder="https://youtube.com/playlist?list=...", id="urls")
                            yield Button("Clear", id="clear_url")

                        # Output directory
                        yield Static("Output Directory:", classes="label")
                        yield Input(value="", placeholder="Leave empty for default", id="output_dir")

                        # Quality preference
                        yield Static("Preferred Quality:", classes="label")
                        yield Input(value="720p", id="quality")

                        # Switches row (audio/resume)
                        with Horizontal(id="switches_row"):
                            with Container(classes="switch_container"):
                                yield Switch(id="audio_only")
                                yield Static("Audio Only", classes="switch_label")
                            with Container(classes="switch_container"):
                                yield Switch(id="resume")
                                yield Static("Resume from Manifest", classes="switch_label")

                        # Layout controls
                        with Horizontal(id="layout_controls"):
                            yield Button("Toggle Advanced", id="toggle_advanced")
                        # Action buttons
                        with Horizontal(id="actions_row"):
                            yield Button("Start Download", variant="primary", id="start")
                            yield Button("Dry Run", id="dry_run")

                    with TabPane("Captions", id="captions_tab"):
                        with Container(classes="switch_container"):
                            yield Switch(id="captions")
                            yield Static("Download Manual Captions", classes="switch_label")
                        with Container(classes="switch_container"):
                            yield Switch(id="captions_auto")
                            yield Static("Allow Auto (ASR) Captions", classes="switch_label")
                        yield Static(
                            "Caption Language Preference (comma-separated):",
                            classes="label",
                        )
                        yield Input(value="en", id="caption_langs")
                        yield Static(
                            "Subtitle Override Languages (optional):", classes="label"
                        )
                        yield Input(placeholder="e.g., en,es,fr", id="sub_langs")

                    with TabPane("Advanced", id="advanced_tab"):
                        yield Static("Layout Ratio (Form %):", classes="label")
                        with Horizontal():
                            yield Input(value="60", id="layout_ratio", placeholder="60", classes="small_input")
                            yield Button("Apply Layout", id="apply_layout")
                        yield Static("Max Parallel Downloads (Jobs):", classes="label")
                        yield Input(value="4", id="jobs", type="integer")
                        yield Static(
                            "Video Title Filter (case-insensitive):", classes="label"
                        )
                        yield Input(
                            placeholder="keyword to include in title", id="filters"
                        )
                        yield Static("Index Range (e.g., 5:10, :20, 10:):", classes="label")
                        yield Input(placeholder="start:end", id="index_range")
                        yield Static("Filename Naming Template:", classes="label")
                        yield Input(value="{index:03d}-{title}", id="naming_template")
                        with Container(classes="switch_container"):
                            yield Switch(id="force")
                            yield Static("Force Re-download", classes="switch_label")

                    with TabPane("Dry Run Results", id="dry_run_tab"):
                        yield Static("", id="dry_run_output")

            # Lower section (status + logs) - occupies remaining space
            with Container(id="lower_section"):
                yield ProgressBar(id="progress_bar")
                with Container(classes="log_container"):
                    yield Button("Copy Logs", id="copy_logs")
                    yield RichLog(id="log_view", auto_scroll=True)
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is first mounted.

        Installs Rich-preserving log handler, then loads persisted user
        preferences (if any) and applies them to the form / layout.
        """
        log_widget = self.query_one(RichLog)
        root_logger = get_logger()
        # Replace existing handlers with our Rich-preserving handler
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger.addHandler(TuiLogHandler(log_widget, self))

        # Load persisted config (best-effort)
        from .config import AppConfig
        cfg_path = Path.home() / ".config" / "yt_pilot" / "config.json"
        try:
            cfg = AppConfig.from_file(cfg_path)
            # Apply caption languages
            if cfg.caption_langs:
                self.query_one("#caption_langs", Input).value = ",".join(cfg.caption_langs)
            # Apply caption toggles
            try:
                self.query_one("#captions", Switch).value = cfg.captions_enabled
                self.query_one("#captions_auto", Switch).value = cfg.captions_auto_enabled
            except Exception:
                pass
            # Apply layout ratio (validate 10-90)
            if 10 <= cfg.layout_ratio <= 90:
                self._layout_ratio = cfg.layout_ratio
                # If the ratio input exists (Advanced tab), update its default
                try:
                    self.query_one("#layout_ratio", Input).value = str(cfg.layout_ratio)
                except Exception:
                    pass
        except Exception:
            # Ignore load errors silently to avoid user disruption
            pass

        # Apply initial layout ratio so upper/lower sections are sized immediately
        self.apply_layout_ratio()
        root_logger.info("TUI Initialized. Logging is redirected here.")

    def set_form_disabled(self, is_disabled: bool) -> None:
        """Enable or disable all input controls."""
        for control in self.query("Input, Switch, Button"):
            control.disabled = is_disabled

    def show_dry_run_results(self, json_output: str) -> None:
        """Displays the dry run JSON output in the appropriate tab."""
        try:
            # Pretty-print the JSON
            parsed_json = json.loads(json_output)
            pretty_json = json.dumps(parsed_json, indent=2)
            self.query_one("#dry_run_output", Static).update(pretty_json)
            self.query_one(TabbedContent).active = "dry_run_tab"
        except json.JSONDecodeError:
            self.query_one("#dry_run_output", Static).update(
                "[bold red]Failed to parse dry-run JSON output.[/bold red]"
            )

    def action_start_download(self) -> None:
        """Start the download when Enter is pressed."""
        urls_input = self.query_one("#urls", Input)
        urls = [url.strip() for url in urls_input.value.split(",") if url.strip()]

        if not urls:
            self.query_one("#log_view", RichLog).write(
                "[bold red]Error: Please provide at least one URL.[/bold red]\n"
            )
            return

        self._log_buffer.clear()
        self.query_one("#log_view", RichLog).clear()
        self._controller.run_download(urls, dry_run=False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        bid = event.button.id
        if bid == "clear_url":
            self.query_one("#urls", Input).value = ""
        elif bid == "copy_logs":
            log_text = "\n".join(self._log_buffer)
            try:
                # Local imports to avoid adding global dependencies
                import shutil, tempfile, importlib
                from pathlib import Path
                copied = False

                # Platform specific primary methods
                if os.name == "nt" and shutil.which("clip"):
                    subprocess.run(["clip"], input=log_text, text=True, check=True)
                    copied = True
                else:
                    sysname = ""
                    try:
                        sysname = os.uname().sysname  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    if sysname == "Darwin" and shutil.which("pbcopy"):
                        subprocess.run(["pbcopy"], input=log_text, text=True, check=True)
                        copied = True

                # Wayland/X11 tools (Linux or others)
                if not copied:
                    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
                        if shutil.which(cmd[0]):
                            subprocess.run(cmd, input=log_text, text=True, check=True)
                            copied = True
                            break

                # Pyperclip fallback if installed
                if not copied:
                    try:
                        pyperclip = importlib.import_module("pyperclip")  # type: ignore
                        pyperclip.copy(log_text)  # type: ignore[attr-defined]
                        copied = True
                    except Exception:
                        pass

                # Temp file fallback
                if not copied:
                    tmp_path = Path(tempfile.gettempdir()) / "yt_pilot_logs.txt"
                    tmp_path.write_text(log_text, encoding="utf-8")
                    self.query_one("#log_view", RichLog).write(f"[yellow]No clipboard utility found. Saved logs to {tmp_path}[/yellow]\n")
                else:
                    self.query_one("#log_view", RichLog).write("Logs copied to clipboard\n")
            except Exception as e:
                self.query_one("#log_view", RichLog).write(f"[red]Failed to copy logs: {e}[/red]\n")
        elif bid == "toggle_advanced":
            # Toggle visibility of Advanced tab
            self._advanced_visible = not self._advanced_visible
            adv = self.query_one("#advanced_tab", TabPane)
            adv.display = self._advanced_visible
            state = "shown" if self._advanced_visible else "hidden"
            self.query_one("#log_view", RichLog).write(f"[yellow]Advanced tab {state}[/yellow]\n")
        elif bid == "apply_layout":
            ratio_input = self.query_one("#layout_ratio", Input).value.strip()
            try:
                val = int(ratio_input)
                if not 10 <= val <= 90:
                    raise ValueError
                self._layout_ratio = val
                self.apply_layout_ratio()
                self.query_one("#log_view", RichLog).write(f"[green]Layout ratio set to {val}%[/green]\n")
            except ValueError:
                self.query_one("#log_view", RichLog).write("[red]Invalid ratio (10-90)[/red]\n")
        elif bid in ("start", "dry_run"):
            is_dry_run = bid == "dry_run"
            urls_input = self.query_one("#urls", Input)
            urls = [url.strip() for url in urls_input.value.split(",") if url.strip()]
            if not urls:
                self.query_one("#log_view", RichLog).write(
                    "[bold red]Error: Please provide at least one URL.[/bold red]\n"
                )
                return
            self._log_buffer.clear()
            self.query_one("#log_view", RichLog).clear()
            self._controller.run_download(urls, is_dry_run)

    def apply_layout_ratio(self) -> None:
        """Apply dynamic height ratio between upper and lower sections."""
        upper = self.query_one("#upper_section")
        lower = self.query_one("#lower_section")
        # Percent heights; Textual accepts percentage strings
        upper.styles.height = f"{self._layout_ratio}%"
        lower.styles.height = f"{100 - self._layout_ratio}%"
        self.refresh(layout=True)





if __name__ == "__main__":
    app = DownloaderApp()
    app.run()
