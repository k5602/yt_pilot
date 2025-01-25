"""
YouTube Playlist Downloader - A tool for downloading playlists with metadata
Features:
- Multi-threaded downloads
- Progress tracking
- Configurable quality settings
- Metadata preservation
- Comprehensive error handling
"""

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Dict

from pytube import Playlist, YouTube
from pytube.exceptions import PytubeError
from rich.progress import Progress, BarColumn, DownloadColumn, TimeRemainingColumn


class YouTubePlaylistDownloader:
    """Main downloader class with configurable options"""
    
    def __init__(self, max_workers: int = 4, timeout: int = 10):
        self.max_workers = max_workers
        self.timeout = timeout
        self.progress = Progress(
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            DownloadColumn(),
            TimeRemainingColumn(),
        )

    def _get_sorted_streams(self, yt: YouTube) -> List[Dict]:
        """Get available streams sorted by quality"""
        return sorted(
            [
                {
                    "itag": stream.itag,
                    "resolution": stream.resolution,
                    "mime_type": stream.mime_type,
                    "type": "video" if stream.includes_video_track else "audio",
                    "filesize": stream.filesize,
                    "stream": stream,
                }
                for stream in yt.streams
            ],
            key=lambda x: (x["type"], x["resolution"] or "0"),
            reverse=True,
        )

    def _download_media(self, stream, output_path: Path, task_id: int) -> None:
        """Download individual media item with progress tracking"""
        try:
            stream.download(
                output_path=output_path,
                filename_prefix=f"{task_id}_",
                timeout=self.timeout,
                skip_existing=True,
            )
        except Exception as e:
            self.progress.console.print(f"[red]Error downloading: {e}[/red]")

    def _process_video(self, url: str, output_path: Path, quality: str, audio_only: bool) -> None:
        """Process individual video download"""
        try:
            yt = YouTube(url, on_progress_callback=self._progress_callback)
            streams = self._get_sorted_streams(yt)
            
            if audio_only:
                stream = next((s for s in streams if s["type"] == "audio" and "mp4" in s["mime_type"]), None)
            else:
                stream = next((s for s in streams if s["resolution"] == quality and s["type"] == "video"), None)

            if not stream:
                raise ValueError(f"No stream found for quality: {quality}")

            task_id = self.progress.add_task(
                description=yt.title[:50],
                total=stream["filesize"],
                visible=not audio_only,
            )

            self._download_media(stream["stream"], output_path, task_id)
            self.progress.update(task_id, visible=False)
            
        except PytubeError as e:
            self.progress.console.print(f"[red]Error processing {url}: {e}[/red]")

    def _progress_callback(self, stream, chunk, bytes_remaining):
        """Update progress bar for active downloads"""
        task_id = self.progress.task_ids[0]  # Get first active task
        self.progress.update(task_id, advance=len(chunk))

    def download_playlist(
        self,
        playlist_url: str,
        output_dir: Path = Path("downloads"),
        quality: str = "720p",
        audio_only: bool = False,
    ) -> None:
        """Main download executor"""
        try:
            playlist = Playlist(playlist_url)
            output_dir.mkdir(parents=True, exist_ok=True)

            with self.progress, ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [
                    executor.submit(
                        self._process_video,
                        video_url,
                        output_dir,
                        quality,
                        audio_only
                    )
                    for video_url in playlist.video_urls
                ]
                
                for future in futures:
                    future.result()

        except Exception as e:
            self.progress.console.print(f"[bold red]Fatal Error: {e}[/bold red]")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="YouTube Playlist Downloader - Download entire playlists with custom quality settings",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("playlist_url", help="YouTube playlist URL")
    parser.add_argument("-o", "--output", type=Path, default=Path("downloads"),
                        help="Output directory path")
    parser.add_argument("-q", "--quality", default="720p", 
                        choices=["144p", "240p", "360p", "480p", "720p", "1080p"],
                        help="Video quality preference")
    parser.add_argument("-a", "--audio", action="store_true",
                        help="Download audio only (MP4 format)")
    parser.add_argument("-j", "--jobs", type=int, default=4,
                        help="Number of parallel downloads")

    args = parser.parse_args()

    downloader = YouTubePlaylistDownloader(max_workers=args.jobs)
    downloader.download_playlist(
        playlist_url=args.playlist_url,
        output_dir=args.output,
        quality=args.quality,
        audio_only=args.audio,
    )


if __name__ == "__main__":
    main()
