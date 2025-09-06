import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
import pytest

# Ensure project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

@pytest.fixture()
def temp_output_dir(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d

@pytest.fixture()
def sample_manifest_entry():
    return {
        "status": "success",
        "quality": "720p",
        "fallback": False,
        "retries": 0,
        "filename": "000-sample.mp4"
    }

@pytest.fixture()
def run_cli(monkeypatch):
    """Helper to invoke CLI main() with args list; returns (exit_code, stdout, stderr)."""
    from io import StringIO
    import contextlib
    from main import main as cli_main

    def _run(args):
        argv = ["python", *args]
        monkeypatch.setattr(sys, 'argv', argv)
        stdout_buf = StringIO()
        stderr_buf = StringIO()
        code = 0
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            try:
                cli_main()
            except SystemExit as e:
                code = int(e.code) if e.code is not None else 0
        return code, stdout_buf.getvalue(), stderr_buf.getvalue()

    return _run
