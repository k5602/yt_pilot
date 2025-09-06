import json
import pytest


@pytest.mark.integration
def test_download_with_report_placeholder(run_cli, tmp_path):
    # Until real downloading & report creation, ensure CLI runs with --report-format json.
    code, out, err = run_cli(
        ["--dry-run", "--report-format", "json", "https://playlist.example/id"]
    )
    assert code == 0
    # Validate last line JSON minimally (same as contract test but integration context)
    try:
        data = json.loads(out.strip().splitlines()[-1])
    except Exception:
        pytest.fail(
            "Expected JSON output at end of dry-run when report-format json is set"
        )
    assert data.get("mode") == "dry-run"
