import json
import pytest


@pytest.mark.contract
def test_dry_run_json_shape(run_cli, tmp_path, monkeypatch):
    # Expect a JSON print containing keys per contract when --dry-run and --report-format json
    code, out, err = run_cli(
        ["--dry-run", "--report-format", "json", "https://playlist.example/id"]
    )
    assert code == 0
    # Extract last JSON object (simplistic assumption now). Implementation must emit proper structure later.
    try:
        data = json.loads(out.strip().splitlines()[-1])
    except Exception:
        pytest.fail("Dry-run JSON not found or invalid JSON")
    for k in ["mode", "playlistUrl", "videos", "qualityOrder"]:
        assert k in data
    assert data.get("mode") == "dry-run"
    assert isinstance(data.get("videos"), list)
