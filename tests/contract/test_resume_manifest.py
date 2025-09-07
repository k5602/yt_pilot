import json
from pathlib import Path
import pytest


@pytest.mark.contract
def test_resume_manifest_skip_logic(run_cli, tmp_path):
    # Simulate manifest presence (implementation will later read it)
    manifest_dir = tmp_path / "downloads"
    manifest_dir.mkdir()
    manifest = {
        "playlist_url": "https://playlist.example/id",
        "videos": {
            "vid1": {
                "status": "success",
                "quality": "720p",
                "fallback": False,
                "retries": 0,
                "filename": "001-vid1.mp4",
            },
            "vid2": {
                "status": "failed",
                "quality": "720p",
                "fallback": False,
                "retries": 1,
                "filename": "002-vid2.mp4",
            },
        },
    }
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest))
    code, out, err = run_cli(
        [
            "--resume",
            "--dry-run",
            "--output",
            str(manifest_dir),
            "https://playlist.example/id",
        ]
    )
    assert code == 0
    # Expectation (placeholder until feature): does not error. Later: assert vid1 omitted from plan.
