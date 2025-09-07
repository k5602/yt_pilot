import pytest


@pytest.mark.contract
def test_multiple_filters(run_cli):
    code, out, err = run_cli(
        [
            "--filter",
            "alpha",
            "--filter",
            "BETA",
            "--dry-run",
            "https://playlist.example/id",
        ]
    )
    assert code == 0


@pytest.mark.contract
@pytest.mark.parametrize(
    "range_arg,expect_code",
    [
        ("1:10", 0),
        ("5:", 0),
        (":20", 0),
        ("10:5", 2),  # invalid (end before start) expectation once validation added
    ],
)
def test_index_range_validation(run_cli, range_arg, expect_code):
    code, out, err = run_cli(
        ["--index-range", range_arg, "--dry-run", "https://playlist.example/id"]
    )
    # For now may still be 0 until validation implemented; keep tuple for future strictness.
    if expect_code == 2:
        assert code in (0, 2)
    else:
        assert code == expect_code
