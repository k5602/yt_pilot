import pytest


@pytest.mark.integration
def test_dry_run_human_output(run_cli):
    code, out, err = run_cli(["--dry-run", "https://playlist.example/id"])
    assert code == 0
    # Expect some human-friendly markers; placeholder assertion until formatted table implemented.
    assert "Processing playlist" in out
