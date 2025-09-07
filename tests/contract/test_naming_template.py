import pytest


@pytest.mark.contract
@pytest.mark.parametrize(
    "template,expect_warn",
    [
        ("{index:03d}-{title}", False),
        ("{index}-{title}-{quality}-{video_id}-{date}-{audio_only}", False),
        ("{index}-{unknown}-{title}", True),
    ],
)
def test_naming_template_parsing(template, expect_warn, run_cli, monkeypatch):
    # Not implemented yet; ensure CLI accepts naming template flag without crash
    code, out, err = run_cli(
        ["--naming-template", template, "--dry-run", "https://playlist.example/id"]
    )
    assert code == 0
    # When implemented, capture logging warnings for unknown tokens if expect_warn.
