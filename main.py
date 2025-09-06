"""Backward-compatible entrypoint delegating to modular package CLI."""

from yt_downloader import run_cli


def main():  # pragma: no cover
    run_cli()


if __name__ == "__main__":  # pragma: no cover
    main()
