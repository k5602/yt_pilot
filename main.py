"""Entrypoint launching the Textual UI."""

from yt_downloader.tui import DownloaderApp


def main():
    # Launch the Textual UI
    app = DownloaderApp()
    app.run()


if __name__ == "__main__":
    main()
