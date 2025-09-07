"""entrypoint delegating to modular package CLI."""

from yt_downloader import run_cli


def main():
    run_cli()


if __name__ == "__main__":
    main()
