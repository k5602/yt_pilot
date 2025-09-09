from pathlib import Path
import tempfile
from unittest.mock import patch, MagicMock
from yt_downloader.captions import CaptionsService
from yt_downloader.models import VideoItem, CaptionTrack


class DummyCap(CaptionsService):
    def __init__(self, manual=True, auto=True):
        super().__init__(Path("."))
        self._manual = manual
        self._auto = auto

    def fetch_manual(self, video: VideoItem):
        if self._manual:
            return CaptionTrack(
                video_id=video.video_id,
                language="en",
                kind="manual",
                format="srt",
                path="m.srt",
            )
        return None

    def fetch_auto(self, video: VideoItem):
        if self._auto:
            return CaptionTrack(
                video_id=video.video_id,
                language="en",
                kind="auto",
                format="srt",
                path="a.srt",
            )
        return None


def make_video():
    return VideoItem(index=1, video_id="vid", title="T", preferred_quality="720p")


def test_obtain_manual_preferred():
    svc = DummyCap(manual=True, auto=True)
    v = make_video()
    tracks = svc.obtain(v, want_manual=True, want_auto=True)
    assert tracks and tracks[0].kind == "manual"


def test_obtain_auto_when_no_manual():
    svc = DummyCap(manual=False, auto=True)
    v = make_video()
    tracks = svc.obtain(v, want_manual=True, want_auto=True)
    assert tracks and tracks[0].kind == "auto"


def test_obtain_none():
    svc = DummyCap(manual=False, auto=False)
    v = make_video()
    tracks = svc.obtain(v, want_manual=True, want_auto=True)
    assert tracks == []


def test_fetch_manual_real_implementation():
    """Test that the real fetch_manual implementation properly handles subtitle extraction."""
    with tempfile.TemporaryDirectory() as temp_dir:
        service = CaptionsService(Path(temp_dir), ["en"])
        video = make_video()
        
        # Mock yt-dlp and urllib to simulate successful subtitle extraction
        mock_subtitle_data = "1\n00:00:01,000 --> 00:00:03,000\nHello world\n\n"
        
        with patch('yt_dlp.YoutubeDL') as mock_ydl_class:
            mock_ydl = MagicMock()
            mock_ydl_class.return_value.__enter__.return_value = mock_ydl
            
            # Mock extract_info to return subtitle information
            mock_ydl.extract_info.return_value = {
                "subtitles": {
                    "en": [
                        {
                            "url": "http://example.com/subtitle.srt",
                            "ext": "srt"
                        }
                    ]
                }
            }
            
            # Mock urllib.request.urlopen
            with patch('urllib.request.urlopen') as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = mock_subtitle_data.encode('utf-8')
                mock_urlopen.return_value.__enter__.return_value = mock_response
                
                # Test the method
                track = service.fetch_manual(video)
                
                # Verify the result
                assert track is not None
                assert track.video_id == "vid"
                assert track.language == "en"
                assert track.kind == "manual"
                assert track.format == "srt"
                
                # Verify the caption file was created
                caption_path = Path(track.path)
                assert caption_path.exists()
                content = caption_path.read_text()
                assert "Hello world" in content


def test_fetch_manual_vtt_conversion():
    """Test that VTT subtitles are properly converted to SRT format."""
    with tempfile.TemporaryDirectory() as temp_dir:
        service = CaptionsService(Path(temp_dir), ["en"])
        video = make_video()
        
        # Mock VTT content that needs conversion
        mock_vtt_data = """WEBVTT

00:00:01.000 --> 00:00:03.000
Hello world

00:00:04.000 --> 00:00:06.000
Second subtitle
"""
        
        with patch('yt_dlp.YoutubeDL') as mock_ydl_class:
            mock_ydl = MagicMock()
            mock_ydl_class.return_value.__enter__.return_value = mock_ydl
            
            # Mock extract_info to return VTT subtitle information
            mock_ydl.extract_info.return_value = {
                "subtitles": {
                    "en": [
                        {
                            "url": "http://example.com/subtitle.vtt",
                            "ext": "vtt"
                        }
                    ]
                }
            }
            
            # Mock urllib.request.urlopen
            with patch('urllib.request.urlopen') as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = mock_vtt_data.encode('utf-8')
                mock_urlopen.return_value.__enter__.return_value = mock_response
                
                # Test the method
                track = service.fetch_manual(video)
                
                # Verify the result
                assert track is not None
                assert track.format == "srt"
                
                # Verify the caption file was created and VTT was converted to SRT
                caption_path = Path(track.path)
                assert caption_path.exists()
                content = caption_path.read_text()
                # Should have SRT timestamps (with commas, not dots)
                assert "00:00:01,000 --> 00:00:03,000" in content
                assert "Hello world" in content
                assert "Second subtitle" in content
