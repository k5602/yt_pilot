import pytest


@pytest.mark.integration
def test_captions_flow_placeholder(run_cli):
    code, out, err = run_cli(
        ["--captions", "--captions-auto", "--dry-run", "https://playlist.example/id"]
    )
    assert code == 0
