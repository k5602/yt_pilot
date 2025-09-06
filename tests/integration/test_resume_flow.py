import json
import pytest

@pytest.mark.integration
def test_resume_flow_placeholder(run_cli, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "manifest.json").write_text(json.dumps({"playlist_url":"https://playlist.example/id","videos":{}}))
    code, out, err = run_cli(["--resume","--dry-run","--output", str(out_dir), "https://playlist.example/id"])
    assert code == 0
