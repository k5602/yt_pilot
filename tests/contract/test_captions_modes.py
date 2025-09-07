import pytest


@pytest.mark.contract
@pytest.mark.parametrize(
    "flags,manual_available,auto_available,expect_kind",
    [
        ([], True, True, None),  # no caption flags -> None
        (["--captions"], True, True, "manual"),
        (
            ["--captions"],
            False,
            True,
            None,
        ),  # manual requested but absent, no auto flag
        (["--captions", "--captions-auto"], False, True, "auto"),
        (["--captions-auto"], False, True, "auto"),
        (["--captions-auto"], False, False, None),
    ],
)
def test_caption_mode_matrix(
    run_cli, flags, manual_available, auto_available, expect_kind, monkeypatch
):
    # We will monkeypatch future captions service hooks; for now ensure CLI does not error with flags.
    args = flags + ["--dry-run", "https://playlist.example/id"]
    code, out, err = run_cli(args)
    assert code == 0
    # Placeholder: when captions implemented, introspect plan/report for caption kind.
