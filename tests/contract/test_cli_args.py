import pytest

# Contract: Ensure CLI parses flags & sets expected configuration or exits with validation codes


@pytest.mark.contract
@pytest.mark.parametrize(
    "args,expect_code,contains",
    [
        (["--quality", "1080p", "--dry-run", "https://playlist.example/id"], 0, None),
        (["--audio", "--dry-run", "https://playlist.example/id"], 0, None),
        (["--jobs", "6", "--dry-run", "https://playlist.example/id"], 0, None),
        (
            ["--index-range", "5:10", "--dry-run", "https://playlist.example/id"],
            0,
            None,
        ),
        (["--index-range", "bad", "--dry-run", "https://playlist.example/id"], 2, None),
    ],
)
def test_cli_basic_args(run_cli, args, expect_code, contains):
    code, out, err = run_cli(args)
    assert code == expect_code
    if contains:
        assert contains in out or contains in err


@pytest.mark.contract
def test_cli_repeated_filter(run_cli):
    code, out, err = run_cli(
        [
            "--filter",
            "foo",
            "--filter",
            "BAR",
            "--dry-run",
            "https://playlist.example/id",
        ]
    )
    assert code in (0,)


@pytest.mark.contract
def test_cli_report_format_json(run_cli):
    code, out, err = run_cli(
        ["--dry-run", "--report-format", "json", "https://playlist.example/id"]
    )
    assert code == 0


@pytest.mark.contract
def test_cli_force_flag(run_cli):
    code, out, err = run_cli(["--force", "--dry-run", "https://playlist.example/id"])
    assert code == 0


@pytest.mark.contract
def test_cli_naming_template(run_cli):
    code, out, err = run_cli(
        [
            "--naming-template",
            "{index:03d}-{title}-{quality}",
            "--dry-run",
            "https://playlist.example/id",
        ]
    )
    assert code == 0
